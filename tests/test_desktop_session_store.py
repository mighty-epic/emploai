import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_local_secret_store_encrypts_and_migrates(tmp_path):
    script_path = tmp_path / "session_store_check.js"
    runtime_home = tmp_path / "runtime"
    session_store_path = REPO_ROOT / "desktop_app" / "session_store.js"
    control_services_path = REPO_ROOT / "desktop_app" / "remote_control_services.js"
    script_path.write_text(
        """
const fs = require('fs');
const { createLocalSecretStore, ENCRYPTED_STORAGE_KIND } = require(process.argv[2]);
const { createRemoteControlServices } = require(process.argv[4]);

const runtimeHome = process.argv[3];
const secretToken = 'nvidia-secret';
const safeStorage = {
  isEncryptionAvailable() { return true; },
  encryptString(value) { return Buffer.from(`wrapped:${value}`, 'utf8'); },
  decryptString(buffer) {
    const value = Buffer.from(buffer).toString('utf8');
    if (!value.startsWith('wrapped:')) throw new Error('bad ciphertext');
    return value.slice('wrapped:'.length);
  },
};

const store = createLocalSecretStore({
  filename: 'local-runtime-secrets.json',
  resolveRuntimeHome: () => runtimeHome,
  safeStorage,
});
store.write({ secrets: { NVIDIA_API_KEY: secretToken } });
const encryptedText = fs.readFileSync(store.resolvePath(), 'utf8');
const encryptedRecord = JSON.parse(encryptedText);
if (encryptedRecord.storage !== ENCRYPTED_STORAGE_KIND) {
  throw new Error(`expected encrypted storage, got ${encryptedRecord.storage}`);
}
if (encryptedText.includes(secretToken)) {
  throw new Error('encrypted local secret file contains plaintext');
}
if (store.read().secrets.NVIDIA_API_KEY !== secretToken) {
  throw new Error('encrypted local secret did not round-trip');
}

fs.writeFileSync(
  store.resolvePath(),
  `${JSON.stringify({ secrets: { NVIDIA_API_KEY: secretToken } })}\n`,
  'utf8',
);
const migrated = store.read();
const migratedRecord = JSON.parse(fs.readFileSync(store.resolvePath(), 'utf8'));
if (migrated.secrets.NVIDIA_API_KEY !== secretToken || migratedRecord.storage !== ENCRYPTED_STORAGE_KIND) {
  throw new Error('legacy plaintext local secret was not migrated');
}

const services = createRemoteControlServices({
  net: { fetch() { throw new Error('network should not be used'); } },
  safeStorage,
  resolveRuntimeHome: () => runtimeHome,
  getBootstrapCache() { return {}; },
});
services.rememberRuntimeSecretOverlay({
  NVIDIA_API_KEY: secretToken,
  EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN: 'obsolete-cloud-token',
  IGNORED_SECRET: 'nope',
});
const overlay = JSON.parse(services.runtimeSecretOverlayEnvironment());
if (overlay.NVIDIA_API_KEY !== secretToken) {
  throw new Error('local provider key was not restored into the runtime overlay');
}
if (overlay.EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN || overlay.IGNORED_SECRET) {
  throw new Error('unsupported account-era secret was retained');
}
const previews = services.runtimeSecretOverlayPreviews();
if (previews.NVIDIA_API_KEY?.redacted_value !== 'nvidia...cret') {
  throw new Error(`unexpected local runtime secret preview: ${previews.NVIDIA_API_KEY?.redacted_value}`);
}

console.log(JSON.stringify({ ok: true, encryptedStorage: encryptedRecord.storage, overlay }));
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["node", str(script_path), str(session_store_path), str(runtime_home), str(control_services_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "EMPLOAI_CLOUD_BACKEND_ENABLED": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
