const loopbackHosts = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);

function localRuntimeBaseUrl(runtimeStatus, bootstrap) {
  const candidate = String(
    runtimeStatus?.api_base_url
    || runtimeStatus?.apiBaseUrl
    || bootstrap?.apiBaseUrl
    || '',
  ).trim();
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== 'http:' || !loopbackHosts.has(parsed.hostname.toLowerCase())) {
      return null;
    }
    return parsed.toString().replace(/\/+$/, '');
  } catch (_error) {
    return null;
  }
}

function createRuntimeStatusProbe({
  net,
  getRuntimeStatusCache,
  getBootstrapCache,
  timeoutMs = 1500,
}) {
  return async function probeCachedRuntimeStatus() {
    const cached = getRuntimeStatusCache();
    const apiBaseUrl = localRuntimeBaseUrl(cached, getBootstrapCache());
    if (!cached || !apiBaseUrl) return null;

    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = controller
      ? setTimeout(() => controller.abort(), Math.max(250, Number(timeoutMs) || 1500))
      : null;
    try {
      const response = await net.fetch(`${apiBaseUrl}/api/app/health?shallow=1`, {
        method: 'GET',
        ...(controller ? { signal: controller.signal } : {}),
      });
      if (!response.ok) throw new Error(`Runtime health returned ${response.status}`);
      const health = await response.json();
      const ok = Boolean(health?.ok);
      return {
        ...cached,
        ok,
        state: ok ? 'ready' : 'offline',
        api_base_url: apiBaseUrl,
        startup_state: health?.startup_state || cached.startup_state || null,
        readiness_scope: health?.readiness_scope || cached.readiness_scope || 'app_api',
        degraded: Boolean(health?.startup_error),
        detail: health?.startup_error || null,
        runtimeProcessDetected: ok,
      };
    } catch (_error) {
      return {
        ...cached,
        ok: false,
        state: 'offline',
        api_base_url: apiBaseUrl,
        degraded: false,
        detail: 'The local EmploAI backend is not responding.',
        runtimeProcessDetected: false,
      };
    } finally {
      if (timer) clearTimeout(timer);
    }
  };
}

module.exports = {
  createRuntimeStatusProbe,
  localRuntimeBaseUrl,
};
