export type FleetTaskStatusLike = {
  task_id?: string | null;
  worker_id?: string | null;
  status?: string | null;
  metadata?: Record<string, unknown> | null;
};

function normalizeStatus(value: string | null | undefined) {
  return String(value || '').trim().toLowerCase();
}

function titleForTarget(targetLabel: string | null | undefined) {
  return String(targetLabel || '').trim() || 'worker';
}

function workspaceBlockerMessage(task: FleetTaskStatusLike) {
  const metadata = task.metadata || {};
  const blocker = metadata.workspace_binding_blocker;
  if (!blocker || typeof blocker !== 'object') {
    return null;
  }

  const detail = blocker as Record<string, unknown>;
  const reason = String(detail.reason || '').trim();
  const workspaceId = String(detail.workspace_id || '').trim();
  const reasonText = reason === 'workspace_binding_missing_or_inactive'
    ? 'No active workspace binding is available for the requested write.'
    : (reason || 'Workspace binding restriction blocked dispatch.');
  return workspaceId ? `${reasonText} Workspace: ${workspaceId}.` : reasonText;
}

export function isBlockedFleetTask(task: FleetTaskStatusLike | null | undefined) {
  return normalizeStatus(task?.status) === 'blocked';
}

export function fleetTaskStatusMessage(task: FleetTaskStatusLike | null | undefined, targetLabel?: string | null) {
  const label = titleForTarget(targetLabel);
  const status = normalizeStatus(task?.status);
  const blocker = task ? workspaceBlockerMessage(task) : null;

  if (status === 'blocked') {
    return blocker ? `Task blocked for ${label}. ${blocker}` : `Task blocked for ${label}. Review the task restrictions before retrying.`;
  }
  if (status === 'running') {
    return `Task started for ${label}.`;
  }
  if (status === 'queued') {
    return `Task queued for ${label}.`;
  }
  if (status === 'completed') {
    return `Task already completed for ${label}.`;
  }
  if (status === 'failed') {
    return `Task failed for ${label}. Check the worker report.`;
  }
  if (status === 'stopped') {
    return `Task stopped for ${label}.`;
  }
  if (status === 'canceled' || status === 'cancelled') {
    return `Task canceled for ${label}.`;
  }
  return `Task accepted for ${label}.`;
}

export function fleetTaskBatchStatusMessage(tasks: FleetTaskStatusLike[] | null | undefined, targetLabel?: string | null) {
  const items = Array.isArray(tasks) ? tasks : [];
  const label = titleForTarget(targetLabel);
  if (!items.length) {
    return `No tasks were dispatched for ${label}.`;
  }

  const blocked = items.filter(isBlockedFleetTask);
  if (blocked.length) {
    const blocker = workspaceBlockerMessage(blocked[0]);
    return blocker
      ? `${blocked.length} of ${items.length} tasks blocked for ${label}. ${blocker}`
      : `${blocked.length} of ${items.length} tasks blocked for ${label}. Review fleet restrictions before retrying.`;
  }

  const running = items.filter((task) => normalizeStatus(task.status) === 'running').length;
  const queued = items.filter((task) => normalizeStatus(task.status) === 'queued').length;
  if (running && queued) {
    return `${running} tasks started and ${queued} queued for ${label}.`;
  }
  if (running) {
    return `${running} task${running === 1 ? '' : 's'} started for ${label}.`;
  }
  if (queued) {
    return `${queued} task${queued === 1 ? '' : 's'} queued for ${label}.`;
  }
  return `${items.length} task${items.length === 1 ? '' : 's'} accepted for ${label}.`;
}
