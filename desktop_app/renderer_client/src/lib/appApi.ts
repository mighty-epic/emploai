import { requestJson } from '../../lib/appHttp';

function isTransientSessionCreateError(error: unknown) {
  const message = error instanceof Error
    ? error.message.toLowerCase()
    : String(error).toLowerCase();
  return (
    message.includes('failed to fetch')
    || message.includes('network request failed')
    || message.includes('load failed')
    || message.includes('timed out')
  );
}

function wait(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
import type { AppProfile, RemoteUser, RemoteDesktop, RemoteMobile, RemoteAuthLoginResult, RemoteAuthOtpChallengeResult, RemoteGoogleAuthStartResult, RemoteGoogleAuthPollResult, RemoteAccountCloudProfile, RemoteAccountProfile, RemoteAccountCloudProfileResult, RemoteAccountSecretItem, RemoteAccountSecretsListResult, RemoteAccountSecretsRevealResult, RemoteAuthLogoutResult, RemoteAccountDataDeleteResult, RemotePairStartResult, RemotePairCompleteResult, SessionSummary, SessionMessage, SessionTimelineEvent, SessionDetail, FleetIdentity, FleetWorker, FleetTask, FleetReport, FleetGroup, FleetToolGrant, FleetWorkspaceBinding, FleetSnapshot, ArtifactSummary, ArtifactDetail, DeleteSessionResult, SessionSearchResult, ScheduledJob, JobCreatePayload, CronFeedItem, AutomationEventRun, ProcessWait, PlannerContract, RecoveryArchiveItem, RecoveryListResponse, PendingConfirmation, ConfirmationCreatePayload, WorkspaceRestoreResponse, ModelProviderGroup, AgentHistoryItem, PendingFile, UploadResponse, ContextCompaction, ContextUsage, TaskBoardSubGoal, TaskBoard, HeartbeatStatus, MemorySummary, AnalyticsSummary, SecuritySummary, ConfigEntry, AgentOverview, TelegramBotConfig, RuntimeWorkerStatus, RuntimeOrchestratorStatus, WorkspaceGitState, SidebarProjectState, SidebarSessionState, SidebarState, SidebarStateResult, VoiceRuntimeStatus, TaskBoardArmResult, AgentConfigurePayload, ToolPackUpdatePayload, SessionBotAssignmentPayload, SessionHeadlessEligibilityPayload, SessionSecurityPermissionPayload, HeadlessConfigurePayload, AgentAction, BridgeStatus, SkillSummary, SkillDetail, SkillLearnResult, SkillValidation, SubAgentTask, SubAgentStatus, MemorySearchResult, MemoryOperation, MemoryOperationResult, MemoryFact } from './appApiTypes';
export type { AppProfile, RemoteUser, RemoteDesktop, RemoteMobile, RemoteAuthLoginResult, RemoteAuthOtpChallengeResult, RemoteGoogleAuthStartResult, RemoteGoogleAuthPollResult, RemoteAccountCloudProfile, RemoteAccountProfile, RemoteAccountCloudProfileResult, RemoteAccountSecretItem, RemoteAccountSecretsListResult, RemoteAccountSecretsRevealResult, RemoteAuthLogoutResult, RemoteAccountDataDeleteResult, RemotePairStartResult, RemotePairCompleteResult, SessionSummary, SessionMessage, SessionTimelineEvent, SessionDetail, FleetIdentity, FleetWorker, FleetTask, FleetReport, FleetGroup, FleetToolGrant, FleetWorkspaceBinding, FleetSnapshot, ArtifactSummary, ArtifactDetail, DeleteSessionResult, SessionSearchResult, ScheduledJob, JobCreatePayload, CronFeedItem, AutomationEventRun, ProcessWait, PlannerContract, RecoveryArchiveItem, RecoveryListResponse, PendingConfirmation, ConfirmationCreatePayload, WorkspaceRestoreResponse, ModelProviderGroup, AgentHistoryItem, PendingFile, UploadResponse, ContextCompaction, ContextUsage, TaskBoardSubGoal, TaskBoard, HeartbeatStatus, MemorySummary, AnalyticsSummary, SecuritySummary, ConfigEntry, AgentOverview, TelegramBotConfig, RuntimeWorkerStatus, RuntimeOrchestratorStatus, WorkspaceGitState, SidebarProjectState, SidebarSessionState, SidebarState, SidebarStateResult, VoiceRuntimeStatus, TaskBoardArmResult, AgentConfigurePayload, ToolPackUpdatePayload, SessionBotAssignmentPayload, SessionHeadlessEligibilityPayload, SessionSecurityPermissionPayload, HeadlessConfigurePayload, AgentAction, BridgeStatus, SkillSummary, SkillDetail, SkillLearnResult, SkillValidation, SubAgentTask, SubAgentStatus, MemorySearchResult, MemoryOperation, MemoryOperationResult, MemoryFact } from './appApiTypes';


function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

function confirmationHeaders(confirmationId?: string | null): Record<string, string> {
  return confirmationId ? { 'X-EmploAI-Confirmation-Id': confirmationId } : {};
}

export async function fetchProfile(apiBaseUrl: string, token: string) {
  return requestJson<AppProfile>({
    scope: 'profile.me',
    url: `${apiBaseUrl}/api/app/me`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchFleetSnapshot(apiBaseUrl: string, token: string) {
  return requestJson<FleetSnapshot>({
    scope: 'fleet.snapshot',
    url: `${apiBaseUrl}/api/fleet/snapshot`,
    init: { headers: authHeaders(token) },
  });
}

export async function setFleetActiveIdentity(
  apiBaseUrl: string,
  token: string,
  identityId: string,
  selectedChatId?: string | null,
  source = 'mobile',
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.identity.active',
    url: `${apiBaseUrl}/api/fleet/active-identity`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        identity_id: identityId,
        selected_chat_id: selectedChatId || null,
        source,
      }),
    },
  });
}

export async function setFleetIdentityActiveChat(
  apiBaseUrl: string,
  token: string,
  identityId: string,
  chatId?: string | null,
  source = 'mobile',
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.identity.chat',
    url: `${apiBaseUrl}/api/fleet/identities/${encodeURIComponent(identityId)}/active-chat`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId || null, source }),
    },
  });
}

export async function createFleetLocalWorker(
  apiBaseUrl: string,
  token: string,
  displayName?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetWorker>({
    scope: 'fleet.worker.create_local',
    url: `${apiBaseUrl}/api/fleet/workers/local`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName || null, metadata: metadata || {} }),
    },
  });
}

export async function createFleetEnrollment(
  apiBaseUrl: string,
  token: string,
  displayName?: string | null,
  expiresInSeconds?: number | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<{ enrollment_id: string; enrollment_token: string; expires_in_seconds: number; display_name?: string | null }>({
    scope: 'fleet.enrollment.create',
    url: `${apiBaseUrl}/api/fleet/enrollments`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: displayName || null,
        expires_in_seconds: expiresInSeconds || null,
        metadata: metadata || {},
      }),
    },
  });
}

export async function renameFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  displayName: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetWorker>({
    scope: 'fleet.worker.rename',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName, metadata: metadata || {} }),
    },
  });
}

export async function resetFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  reason?: string | null,
  metadata?: Record<string, unknown>,
  confirmationId?: string | null,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.reset',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/reset`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || null, metadata: metadata || {} }),
    },
  });
}

export async function deleteFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  wipeState = true,
  confirmationId?: string | null,
) {
  const suffix = `?wipe_state=${wipeState ? 'true' : 'false'}`;
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.delete',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}${suffix}`,
    init: { method: 'DELETE', headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) } },
  });
}

export async function stopFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  reason?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.stop',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/stop`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || null, metadata: metadata || {} }),
    },
  });
}

export async function stopAllFleetWorkers(
  apiBaseUrl: string,
  token: string,
  reason?: string | null,
  metadata?: Record<string, unknown>,
  confirmationId?: string | null,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.stop_all',
    url: `${apiBaseUrl}/api/fleet/stop-all`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || null, metadata: metadata || {} }),
    },
  });
}

export async function requestFleetWorkerPreview(apiBaseUrl: string, token: string, workerId: string) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.preview',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/preview`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    },
  });
}

export async function assignFleetWorkerTask(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  prompt: string,
  metadata?: Record<string, unknown>,
  options?: { target_session_id?: string | null; target_mode?: string | null; workspace_id?: string | null; requires_workspace_write?: boolean },
) {
  return requestJson<FleetTask>({
    scope: 'fleet.task.assign',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/tasks`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        source: 'mobile',
        target_session_id: options?.target_session_id || null,
        target_mode: options?.target_mode || 'auto',
        metadata: metadata || {},
        workspace_id: options?.workspace_id || null,
        requires_workspace_write: Boolean(options?.requires_workspace_write),
      }),
    },
  });
}

export async function createFleetGroup(
  apiBaseUrl: string,
  token: string,
  displayName: string,
  workerIds: string[] = [],
  description?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetGroup>({
    scope: 'fleet.group.create',
    url: `${apiBaseUrl}/api/fleet/groups`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: displayName,
        description: description || null,
        worker_ids: workerIds,
        metadata: metadata || {},
      }),
    },
  });
}

export async function updateFleetGroup(
  apiBaseUrl: string,
  token: string,
  groupId: string,
  payload: { display_name: string; description?: string | null; worker_ids?: string[]; metadata?: Record<string, unknown> },
) {
  return requestJson<FleetGroup>({
    scope: 'fleet.group.update',
    url: `${apiBaseUrl}/api/fleet/groups/${encodeURIComponent(groupId)}`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: payload.display_name,
        description: payload.description || null,
        worker_ids: payload.worker_ids || [],
        metadata: payload.metadata || {},
      }),
    },
  });
}

export async function deleteFleetGroup(apiBaseUrl: string, token: string, groupId: string, confirmationId?: string | null) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.group.delete',
    url: `${apiBaseUrl}/api/fleet/groups/${encodeURIComponent(groupId)}`,
    init: { method: 'DELETE', headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) } },
  });
}

export async function assignFleetGroupTask(
  apiBaseUrl: string,
  token: string,
  groupId: string,
  prompt: string,
  metadata?: Record<string, unknown>,
  options?: { target_session_id?: string | null; target_mode?: string | null; workspace_id?: string | null; requires_workspace_write?: boolean },
  confirmationId?: string | null,
) {
  return requestJson<FleetTask[]>({
    scope: 'fleet.group.task.assign',
    url: `${apiBaseUrl}/api/fleet/groups/${encodeURIComponent(groupId)}/tasks`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({
        prompt,
        source: 'mobile',
        target_session_id: options?.target_session_id || null,
        target_mode: options?.target_mode || 'auto',
        metadata: metadata || {},
        workspace_id: options?.workspace_id || null,
        requires_workspace_write: Boolean(options?.requires_workspace_write),
      }),
    },
  });
}

export async function continueFleetWorkerQueue(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  reviewedReportId?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.queue.continue',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/queue/continue`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reviewed_report_id: reviewedReportId || null,
        source: 'mobile',
        metadata: metadata || {},
      }),
    },
  });
}

export async function reorderFleetTasks(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  taskIds: string[],
) {
  return requestJson<FleetTask[]>({
    scope: 'fleet.tasks.reorder',
    url: `${apiBaseUrl}/api/fleet/tasks/reorder`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ worker_id: workerId, task_ids: taskIds }),
    },
  });
}

export async function redirectFleetTask(
  apiBaseUrl: string,
  token: string,
  taskId: string,
  direction: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetTask>({
    scope: 'fleet.task.redirect',
    url: `${apiBaseUrl}/api/fleet/tasks/${encodeURIComponent(taskId)}/redirect`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ direction, source: 'mobile', metadata: metadata || {} }),
    },
  });
}

export async function updateFleetTaskStatus(
  apiBaseUrl: string,
  token: string,
  taskId: string,
  status: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetTask>({
    scope: 'fleet.task.status',
    url: `${apiBaseUrl}/api/fleet/tasks/${encodeURIComponent(taskId)}/status`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, metadata: metadata || {} }),
    },
  });
}

export async function decideFleetToolGrant(
  apiBaseUrl: string,
  token: string,
  grantId: string,
  approved: boolean,
  approvedTurns?: number | null,
) {
  return requestJson<FleetToolGrant>({
    scope: 'fleet.tool_grant.decide',
    url: `${apiBaseUrl}/api/fleet/tool-grants/${encodeURIComponent(grantId)}/decision`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approved,
        approved_turns: approvedTurns || null,
        approved_by: 'mobile',
      }),
    },
  });
}

export async function searchFleetReports(
  apiBaseUrl: string,
  token: string,
  payload: { query?: string | null; worker?: string | null; status?: string | null; limit?: number },
) {
  return requestJson<{ reports: FleetReport[]; count: number }>({
    scope: 'fleet.reports.search',
    url: `${apiBaseUrl}/api/fleet/reports/search`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: payload.query || null,
        worker: payload.worker || null,
        status: payload.status || null,
        limit: payload.limit || 20,
      }),
    },
  });
}

export async function fetchSessions(apiBaseUrl: string, token: string) {
  return requestJson<SessionSummary[]>({
    scope: 'sessions.list',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionDetail(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.detail',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionArtifacts(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<ArtifactSummary[]>({
    scope: 'sessions.artifacts.list',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/artifacts`,
    init: { headers: authHeaders(token) },
  });
}

export async function uploadAppAttachment(
  apiBaseUrl: string,
  token: string,
  file: Blob,
  options?: { filename?: string | null; sessionId?: string | null },
) {
  const form = new FormData();
  const filename = String(options?.filename || (file as { name?: string }).name || 'upload').trim() || 'upload';
  form.append('file', file, filename);
  const sessionId = String(options?.sessionId || '').trim();
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return requestJson<UploadResponse>({
    scope: 'chat.upload',
    url: `${apiBaseUrl}/api/app/upload${query}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
      body: form,
    },
    timeoutMs: 60000,
  });
}

export async function fetchSessionArtifactDetail(apiBaseUrl: string, token: string, sessionId: string, artifactId: string) {
  return requestJson<ArtifactDetail>({
    scope: 'sessions.artifacts.detail',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(artifactId)}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionArtifactBlob(apiBaseUrl: string, token: string, sessionId: string, artifactId: string) {
  const response = await fetch(
    `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
    { headers: authHeaders(token) },
  );
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `Artifact download failed (${response.status})`);
  }
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] || `${artifactId}.bin`,
    mimeType: response.headers.get('content-type') || 'application/octet-stream',
  };
}

export async function searchSessions(
  apiBaseUrl: string,
  token: string,
  query: string,
  limit = 40,
) {
  return requestJson<{ results: SessionSearchResult[] }>({
    scope: 'sessions.search',
    url: `${apiBaseUrl}/api/app/sessions/search`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query, limit }),
    },
  });
}

export async function appendSessionTimelineEvent(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
  payload: {
    kind: string;
    title: string;
    content: string;
    tone?: 'neutral' | 'accent' | 'warn' | 'error';
    channel?: 'telegram' | 'app' | 'system';
    source_format?: string;
    metadata?: Record<string, unknown>;
    source_client_id?: string;
  }
) {
  return requestJson<{ event: SessionTimelineEvent }>({
    scope: 'session-timeline-append',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/timeline`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
}

export async function createSession(
  apiBaseUrl: string,
  token: string,
  nameOrOptions?: string | {
    name?: string;
    workspace?: string;
    workspace_id?: string | null;
    workspace_binding_status?: string | null;
    telegram_bot_config_id?: string | null;
    enabled_tool_packs?: string[];
    security_permission_mode?: 'low' | 'standard' | 'full_permissions';
    headless_eligible?: boolean;
    fleet_identity_id?: string | null;
    fleet_identity_role?: string | null;
    fleet_worker_id?: string | null;
  },
  workspaceArg?: string,
) {
  const payload = typeof nameOrOptions === 'string'
    ? { name: nameOrOptions, workspace: workspaceArg }
    : {
        name: nameOrOptions?.name,
        workspace: nameOrOptions?.workspace,
        workspace_id: nameOrOptions?.workspace_id,
        workspace_binding_status: nameOrOptions?.workspace_binding_status,
        telegram_bot_config_id: nameOrOptions?.telegram_bot_config_id,
        enabled_tool_packs: nameOrOptions?.enabled_tool_packs,
        security_permission_mode: nameOrOptions?.security_permission_mode,
        headless_eligible: nameOrOptions?.headless_eligible,
        fleet_identity_id: nameOrOptions?.fleet_identity_id,
        fleet_identity_role: nameOrOptions?.fleet_identity_role,
        fleet_worker_id: nameOrOptions?.fleet_worker_id,
      };
  const request = () => requestJson<{ session: SessionDetail }>({
    scope: 'sessions.create',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
  try {
    return await request();
  } catch (error) {
    if (!isTransientSessionCreateError(error)) {
      throw error;
    }
    await wait(900);
    return request();
  }
}

export async function activateSession(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.activate',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}/activate`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function deleteSession(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<DeleteSessionResult>({
    scope: 'sessions.delete',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}`,
    init: {
      method: 'DELETE',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchJobs(apiBaseUrl: string, token: string) {
  return requestJson<ScheduledJob[]>({
    scope: 'automations.list',
    url: `${apiBaseUrl}/api/app/automations`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchCronFeed(apiBaseUrl: string, token: string) {
  return requestJson<CronFeedItem[]>({
    scope: 'events.feed',
    url: `${apiBaseUrl}/api/app/events`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAutomationEventRuns(apiBaseUrl: string, token: string) {
  return requestJson<AutomationEventRun[]>({
    scope: 'automations.runs',
    url: `${apiBaseUrl}/api/app/events/runs`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchProcessWaits(apiBaseUrl: string, token: string) {
  return requestJson<ProcessWait[]>({
    scope: 'automations.process_waits',
    url: `${apiBaseUrl}/api/app/events/process-waits`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchPlannerContracts(apiBaseUrl: string, token: string) {
  return requestJson<PlannerContract[]>({
    scope: 'automations.planner_contracts',
    url: `${apiBaseUrl}/api/app/events/planner-contracts`,
    init: { headers: authHeaders(token) },
  });
}

export async function cancelAutomationEventRun(apiBaseUrl: string, token: string, eventRunId: string, reason?: string, confirmationId?: string | null) {
  return requestJson<AutomationEventRun>({
    scope: 'automations.runs.cancel',
    url: `${apiBaseUrl}/api/app/events/runs/${encodeURIComponent(eventRunId)}/cancel`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || 'Canceled by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function retryAutomationEventRun(apiBaseUrl: string, token: string, eventRunId: string, reason?: string) {
  return requestJson<AutomationEventRun>({
    scope: 'automations.runs.retry',
    url: `${apiBaseUrl}/api/app/events/runs/${encodeURIComponent(eventRunId)}/retry`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || 'Retry requested by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function cancelProcessWait(apiBaseUrl: string, token: string, processWaitId: string, reason?: string, confirmationId?: string | null) {
  return requestJson<ProcessWait>({
    scope: 'automations.process_waits.cancel',
    url: `${apiBaseUrl}/api/app/events/process-waits/${encodeURIComponent(processWaitId)}/cancel`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || 'Canceled by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function stopProcessWait(apiBaseUrl: string, token: string, processWaitId: string, reason?: string, confirmationId?: string | null) {
  return requestJson<ProcessWait>({
    scope: 'automations.process_waits.stop',
    url: `${apiBaseUrl}/api/app/events/process-waits/${encodeURIComponent(processWaitId)}/stop`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || 'Stopped by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function setProcessWaitPersistent(apiBaseUrl: string, token: string, processWaitId: string, persistent: boolean, reason?: string) {
  return requestJson<ProcessWait>({
    scope: 'automations.process_waits.persistent',
    url: `${apiBaseUrl}/api/app/events/process-waits/${encodeURIComponent(processWaitId)}/persistent`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ persistent, reason }),
    },
    timeoutMs: 30000,
  });
}

export async function updatePlannerContractStatus(apiBaseUrl: string, token: string, contractId: string, status: string) {
  return requestJson<PlannerContract>({
    scope: 'automations.planner_contracts.status',
    url: `${apiBaseUrl}/api/app/events/planner-contracts/${encodeURIComponent(contractId)}/status`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchRecoveryItems(apiBaseUrl: string, token: string) {
  return requestJson<RecoveryListResponse>({
    scope: 'recovery.list',
    url: `${apiBaseUrl}/api/app/recovery`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchPendingConfirmations(apiBaseUrl: string, token: string) {
  return requestJson<{ items: PendingConfirmation[] }>({
    scope: 'confirmations.list',
    url: `${apiBaseUrl}/api/app/confirmations`,
    init: { headers: authHeaders(token) },
  });
}

export async function createPendingConfirmation(apiBaseUrl: string, token: string, payload: ConfirmationCreatePayload) {
  return requestJson<PendingConfirmation>({
    scope: 'confirmations.create',
    url: `${apiBaseUrl}/api/app/confirmations`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function approvePendingConfirmation(apiBaseUrl: string, token: string, confirmationId: string, decidedBySurface = 'app') {
  return requestJson<PendingConfirmation>({
    scope: 'confirmations.approve',
    url: `${apiBaseUrl}/api/app/confirmations/${encodeURIComponent(confirmationId)}/approve`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ decided_by_surface: decidedBySurface }),
    },
    timeoutMs: 30000,
  });
}

export async function denyPendingConfirmation(apiBaseUrl: string, token: string, confirmationId: string, decidedBySurface = 'app') {
  return requestJson<PendingConfirmation>({
    scope: 'confirmations.deny',
    url: `${apiBaseUrl}/api/app/confirmations/${encodeURIComponent(confirmationId)}/deny`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ decided_by_surface: decidedBySurface }),
    },
    timeoutMs: 30000,
  });
}

export async function restoreRecoveryItem(apiBaseUrl: string, token: string, archiveId: string) {
  return requestJson<{ ok: boolean; action: string; item?: RecoveryArchiveItem }>({
    scope: 'recovery.restore',
    url: `${apiBaseUrl}/api/app/recovery/${encodeURIComponent(archiveId)}/restore`,
    init: { method: 'POST', headers: authHeaders(token) },
    timeoutMs: 30000,
  });
}

export async function permanentlyDeleteRecoveryItem(apiBaseUrl: string, token: string, archiveId: string, confirmationId?: string | null) {
  return requestJson<{ ok: boolean; action: string; item?: RecoveryArchiveItem }>({
    scope: 'recovery.permanent_delete',
    url: `${apiBaseUrl}/api/app/recovery/${encodeURIComponent(archiveId)}`,
    init: {
      method: 'DELETE',
      headers: {
        ...authHeaders(token),
        ...(confirmationId ? { 'X-EmploAI-Confirmation-Id': confirmationId } : {}),
      },
    },
    timeoutMs: 30000,
  });
}

export async function restoreWorkspaceFiles(apiBaseUrl: string, token: string, payload: { workspace_id?: string | null; machine_id?: string | null; local_path?: string | null }) {
  return requestJson<WorkspaceRestoreResponse>({
    scope: 'recovery.workspace.restore',
    url: `${apiBaseUrl}/api/app/workspace/restore`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    timeoutMs: 60000,
  });
}

export async function createJob(apiBaseUrl: string, token: string, payload: JobCreatePayload) {
  return requestJson<ScheduledJob>({
    scope: 'automations.create',
    url: `${apiBaseUrl}/api/app/automations`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function acknowledgeAutomationEvent(apiBaseUrl: string, token: string, eventId: string) {
  return requestJson<CronFeedItem>({
    scope: 'automations.events.ack',
    url: `${apiBaseUrl}/api/app/events/${encodeURIComponent(eventId)}/ack`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchTelegramBotConfigs(apiBaseUrl: string, token: string) {
  return requestJson<TelegramBotConfig[]>({
    scope: 'telegram-bots.list',
    url: `${apiBaseUrl}/api/app/telegram-bots`,
    init: { headers: authHeaders(token) },
  });
}

export async function createTelegramBotConfig(apiBaseUrl: string, token: string, payload: { label: string; bot_token: string }) {
  return requestJson<TelegramBotConfig>({
    scope: 'telegram-bots.create',
    url: `${apiBaseUrl}/api/app/telegram-bots`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateTelegramBotConfig(apiBaseUrl: string, token: string, botConfigId: string, payload: { label?: string; bot_token?: string; is_default?: boolean }) {
  return requestJson<TelegramBotConfig>({
    scope: 'telegram-bots.update',
    url: `${apiBaseUrl}/api/app/telegram-bots/${encodeURIComponent(botConfigId)}`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function deleteTelegramBotConfig(apiBaseUrl: string, token: string, botConfigId: string) {
  return requestJson<{ ok: boolean; id: string }>({
    scope: 'telegram-bots.delete',
    url: `${apiBaseUrl}/api/app/telegram-bots/${encodeURIComponent(botConfigId)}`,
    init: {
      method: 'DELETE',
      headers: authHeaders(token),
    },
  });
}

export async function updateSessionToolPacks(apiBaseUrl: string, token: string, sessionId: string, payload: ToolPackUpdatePayload) {
  return requestJson<SessionDetail>({
    scope: 'sessions.toolpacks',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/tool-packs`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateSessionTelegramBotAssignment(apiBaseUrl: string, token: string, sessionId: string, payload: SessionBotAssignmentPayload) {
  return requestJson<SessionDetail>({
    scope: 'sessions.telegram-bot',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/telegram-bot`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateSessionHeadlessEligibility(apiBaseUrl: string, token: string, sessionId: string, payload: SessionHeadlessEligibilityPayload) {
  return requestJson<SessionDetail>({
    scope: 'sessions.headless-eligibility',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/headless-eligibility`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateSessionSecurityPermissionMode(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
  payload: SessionSecurityPermissionPayload,
  confirmationId?: string | null,
) {
  return requestJson<SessionDetail>({
    scope: 'sessions.security-permission-mode',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/security-permission-mode`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchRuntimeOrchestratorStatus(apiBaseUrl: string, token: string) {
  return requestJson<RuntimeOrchestratorStatus>({
    scope: 'runtime.orchestrator',
    url: `${apiBaseUrl}/api/app/runtime/orchestrator`,
    init: { headers: authHeaders(token) },
  });
}

export async function configureHeadlessRuntime(apiBaseUrl: string, token: string, payload: HeadlessConfigurePayload) {
  return requestJson<RuntimeOrchestratorStatus>({
    scope: 'runtime.headless.configure',
    url: `${apiBaseUrl}/api/app/runtime/headless`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchWorkspaceGitState(apiBaseUrl: string, token: string, path: string) {
  const params = new URLSearchParams();
  params.set('path', path);
  return requestJson<WorkspaceGitState>({
    scope: 'workspace.git.info',
    url: `${apiBaseUrl}/api/app/workspace/git?${params.toString()}`,
    init: { headers: authHeaders(token) },
  });
}

export async function checkoutWorkspaceGitBranch(apiBaseUrl: string, token: string, path: string, branch: string) {
  return requestJson<WorkspaceGitState>({
    scope: 'workspace.git.checkout',
    url: `${apiBaseUrl}/api/app/workspace/git/checkout`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, branch }),
    },
    timeoutMs: 30000,
  });
}

export async function actOnJob(apiBaseUrl: string, token: string, jobId: string, action: 'run' | 'enable' | 'disable' | 'delete', confirmationId?: string | null) {
  const method = action === 'delete' ? 'DELETE' : 'POST';
  const automationAction = action === 'enable' ? 'resume' : action === 'disable' ? 'pause' : action;
  const url = action === 'delete'
    ? `${apiBaseUrl}/api/app/automations/${jobId}`
    : `${apiBaseUrl}/api/app/automations/${jobId}/${automationAction}`;

  return requestJson({
    scope: `automations.${action}`,
    url,
    init: {
      method,
      headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) },
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentOverview(
  apiBaseUrl: string,
  token: string,
  params?: { sessionId?: string; historyCount?: number; analyticsDays?: number }
) {
  const query = new URLSearchParams();
  if (params?.sessionId) query.set('session_id', params.sessionId);
  if (params?.historyCount) query.set('history_count', String(params.historyCount));
  if (params?.analyticsDays) query.set('analytics_days', String(params.analyticsDays));

  return requestJson<AgentOverview>({
    scope: 'agent.overview',
    url: `${apiBaseUrl}/api/app/agent/overview${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchVoiceRuntimeStatus(apiBaseUrl: string, token: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.status',
    url: `${apiBaseUrl}/api/app/voice/status`,
    init: { headers: authHeaders(token) },
  });
}

export async function warmVoiceRuntime(apiBaseUrl: string, token: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.warm',
    url: `${apiBaseUrl}/api/app/voice/warm`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 120000,
  });
}

export async function configureVoiceTtsBackend(apiBaseUrl: string, token: string, backend: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.tts.configure',
    url: `${apiBaseUrl}/api/app/voice/tts`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ backend }),
    },
    timeoutMs: 120000,
  });
}

export async function configureVoiceSttBackend(apiBaseUrl: string, token: string, backend: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.stt.configure',
    url: `${apiBaseUrl}/api/app/voice/stt`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ backend }),
    },
    timeoutMs: 120000,
  });
}

export async function fetchTaskBoard(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<{ task_board?: TaskBoard | null }>({
    scope: 'agent.taskboard.get',
    url: `${apiBaseUrl}/api/app/agent/task-board${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function forceTaskBoardReassess(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.taskboard.reassess',
    url: `${apiBaseUrl}/api/app/agent/task-board/reassess${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function setTaskBoardArmedNextTurn(
  apiBaseUrl: string,
  token: string,
  armed: boolean,
  sessionId?: string,
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<TaskBoardArmResult>({
    scope: 'agent.taskboard.arm',
    url: `${apiBaseUrl}/api/app/agent/task-board/arm${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ armed }),
    },
    timeoutMs: 30000,
  });
}

export async function configureAgent(
  apiBaseUrl: string,
  token: string,
  payload: AgentConfigurePayload,
  sessionId?: string
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.configure',
    url: `${apiBaseUrl}/api/app/agent/configure${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function reloadProviderKeys(
  apiBaseUrl: string,
  token: string,
  values: Record<string, string | undefined>,
) {
  return requestJson<AgentAction>({
    scope: 'agent.provider_keys.reload',
    url: `${apiBaseUrl}/api/app/agent/provider-keys/reload`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ values }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchBridgeStatus(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<BridgeStatus>({
    scope: 'agent.bridge.status',
    url: `${apiBaseUrl}/api/app/agent/bridge-status${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAgentConfig(apiBaseUrl: string, token: string, key?: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (key) query.set('key', key);
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<{ items: ConfigEntry[] }>({
    scope: 'agent.config.list',
    url: `${apiBaseUrl}/api/app/agent/config${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function updateAgentConfig(
  apiBaseUrl: string,
  token: string,
  payload: { key: string; value: unknown },
  sessionId?: string
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<ConfigEntry>({
    scope: 'agent.config.update',
    url: `${apiBaseUrl}/api/app/agent/config${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function searchAgentMemory(apiBaseUrl: string, token: string, query: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<{ query: string; results: MemorySearchResult[] }>({
    scope: 'agent.memory.search',
    url: `${apiBaseUrl}/api/app/agent/memory/search${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    },
    timeoutMs: 30000,
  });
}

export async function appendAgentMemoryNote(apiBaseUrl: string, token: string, note: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.memory.note',
    url: `${apiBaseUrl}/api/app/agent/memory/note${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ note }),
    },
    timeoutMs: 30000,
  });
}

export async function applyAgentMemoryOperations(
  apiBaseUrl: string,
  token: string,
  operations: MemoryOperation[],
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<MemoryOperationResult>({
    scope: 'agent.memory.operations',
    url: `${apiBaseUrl}/api/app/agent/memory/operations${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ operations }),
    },
    timeoutMs: 30000,
  });
}

export async function addAgentMemoryFact(
  apiBaseUrl: string,
  token: string,
  payload: { content: string; category?: string; tags?: string[]; trust?: number },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<MemoryFact>({
    scope: 'agent.memory.facts.add',
    url: `${apiBaseUrl}/api/app/agent/memory/facts${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentMemoryFacts(
  apiBaseUrl: string,
  token: string,
  sessionId?: string,
  options?: { category?: string; limit?: number }
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (options?.category) params.set('category', options.category);
  if (options?.limit) params.set('limit', String(options.limit));

  return requestJson<{ items: MemoryFact[] }>({
    scope: 'agent.memory.facts.list',
    url: `${apiBaseUrl}/api/app/agent/memory/facts${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
    timeoutMs: 30000,
  });
}

export async function deleteAgentMemoryFact(
  apiBaseUrl: string,
  token: string,
  factId: number,
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.memory.facts.delete',
    url: `${apiBaseUrl}/api/app/agent/memory/facts/${encodeURIComponent(String(factId))}${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'DELETE',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function rateAgentMemoryFact(
  apiBaseUrl: string,
  token: string,
  payload: { fact_id: number; helpful: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<MemoryFact>({
    scope: 'agent.memory.facts.feedback',
    url: `${apiBaseUrl}/api/app/agent/memory/facts/feedback${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function clearAgentPendingFiles(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.files.clear',
    url: `${apiBaseUrl}/api/app/agent/files/clear${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function forgetLastAgentMessage(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.forget',
    url: `${apiBaseUrl}/api/app/agent/forget-last${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function resetAgentContext(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.reset',
    url: `${apiBaseUrl}/api/app/agent/reset${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function compactAgentContext(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.compact',
    url: `${apiBaseUrl}/api/app/agent/compact${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentSkills(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<{ items: SkillSummary[] }>({
    scope: 'agent.skills.list',
    url: `${apiBaseUrl}/api/app/agent/skills${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAgentSkillDetail(
  apiBaseUrl: string,
  token: string,
  name: string,
  sessionId?: string,
  options?: { includeResources?: boolean }
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (options?.includeResources) params.set('include_resources', 'true');

  return requestJson<SkillDetail>({
    scope: 'agent.skills.view',
    url: `${apiBaseUrl}/api/app/agent/skills/${encodeURIComponent(name)}${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
    timeoutMs: 30000,
  });
}

export async function learnAgentSkill(
  apiBaseUrl: string,
  token: string,
  payload: { name: string; description?: string | null; workflow?: string; activate?: boolean; overwrite?: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SkillLearnResult>({
    scope: 'agent.skills.learn',
    url: `${apiBaseUrl}/api/app/agent/skills/learn${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function activateAgentSkill(
  apiBaseUrl: string,
  token: string,
  payload: { name: string; active?: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.skills.activate',
    url: `${apiBaseUrl}/api/app/agent/skills/activate${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function validateAgentSkill(apiBaseUrl: string, token: string, name: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SkillValidation>({
    scope: 'agent.skills.validate',
    url: `${apiBaseUrl}/api/app/agent/skills/validate${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name, active: true }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchSubAgents(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SubAgentStatus>({
    scope: 'agent.subagents.list',
    url: `${apiBaseUrl}/api/app/agent/subagents${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function spawnSubAgent(
  apiBaseUrl: string,
  token: string,
  payload: { prompt: string; headless?: boolean; max_turns?: number },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.subagents.spawn',
    url: `${apiBaseUrl}/api/app/agent/subagents${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function controlAgentRun(
  apiBaseUrl: string,
  token: string,
  action: 'pause' | 'stop' | 'restart',
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: `agent.control.${action}`,
    url: `${apiBaseUrl}/api/app/agent/control/${action}${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function remoteRegisterAccount(
  apiBaseUrl: string,
  payload: {
    email: string;
    password: string;
    display_name?: string;
    actor_kind: 'mobile' | 'desktop';
    device_name?: string;
    device_platform?: string;
    device_key?: string;
    remember_me?: boolean;
  }
) {
  return requestJson<RemoteAuthOtpChallengeResult | RemoteAuthLoginResult>({
    scope: 'remote.auth.register',
    url: `${apiBaseUrl}/api/remote/auth/register`,
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function remoteLogin(
  apiBaseUrl: string,
  payload: {
    email: string;
    password: string;
    actor_kind: 'mobile' | 'desktop';
    device_name?: string;
    device_platform?: string;
    device_key?: string;
    remember_me?: boolean;
  }
) {
  return requestJson<RemoteAuthOtpChallengeResult | RemoteAuthLoginResult>({
    scope: 'remote.auth.login',
    url: `${apiBaseUrl}/api/remote/auth/login`,
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function remoteVerifyOtp(
  apiBaseUrl: string,
  payload: {
    challenge_id: string;
    code: string;
  }
) {
  return requestJson<RemoteAuthLoginResult>({
    scope: 'remote.auth.otp.verify',
    url: `${apiBaseUrl}/api/remote/auth/otp/verify`,
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function remoteResendOtp(
  apiBaseUrl: string,
  payload: {
    challenge_id: string;
  }
) {
  return requestJson<RemoteAuthOtpChallengeResult>({
    scope: 'remote.auth.otp.resend',
    url: `${apiBaseUrl}/api/remote/auth/otp/resend`,
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function remoteStartGoogleAuth(
  apiBaseUrl: string,
  payload: {
    actor_kind: 'mobile' | 'desktop';
    device_name?: string;
    device_platform?: string;
    device_key?: string;
    remember_me?: boolean;
  }
) {
  return requestJson<RemoteGoogleAuthStartResult>({
    scope: 'remote.auth.google.start',
    url: `${apiBaseUrl}/api/remote/auth/google/start`,
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function remotePollGoogleAuth(
  apiBaseUrl: string,
  payload: {
    request_id: string;
    poll_token: string;
  }
) {
  return requestJson<RemoteGoogleAuthPollResult>({
    scope: 'remote.auth.google.poll',
    url: `${apiBaseUrl}/api/remote/auth/google/poll`,
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function remoteLogout(apiBaseUrl: string, token: string) {
  return requestJson<RemoteAuthLogoutResult>({
    scope: 'remote.auth.logout',
    url: `${apiBaseUrl}/api/remote/auth/logout`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchRemoteAccountProfile(apiBaseUrl: string, token: string) {
  return requestJson<RemoteAccountProfile>({
    scope: 'remote.account.me',
    url: `${apiBaseUrl}/api/remote/account/me`,
    init: {
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchRemoteAccountCloudProfile(apiBaseUrl: string, token: string) {
  return requestJson<RemoteAccountCloudProfileResult>({
    scope: 'remote.account.profile.get',
    url: `${apiBaseUrl}/api/remote/account/profile`,
    init: {
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function updateRemoteAccountCloudProfile(
  apiBaseUrl: string,
  token: string,
  profile: RemoteAccountCloudProfile
) {
  return requestJson<RemoteAccountCloudProfileResult>({
    scope: 'remote.account.profile.put',
    url: `${apiBaseUrl}/api/remote/account/profile`,
    init: {
      method: 'PUT',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ profile }),
    },
    timeoutMs: 30000,
  });
}

export async function deleteRemoteAccountData(apiBaseUrl: string, token: string, confirmationId?: string | null) {
  return requestJson<RemoteAccountDataDeleteResult>({
    scope: 'remote.account.data.delete',
    url: `${apiBaseUrl}/api/remote/account/data`,
    init: {
      method: 'DELETE',
      headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) },
    },
    timeoutMs: 30000,
  });
}

export async function fetchRemoteAccountSecrets(apiBaseUrl: string, token: string, namespace = 'setup') {
  const params = new URLSearchParams();
  if (namespace) params.set('namespace', namespace);
  return requestJson<RemoteAccountSecretsListResult>({
    scope: 'remote.account.secrets.list',
    url: `${apiBaseUrl}/api/remote/account/secrets${params.size ? `?${params.toString()}` : ''}`,
    init: {
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function updateRemoteAccountSecrets(
  apiBaseUrl: string,
  token: string,
  payload: { namespace?: string; secrets: Record<string, string>; metadata?: Record<string, unknown> }
) {
  return requestJson<RemoteAccountSecretsListResult>({
    scope: 'remote.account.secrets.put',
    url: `${apiBaseUrl}/api/remote/account/secrets`,
    init: {
      method: 'PUT',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ namespace: payload.namespace || 'setup', secrets: payload.secrets, metadata: payload.metadata || {} }),
    },
    timeoutMs: 30000,
  });
}

export async function revealRemoteAccountSecrets(
  apiBaseUrl: string,
  token: string,
  payload: { namespace?: string; names?: string[]; manualReveal?: boolean }
) {
  const headers = {
    ...authHeaders(token),
    'Content-Type': 'application/json',
    ...(payload.manualReveal ? { 'X-EmploAI-Manual-Secret-Reveal': 'true' } : {}),
  };
  return requestJson<RemoteAccountSecretsRevealResult>({
    scope: 'remote.account.secrets.reveal',
    url: `${apiBaseUrl}/api/remote/account/secrets/reveal`,
    init: {
      method: 'POST',
      headers,
      body: JSON.stringify({ namespace: payload.namespace || 'setup', names: payload.names || [] }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchRemoteDesktops(apiBaseUrl: string, token: string) {
  return requestJson<RemoteDesktop[]>({
    scope: 'remote.desktops.list',
    url: `${apiBaseUrl}/api/remote/desktops`,
    init: {
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function remoteStartPairing(apiBaseUrl: string, token: string, desktopId?: string) {
  return requestJson<RemotePairStartResult>({
    scope: 'remote.pair.start',
    url: `${apiBaseUrl}/api/remote/pair/start`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ desktop_id: desktopId || null }),
    },
    timeoutMs: 30000,
  });
}

export async function remoteCompletePairing(apiBaseUrl: string, token: string, pairingToken: string) {
  return requestJson<RemotePairCompleteResult>({
    scope: 'remote.pair.complete',
    url: `${apiBaseUrl}/api/remote/pair/complete`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ pairing_token: pairingToken }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchSidebarState(apiBaseUrl: string, token: string) {
  return requestJson<SidebarStateResult>({
    scope: 'sidebar-state.get',
    url: `${apiBaseUrl}/api/app/sidebar-state`,
    init: {
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function updateSidebarState(apiBaseUrl: string, token: string, state: SidebarState) {
  return requestJson<SidebarStateResult>({
    scope: 'sidebar-state.put',
    url: `${apiBaseUrl}/api/app/sidebar-state`,
    init: {
      method: 'PUT',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ state }),
    },
    timeoutMs: 30000,
  });
}
