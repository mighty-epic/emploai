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

  const startHost = () => runBackendJson(['fleet-host-start'], { timeoutMs: 30_000 });

  const bootstrap = () => runBackendJson(
    ['yggdrasil-bootstrap', '--install', '--start', '--configure-default-peers'],
    { timeoutMs: 5 * 60_000 },
  );

  const createPairing = async (payload = {}) => {
    const displayName = cleanLabel(payload.displayName || payload.display_name, 'Paired computer');
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
    const deviceName = cleanLabel(payload.deviceName || payload.device_name, 'EmploAI computer');
    await bootstrap();
    return runBackendJson([
      'fleet-yggdrasil-join',
      pairingToken,
      '--device-name',
      deviceName,
    ], { timeoutMs: 60_000 });
  };

  const permissions = () => runBackendJson(['fleet-yggdrasil-permissions'], { timeoutMs: 15_000 });

  const setPermissions = (payload = {}) => runBackendJson([
    'fleet-yggdrasil-permissions',
    '--set-json',
    JSON.stringify(payload.permissions || {}),
  ], { timeoutMs: 15_000 });

  const decidePermissionRequest = (payload = {}) => {
    const requestId = String(payload.requestId || payload.request_id || '').trim();
    const decision = payload.approve ? 'approve' : 'deny';
    if (!requestId) throw new Error('requestId is required');
    return runBackendJson([
      'fleet-yggdrasil-permissions',
      '--request-id', requestId,
      '--decision', decision,
    ], { timeoutMs: 15_000 });
  };

  const activity = () => runBackendJson(['fleet-yggdrasil-activity'], { timeoutMs: 15_000 });

  const requestManager = (payload = {}) => {
    const requestKind = String(payload.requestKind || payload.request_kind || '').trim().toLowerCase();
    const message = String(payload.message || '').trim();
    if (!['question', 'approval', 'blocked'].includes(requestKind)) {
      throw new Error('requestKind must be question, approval, or blocked');
    }
    if (!message) throw new Error('message is required');
    const args = ['fleet-yggdrasil-request', '--kind', requestKind, '--message', message];
    const identityId = String(payload.identityId || payload.identity_id || '').trim();
    const identityLabel = cleanLabel(payload.identityLabel || payload.identity_label, '');
    if (identityId) args.push('--identity-id', identityId);
    if (identityLabel) args.push('--identity-label', identityLabel);
    return runBackendJson(args, { timeoutMs: 15_000 });
  };

  return { status, startHost, bootstrap, createPairing, join, permissions, setPermissions, decidePermissionRequest, activity, requestManager };
}

module.exports = {
  PAIRING_TOKEN_PREFIX,
  cleanPairingToken,
  createFleetYggdrasilServices,
};
