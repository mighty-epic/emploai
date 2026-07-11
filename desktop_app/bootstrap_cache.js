'use strict';

function nonEmptyText(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function mergeBootstrapCache(previous, payload, options = {}) {
  if (!payload || typeof payload !== 'object') {
    return payload;
  }

  const preserveConnectedSession = options.preserveConnectedSession !== false;
  const processDetected = Boolean(
    payload.runtimeProcessDetected || payload.runtimeStatus?.runtimeProcessDetected
  );
  const missingFreshSession = !nonEmptyText(payload.accessToken || payload.access_token);
  const hasPreviousSession = Boolean(
    previous
    && nonEmptyText(previous.apiBaseUrl || previous.api_base_url)
    && nonEmptyText(previous.accessToken || previous.access_token)
  );

  if (!preserveConnectedSession || !processDetected || !missingFreshSession || !hasPreviousSession) {
    return payload;
  }

  return {
    ...payload,
    apiBaseUrl: payload.apiBaseUrl || payload.api_base_url || previous.apiBaseUrl || previous.api_base_url,
    accessToken: previous.accessToken || previous.access_token,
    currentSessionId: payload.currentSessionId ?? previous.currentSessionId ?? null,
    deviceId: payload.deviceId ?? previous.deviceId ?? null,
  };
}

module.exports = { mergeBootstrapCache };
