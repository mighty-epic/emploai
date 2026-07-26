const DEFAULT_CHECK_INTERVAL_MS = 5_000;
const DEFAULT_FAILURE_THRESHOLD = 2;
const DEFAULT_RETRY_DELAY_MS = 10_000;
const DEFAULT_MAX_RETRY_DELAY_MS = 60_000;

function createRuntimeRecoverySupervisor({
  getRuntimeStatus,
  startRuntime,
  canRecover = () => true,
  onStateChange = () => {},
  checkIntervalMs = DEFAULT_CHECK_INTERVAL_MS,
  failureThreshold = DEFAULT_FAILURE_THRESHOLD,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  maxRetryDelayMs = DEFAULT_MAX_RETRY_DELAY_MS,
  now = () => Date.now(),
  setIntervalFn = setInterval,
  clearIntervalFn = clearInterval,
}) {
  let active = false;
  let suspended = false;
  let timer = null;
  let checkPromise = null;
  let consecutiveFailures = 0;
  let nextRetryAt = 0;
  let currentRetryDelayMs = Math.max(1, Number(retryDelayMs) || DEFAULT_RETRY_DELAY_MS);

  const emit = (state, detail = {}) => {
    try {
      onStateChange({ state, ...detail });
    } catch (_error) {
      // Recovery must not be disabled by diagnostic listeners.
    }
  };

  const resetFailures = () => {
    consecutiveFailures = 0;
    nextRetryAt = 0;
    currentRetryDelayMs = Math.max(1, Number(retryDelayMs) || DEFAULT_RETRY_DELAY_MS);
  };

  const deferRetry = () => {
    nextRetryAt = now() + currentRetryDelayMs;
    currentRetryDelayMs = Math.min(
      Math.max(currentRetryDelayMs * 2, 1),
      Math.max(1, Number(maxRetryDelayMs) || DEFAULT_MAX_RETRY_DELAY_MS),
    );
  };

  const checkNow = async () => {
    if (!active || suspended || !canRecover()) {
      return { state: suspended ? 'suspended' : 'inactive' };
    }
    if (checkPromise) {
      return checkPromise;
    }

    checkPromise = (async () => {
      let status;
      try {
        status = await getRuntimeStatus();
      } catch (error) {
        status = { ok: false, detail: String(error?.message || error || 'Runtime status failed.') };
      }

      if (status?.ok) {
        if (consecutiveFailures > 0 || nextRetryAt > 0) {
          emit('healthy');
        }
        resetFailures();
        return { state: 'healthy', status };
      }

      consecutiveFailures += 1;
      if (consecutiveFailures < Math.max(1, Number(failureThreshold) || DEFAULT_FAILURE_THRESHOLD)) {
        emit('confirming', { consecutiveFailures, status });
        return { state: 'confirming', status };
      }
      if (now() < nextRetryAt) {
        return { state: 'backoff', status, nextRetryAt };
      }

      emit('recovering', { consecutiveFailures, status });
      try {
        const payload = await startRuntime();
        const recoveredStatus = payload?.runtimeStatus || null;
        if (recoveredStatus?.ok) {
          resetFailures();
          emit('recovered', { status: recoveredStatus });
          return { state: 'recovered', status: recoveredStatus, payload };
        }
        deferRetry();
        emit('recovery_failed', { status: recoveredStatus || status, nextRetryAt });
        return { state: 'recovery_failed', status: recoveredStatus || status, payload, nextRetryAt };
      } catch (error) {
        deferRetry();
        const detail = String(error?.message || error || 'Runtime recovery failed.');
        emit('recovery_failed', { detail, nextRetryAt });
        return { state: 'recovery_failed', detail, nextRetryAt };
      }
    })();

    try {
      return await checkPromise;
    } finally {
      checkPromise = null;
    }
  };

  const start = () => {
    if (active) return;
    active = true;
    timer = setIntervalFn(() => {
      void checkNow();
    }, Math.max(250, Number(checkIntervalMs) || DEFAULT_CHECK_INTERVAL_MS));
  };

  const stop = () => {
    active = false;
    if (timer) {
      clearIntervalFn(timer);
      timer = null;
    }
    resetFailures();
  };

  const suspend = () => {
    suspended = true;
    resetFailures();
    emit('suspended');
  };

  const resume = () => {
    suspended = false;
    resetFailures();
    emit('resumed');
  };

  return {
    start,
    stop,
    suspend,
    resume,
    checkNow,
    snapshot: () => ({
      active,
      suspended,
      checking: Boolean(checkPromise),
      consecutiveFailures,
      nextRetryAt,
    }),
  };
}

module.exports = {
  createRuntimeRecoverySupervisor,
};
