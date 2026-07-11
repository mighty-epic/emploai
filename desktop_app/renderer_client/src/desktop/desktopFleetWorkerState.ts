const UNAVAILABLE_FLEET_WORKER_STATES = new Set([
  'archived',
  'deleted',
  'disconnected',
  'error',
  'offline',
  'stopped',
]);

function normalizedWorkerState(worker: any) {
  return String(worker?.state || worker?.status || worker?.runtime_state || '').trim().toLowerCase();
}

export function fleetWorkerStatusLabel(worker: any, activeTask?: any) {
  const status = normalizedWorkerState(worker);
  const kind = String(worker?.kind || '').trim().toLowerCase();
  if (kind === 'local' && !activeTask && (!status || status === 'offline' || status === 'stale' || status === 'idle')) {
    return 'ready';
  }
  return status || 'unknown';
}

export function isFleetWorkerAvailable(worker: any) {
  const status = normalizedWorkerState(worker);
  const kind = String(worker?.kind || '').trim().toLowerCase();
  if (kind === 'local' && (status === 'offline' || status === 'stale' || status === 'idle' || !status)) {
    return true;
  }
  return !UNAVAILABLE_FLEET_WORKER_STATES.has(status);
}
