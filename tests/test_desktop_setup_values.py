from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_setup_value_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/setupValues.ts', 'utf8');
        const output = ts.transpileModule(source, {
          compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2020,
          },
        }).outputText;
        const moduleRef = { exports: {} };
        vm.runInNewContext(output, {
          module: moduleRef,
          exports: moduleRef.exports,
          require: (id) => {
            throw new Error(`Unexpected runtime require: ${id}`);
          },
          Object,
          Set,
          String,
        });
        const setup = moduleRef.exports;

        const normalized = setup.normalizeDesktopSetupValues({
          DEFAULT_WORKSPACE: 'C:/Work',
          EMPLOAI_REMOTE_DESKTOP_NAME: null,
        });
        assert.strictEqual(normalized.DEFAULT_WORKSPACE, 'C:/Work');
        assert.strictEqual(normalized.EMPLOAI_REMOTE_DESKTOP_NAME, '');
        assert.strictEqual(normalized.VOICE_DEFAULT_ENGINE, '');
        assert.strictEqual(setup.normalizeDesktopSetupValues(undefined).DEFAULT_WORKSPACE, '');

        const values = {
          DEFAULT_WORKSPACE: ' C:/Work ',
          PLANNER_MODEL: 'gpt-5.4',
          OPENAI_API_KEY: 'sk-test',
          NVIDIA_API_KEY: 'nvapi-test',
          EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN: 'remembered-token',
          EMPLOAI_REMOTE_CONTROL_PASSWORD: 'account-password',
          GMAIL_LOGIN_PASSWORD: 'gmail-password',
          VOICE_DEFAULT_ENGINE: 'kokoro',
        };

        const local = setup.sanitizeLocalSetupValues(values);
        assert.strictEqual(local.DEFAULT_WORKSPACE, ' C:/Work ');
        assert.strictEqual(local.PLANNER_MODEL, 'gpt-5.4');
        assert.strictEqual(local.OPENAI_API_KEY, undefined);
        assert.strictEqual(local.NVIDIA_API_KEY, undefined);
        assert.strictEqual(local.EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN, undefined);
        assert.strictEqual(local.EMPLOAI_REMOTE_CONTROL_PASSWORD, undefined);
        assert.strictEqual(local.GMAIL_LOGIN_PASSWORD, undefined);

        const runtimeSave = setup.setupValuesForRuntimeSave(values);
        assert.strictEqual(runtimeSave.OPENAI_API_KEY, 'sk-test');
        assert.strictEqual(runtimeSave.NVIDIA_API_KEY, 'nvapi-test');
        assert.strictEqual(runtimeSave.EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN, undefined);
        assert.strictEqual(runtimeSave.EMPLOAI_REMOTE_CONTROL_PASSWORD, undefined);
        assert.strictEqual(runtimeSave.GMAIL_LOGIN_PASSWORD, undefined);

        assert.strictEqual(setup.hasFilledSetupSecret(values), true);
        assert.strictEqual(setup.hasFilledRestartRequiredSetupSecret(values), false);
        assert.strictEqual(setup.hasFilledRestartRequiredSetupSecret({ TELEGRAM_BOT_TOKEN: '123:abc' }), true);
        assert.strictEqual(setup.hasFilledLiveApplySetupSecret(values), true);
        assert.strictEqual(setup.hasFilledRestartRequiredSetupSecret({ EMPLOAI_REMOTE_CONTROL_PASSWORD: 'secret' }), false);

        const changed = setup.changedSetupFields(
          { DEFAULT_WORKSPACE: ' C:/Work ', PLANNER_MODEL: 'gpt-5.4', VOICE_DEFAULT_ENGINE: 'kokoro' },
          { DEFAULT_WORKSPACE: 'C:/Work', PLANNER_MODEL: 'gpt-5.4', VOICE_DEFAULT_ENGINE: 'none' },
        );
        assert.strictEqual(JSON.stringify(changed), JSON.stringify(['VOICE_DEFAULT_ENGINE']));
        assert.strictEqual(setup.RESTART_REQUIRED_SETUP_FIELDS.has('EMPLOAI_REMOTE_CONTROL_BASE_URL'), true);
        assert.strictEqual(setup.LIVE_APPLY_SETUP_FIELDS.has('VOICE_DEFAULT_ENGINE'), true);
        assert.strictEqual(setup.SETUP_PROVIDER_SECRET_LABELS.NVIDIA_API_KEY, 'NVIDIA API key');
        assert.strictEqual(setup.SETUP_PROVIDER_SECRET_PROVIDER_KEYS.NVIDIA_API_KEY, 'nvidia');
        assert.strictEqual(setup.SETUP_PROVIDER_DISPLAY_LABELS.nvidia, 'NVIDIA NIM');

        const dedupedProviders = setup.configuredProviderChipLabels(
          ['OpenAI'],
          ['OPENAI_API_KEY', 'NVIDIA_API_KEY'],
        );
        assert.strictEqual(JSON.stringify(dedupedProviders), JSON.stringify(['OpenAI', 'NVIDIA NIM']));
        """
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=CLIENT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
