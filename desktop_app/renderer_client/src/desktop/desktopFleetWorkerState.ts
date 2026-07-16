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

export function fleetReportSummary(report: any) {
  const structured = String(
    report?.provider_failure?.user_message
    || report?.failure?.user_message
    || report?.summary
    || '',
  ).trim();
  if (!structured) return 'No report yet';
  if (/usage_limit_reached|usage limit has been reached/i.test(structured)) {
    return 'This provider has reached its usage limit. Switch provider or wait for its reset before retrying.';
  }
  if (/authentication_failed|invalid api key|unauthori[sz]ed/i.test(structured)) {
    return 'The provider rejected its configured credentials. Review the provider settings before retrying.';
  }
  if (/quota_exceeded|billing_required/i.test(structured)) {
    return 'This provider needs quota or billing attention before it can continue.';
  }
  if (/^provider error:\s*[\[{]/i.test(structured)) {
    return 'The provider could not complete this task. Review the provider status before retrying.';
  }
  return structured;
}
