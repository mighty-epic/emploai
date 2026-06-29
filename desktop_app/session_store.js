const fs = require('fs');
const path = require('path');

const ENCRYPTED_STORAGE_KIND = 'electron_safe_storage';
const ENVELOPE_VERSION = 2;

function createRemoteAccountSessionStore({
  resolveRuntimeHome,
  safeStorage,
  filename = 'remote-account-session.json',
} = {}) {
  if (typeof resolveRuntimeHome !== 'function') {
    throw new Error('resolveRuntimeHome is required');
  }

  function resolvePath() {
    return path.join(resolveRuntimeHome(), filename);
  }

  function encryptionAvailable() {
    try {
      return Boolean(
        safeStorage &&
        typeof safeStorage.isEncryptionAvailable === 'function' &&
        safeStorage.isEncryptionAvailable() &&
        typeof safeStorage.encryptString === 'function' &&
        typeof safeStorage.decryptString === 'function'
      );
    } catch (_error) {
      return false;
    }
  }

  function normalizePayload(payload) {
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const normalized = { ...payload };
    if (normalized.rememberMe === undefined) {
      normalized.rememberMe = true;
    }
    return normalized;
  }

  function decodeEnvelope(record) {
    if (!record || typeof record !== 'object') {
      return { payload: null, legacy: false };
    }

    if (record.storage === ENCRYPTED_STORAGE_KIND && record.ciphertext) {
      if (!encryptionAvailable()) {
        return { payload: null, legacy: false };
      }
      const plaintext = safeStorage.decryptString(Buffer.from(String(record.ciphertext), 'base64'));
      return { payload: JSON.parse(plaintext), legacy: false };
    }

    if (record.storage === 'plain_json_fallback' && record.payload && typeof record.payload === 'object') {
      return { payload: record.payload, legacy: false };
    }

    return { payload: record, legacy: true };
  }

  function encodePayload(payload) {
    if (encryptionAvailable()) {
      const ciphertext = safeStorage.encryptString(JSON.stringify(payload)).toString('base64');
      return {
        version: ENVELOPE_VERSION,
        storage: ENCRYPTED_STORAGE_KIND,
        encoding: 'base64',
        ciphertext,
      };
    }

    return {
      version: ENVELOPE_VERSION,
      storage: 'plain_json_fallback',
      payload,
    };
  }

  function write(payload) {
    const filePath = resolvePath();
    const normalized = normalizePayload(payload);
    if (!normalized) {
      throw new Error('Remote account session payload must be an object.');
    }
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, `${JSON.stringify(encodePayload(normalized), null, 2)}\n`, 'utf-8');
    try {
      fs.chmodSync(filePath, 0o600);
    } catch (_error) {
      // Windows ACLs are inherited; chmod is best-effort here.
    }
    return normalized;
  }

  function read() {
    const filePath = resolvePath();
    try {
      if (!fs.existsSync(filePath)) {
        return null;
      }
      const record = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      const decoded = decodeEnvelope(record);
      const payload = normalizePayload(decoded.payload);
      if (payload && decoded.legacy && encryptionAvailable()) {
        try {
          write(payload);
        } catch (_error) {
          // Reading a legacy session should still succeed if migration fails.
        }
      }
      return payload;
    } catch (_error) {
      return null;
    }
  }

  function clear() {
    const filePath = resolvePath();
    try {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    } catch (_error) {
      // no-op
    }
  }

  function storageKind() {
    return encryptionAvailable() ? ENCRYPTED_STORAGE_KIND : 'plain_json_fallback';
  }

  return {
    clear,
    read,
    resolvePath,
    storageKind,
    write,
  };
}

module.exports = {
  createRemoteAccountSessionStore,
  ENCRYPTED_STORAGE_KIND,
};
