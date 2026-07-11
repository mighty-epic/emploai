const fs = require('fs');
const path = require('path');

const ENCRYPTED_STORAGE_KIND = 'electron_safe_storage';
const UNAVAILABLE_STORAGE_KIND = 'secure_storage_unavailable';
const ENVELOPE_VERSION = 2;

function atomicWriteUtf8(filePath, text) {
  const directory = path.dirname(filePath);
  const temporaryPath = path.join(
    directory,
    `.${path.basename(filePath)}.${process.pid}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`,
  );
  fs.mkdirSync(directory, { recursive: true });
  let fileDescriptor = null;
  try {
    fileDescriptor = fs.openSync(temporaryPath, 'wx', 0o600);
    fs.writeFileSync(fileDescriptor, text, 'utf-8');
    fs.fsyncSync(fileDescriptor);
    fs.closeSync(fileDescriptor);
    fileDescriptor = null;
    fs.renameSync(temporaryPath, filePath);
    try {
      fs.chmodSync(filePath, 0o600);
    } catch (_error) {
      // Windows ACLs are inherited; chmod is best-effort here.
    }
  } finally {
    if (fileDescriptor !== null) {
      try {
        fs.closeSync(fileDescriptor);
      } catch (_error) {
        // Best-effort cleanup after a failed write.
      }
    }
    try {
      if (fs.existsSync(temporaryPath)) {
        fs.unlinkSync(temporaryPath);
      }
    } catch (_error) {
      // Best-effort cleanup after a failed rename.
    }
  }
}

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

  function resolveBackupPath() {
    return `${resolvePath()}.bak`;
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
      return { payload: encryptionAvailable() ? record.payload : null, legacy: true };
    }

    return { payload: encryptionAvailable() ? record : null, legacy: true };
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

    throw new Error('Secure credential storage is unavailable; refusing to persist plaintext secrets.');
  }

  function write(payload) {
    const filePath = resolvePath();
    const normalized = normalizePayload(payload);
    if (!normalized) {
      throw new Error('Remote account session payload must be an object.');
    }
    const encoded = encodePayload(normalized);
    const serialized = `${JSON.stringify(encoded, null, 2)}\n`;
    atomicWriteUtf8(filePath, serialized);
    atomicWriteUtf8(resolveBackupPath(), serialized);
    return normalized;
  }

  function read() {
    const filePath = resolvePath();
    try {
      const backupPath = resolveBackupPath();
      if (!fs.existsSync(filePath) && !fs.existsSync(backupPath)) {
        return null;
      }
      for (const candidate of [filePath, backupPath]) {
        try {
          if (!fs.existsSync(candidate)) {
            continue;
          }
          const record = JSON.parse(fs.readFileSync(candidate, 'utf-8'));
          const decoded = decodeEnvelope(record);
          const payload = normalizePayload(decoded.payload);
          if (!payload) {
            continue;
          }
          if (candidate === backupPath || (decoded.legacy && encryptionAvailable())) {
            write(payload);
          }
          return payload;
        } catch (_error) {
          // Try the durable backup before treating the session as unavailable.
        }
      }
      return null;
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
      const backupPath = resolveBackupPath();
      if (fs.existsSync(backupPath)) {
        fs.unlinkSync(backupPath);
      }
    } catch (_error) {
      // no-op
    }
  }

  function storageKind() {
    return encryptionAvailable() ? ENCRYPTED_STORAGE_KIND : UNAVAILABLE_STORAGE_KIND;
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
  UNAVAILABLE_STORAGE_KIND,
};
