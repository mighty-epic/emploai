const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createRemoteAccountSessionStore } = require('./session_store');
const { cloudBackendEnabled, mobileConnectionEnabled, standaloneDesktopEnabled } = require('./standalone_mode');

function createRemoteControlServices({ net, shell, safeStorage, resolveRuntimeHome, saveSetup, getBootstrapCache }) {
  if (!net || !shell || !safeStorage || typeof resolveRuntimeHome !== 'function' || typeof saveSetup !== 'function' || typeof getBootstrapCache !== 'function') {
    throw new Error('Remote control services require Electron APIs, runtime path, setup saver, and bootstrap cache access.');
  }
  const remoteAccountSessionFilename = 'remote-account-session.json';
  const localRuntimeSecretsFilename = 'local-runtime-secrets.json';
  const remoteDesktopIdentityFilename = 'remote-desktop-identity.json';
  const defaultRemoteControlBaseUrl = 'https://api.kraitos.app';
  const remoteControlRequestTimeoutMs = 30000;
  const setupSecretFields = [
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'GOOGLE_API_KEY',
    'XAI_API_KEY',
    'DEEPSEEK_API_KEY',
    'NVIDIA_API_KEY',
    'OPENROUTER_API_KEY',
    'TELEGRAM_BOT_TOKEN',
    'GMAIL_LOGIN_EMAIL',
    'GMAIL_LOGIN_PASSWORD',
  ];
  const setupProviderSecretFields = new Set([
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'GOOGLE_API_KEY',
    'XAI_API_KEY',
    'DEEPSEEK_API_KEY',
    'NVIDIA_API_KEY',
    'OPENROUTER_API_KEY',
  ]);
  const localRuntimeSetupSecretFields = new Set([
    ...setupProviderSecretFields,
    'TELEGRAM_BOT_TOKEN',
    'EMPLOAI_TELEGRAM_BOT_TOKENS_JSON',
  ]);
  const remoteAccountRuntimeOverlayFields = new Set([
    'EMPLOAI_REMOTE_CONTROL_BASE_URL',
    'EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN',
    'EMPLOAI_REMOTE_CONTROL_USER_ID',
    'EMPLOAI_REMOTE_CONTROL_DESKTOP_ID',
  ]);
  const runtimeOverlayFields = new Set([
    ...localRuntimeSetupSecretFields,
    ...remoteAccountRuntimeOverlayFields,
  ]);
  const localSetupSecretFields = new Set([
    ...setupSecretFields,
    'GEMINI_API_KEY',
    'EMPLOAI_TELEGRAM_BOT_TOKENS_JSON',
    'EMPLOAI_REMOTE_CONTROL_PASSWORD',
    'EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN',
    'GMAIL_EMAIL',
    'GMAIL_PASSWORD',
  ]);

  let remoteAccountMemorySession = null;
  const remoteAccountSessionStore = createRemoteAccountSessionStore({
    filename: remoteAccountSessionFilename,
    resolveRuntimeHome,
    safeStorage,
  });
  const localRuntimeSecretStore = createRemoteAccountSessionStore({
    filename: localRuntimeSecretsFilename,
    resolveRuntimeHome,
    safeStorage,
  });
  let runtimeSecretOverlay = readLocalRuntimeSecretOverlay();

  function resolveRemoteAccountSessionPath() {
    return remoteAccountSessionStore.resolvePath();
  }

  function readRemoteAccountSession() {
    return remoteAccountSessionStore.read();
  }

  function currentRemoteAccountSession() {
    return remoteAccountMemorySession || readRemoteAccountSession();
  }

  function cloudDisabledStatus(session = currentRemoteAccountSession()) {
    return {
      signedIn: false,
      cloudDisabled: true,
      mobileDisabled: !mobileConnectionEnabled(),
      standalone: standaloneDesktopEnabled(),
      apiBaseUrl: normalizeRemoteBaseUrl(session?.apiBaseUrl),
      sessionPath: resolveRemoteAccountSessionPath(),
      sessionStorage: remoteAccountSessionStore.storageKind(),
      detail: 'Cloud account and mobile pairing are disabled in standalone desktop mode.',
    };
  }

  function ensureCloudAccountEnabled() {
    if (!cloudBackendEnabled()) {
      throw new Error('Cloud account and mobile pairing are disabled in standalone desktop mode.');
    }
  }

  function writeRemoteAccountSession(payload) {
    return remoteAccountSessionStore.write(payload);
  }

  function setRemoteAccountSession(payload, { rememberMe = true } = {}) {
    if (rememberMe) {
      remoteAccountMemorySession = null;
      return writeRemoteAccountSession(payload);
    }
    remoteAccountMemorySession = payload;
    return payload;
  }

  function clearRemoteAccountSession() {
    remoteAccountMemorySession = null;
    remoteAccountSessionStore.clear();
  }

  function normalizeRuntimeSecretOverlay(secrets = {}) {
    const values = {};
    for (const [key, rawValue] of Object.entries(secrets || {})) {
      const cleanKey = String(key || '').trim();
      const value = String(rawValue || '').trim();
      if (cleanKey && value && localRuntimeSetupSecretFields.has(cleanKey)) {
        values[cleanKey] = value;
      }
    }
    if (values.GOOGLE_API_KEY && !values.GEMINI_API_KEY) {
      values.GEMINI_API_KEY = values.GOOGLE_API_KEY;
    }
    return values;
  }

  function readLocalRuntimeSecretOverlay() {
    const payload = localRuntimeSecretStore.read();
    const secrets = payload?.secrets && typeof payload.secrets === 'object' ? payload.secrets : {};
    return normalizeRuntimeSecretOverlay(secrets);
  }

  function persistRuntimeSecretOverlay() {
    const secrets = normalizeRuntimeSecretOverlay(runtimeSecretOverlay);
    runtimeSecretOverlay = secrets;
    if (!Object.keys(secrets).length) {
      localRuntimeSecretStore.clear();
      return;
    }
    localRuntimeSecretStore.write({
      secrets,
      savedAt: new Date().toISOString(),
    });
  }

  function normalizeRemoteBaseUrl(value) {
    return String(value || defaultRemoteControlBaseUrl).trim().replace(/\/+$/, '') || defaultRemoteControlBaseUrl;
  }

  function resolveRemoteDesktopIdentityPath() {
    return path.join(resolveRuntimeHome(), remoteDesktopIdentityFilename);
  }

  function resolveRemoteDesktopKey(candidate) {
    const provided = String(candidate || '').trim();
    if (provided) {
      return provided;
    }

    const filePath = resolveRemoteDesktopIdentityPath();
    try {
      if (fs.existsSync(filePath)) {
        const existing = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        const key = String(existing?.deviceKey || '').trim();
        if (key) {
          return key;
        }
      }
    } catch (_error) {
      // Fall through and write a new stable key.
    }

    const deviceKey = `desktop-${crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex')}`;
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, `${JSON.stringify({ deviceKey, createdAt: new Date().toISOString() }, null, 2)}\n`, 'utf-8');
    try {
      fs.chmodSync(filePath, 0o600);
    } catch (_error) {
      // Windows ACLs are inherited; chmod is best-effort here.
    }
    return deviceKey;
  }

  function resolveRemoteDesktopName(candidate) {
    const provided = String(candidate || '').trim();
    if (provided) {
      return provided;
    }
    const hostname = String(os.hostname() || '').trim();
    return hostname ? `EmploAI Desktop (${hostname})` : 'EmploAI Desktop';
  }

  async function remoteControlJson(baseUrl, endpoint, options = {}) {
    const fetchImpl = net.fetch ? net.fetch.bind(net) : fetch;
    const timeoutMs = Number.isFinite(Number(options.timeoutMs))
      ? Math.max(1000, Math.trunc(Number(options.timeoutMs)))
      : remoteControlRequestTimeoutMs;
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutError = new Error(`Request to ${endpoint} timed out after ${Math.round(timeoutMs / 1000)} seconds.`);
    let timedOut = false;
    let timeout = null;
    let response;
    const requestUrl = `${normalizeRemoteBaseUrl(baseUrl)}${endpoint}`;
    const fetchPromise = fetchImpl(requestUrl, {
      method: options.method || 'GET',
      headers: {
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      ...(controller ? { signal: controller.signal } : {}),
    });
    fetchPromise.catch(() => null);
    try {
      response = await Promise.race([
        fetchPromise,
        new Promise((_resolve, reject) => {
          timeout = setTimeout(() => {
            timedOut = true;
            controller?.abort();
            reject(timeoutError);
          }, timeoutMs);
        }),
      ]);
    } catch (error) {
      if (timedOut || controller?.signal?.aborted || error?.name === 'AbortError') {
        throw timeoutError;
      }
      throw error;
    } finally {
      if (timeout) {
        clearTimeout(timeout);
      }
    }
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (_error) {
      payload = { detail: text };
    }
    if (!response.ok) {
      throw new Error(payload?.detail || `${response.status} ${response.statusText}`);
    }
    return payload;
  }

  async function remoteAuthStatus() {
    const session = currentRemoteAccountSession();
    if (!cloudBackendEnabled()) {
      return cloudDisabledStatus(session);
    }
    if (!session?.sessionToken) {
      return {
        signedIn: false,
        apiBaseUrl: normalizeRemoteBaseUrl(session?.apiBaseUrl),
        sessionPath: resolveRemoteAccountSessionPath(),
        sessionStorage: remoteAccountSessionStore.storageKind(),
      };
    }
    try {
      const profile = await remoteControlJson(session.apiBaseUrl, '/api/remote/account/me', {
        token: session.sessionToken,
      });
      const next = setRemoteAccountSession({
        ...session,
        apiBaseUrl: normalizeRemoteBaseUrl(session.apiBaseUrl),
        actorKind: profile.actor_kind || 'desktop',
        user: profile.user || null,
        desktop: profile.desktop || null,
        profile: profile.profile || null,
        verifiedAt: new Date().toISOString(),
      }, {
        rememberMe: Boolean(session.rememberMe),
      });
      return {
        signedIn: true,
        apiBaseUrl: next.apiBaseUrl,
        user: next.user,
        desktop: next.desktop,
        profile: next.profile || null,
        sessionPath: resolveRemoteAccountSessionPath(),
        sessionStorage: remoteAccountSessionStore.storageKind(),
      };
    } catch (error) {
      return {
        signedIn: false,
        apiBaseUrl: normalizeRemoteBaseUrl(session.apiBaseUrl),
        error: error?.message || String(error),
        sessionPath: resolveRemoteAccountSessionPath(),
        sessionStorage: remoteAccountSessionStore.storageKind(),
      };
    }
  }

  async function remoteAuthListDesktops() {
    const session = remoteAccountSessionOrThrow();
    return remoteControlJson(session.apiBaseUrl, '/api/remote/desktops', {
      token: session.sessionToken,
    });
  }

  async function finishLegacyRemoteAuthIfSession(apiBaseUrl, result, loginProvider = 'password') {
    if (!result?.session_token) {
      return result;
    }
    const rememberMe = result.remember_me === undefined ? true : Boolean(result.remember_me);
    setRemoteAccountSession(
      {
        apiBaseUrl,
        sessionToken: result.session_token,
        actorKind: result.actor_kind || 'desktop',
        user: result.user || null,
        desktop: result.desktop || null,
        savedAt: new Date().toISOString(),
        loginProvider,
        rememberMe,
        expiresInSeconds: result.expires_in_seconds || null,
      },
      { rememberMe },
    );
    return remoteAuthStatus();
  }

  async function remoteAuthLogin(payload = {}) {
    ensureCloudAccountEnabled();
    const apiBaseUrl = normalizeRemoteBaseUrl(payload.apiBaseUrl);
    const email = String(payload.email || '').trim();
    const password = String(payload.password || '').trim();
    if (!email || !password) {
      throw new Error('Email and password are required.');
    }
    const result = await remoteControlJson(apiBaseUrl, '/api/remote/auth/login', {
      method: 'POST',
      body: {
        email,
        password,
        actor_kind: 'desktop',
        device_name: resolveRemoteDesktopName(payload.deviceName),
        device_platform: 'desktop-electron',
        device_key: resolveRemoteDesktopKey(payload.deviceKey),
        remember_me: Boolean(payload.rememberMe || payload.remember_me),
      },
    });
    return finishLegacyRemoteAuthIfSession(apiBaseUrl, result, 'password');
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function remoteAuthGoogleLogin(payload = {}) {
    ensureCloudAccountEnabled();
    const apiBaseUrl = normalizeRemoteBaseUrl(payload.apiBaseUrl);
    const started = await remoteControlJson(apiBaseUrl, '/api/remote/auth/google/start', {
      method: 'POST',
      body: {
        actor_kind: 'desktop',
        device_name: resolveRemoteDesktopName(payload.deviceName),
        device_platform: 'desktop-electron',
        device_key: resolveRemoteDesktopKey(payload.deviceKey),
        remember_me: Boolean(payload.rememberMe || payload.remember_me),
      },
    });
    if (!started?.auth_url || !started?.request_id || !started?.poll_token) {
      throw new Error('Google sign-in did not return a login request.');
    }
    await shell.openExternal(started.auth_url);
    const startedAt = Date.now();
    const timeoutMs = Math.max(30000, Number(started.expires_in_seconds || 300) * 1000);
    while (Date.now() - startedAt < timeoutMs) {
      await wait(1500);
      const result = await remoteControlJson(apiBaseUrl, '/api/remote/auth/google/poll', {
        method: 'POST',
        body: {
          request_id: started.request_id,
          poll_token: started.poll_token,
        },
      });
      if (result?.status === 'complete') {
        setRemoteAccountSession({
          apiBaseUrl,
          sessionToken: result.session_token,
          actorKind: 'desktop',
          user: result.user || null,
          desktop: result.desktop || null,
          savedAt: new Date().toISOString(),
          loginProvider: 'google',
          rememberMe: Boolean(result.remember_me),
          expiresInSeconds: result.expires_in_seconds || null,
        }, {
          rememberMe: Boolean(result.remember_me),
        });
        return remoteAuthStatus();
      }
      if (result?.status === 'error' || result?.status === 'expired') {
        throw new Error(result.error || 'Google sign-in did not complete.');
      }
    }
    throw new Error('Google sign-in timed out. Try again from the account screen.');
  }

  async function remoteAuthRegister(payload = {}) {
    ensureCloudAccountEnabled();
    const apiBaseUrl = normalizeRemoteBaseUrl(payload.apiBaseUrl);
    const result = await remoteControlJson(apiBaseUrl, '/api/remote/auth/register', {
      method: 'POST',
      body: {
        email: String(payload.email || '').trim(),
        password: String(payload.password || '').trim(),
        display_name: String(payload.displayName || '').trim() || undefined,
        actor_kind: 'desktop',
        device_name: resolveRemoteDesktopName(payload.deviceName),
        device_platform: 'desktop-electron',
        device_key: resolveRemoteDesktopKey(payload.deviceKey),
        remember_me: Boolean(payload.rememberMe || payload.remember_me),
      },
    });
    return finishLegacyRemoteAuthIfSession(apiBaseUrl, result, 'password');
  }

  async function remoteAuthVerifyOtp(payload = {}) {
    ensureCloudAccountEnabled();
    const apiBaseUrl = normalizeRemoteBaseUrl(payload.apiBaseUrl);
    const challengeId = String(payload.challengeId || payload.challenge_id || '').trim();
    const code = String(payload.code || '').trim();
    if (!challengeId || !code) {
      throw new Error('Verification code is required.');
    }
    const result = await remoteControlJson(apiBaseUrl, '/api/remote/auth/otp/verify', {
      method: 'POST',
      body: {
        challenge_id: challengeId,
        code,
      },
    });
    setRemoteAccountSession({
      apiBaseUrl,
      sessionToken: result.session_token,
      actorKind: result.actor_kind || 'desktop',
      user: result.user || null,
      desktop: result.desktop || null,
      savedAt: new Date().toISOString(),
      loginProvider: 'password',
      rememberMe: Boolean(result.remember_me),
      expiresInSeconds: result.expires_in_seconds || null,
    }, {
      rememberMe: Boolean(result.remember_me),
    });
    return remoteAuthStatus();
  }

  async function remoteAuthResendOtp(payload = {}) {
    ensureCloudAccountEnabled();
    const apiBaseUrl = normalizeRemoteBaseUrl(payload.apiBaseUrl);
    const challengeId = String(payload.challengeId || payload.challenge_id || '').trim();
    if (!challengeId) {
      throw new Error('Verification challenge is required.');
    }
    return remoteControlJson(apiBaseUrl, '/api/remote/auth/otp/resend', {
      method: 'POST',
      body: {
        challenge_id: challengeId,
      },
    });
  }

  async function remoteAuthLogout() {
    if (!cloudBackendEnabled()) {
      return cloudDisabledStatus();
    }
    const session = currentRemoteAccountSession();
    if (session?.sessionToken) {
      await remoteControlJson(session.apiBaseUrl, '/api/remote/auth/logout', {
        method: 'POST',
        token: session.sessionToken,
      }).catch(() => null);
    }
    clearRemoteAccountSession();
    return { signedIn: false, apiBaseUrl: defaultRemoteControlBaseUrl, sessionPath: resolveRemoteAccountSessionPath() };
  }

  async function remoteAuthCreatePairingToken() {
    const session = currentRemoteAccountSession();
    if (!session?.sessionToken) {
      throw new Error('Desktop is not signed in.');
    }
    const result = await remoteControlJson(session.apiBaseUrl, '/api/remote/pair/start', {
      method: 'POST',
      token: session.sessionToken,
      body: { desktop_id: session.desktop?.desktop_id || null },
    });
    return result;
  }

  function remoteAccountSessionOrThrow() {
    ensureCloudAccountEnabled();
    const session = currentRemoteAccountSession();
    if (!session?.sessionToken) {
      throw new Error('Desktop is not signed in.');
    }
    return session;
  }

  function setupSecretMetadata() {
    return {
      OPENAI_API_KEY: { label: 'OpenAI API key', kind: 'provider_api_key' },
      ANTHROPIC_API_KEY: { label: 'Anthropic API key', kind: 'provider_api_key' },
      GOOGLE_API_KEY: { label: 'Google Gemini API key', kind: 'provider_api_key' },
      XAI_API_KEY: { label: 'xAI Grok API key', kind: 'provider_api_key' },
      DEEPSEEK_API_KEY: { label: 'DeepSeek API key', kind: 'provider_api_key' },
      NVIDIA_API_KEY: { label: 'NVIDIA API key', kind: 'provider_api_key' },
      OPENROUTER_API_KEY: { label: 'OpenRouter API key', kind: 'provider_api_key' },
      TELEGRAM_BOT_TOKEN: { label: 'Telegram bot token', kind: 'telegram_bot_token' },
    };
  }

  function setupValuesFromRemoteProfile(profile = {}) {
    const values = {};
    const preferences = profile?.preferences && typeof profile.preferences === 'object' ? profile.preferences : {};
    const integrations = profile?.integrations && typeof profile.integrations === 'object' ? profile.integrations : {};
    const telegram = integrations.telegram && typeof integrations.telegram === 'object' ? integrations.telegram : {};
    const defaultWorkspace = String(preferences.default_workspace || '').trim();
    const plannerModel = String(preferences.planner_model || '').trim();
    const interruptPolicy = String(preferences.interrupt_policy_default || '').trim().toLowerCase();
    if (defaultWorkspace) {
      values.DEFAULT_WORKSPACE = defaultWorkspace;
    }
    if (plannerModel) {
      values.PLANNER_MODEL = plannerModel;
    }
    if (['none', 'steer_now', 'after_tool'].includes(interruptPolicy)) {
      values.INTERRUPT_POLICY_DEFAULT = interruptPolicy;
    }
    const allowedUserIds = Array.isArray(telegram.allowed_user_ids)
      ? telegram.allowed_user_ids
      : Array.isArray(telegram.allowedUserIds)
        ? telegram.allowedUserIds
        : [];
    const cleanAllowedUserIds = allowedUserIds
      .map((item) => String(item || '').trim().replace(/^\+/, ''))
      .filter((item, index, items) => /^-?\d+$/.test(item) && items.indexOf(item) === index);
    if (cleanAllowedUserIds.length) {
      values.ALLOWED_USER_IDS = cleanAllowedUserIds.join(',');
    }
    return values;
  }

  function sanitizeSetupValuesForLocal(values = {}) {
    const cleanValues = {};
    for (const [key, rawValue] of Object.entries(values || {})) {
      const cleanKey = String(key);
      if (localSetupSecretFields.has(cleanKey) && !localRuntimeSetupSecretFields.has(cleanKey)) {
        continue;
      }
      cleanValues[key] = rawValue;
    }
    return cleanValues;
  }

  function rememberRuntimeSecretOverlay(values = {}) {
    const nextValues = {};
    for (const [key, rawValue] of Object.entries(values || {})) {
      const cleanKey = String(key || '').trim();
      if (!localRuntimeSetupSecretFields.has(cleanKey)) {
        continue;
      }
      const value = String(rawValue || '').trim();
      if (value) {
        runtimeSecretOverlay[cleanKey] = value;
        nextValues[cleanKey] = value;
      } else {
        delete runtimeSecretOverlay[cleanKey];
      }
    }
    persistRuntimeSecretOverlay();
    return nextValues;
  }

  function redactSecretValue(rawValue) {
    const value = String(rawValue || '').trim();
    if (!value) {
      return '';
    }
    if (value.length <= 8) {
      return `${value.slice(0, 2)}...${value.slice(-2)}`;
    }
    return `${value.slice(0, Math.min(6, value.length - 4))}...${value.slice(-4)}`;
  }

  function runtimeSecretOverlayPreviews() {
    const previews = {};
    for (const [key, rawValue] of Object.entries(runtimeSecretOverlay || {})) {
      const cleanKey = String(key || '').trim();
      const value = String(rawValue || '').trim();
      if (cleanKey && value && setupProviderSecretFields.has(cleanKey)) {
        previews[cleanKey] = {
          redacted_value: redactSecretValue(value),
          source: 'local_runtime',
        };
      }
    }
    return previews;
  }

  function remoteAccountRuntimeOverlayValues() {
    if (!cloudBackendEnabled()) {
      return {};
    }
    const session = currentRemoteAccountSession();
    const sessionToken = String(session?.sessionToken || session?.session_token || '').trim();
    if (!sessionToken) {
      return {};
    }
    const values = {
      EMPLOAI_REMOTE_CONTROL_BASE_URL: normalizeRemoteBaseUrl(session.apiBaseUrl || session.api_base_url),
      EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN: sessionToken,
    };
    const userId = String(session?.user?.user_id || session?.user_id || '').trim();
    if (userId) {
      values.EMPLOAI_REMOTE_CONTROL_USER_ID = userId;
    }
    const desktopId = String(session?.desktop?.desktop_id || session?.desktop_id || '').trim();
    if (desktopId) {
      values.EMPLOAI_REMOTE_CONTROL_DESKTOP_ID = desktopId;
    }
    return values;
  }

  function runtimeSecretOverlayEnvironment() {
    const values = remoteAccountRuntimeOverlayValues();
    for (const [key, rawValue] of Object.entries(runtimeSecretOverlay || {})) {
      const cleanKey = String(key || '').trim();
      const value = String(rawValue || '').trim();
      if (cleanKey && value && runtimeOverlayFields.has(cleanKey)) {
        values[cleanKey] = value;
      }
    }
    return Object.keys(values).length ? JSON.stringify(values) : '';
  }

  function readRuntimeEnvValues() {
    const envFile = path.join(resolveRuntimeHome(), '.env');
    const values = {};
    let text = '';
    try {
      text = fs.readFileSync(envFile, 'utf-8');
    } catch (_error) {
      return values;
    }
    for (const rawLine of text.split(/\r?\n/)) {
      const line = String(rawLine || '').trim();
      if (!line || line.startsWith('#')) {
        continue;
      }
      const normalizedLine = line.startsWith('export ') ? line.slice(7).trim() : line;
      const equalsIndex = normalizedLine.indexOf('=');
      if (equalsIndex <= 0) {
        continue;
      }
      const key = normalizedLine.slice(0, equalsIndex).trim();
      let value = normalizedLine.slice(equalsIndex + 1).trim();
      if (
        value.length >= 2
        && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))
      ) {
        value = value.slice(1, -1);
      }
      if (key) {
        values[key] = value;
      }
    }
    return values;
  }

  function runtimeValuesChanged(values = {}) {
    const existing = readRuntimeEnvValues();
    return Object.entries(values || {}).some(([key, rawValue]) => {
      const cleanValue = String(rawValue || '').trim();
      return cleanValue && String(existing[key] || '').trim() !== cleanValue;
    });
  }

  async function remoteAuthRevealSecrets(session, namespace, names = []) {
    const revealed = await remoteControlJson(session.apiBaseUrl, '/api/remote/account/secrets/reveal', {
      method: 'POST',
      token: session.sessionToken,
      headers: { 'X-EmploAI-Manual-Secret-Reveal': 'true' },
      body: {
        namespace,
        names,
      },
    });
    return revealed?.secrets && typeof revealed.secrets === 'object' ? revealed.secrets : {};
  }

  async function remoteAuthListSecrets(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    const namespace = String(payload.namespace || 'setup').trim() || 'setup';
    return remoteControlJson(session.apiBaseUrl, `/api/remote/account/secrets?namespace=${encodeURIComponent(namespace)}`, {
      token: session.sessionToken,
    });
  }

  async function remoteAuthSaveSetupSecrets(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    const values = payload.values || {};
    const secrets = {};
    for (const field of setupSecretFields) {
      const value = String(values[field] || '').trim();
      if (value) {
        secrets[field] = value;
      }
    }
    if (!Object.keys(secrets).length) {
      return remoteAuthListSecrets({ namespace: 'setup' });
    }
    const existingSecrets = await remoteAuthListSecrets({ namespace: 'setup' });
    const existingSecretNames = new Set((existingSecrets?.items || []).map((item) => String(item?.name || '').trim()).filter(Boolean));
    const blockedProviderFields = Object.keys(secrets).filter((field) => (
      setupProviderSecretFields.has(field) && existingSecretNames.has(field)
    ));
    if (blockedProviderFields.length) {
      const metadata = setupSecretMetadata();
      const labels = blockedProviderFields
        .map((field) => metadata[field]?.label || field)
        .join(', ');
      throw new Error(`Remove the saved ${labels} before replacing ${blockedProviderFields.length === 1 ? 'it' : 'them'}.`);
    }
    return remoteControlJson(session.apiBaseUrl, '/api/remote/account/secrets', {
      method: 'PUT',
      token: session.sessionToken,
      body: {
        namespace: 'setup',
        secrets,
        metadata: setupSecretMetadata(),
      },
    });
  }

  async function remoteAuthSaveSecrets(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    const namespace = String(payload.namespace || '').trim();
    const rawSecrets = payload.secrets && typeof payload.secrets === 'object' ? payload.secrets : {};
    const secrets = {};
    for (const [rawName, rawValue] of Object.entries(rawSecrets)) {
      const name = String(rawName || '').trim();
      const value = String(rawValue || '').trim();
      if (name && value) {
        secrets[name] = value;
      }
    }
    if (!namespace) {
      throw new Error('Secret namespace is required.');
    }
    if (!Object.keys(secrets).length) {
      return remoteAuthListSecrets({ namespace });
    }
    return remoteControlJson(session.apiBaseUrl, '/api/remote/account/secrets', {
      method: 'PUT',
      token: session.sessionToken,
      body: {
        namespace,
        secrets,
        metadata: payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {},
      },
    });
  }

  async function remoteAuthApplyAccountData() {
    const session = remoteAccountSessionOrThrow();
    const account = await remoteControlJson(session.apiBaseUrl, '/api/remote/account/me', {
      token: session.sessionToken,
    });
    const profile = account?.profile && typeof account.profile === 'object' ? account.profile : {};
    const [setupSecrets, telegramBotSecrets] = await Promise.all([
      remoteAuthRevealSecrets(session, 'setup'),
      remoteAuthRevealSecrets(session, 'telegram_bots').catch(() => ({})),
    ]);
    const values = setupValuesFromRemoteProfile(profile);
    const cleanValues = {};
    for (const [key, rawValue] of Object.entries(values)) {
      const value = String(rawValue || '').trim();
      if (value) {
        cleanValues[key] = value;
      }
    }
    const runtimeSecretValues = {};
    for (const [key, rawValue] of Object.entries(setupSecrets)) {
      const cleanKey = String(key || '').trim();
      const value = String(rawValue || '').trim();
      if (value && localRuntimeSetupSecretFields.has(cleanKey)) {
        runtimeSecretValues[cleanKey] = value;
      }
    }
    const count = Object.keys(cleanValues).length + Object.keys(setupSecrets).length + Object.keys(telegramBotSecrets).length;
    if (!count) {
      return {
        applied: false,
        count: 0,
        profile,
        setupSecretCount: Object.keys(setupSecrets).length,
        telegramBotSecretCount: Object.keys(telegramBotSecrets).length,
        detail: 'No saved setup found.',
      };
    }
    const localApplyValues = {
      ...cleanValues,
      ...runtimeSecretValues,
    };
    rememberRuntimeSecretOverlay(runtimeSecretValues);
    if (!Object.keys(localApplyValues).length) {
      return {
        applied: false,
        count,
        profile,
        bootstrap: getBootstrapCache(),
        setupSecretCount: Object.keys(setupSecrets).length,
        telegramBotSecretCount: Object.keys(telegramBotSecrets).length,
        detail: 'Saved account data is already available to the runtime.',
      };
    }
    try {
      const restartPolicy = runtimeValuesChanged(runtimeSecretValues) ? 'auto' : 'never';
      const bootstrap = await saveSetup({ values: localApplyValues, restart_policy: restartPolicy });
      return {
        applied: true,
        count,
        profile,
        bootstrap,
        setupSecretCount: Object.keys(setupSecrets).length,
        telegramBotSecretCount: Object.keys(telegramBotSecrets).length,
      };
    } catch (error) {
      return {
        applied: false,
        count,
        profile,
        setupSecretCount: Object.keys(setupSecrets).length,
        telegramBotSecretCount: Object.keys(telegramBotSecrets).length,
        detail: error?.message || String(error),
      };
    }
  }

  async function remoteAuthDeleteSecret(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    const namespace = String(payload.namespace || '').trim();
    const name = String(payload.name || '').trim();
    if (!namespace || !name) {
      throw new Error('Secret namespace and name are required.');
    }
    return remoteControlJson(
      session.apiBaseUrl,
      `/api/remote/account/secrets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
      {
        method: 'DELETE',
        token: session.sessionToken,
        headers: payload.confirmationId || payload.confirmation_id
          ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
          : {},
      },
    );
  }

  async function remoteAuthDeleteAccountData(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    return remoteControlJson(session.apiBaseUrl, '/api/remote/account/data', {
      method: 'DELETE',
      token: session.sessionToken,
      headers: payload.confirmationId || payload.confirmation_id
        ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
        : {},
    });
  }

  async function remoteAuthProfile() {
    const session = remoteAccountSessionOrThrow();
    return remoteControlJson(session.apiBaseUrl, '/api/remote/account/profile', {
      token: session.sessionToken,
    });
  }

  async function remoteAuthUpdateProfile(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    const profile = payload.profile && typeof payload.profile === 'object' ? payload.profile : {};
    const result = await remoteControlJson(session.apiBaseUrl, '/api/remote/account/profile', {
      method: 'PUT',
      token: session.sessionToken,
      body: { profile },
    });
    if (result?.profile && typeof result.profile === 'object') {
      setRemoteAccountSession({
        ...session,
        profile: result.profile,
        verifiedAt: new Date().toISOString(),
      }, {
        rememberMe: Boolean(session.rememberMe),
      });
    }
    return result;
  }

  async function remoteAuthApplySetupSecrets(payload = {}) {
    const session = remoteAccountSessionOrThrow();
    const names = Array.isArray(payload.names) && payload.names.length
      ? payload.names.map((item) => String(item || '').trim()).filter(Boolean)
      : setupSecretFields;
    const revealed = await remoteControlJson(session.apiBaseUrl, '/api/remote/account/secrets/reveal', {
      method: 'POST',
      token: session.sessionToken,
      headers: { 'X-EmploAI-Manual-Secret-Reveal': 'true' },
      body: {
        namespace: 'setup',
        names,
      },
    });
    const secrets = revealed?.secrets && typeof revealed.secrets === 'object' ? revealed.secrets : {};
    if (!Object.keys(secrets).length) {
      return { applied: false, count: 0, bootstrap: getBootstrapCache(), detail: 'No saved setup found.' };
    }
    const runtimeSecretValues = {};
    for (const [key, rawValue] of Object.entries(secrets)) {
      const cleanKey = String(key || '').trim();
      const value = String(rawValue || '').trim();
      if (value && localRuntimeSetupSecretFields.has(cleanKey)) {
        runtimeSecretValues[cleanKey] = value;
      }
    }
    if (Object.keys(runtimeSecretValues).length) {
      rememberRuntimeSecretOverlay(runtimeSecretValues);
      const restartPolicy = runtimeValuesChanged(runtimeSecretValues) ? 'auto' : 'never';
      const bootstrap = await saveSetup({ values: runtimeSecretValues, restart_policy: restartPolicy });
      return {
        applied: true,
        count: Object.keys(secrets).length,
        bootstrap,
        detail: restartPolicy === 'auto'
          ? 'Saved setup secrets were applied and the runtime restarted.'
          : 'Saved setup secrets are already available to the runtime.',
      };
    }
    return {
      applied: true,
      count: Object.keys(secrets).length,
      bootstrap: getBootstrapCache(),
      detail: 'Saved setup secrets are already available to the runtime.',
    };
  }

  function localAppSessionOrThrow() {
    const bootstrap = getBootstrapCache() || {};
    const apiBaseUrl = String(bootstrap.apiBaseUrl || bootstrap.api_base_url || '').trim().replace(/\/+$/, '');
    const accessToken = String(bootstrap.accessToken || bootstrap.access_token || '').trim();
    if (!apiBaseUrl || !accessToken) {
      throw new Error('Local desktop backend is not ready yet.');
    }
    return { apiBaseUrl, accessToken };
  }

  async function localAppApi(pathname, options = {}) {
    const local = localAppSessionOrThrow();
    return remoteControlJson(local.apiBaseUrl, pathname, {
      method: options.method || 'GET',
      token: local.accessToken,
      body: options.body,
      headers: options.headers || {},
    });
  }

  async function fleetApi(pathname, options = {}) {
    try {
      return await localAppApi(pathname, options);
    } catch (error) {
      if (!cloudBackendEnabled()) {
        throw error;
      }
    }
    const session = remoteAccountSessionOrThrow();
    return remoteControlJson(session.apiBaseUrl, pathname, {
      method: options.method || 'GET',
      token: session.sessionToken,
      body: options.body,
      headers: options.headers || {},
    });
  }

  async function fleetSnapshot() {
    return fleetApi('/api/fleet/snapshot');
  }

  async function fleetSetActiveIdentity(payload = {}) {
    const identityId = String(payload.identity_id || payload.identityId || '').trim();
    if (!identityId) {
      throw new Error('identity_id is required');
    }
    return fleetApi('/api/fleet/active-identity', {
      method: 'PUT',
      body: {
        identity_id: identityId,
        selected_chat_id: payload.selected_chat_id || payload.selectedChatId || null,
        source: payload.source || 'desktop',
      },
    });
  }

  async function fleetSetIdentityActiveChat(payload = {}) {
    const identityId = String(payload.identity_id || payload.identityId || '').trim();
    if (!identityId) {
      throw new Error('identity_id is required');
    }
    return fleetApi(`/api/fleet/identities/${encodeURIComponent(identityId)}/active-chat`, {
      method: 'PUT',
      body: {
        chat_id: payload.chat_id || payload.chatId || null,
        source: payload.source || 'desktop',
      },
    });
  }

  async function fleetCreateLocalWorker(payload = {}) {
    return fleetApi('/api/fleet/workers/local', {
      method: 'POST',
      body: {
        display_name: payload.display_name || payload.displayName || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetCreateEnrollment(payload = {}) {
    return fleetApi('/api/fleet/enrollments', {
      method: 'POST',
      body: {
        display_name: payload.display_name || payload.displayName || null,
        expires_in_seconds: payload.expires_in_seconds || payload.expiresInSeconds || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetRenameWorker(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    const displayName = String(payload.display_name || payload.displayName || '').trim();
    const queuePolicy = String(payload.queue_policy || payload.queuePolicy || '').trim();
    if (!workerId || (!displayName && !queuePolicy)) {
      throw new Error('worker_id and a worker update are required');
    }
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}`, {
      method: 'PUT',
      body: {
        display_name: displayName || null,
        queue_policy: queuePolicy || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetResetWorker(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    if (!workerId) {
      throw new Error('worker_id is required');
    }
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}/reset`, {
      method: 'POST',
      headers: payload.confirmationId || payload.confirmation_id
        ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
        : {},
      body: {
        reason: payload.reason || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetDeleteWorker(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    if (!workerId) {
      throw new Error('worker_id is required');
    }
    const wipeState = payload.wipe_state === undefined ? payload.wipeState : payload.wipe_state;
    const suffix = wipeState === false ? '?wipe_state=false' : '';
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}${suffix}`, {
      method: 'DELETE',
      headers: payload.confirmationId || payload.confirmation_id
        ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
        : {},
    });
  }

  async function fleetStopWorker(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    if (!workerId) {
      throw new Error('worker_id is required');
    }
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}/stop`, {
      method: 'POST',
      body: {
        reason: payload.reason || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetStopAll(payload = {}) {
    return fleetApi('/api/fleet/stop-all', {
      method: 'POST',
      headers: payload.confirmationId || payload.confirmation_id
        ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
        : {},
      body: {
        reason: payload.reason || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetRequestWorkerPreview(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    if (!workerId) {
      throw new Error('worker_id is required');
    }
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}/preview`, {
      method: 'POST',
      body: {},
    });
  }

  async function fleetAssignTask(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    const prompt = String(payload.prompt || '').trim();
    if (!workerId || !prompt) {
      throw new Error('worker_id and prompt are required');
    }
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}/tasks`, {
      method: 'POST',
      body: {
        prompt,
        source: payload.source || 'manager',
        target_session_id: payload.target_session_id || payload.targetSessionId || null,
        target_mode: payload.target_mode || payload.targetMode || 'auto',
        workspace_id: payload.workspace_id || payload.workspaceId || null,
        requires_workspace_write: Boolean(payload.requires_workspace_write || payload.requiresWorkspaceWrite),
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetCreateGroup(payload = {}) {
    const displayName = String(payload.display_name || payload.displayName || '').trim();
    if (!displayName) {
      throw new Error('display_name is required');
    }
    const workerIds = Array.isArray(payload.worker_ids) ? payload.worker_ids : (Array.isArray(payload.workerIds) ? payload.workerIds : []);
    return fleetApi('/api/fleet/groups', {
      method: 'POST',
      body: {
        display_name: displayName,
        description: payload.description || null,
        worker_ids: workerIds,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetUpdateGroup(payload = {}) {
    const groupId = String(payload.group_id || payload.groupId || '').trim();
    const displayName = String(payload.display_name || payload.displayName || '').trim();
    if (!groupId || !displayName) {
      throw new Error('group_id and display_name are required');
    }
    const workerIds = Array.isArray(payload.worker_ids) ? payload.worker_ids : (Array.isArray(payload.workerIds) ? payload.workerIds : []);
    return fleetApi(`/api/fleet/groups/${encodeURIComponent(groupId)}`, {
      method: 'PUT',
      body: {
        display_name: displayName,
        description: payload.description || null,
        worker_ids: workerIds,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetDeleteGroup(payload = {}) {
    const groupId = String(payload.group_id || payload.groupId || '').trim();
    if (!groupId) {
      throw new Error('group_id is required');
    }
    return fleetApi(`/api/fleet/groups/${encodeURIComponent(groupId)}`, {
      method: 'DELETE',
      headers: payload.confirmationId || payload.confirmation_id
        ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
        : {},
    });
  }

  async function fleetAssignGroupTask(payload = {}) {
    const groupId = String(payload.group_id || payload.groupId || '').trim();
    const prompt = String(payload.prompt || '').trim();
    if (!groupId || !prompt) {
      throw new Error('group_id and prompt are required');
    }
    return fleetApi(`/api/fleet/groups/${encodeURIComponent(groupId)}/tasks`, {
      method: 'POST',
      headers: payload.confirmationId || payload.confirmation_id
        ? { 'X-EmploAI-Confirmation-Id': payload.confirmationId || payload.confirmation_id }
        : {},
      body: {
        prompt,
        source: payload.source || 'manager',
        target_session_id: payload.target_session_id || payload.targetSessionId || null,
        target_mode: payload.target_mode || payload.targetMode || 'auto',
        workspace_id: payload.workspace_id || payload.workspaceId || null,
        requires_workspace_write: Boolean(payload.requires_workspace_write || payload.requiresWorkspaceWrite),
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetContinueWorkerQueue(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    if (!workerId) {
      throw new Error('worker_id is required');
    }
    return fleetApi(`/api/fleet/workers/${encodeURIComponent(workerId)}/queue/continue`, {
      method: 'POST',
      body: {
        reviewed_report_id: payload.reviewed_report_id || payload.reviewedReportId || null,
        source: payload.source || 'desktop',
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetReorderTasks(payload = {}) {
    const workerId = String(payload.worker_id || payload.workerId || '').trim();
    const taskIds = Array.isArray(payload.task_ids) ? payload.task_ids : (Array.isArray(payload.taskIds) ? payload.taskIds : []);
    if (!workerId || !taskIds.length) {
      throw new Error('worker_id and task_ids are required');
    }
    return fleetApi('/api/fleet/tasks/reorder', {
      method: 'PUT',
      body: {
        worker_id: workerId,
        task_ids: taskIds,
      },
    });
  }

  async function fleetRedirectTask(payload = {}) {
    const taskId = String(payload.task_id || payload.taskId || '').trim();
    const direction = String(payload.direction || '').trim();
    if (!taskId || !direction) {
      throw new Error('task_id and direction are required');
    }
    return fleetApi(`/api/fleet/tasks/${encodeURIComponent(taskId)}/redirect`, {
      method: 'POST',
      body: {
        direction,
        source: payload.source || 'manager',
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetUpdateTaskStatus(payload = {}) {
    const taskId = String(payload.task_id || payload.taskId || '').trim();
    const status = String(payload.status || '').trim();
    if (!taskId || !status) {
      throw new Error('task_id and status are required');
    }
    return fleetApi(`/api/fleet/tasks/${encodeURIComponent(taskId)}/status`, {
      method: 'PUT',
      body: {
        status,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetCreateTaskReport(payload = {}) {
    const taskId = String(payload.task_id || payload.taskId || '').trim();
    if (!taskId) {
      throw new Error('task_id is required');
    }
    return fleetApi(`/api/fleet/tasks/${encodeURIComponent(taskId)}/report`, {
      method: 'POST',
      body: {
        status: payload.status || 'completed',
        summary: payload.summary || 'No summary provided.',
        evidence: Array.isArray(payload.evidence) ? payload.evidence : [],
        artifacts: Array.isArray(payload.artifacts) ? payload.artifacts : [],
        blockers: Array.isArray(payload.blockers) ? payload.blockers : [],
        confidence: payload.confidence || null,
        next_suggested_action: payload.next_suggested_action || payload.nextSuggestedAction || null,
        raw: payload.raw || {},
      },
    });
  }

  async function fleetSearchReports(payload = {}) {
    return fleetApi('/api/fleet/reports/search', {
      method: 'POST',
      body: {
        query: payload.query || null,
        worker: payload.worker || null,
        status: payload.status || null,
        limit: payload.limit || 20,
      },
    });
  }

  async function fleetUpsertWorkspaceBinding(payload = {}) {
    return fleetApi('/api/fleet/workspace-bindings', {
      method: 'PUT',
      body: {
        workspace_id: payload.workspace_id || payload.workspaceId,
        machine_id: payload.machine_id || payload.machineId,
        local_path: payload.local_path || payload.localPath,
        label: payload.label || null,
        status: payload.status || 'active',
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetRequestToolGrant(payload = {}) {
    return fleetApi('/api/fleet/tool-grants', {
      method: 'POST',
      body: {
        target_kind: payload.target_kind || payload.targetKind || 'worker',
        target_id: payload.target_id || payload.targetId,
        tool_pack_id: payload.tool_pack_id || payload.toolPackId,
        reason: payload.reason || '',
        task_id: payload.task_id || payload.taskId || null,
        requested_turns: payload.requested_turns || payload.requestedTurns || 10,
        requested_by: payload.requested_by || payload.requestedBy || null,
      },
    });
  }

  async function fleetDecideToolGrant(payload = {}) {
    const grantId = String(payload.grant_id || payload.grantId || '').trim();
    if (!grantId) {
      throw new Error('grant_id is required');
    }
    return fleetApi(`/api/fleet/tool-grants/${encodeURIComponent(grantId)}/decision`, {
      method: 'POST',
      body: {
        approved: Boolean(payload.approved),
        approved_turns: payload.approved_turns || payload.approvedTurns || null,
        approved_by: payload.approved_by || payload.approvedBy || null,
      },
    });
  }

  return {
    runtimeSecretOverlayEnvironment,
    runtimeSecretOverlayPreviews,
    sanitizeSetupValuesForLocal,
    rememberRuntimeSecretOverlay,
    remoteAuthStatus,
    remoteAuthListDesktops,
    remoteAuthLogin,
    remoteAuthGoogleLogin,
    remoteAuthRegister,
    remoteAuthVerifyOtp,
    remoteAuthResendOtp,
    remoteAuthLogout,
    remoteAuthCreatePairingToken,
    remoteAuthListSecrets,
    remoteAuthSaveSetupSecrets,
    remoteAuthSaveSecrets,
    remoteAuthApplyAccountData,
    remoteAuthDeleteSecret,
    remoteAuthDeleteAccountData,
    remoteAuthProfile,
    remoteAuthUpdateProfile,
    remoteAuthApplySetupSecrets,
    fleetSnapshot,
    fleetSetActiveIdentity,
    fleetSetIdentityActiveChat,
    fleetCreateLocalWorker,
    fleetCreateEnrollment,
    fleetRenameWorker,
    fleetResetWorker,
    fleetDeleteWorker,
    fleetStopWorker,
    fleetStopAll,
    fleetRequestWorkerPreview,
    fleetCreateGroup,
    fleetUpdateGroup,
    fleetDeleteGroup,
    fleetAssignTask,
    fleetAssignGroupTask,
    fleetContinueWorkerQueue,
    fleetReorderTasks,
    fleetRedirectTask,
    fleetUpdateTaskStatus,
    fleetCreateTaskReport,
    fleetSearchReports,
    fleetUpsertWorkspaceBinding,
    fleetRequestToolGrant,
    fleetDecideToolGrant,
  };
}

module.exports = {
  createRemoteControlServices,
};
