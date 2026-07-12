'use strict';

const PAIRING_TOKEN_PREFIX = 'emploai-yggdrasil-v1.';

function cleanLabel(value, fallback) {
  const cleaned = String(value || '').trim().replace(/[\r\n\t]+/g, ' ').slice(0, 120);
  return cleaned || fallback;
}

function cleanPairingToken(value) {
  const token = String(value || '').trim();
  if (!token.startsWith(PAIRING_TOKEN_PREFIX)) {
    throw new Error('Paste a complete EmploAI Yggdrasil Fleet pairing code.');
  }
  if (token.length > 16_384) {
    throw new Error('The Fleet pairing code is unexpectedly large.');
  }
  return token;
}

function createFleetYggdrasilServices({ runBackendJson }) {
  if (typeof runBackendJson !== 'function') {
    throw new TypeError('runBackendJson is required');
  }

  const status = () => runBackendJson(['yggdrasil-status'], { timeoutMs: 15_000 });

  const bootstrap = () => runBackendJson(
    ['yggdrasil-bootstrap', '--install', '--start', '--configure-default-peers'],
    { timeoutMs: 5 * 60_000 },
  );

  const createPairing = async (payload = {}) => {
    const displayName = cleanLabel(payload.displayName || payload.display_name, 'Yggdrasil worker');
    const requestedTtl = Number(payload.expiresInSeconds || payload.expires_in_seconds || 30 * 60);
    const expiresInSeconds = Math.min(24 * 60 * 60, Math.max(60, Math.trunc(requestedTtl || 30 * 60)));
    await bootstrap();
    return runBackendJson([
      'fleet-yggdrasil-pair',
      '--display-name',
      displayName,
      '--expires-in-seconds',
      String(expiresInSeconds),
      '--configure-manager-bind',
    ], { timeoutMs: 90_000 });
  };

  const join = async (payload = {}) => {
    const pairingToken = cleanPairingToken(payload.pairingToken || payload.pairing_token);
    const deviceName = cleanLabel(payload.deviceName || payload.device_name, 'EmploAI worker');
    await bootstrap();
    return runBackendJson([
      'fleet-yggdrasil-join',
      pairingToken,
      '--device-name',
      deviceName,
    ], { timeoutMs: 60_000 });
  };

  return { status, bootstrap, createPairing, join };
}

module.exports = {
  PAIRING_TOKEN_PREFIX,
  cleanPairingToken,
  createFleetYggdrasilServices,
};
