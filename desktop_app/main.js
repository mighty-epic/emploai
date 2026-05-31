const { app, BrowserWindow, ipcMain, shell, clipboard, net, protocol, dialog } = require('electron');
const { execFile, spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'emploai',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      corsEnabled: true,
    },
  },
]);

const repoRoot = path.resolve(__dirname, '..');
const desktopRoot = __dirname;
const packagedRendererIndex = path.join(desktopRoot, 'renderer', 'index.html');
const devRendererIndex = path.join(repoRoot, 'mobile_app', 'client', 'dist', 'index.html');
const packagedBackendExe = path.join(desktopRoot, 'backend', 'EmploAIBackend.exe');
const configuredPythonCommand = String(process.env.EMPLOAI_DESKTOP_PYTHON || '').trim();

let mainWindow = null;
let bootstrapCache = null;
let runtimeStatusCache = null;
let shutdownForQuitPromise = null;
let quitAfterManagedShutdown = false;
let resolvedDevBackendCommand = null;

function emitRuntimeEvent(payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('emploai:runtime-event', payload);
  }
}

function commandAvailable(command, probeArgs = []) {
  try {
    const result = spawnSync(command, probeArgs, {
      windowsHide: true,
      stdio: 'ignore',
    });
    return !result.error;
  } catch (_error) {
    return false;
  }
}

function resolveDevBackendCommand() {
  if (resolvedDevBackendCommand) {
    return resolvedDevBackendCommand;
  }

  const candidates = [];
  if (configuredPythonCommand) {
    candidates.push({
      command: configuredPythonCommand,
      prefixArgs: ['-m', 'deploy.windows.release_backend'],
      probeArgs: ['--version'],
    });
  }
  candidates.push(
    {
      command: 'python',
      prefixArgs: ['-m', 'deploy.windows.release_backend'],
      probeArgs: ['--version'],
    },
    {
      command: 'py',
      prefixArgs: ['-3', '-m', 'deploy.windows.release_backend'],
      probeArgs: ['-3', '--version'],
    },
    {
      command: 'py',
      prefixArgs: ['-m', 'deploy.windows.release_backend'],
      probeArgs: ['--version'],
    },
  );

  const resolved = candidates.find((candidate) => commandAvailable(candidate.command, candidate.probeArgs));
  resolvedDevBackendCommand = resolved || {
    command: configuredPythonCommand || 'python',
    prefixArgs: ['-m', 'deploy.windows.release_backend'],
  };
  return resolvedDevBackendCommand;
}

function resolveBackendCommand() {
  if (app.isPackaged && fs.existsSync(packagedBackendExe)) {
    return {
      command: packagedBackendExe,
      prefixArgs: [],
      cwd: path.dirname(packagedBackendExe),
    };
  }

  const devBackend = resolveDevBackendCommand();
  return {
    command: devBackend.command,
    prefixArgs: devBackend.prefixArgs,
    cwd: repoRoot,
  };
}

function resolveRendererIndex() {
  if (app.isPackaged && fs.existsSync(packagedRendererIndex)) {
    return packagedRendererIndex;
  }
  return devRendererIndex;
}

function resolveRendererRoot() {
  return path.dirname(resolveRendererIndex());
}

function resolveRendererAssetPath(rendererRoot, requestUrl) {
  const requestPath = decodeURIComponent(requestUrl.pathname || '/');
  const trimmedPath = requestPath.replace(/^\/+/, '');
  const fallbackPath = path.join(rendererRoot, 'index.html');

  if (!trimmedPath) {
    return fallbackPath;
  }

  const candidatePath = path.normalize(path.join(rendererRoot, trimmedPath));
  const relativePath = path.relative(rendererRoot, candidatePath);
  const escapedRoot = relativePath.startsWith('..') || path.isAbsolute(relativePath);
  if (escapedRoot) {
    return fallbackPath;
  }

  try {
    const stat = fs.statSync(candidatePath);
    if (stat.isFile()) {
      return candidatePath;
    }
  } catch (_error) {
    return fallbackPath;
  }

  return fallbackPath;
}

function runBackendJson(args, options = {}) {
  const backend = resolveBackendCommand();
  const payload = options.input === undefined ? null : JSON.stringify(options.input);

  return new Promise((resolve, reject) => {
    const child = execFile(
      backend.command,
      [...backend.prefixArgs, ...args],
      {
        cwd: backend.cwd,
        maxBuffer: 8 * 1024 * 1024,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        if (error) {
          if (error.code === 'ENOENT') {
            reject(new Error(`Backend helper command not found: ${backend.command}`));
            return;
          }
          reject(new Error(stderr?.trim() || error.message));
          return;
        }
        const text = String(stdout || '').trim();
        if (!text) {
          reject(new Error(stderr?.trim() || 'No JSON payload returned from backend helper'));
          return;
        }
        try {
          resolve(JSON.parse(text));
        } catch (parseError) {
          reject(new Error(`Failed to parse backend helper JSON: ${parseError.message}\n${text}`));
        }
      }
    );

    if (payload !== null && child.stdin) {
      child.stdin.end(payload);
    }
  });
}

function runBackendJsonStream(args, options = {}) {
  const backend = resolveBackendCommand();
  const payload = options.input === undefined ? null : JSON.stringify(options.input);

  return new Promise((resolve, reject) => {
    const child = spawn(
      backend.command,
      [...backend.prefixArgs, ...args],
      {
        cwd: backend.cwd,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      }
    );

    let stdoutBuffer = '';
    let stderrBuffer = '';
    let lineBuffer = '';
    let finalPayload = null;
    let streamedError = null;

    const handleLine = (line) => {
      const text = String(line || '').trim();
      if (!text) {
        return;
      }
      let parsed = null;
      try {
        parsed = JSON.parse(text);
      } catch (_error) {
        stdoutBuffer += `${text}\n`;
        return;
      }

      if (parsed && parsed.kind === 'voice_pack_progress') {
        if (parsed.state === 'error') {
          streamedError = parsed.message || null;
        }
        if (typeof options.onEvent === 'function') {
          options.onEvent(parsed);
        }
        return;
      }

      if (parsed && parsed.kind === 'bootstrap' && parsed.payload) {
        finalPayload = parsed.payload;
        return;
      }

      if (parsed && typeof parsed === 'object' && !parsed.kind) {
        finalPayload = parsed;
        return;
      }

      stdoutBuffer += `${text}\n`;
    };

    child.stdout.on('data', (chunk) => {
      lineBuffer += String(chunk || '');
      let newlineIndex = lineBuffer.indexOf('\n');
      while (newlineIndex !== -1) {
        const line = lineBuffer.slice(0, newlineIndex);
        lineBuffer = lineBuffer.slice(newlineIndex + 1);
        handleLine(line);
        newlineIndex = lineBuffer.indexOf('\n');
      }
    });

    child.stderr.on('data', (chunk) => {
      stderrBuffer += String(chunk || '');
    });

    child.on('error', (error) => {
      reject(new Error(error?.message || 'Failed to launch backend helper'));
    });

    child.on('close', (code) => {
      if (lineBuffer.trim()) {
        handleLine(lineBuffer);
        lineBuffer = '';
      }

      if (code !== 0) {
        reject(
          new Error(
            streamedError ||
            stderrBuffer.trim() ||
            stdoutBuffer.trim() ||
            `Backend helper exited with code ${code}`
          )
        );
        return;
      }

      if (!finalPayload) {
        reject(new Error(stderrBuffer.trim() || stdoutBuffer.trim() || 'No JSON payload returned from backend helper'));
        return;
      }

      resolve(finalPayload);
    });

    if (payload !== null && child.stdin) {
      child.stdin.end(payload);
      return;
    }
    if (child.stdin) {
      child.stdin.end();
    }
  });
}

function updateBootstrapCaches(payload) {
  bootstrapCache = payload;
  runtimeStatusCache = payload?.runtimeStatus || null;
}

async function bootstrapRuntime() {
  emitRuntimeEvent({ type: 'bootstrap_start' });
  const payload = await runBackendJson(['bootstrap', '--launch-if-needed']);
  updateBootstrapCaches(payload);
  emitRuntimeEvent({
    type: 'bootstrap_ready',
    payload,
  });
  return payload;
}

async function startLocalRuntime(options = {}) {
  emitRuntimeEvent({ type: 'runtime_starting' });
  const attachTimeoutSeconds = Number.isFinite(Number(options?.attachTimeoutSeconds))
    ? Math.max(2, Math.trunc(Number(options.attachTimeoutSeconds)))
    : null;
  const restartAttachTimeoutSeconds = Number.isFinite(Number(options?.restartAttachTimeoutSeconds))
    ? Math.max(2, Math.trunc(Number(options.restartAttachTimeoutSeconds)))
    : null;
  const args = ['start'];
  if (attachTimeoutSeconds) {
    args.push('--attach-timeout-seconds', String(attachTimeoutSeconds));
  }
  if (restartAttachTimeoutSeconds) {
    args.push('--restart-attach-timeout-seconds', String(restartAttachTimeoutSeconds));
  }
  const payload = await runBackendJson(args);
  updateBootstrapCaches(payload);
  emitRuntimeEvent({
    type: 'runtime_started',
    payload,
  });
  return payload;
}

async function stopLocalRuntime() {
  emitRuntimeEvent({ type: 'runtime_stopping' });
  const payload = await runBackendJson(['stop']);
  updateBootstrapCaches(payload);
  emitRuntimeEvent({
    type: 'runtime_stopped',
    payload,
  });
  return payload;
}

async function getRuntimeStatus() {
  const status = await runBackendJson(['status']);
  runtimeStatusCache = status;
  emitRuntimeEvent({ type: 'runtime_status', payload: status });
  return status;
}

async function saveSetup(payload) {
  const next = await runBackendJson(['save-setup'], { input: payload });
  updateBootstrapCaches(next);
  emitRuntimeEvent({
    type: 'setup_saved',
    payload: next,
  });
  return next;
}

async function installVoicePack(packId) {
  const next = await runBackendJsonStream(
    ['install-voice-pack', '--pack', String(packId || ''), '--stream-progress'],
    {
      onEvent: (eventPayload) => {
        emitRuntimeEvent({
          type: 'voice_pack_progress',
          payload: eventPayload,
        });
      },
    }
  );
  updateBootstrapCaches(next);
  emitRuntimeEvent({
    type: 'voice_pack_installed',
    payload: next,
  });
  return next;
}

async function removeVoicePack(packId) {
  const next = await runBackendJson(['remove-voice-pack', '--pack', String(packId || '')]);
  updateBootstrapCaches(next);
  emitRuntimeEvent({
    type: 'voice_pack_removed',
    payload: next,
  });
  return next;
}

async function setDefaultVoiceEngine(engine) {
  const next = await runBackendJson(['set-voice-engine', '--engine', String(engine || '')]);
  updateBootstrapCaches(next);
  emitRuntimeEvent({
    type: 'voice_engine_selected',
    payload: next,
  });
  return next;
}

async function checkUpdates(force = false) {
  return runBackendJson(force ? ['check-updates', '--force'] : ['check-updates']);
}

async function installUpdate() {
  const result = await runBackendJson(['install-update']);
  if (result?.launched) {
    setTimeout(() => app.quit(), 250);
  }
  return result;
}

async function openManagedPath(targetPath) {
  const value = String(targetPath || '').trim();
  if (!value) {
    throw new Error('A path is required');
  }
  return shell.openPath(value);
}

function chromeCandidatePaths() {
  return [
    process.env['PROGRAMFILES'] ? path.join(process.env['PROGRAMFILES'], 'Google', 'Chrome', 'Application', 'chrome.exe') : null,
    process.env['PROGRAMFILES(X86)'] ? path.join(process.env['PROGRAMFILES(X86)'], 'Google', 'Chrome', 'Application', 'chrome.exe') : null,
    process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe') : null,
  ].filter(Boolean);
}

async function openChromeExtensionsPage() {
  const target = 'chrome://extensions/';
  for (const candidate of chromeCandidatePaths()) {
    if (!candidate || !fs.existsSync(candidate)) {
      continue;
    }
    execFile(candidate, [target], {
      windowsHide: true,
    });
    return '';
  }
  return shell.openExternal(target);
}

async function copyManagedText(textValue) {
  const value = String(textValue || '');
  clipboard.writeText(value);
  return { ok: true, text: value };
}

const SETUP_VALIDATION_TIMEOUT_MS = 8000;

function setupValidationResult(field, status, message) {
  return {
    field,
    status,
    message,
  };
}

async function fetchValidationPayload(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SETUP_VALIDATION_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    const contentType = String(response.headers.get('content-type') || '').toLowerCase();
    let payload = null;
    let text = '';

    if (contentType.includes('application/json')) {
      try {
        payload = await response.json();
      } catch (_error) {
        payload = null;
      }
    } else {
      try {
        text = await response.text();
      } catch (_error) {
        text = '';
      }
    }

    return { response, payload, text };
  } finally {
    clearTimeout(timeout);
  }
}

function extractValidationMessage(payload, fallback, text = '') {
  if (typeof payload === 'string' && payload.trim()) {
    return payload.trim();
  }
  if (payload && typeof payload === 'object') {
    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message.trim();
    }
    if (typeof payload.description === 'string' && payload.description.trim()) {
      return payload.description.trim();
    }
    if (typeof payload.error === 'string' && payload.error.trim()) {
      return payload.error.trim();
    }
    if (payload.error && typeof payload.error.message === 'string' && payload.error.message.trim()) {
      return payload.error.message.trim();
    }
  }
  if (text && text.trim()) {
    return text.trim();
  }
  return fallback;
}

async function validateSetupField(fieldName, rawValue) {
  const field = String(fieldName || '').trim();
  const value = String(rawValue || '').trim();

  if (!field) {
    throw new Error('A setup field is required for validation');
  }
  if (!value) {
    return setupValidationResult(field, 'idle', '');
  }

  try {
    if (field === 'OPENAI_API_KEY') {
      const { response, payload, text } = await fetchValidationPayload('https://api.openai.com/v1/models', {
        headers: {
          Authorization: `Bearer ${value}`,
        },
      });
      return response.ok
        ? setupValidationResult(field, 'valid', 'Valid OpenAI key')
        : setupValidationResult(field, 'invalid', extractValidationMessage(payload, `OpenAI rejected this key (${response.status})`, text));
    }

    if (field === 'ANTHROPIC_API_KEY') {
      const { response, payload, text } = await fetchValidationPayload('https://api.anthropic.com/v1/models', {
        headers: {
          'x-api-key': value,
          'anthropic-version': '2023-06-01',
        },
      });
      return response.ok
        ? setupValidationResult(field, 'valid', 'Valid Anthropic key')
        : setupValidationResult(field, 'invalid', extractValidationMessage(payload, `Anthropic rejected this key (${response.status})`, text));
    }

    if (field === 'GOOGLE_API_KEY') {
      const { response, payload, text } = await fetchValidationPayload(`https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(value)}`);
      return response.ok
        ? setupValidationResult(field, 'valid', 'Valid Gemini key')
        : setupValidationResult(field, 'invalid', extractValidationMessage(payload, `Google rejected this key (${response.status})`, text));
    }

    if (field === 'XAI_API_KEY') {
      const { response, payload, text } = await fetchValidationPayload('https://api.x.ai/v1/models', {
        headers: {
          Authorization: `Bearer ${value}`,
        },
      });
      return response.ok
        ? setupValidationResult(field, 'valid', 'Valid xAI key')
        : setupValidationResult(field, 'invalid', extractValidationMessage(payload, `xAI rejected this key (${response.status})`, text));
    }

    if (field === 'DEEPSEEK_API_KEY') {
      const { response, payload, text } = await fetchValidationPayload('https://api.deepseek.com/models', {
        headers: {
          Authorization: `Bearer ${value}`,
        },
      });
      return response.ok
        ? setupValidationResult(field, 'valid', 'Valid DeepSeek key')
        : setupValidationResult(field, 'invalid', extractValidationMessage(payload, `DeepSeek rejected this key (${response.status})`, text));
    }

    if (field === 'OPENROUTER_API_KEY') {
      const { response, payload, text } = await fetchValidationPayload('https://openrouter.ai/api/v1/models', {
        headers: {
          Authorization: `Bearer ${value}`,
        },
      });
      return response.ok
        ? setupValidationResult(field, 'valid', 'Valid OpenRouter key')
        : setupValidationResult(field, 'invalid', extractValidationMessage(payload, `OpenRouter rejected this key (${response.status})`, text));
    }

    if (field === 'TELEGRAM_BOT_TOKEN') {
      const { response, payload, text } = await fetchValidationPayload(`https://api.telegram.org/bot${encodeURIComponent(value)}/getMe`);
      if (response.ok && payload?.ok && payload?.result) {
        const botLabel = payload.result.username ? `@${payload.result.username}` : payload.result.first_name || 'bot';
        return setupValidationResult(field, 'valid', `Valid Telegram bot ${botLabel}`);
      }
      return setupValidationResult(field, 'invalid', extractValidationMessage(payload, 'Telegram rejected this bot token', text));
    }

    if (field === 'ALLOWED_USER_IDS') {
      const ids = value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      const valid = ids.length > 0 && ids.every((item) => /^\d+$/.test(item));
      return valid
        ? setupValidationResult(field, 'valid', `${ids.length} Telegram user id${ids.length === 1 ? '' : 's'} accepted`)
        : setupValidationResult(field, 'invalid', 'Use numeric Telegram user IDs separated by commas');
    }

    if (field === 'EMPLOAI_REMOTE_CONTROL_BASE_URL') {
      try {
        const parsed = new URL(value);
        const valid = parsed.protocol === 'https:' || parsed.protocol === 'http:';
        return valid
          ? setupValidationResult(field, 'valid', 'Remote control service URL format looks valid')
          : setupValidationResult(field, 'invalid', 'Remote control service URL must use http:// or https://');
      } catch (_error) {
        return setupValidationResult(field, 'invalid', 'Remote control service URL must be a valid URL');
      }
    }

    if (field === 'EMPLOAI_REMOTE_CONTROL_EMAIL') {
      const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
      return valid
        ? setupValidationResult(field, 'valid', 'Remote control email format looks valid')
        : setupValidationResult(field, 'invalid', 'Use a normal email address');
    }

    return setupValidationResult(field, 'idle', '');
  } catch (error) {
    const detail = error?.name === 'AbortError'
      ? 'Validation timed out'
      : error?.message || 'Validation could not complete';
    return setupValidationResult(field, 'error', detail);
  }
}

function memoryTemplate() {
  return [
    '# MEMORY.md - Long-Term Memory',
    '',
    '## User Preferences',
    '',
    '*(Add user preferences here)*',
    '',
    '## Key Events',
    '',
    '*(Important events and decisions)*',
    '',
    '## Lessons Learned',
    '',
    '*(Things to remember for future interactions)*',
    '',
    '## Context',
    '',
    '*(General context about the user, projects, etc.)*',
    '',
  ].join('\n');
}

function resolveMemoryPaths() {
  const runtimeHome = resolveRuntimeHome();
  const memoryDirPath = path.join(runtimeHome, 'memory');
  const memoryFilePath = path.join(runtimeHome, 'MEMORY.md');
  return {
    runtimeHome,
    memoryDirPath,
    memoryFilePath,
  };
}

function summarizeMemoryLogs(memoryDirPath) {
  try {
    const files = fs
      .readdirSync(memoryDirPath, { withFileTypes: true })
      .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith('.md'))
      .map((entry) => entry.name)
      .sort();
    return {
      dailyLogCount: files.length,
      oldestLog: files[0] || null,
      newestLog: files[files.length - 1] || null,
    };
  } catch (_error) {
    return {
      dailyLogCount: 0,
      oldestLog: null,
      newestLog: null,
    };
  }
}

async function readManagedMemory() {
  const { memoryDirPath, memoryFilePath } = resolveMemoryPaths();
  fs.mkdirSync(memoryDirPath, { recursive: true });
  const exists = fs.existsSync(memoryFilePath);
  const content = exists ? fs.readFileSync(memoryFilePath, 'utf-8') : memoryTemplate();
  return {
    ok: true,
    exists,
    memoryFilePath,
    memoryDirPath,
    content,
    ...summarizeMemoryLogs(memoryDirPath),
  };
}

async function writeManagedMemory(contentValue) {
  const { memoryDirPath, memoryFilePath } = resolveMemoryPaths();
  fs.mkdirSync(memoryDirPath, { recursive: true });
  const content = String(contentValue ?? '');
  fs.writeFileSync(memoryFilePath, content, 'utf-8');
  return readManagedMemory();
}

function resolveSidebarStatePath() {
  return path.join(resolveRuntimeHome(), 'desktop-sidebar-state.json');
}

function readSidebarState() {
  const filePath = resolveSidebarStatePath();
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch (_error) {
    return null;
  }
}

function writeSidebarState(state) {
  const filePath = resolveSidebarStatePath();
  fs.mkdirSync(path.dirname(filePath), { recursive: true });

  if (state == null) {
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
    }
    return null;
  }

  fs.writeFileSync(filePath, `${JSON.stringify(state, null, 2)}\n`, 'utf-8');
  return state;
}

function getSidebarPathStatus(targetPath) {
  const candidate = String(targetPath || '').trim();
  if (!candidate) {
    return {
      requestedPath: null,
      resolvedPath: null,
      exists: false,
      isDirectory: false,
    };
  }

  try {
    const resolvedPath = path.resolve(candidate);
    if (!fs.existsSync(resolvedPath)) {
      return {
        requestedPath: candidate,
        resolvedPath,
        exists: false,
        isDirectory: false,
      };
    }

    const stat = fs.statSync(resolvedPath);
    return {
      requestedPath: candidate,
      resolvedPath,
      exists: true,
      isDirectory: Boolean(stat.isDirectory()),
    };
  } catch (_error) {
    return {
      requestedPath: candidate,
      resolvedPath: null,
      exists: false,
      isDirectory: false,
    };
  }
}

function runGitCommand(targetPath, gitArgs) {
  const cwd = path.resolve(String(targetPath || '').trim() || '.');
  const result = spawnSync('git', ['-C', cwd, ...gitArgs], {
    windowsHide: true,
    encoding: 'utf-8',
  });
  if (result.error) {
    return {
      ok: false,
      error: result.error.message || 'git command failed',
      stdout: '',
      stderr: '',
    };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      error: String(result.stderr || result.stdout || '').trim() || `git exited with code ${result.status}`,
      stdout: String(result.stdout || '').trim(),
      stderr: String(result.stderr || '').trim(),
    };
  }
  return {
    ok: true,
    error: null,
    stdout: String(result.stdout || '').trim(),
    stderr: String(result.stderr || '').trim(),
  };
}

function getSidebarGitRepoInfo(targetPath) {
  const candidate = String(targetPath || '').trim();
  if (!candidate) {
    return {
      requestedPath: null,
      resolvedPath: null,
      repoRoot: null,
      isGitRepo: false,
      currentBranch: null,
      branches: [],
      error: null,
    };
  }

  const pathStatus = getSidebarPathStatus(candidate);
  const resolvedPath = pathStatus?.resolvedPath || path.resolve(candidate);
  if (!pathStatus?.exists || !pathStatus?.isDirectory) {
    return {
      requestedPath: candidate,
      resolvedPath,
      repoRoot: null,
      isGitRepo: false,
      currentBranch: null,
      branches: [],
      error: 'Folder not available',
    };
  }

  const topLevel = runGitCommand(resolvedPath, ['rev-parse', '--show-toplevel']);
  if (!topLevel.ok || !topLevel.stdout) {
    return {
      requestedPath: candidate,
      resolvedPath,
      repoRoot: null,
      isGitRepo: false,
      currentBranch: null,
      branches: [],
      error: null,
    };
  }

  const repoRoot = path.resolve(topLevel.stdout);
  const currentBranchResult = runGitCommand(resolvedPath, ['branch', '--show-current']);
  const branchListResult = runGitCommand(resolvedPath, ['for-each-ref', '--format=%(refname:short)', 'refs/heads']);
  const currentBranch = currentBranchResult.ok ? String(currentBranchResult.stdout || '').trim() || null : null;
  const branches = branchListResult.ok
    ? Array.from(new Set(
        String(branchListResult.stdout || '')
          .split(/\r?\n/)
          .map((item) => String(item || '').trim())
          .filter(Boolean),
      ))
    : [];

  if (currentBranch && !branches.includes(currentBranch)) {
    branches.unshift(currentBranch);
  }

  return {
    requestedPath: candidate,
    resolvedPath,
    repoRoot,
    isGitRepo: true,
    currentBranch,
    branches,
    error: null,
  };
}

function checkoutSidebarGitBranch(targetPath, branchName) {
  const branch = String(branchName || '').trim();
  const info = getSidebarGitRepoInfo(targetPath);
  if (!info.isGitRepo || !info.resolvedPath) {
    return {
      ...info,
      error: info.error || 'Not a Git repository',
    };
  }
  if (!branch) {
    return {
      ...info,
      error: 'Missing branch name',
    };
  }
  if (info.currentBranch === branch) {
    return info;
  }
  const switched = runGitCommand(info.resolvedPath, ['switch', branch]);
  if (!switched.ok) {
    return {
      ...info,
      error: switched.error || 'Failed to switch branch',
    };
  }
  return getSidebarGitRepoInfo(info.resolvedPath);
}

async function pickSidebarFolder(defaultPath) {
  const candidate = String(defaultPath || '').trim();
  const result = await dialog.showOpenDialog(mainWindow || undefined, {
    title: 'Choose Project Folder',
    properties: ['openDirectory', 'createDirectory'],
    defaultPath: candidate || resolveRuntimeHome(),
  });

  if (result.canceled || !Array.isArray(result.filePaths) || !result.filePaths[0]) {
    return null;
  }

  return path.resolve(result.filePaths[0]);
}

function resolveRuntimeHome() {
  const configured = String(process.env.EMPLOAI_HOME || '').trim();
  if (configured) {
    return path.resolve(configured);
  }

  const base = process.env.LOCALAPPDATA || process.env.APPDATA || app.getPath('home');
  return path.resolve(path.join(base, 'EmploAI'));
}

function loadDesktopShutdownPreferences() {
  const configPath = path.join(resolveRuntimeHome(), 'config.json');
  try {
    const payload = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    const desktop = payload?.channels?.desktop || {};
    return {
      keepRuntimeOnAppClose: Boolean(desktop.keep_runtime_on_app_close),
    };
  } catch (_error) {
    return {
      keepRuntimeOnAppClose: false,
    };
  }
}

async function shutdownManagedProcessesForQuit() {
  if (shutdownForQuitPromise) {
    return shutdownForQuitPromise;
  }

  shutdownForQuitPromise = (async () => {
    const preferences = loadDesktopShutdownPreferences();
    if (preferences.keepRuntimeOnAppClose) {
      return { keptAlive: true };
    }

    try {
      await stopLocalRuntime();
      return { keptAlive: false, stopped: true };
    } catch (error) {
      console.error('Failed to stop local runtime during desktop app shutdown:', error);
      return { keptAlive: false, stopped: false, error: String(error) };
    }
  })();

  return shutdownForQuitPromise;
}

async function loadRenderer(window) {
  const devUrl = process.env.EMPLOAI_DESKTOP_RENDERER_URL;
  if (devUrl) {
    await window.loadURL(devUrl);
    return;
  }

  const rendererIndex = resolveRendererIndex();
  if (!fs.existsSync(rendererIndex)) {
    const html = [
      '<html><body style="background:#0b1020;color:#fff;font-family:Segoe UI;padding:32px;">',
      '<h2>Desktop renderer not built</h2>',
      '<p>Run <code>npm --prefix mobile_app/client run export:web</code> before launching the desktop shell without a dev server.</p>',
      '</body></html>',
    ].join('');
    await window.loadURL(`data:text/html,${encodeURIComponent(html)}`);
    return;
  }

  await window.loadURL('emploai://renderer/');
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1540,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: '#0b1020',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });

  await loadRenderer(mainWindow);
}

app.whenReady().then(async () => {
  protocol.handle('emploai', (request) => {
    const rendererRoot = resolveRendererRoot();
    const targetFile = resolveRendererAssetPath(rendererRoot, new URL(request.url));
    return net.fetch(pathToFileURL(targetFile).toString());
  });

  ipcMain.handle('emploai:bootstrap', async () => {
    if (bootstrapCache) {
      return bootstrapCache;
    }
    return bootstrapRuntime();
  });

  ipcMain.handle('emploai:get-runtime-status', async () => {
    if (runtimeStatusCache) {
      return runtimeStatusCache;
    }
    return getRuntimeStatus();
  });

  ipcMain.handle('emploai:runtime:start', async (_event, payload) => startLocalRuntime(payload || {}));
  ipcMain.handle('emploai:runtime:stop', async () => stopLocalRuntime());
  ipcMain.handle('emploai:setup:save', async (_event, payload) => saveSetup(payload || {}));
  ipcMain.handle('emploai:setup:validate-field', async (_event, payload) => validateSetupField(payload?.field, payload?.value));
  ipcMain.handle('emploai:voice-packs:install', async (_event, packId) => installVoicePack(packId));
  ipcMain.handle('emploai:voice-packs:remove', async (_event, packId) => removeVoicePack(packId));
  ipcMain.handle('emploai:voice-packs:set-default-engine', async (_event, engine) => setDefaultVoiceEngine(engine));
  ipcMain.handle('emploai:updates:check', async (_event, payload) => checkUpdates(Boolean(payload?.force)));
  ipcMain.handle('emploai:updates:install', async () => installUpdate());
  ipcMain.handle('emploai:shell:open-path', async (_event, targetPath) => openManagedPath(targetPath));
  ipcMain.handle('emploai:shell:open-chrome-extensions', async () => openChromeExtensionsPage());
  ipcMain.handle('emploai:clipboard:write-text', async (_event, textValue) => copyManagedText(textValue));
  ipcMain.handle('emploai:memory:read', async () => readManagedMemory());
  ipcMain.handle('emploai:memory:write', async (_event, payload) => writeManagedMemory(payload?.content));
  ipcMain.handle('emploai:sidebar:read-state', async () => readSidebarState());
  ipcMain.handle('emploai:sidebar:write-state', async (_event, payload) => writeSidebarState(payload?.state ?? null));
  ipcMain.handle('emploai:sidebar:pick-folder', async (_event, payload) => pickSidebarFolder(payload?.defaultPath));
  ipcMain.handle('emploai:sidebar:path-status', async (_event, payload) => getSidebarPathStatus(payload?.path));
  ipcMain.handle('emploai:sidebar:git-repo-info', async (_event, payload) => getSidebarGitRepoInfo(payload?.path));
  ipcMain.handle('emploai:sidebar:checkout-branch', async (_event, payload) => checkoutSidebarGitBranch(payload?.path, payload?.branch));

  await createWindow();

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on('before-quit', (event) => {
  if (quitAfterManagedShutdown) {
    return;
  }

  event.preventDefault();
  shutdownManagedProcessesForQuit().finally(() => {
    quitAfterManagedShutdown = true;
    app.quit();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
