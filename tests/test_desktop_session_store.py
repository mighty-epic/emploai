import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_remote_session_store_encrypts_and_migrates(tmp_path):
    script_path = tmp_path / "session_store_check.js"
    runtime_home = tmp_path / "runtime"
    session_store_path = REPO_ROOT / "desktop_app" / "session_store.js"
    remote_control_services_path = REPO_ROOT / "desktop_app" / "remote_control_services.js"
    script_path.write_text(
        """
const fs = require('fs');
const path = require('path');
const { createRemoteAccountSessionStore, ENCRYPTED_STORAGE_KIND } = require(process.argv[2]);
const { createRemoteControlServices } = require(process.argv[4]);

const runtimeHome = process.argv[3];
const secretToken = 'secret-session-token';
const safeStorage = {
  isEncryptionAvailable() {
    return true;
  },
  encryptString(value) {
    return Buffer.from(`wrapped:${value}`, 'utf8');
  },
  decryptString(buffer) {
    const value = Buffer.from(buffer).toString('utf8');
    if (!value.startsWith('wrapped:')) {
      throw new Error('bad ciphertext');
    }
    return value.slice('wrapped:'.length);
  },
};

const store = createRemoteAccountSessionStore({
  resolveRuntimeHome: () => runtimeHome,
  safeStorage,
});

store.write({ apiBaseUrl: 'https://api.kraitos.app', sessionToken: secretToken });
const encryptedText = fs.readFileSync(store.resolvePath(), 'utf8');
const encryptedRecord = JSON.parse(encryptedText);
if (encryptedRecord.storage !== ENCRYPTED_STORAGE_KIND) {
  throw new Error(`expected encrypted storage, got ${encryptedRecord.storage}`);
}
if (encryptedText.includes(secretToken)) {
  throw new Error('encrypted session file contains the plaintext token');
}
if (store.read().sessionToken !== secretToken) {
  throw new Error('encrypted session did not round-trip');
}

fs.writeFileSync(
  store.resolvePath(),
  `${JSON.stringify({ apiBaseUrl: 'https://api.kraitos.app', sessionToken: secretToken })}\\n`,
  'utf8',
);
const migrated = store.read();
const migratedText = fs.readFileSync(store.resolvePath(), 'utf8');
const migratedRecord = JSON.parse(migratedText);
if (migrated.sessionToken !== secretToken) {
  throw new Error('legacy plaintext session did not read');
}
if (migratedRecord.storage !== ENCRYPTED_STORAGE_KIND) {
  throw new Error('legacy plaintext session was not migrated');
}
if (migratedText.includes(secretToken)) {
  throw new Error('migrated session file contains the plaintext token');
}

const fallbackStore = createRemoteAccountSessionStore({
  filename: 'fallback-session.json',
  resolveRuntimeHome: () => runtimeHome,
  safeStorage: { isEncryptionAvailable: () => false },
});
fallbackStore.write({ apiBaseUrl: 'https://api.kraitos.app', sessionToken: secretToken });
const fallbackRecord = JSON.parse(fs.readFileSync(fallbackStore.resolvePath(), 'utf8'));
if (fallbackRecord.storage !== 'plain_json_fallback') {
  throw new Error('fallback store should declare plaintext fallback storage');
}
if (fallbackStore.read().sessionToken !== secretToken) {
  throw new Error('fallback session did not round-trip');
}

store.write({
  apiBaseUrl: 'https://api.kraitos.app/',
  sessionToken: secretToken,
  user: { user_id: 77 },
  desktop: { desktop_id: 'desktop-abc' },
});
const encryptedSessionText = fs.readFileSync(store.resolvePath(), 'utf8');
if (encryptedSessionText.includes(secretToken) || encryptedSessionText.includes('desktop-abc')) {
  throw new Error('encrypted remote session leaked plaintext metadata or token');
}
const services = createRemoteControlServices({
  net: { fetch() { throw new Error('network should not be used'); } },
  shell: { openExternal() {} },
  safeStorage,
  resolveRuntimeHome: () => runtimeHome,
  saveSetup() {},
  getBootstrapCache() { return {}; },
});
const overlay = JSON.parse(services.runtimeSecretOverlayEnvironment());
if (overlay.EMPLOAI_REMOTE_CONTROL_BASE_URL !== 'https://api.kraitos.app') {
  throw new Error(`unexpected remote base URL overlay: ${overlay.EMPLOAI_REMOTE_CONTROL_BASE_URL}`);
}
if (overlay.EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN !== secretToken) {
  throw new Error('remote session token was not exposed to the backend overlay');
}
if (overlay.EMPLOAI_REMOTE_CONTROL_USER_ID !== '77') {
  throw new Error('remote user id was not exposed to the backend overlay');
}
if (overlay.EMPLOAI_REMOTE_CONTROL_DESKTOP_ID !== 'desktop-abc') {
  throw new Error('remote desktop id was not exposed to the backend overlay');
}

services.rememberRuntimeSecretOverlay({ NVIDIA_API_KEY: 'nvidia-secret', IGNORED_SECRET: 'nope' });
const localSecretPath = path.join(runtimeHome, 'local-runtime-secrets.json');
const localSecretText = fs.readFileSync(localSecretPath, 'utf8');
if (localSecretText.includes('nvidia-secret')) {
  throw new Error('encrypted local runtime secret file contains the plaintext NVIDIA key');
}
const reloadedServices = createRemoteControlServices({
  net: { fetch() { throw new Error('network should not be used'); } },
  shell: { openExternal() {} },
  safeStorage,
  resolveRuntimeHome: () => runtimeHome,
  saveSetup() {},
  getBootstrapCache() { return {}; },
});
const reloadedOverlay = JSON.parse(reloadedServices.runtimeSecretOverlayEnvironment());
if (reloadedOverlay.NVIDIA_API_KEY !== 'nvidia-secret') {
  throw new Error('local NVIDIA key was not restored into the backend overlay');
}
if (reloadedOverlay.IGNORED_SECRET) {
  throw new Error('unsupported local runtime secret was restored');
}
const runtimeSecretPreviews = reloadedServices.runtimeSecretOverlayPreviews();
if (runtimeSecretPreviews.NVIDIA_API_KEY?.redacted_value !== 'nvidia...cret') {
  throw new Error(`unexpected local runtime secret preview: ${runtimeSecretPreviews.NVIDIA_API_KEY?.redacted_value}`);
}
if (runtimeSecretPreviews.IGNORED_SECRET) {
  throw new Error('unsupported local runtime secret preview was exposed');
}

console.log(JSON.stringify({ ok: true, encryptedStorage: encryptedRecord.storage, overlay }));
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["node", str(script_path), str(session_store_path), str(runtime_home), str(remote_control_services_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
