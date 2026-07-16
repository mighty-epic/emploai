const { createLocalSecretStore } = require('./session_store');

function createRemoteControlServices({ net, safeStorage, resolveRuntimeHome, getBootstrapCache }) {
  if (!net || !safeStorage || typeof resolveRuntimeHome !== 'function' || typeof getBootstrapCache !== 'function') {
    throw new Error('Local control services require Electron networking, runtime path, and bootstrap cache access.');
  }
  const localRuntimeSecretsFilename = 'local-runtime-secrets.json';
  const defaultRemoteControlBaseUrl = 'http://127.0.0.1';
  const remoteControlRequestTimeoutMs = 30000;
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
  const runtimeOverlayFields = new Set(localRuntimeSetupSecretFields);
  const localSetupSecretFields = new Set([
    ...localRuntimeSetupSecretFields,
    'GEMINI_API_KEY',
    'EMPLOAI_REMOTE_CONTROL_PASSWORD',
    'EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN',
    'GMAIL_LOGIN_EMAIL',
    'GMAIL_LOGIN_PASSWORD',
    'GMAIL_EMAIL',
    'GMAIL_PASSWORD',
  ]);

  const localRuntimeSecretStore = createLocalSecretStore({
    filename: localRuntimeSecretsFilename,
    resolveRuntimeHome,
    safeStorage,
  });
  let runtimeSecretOverlay = readLocalRuntimeSecretOverlay();

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
    const candidate = String(value || defaultRemoteControlBaseUrl).trim().replace(/\/+$/, '') || defaultRemoteControlBaseUrl;
    const parsed = new URL(candidate);
    const hostname = String(parsed.hostname || '').replace(/^\[|\]$/g, '').toLowerCase();
    if (!['127.0.0.1', 'localhost', '::1'].includes(hostname)) {
      throw new Error('The desktop control service only permits the local EmploAI backend.');
    }
    return candidate;
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

  function runtimeSecretOverlayEnvironment() {
    const values = {};
    for (const [key, rawValue] of Object.entries(runtimeSecretOverlay || {})) {
      const cleanKey = String(key || '').trim();
      const value = String(rawValue || '').trim();
      if (cleanKey && value && runtimeOverlayFields.has(cleanKey)) {
        values[cleanKey] = value;
      }
    }
    return Object.keys(values).length ? JSON.stringify(values) : '';
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
    return localAppApi(pathname, options);
  }

  async function fleetSnapshot() {
    return fleetApi('/api/fleet/snapshot');
  }

  async function fleetDelegateToComputer(payload = {}) {
    const desktopId = String(payload.desktop_id || payload.desktopId || '').trim();
    const prompt = String(payload.prompt || '').trim();
    if (!desktopId || !prompt) throw new Error('desktop_id and prompt are required');
    return fleetApi(`/api/fleet/desktops/${encodeURIComponent(desktopId)}/delegations`, {
      method: 'POST',
      body: {
        prompt,
        target_kind: payload.target_kind || payload.targetKind || 'manager',
        target_selector: payload.target_selector || payload.targetSelector || null,
        metadata: payload.metadata || {},
      },
    });
  }

  async function fleetCreateWorkerOnComputer(payload = {}) {
    const desktopId = String(payload.desktop_id || payload.desktopId || '').trim();
    const displayName = String(payload.display_name || payload.displayName || '').trim();
    if (!desktopId || !displayName) throw new Error('desktop_id and display_name are required');
    return fleetApi(`/api/fleet/desktops/${encodeURIComponent(desktopId)}/workers`, {
      method: 'POST',
      body: { display_name: displayName },
    });
  }

  async function fleetRequestComputerPermissions(payload = {}) {
    const desktopId = String(payload.desktop_id || payload.desktopId || '').trim();
    if (!desktopId) throw new Error('desktop_id is required');
    return fleetApi(`/api/fleet/desktops/${encodeURIComponent(desktopId)}/permissions/request`, {
      method: 'POST',
      body: {
        permissions: payload.permissions || {},
        reason: payload.reason || null,
      },
    });
  }

  async function fleetDecideUpstreamRequest(payload = {}) {
    const desktopId = String(payload.desktop_id || payload.desktopId || '').trim();
    const requestId = String(payload.request_id || payload.requestId || '').trim();
    const decision = String(payload.decision || '').trim().toLowerCase();
    if (!desktopId || !requestId) throw new Error('desktop_id and request_id are required');
    if (!['approved', 'denied', 'replied'].includes(decision)) throw new Error('Unsupported request decision');
    return fleetApi(`/api/fleet/desktops/${encodeURIComponent(desktopId)}/requests/${encodeURIComponent(requestId)}/decision`, {
      method: 'POST',
      body: { decision, response: payload.response || null },
    });
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

  async function fleetRequestComputerPreview(payload = {}) {
    const desktopId = String(payload.desktop_id || payload.desktopId || '').trim();
    if (!desktopId) {
      throw new Error('desktop_id is required');
    }
    return fleetApi(`/api/fleet/desktops/${encodeURIComponent(desktopId)}/preview`, {
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
    fleetSnapshot,
    fleetDelegateToComputer,
    fleetCreateWorkerOnComputer,
    fleetRequestComputerPermissions,
    fleetDecideUpstreamRequest,
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
    fleetRequestComputerPreview,
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
