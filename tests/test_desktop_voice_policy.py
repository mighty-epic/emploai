from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_voice_policy_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopVoicePolicy.ts', 'utf8');
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
          String,
        });
        const voice = moduleRef.exports;

        assert.strictEqual(voice.VOICE_ENGINE_NONE, 'none');
        assert.strictEqual(voice.VOICE_ENGINE_ENGLISH, 'english_local');
        assert.strictEqual(voice.VOICE_ENGINE_HEBREW, 'hebrew_local');
        assert.strictEqual(voice.ALWAYS_ON_VOICE_AUTO_SEND, false);

        assert.strictEqual(voice.composeVoiceDraftInput('', ' hello '), 'hello');
        assert.strictEqual(voice.composeVoiceDraftInput('Open Gmail   ', ' now '), 'Open Gmail now');
        assert.strictEqual(voice.composeVoiceDraftInput('Open Gmail', ''), 'Open Gmail');

        assert.strictEqual(voice.appendVoiceTranscriptSegment('', ' hello '), 'hello');
        assert.strictEqual(voice.appendVoiceTranscriptSegment('hello', 'world'), 'hello world');
        assert.strictEqual(voice.appendVoiceTranscriptSegment('hello world', 'world'), 'hello world');
        assert.strictEqual(voice.appendVoiceTranscriptSegment('repeat', 'repeat'), 'repeat');

        assert.strictEqual(voice.jarvisBargeInSpeechWordCount(' wait, stop '), 2);
        assert.strictEqual(voice.isMeaningfulJarvisBargeInText('ok'), false);
        assert.strictEqual(voice.isMeaningfulJarvisBargeInText('wait stop'), true);

        assert.strictEqual(voice.normalizeJarvisSttBackend('openai'), voice.STT_BACKEND_OPENAI_REALTIME);
        assert.strictEqual(voice.normalizeJarvisSttBackend('realtime-api'), voice.STT_BACKEND_OPENAI_REALTIME);
        assert.strictEqual(voice.normalizeJarvisSttBackend('anything-else'), voice.STT_BACKEND_LOCAL_WHISPER);
        assert.strictEqual(voice.jarvisSttBackendLabel('openai'), 'Realtime API');
        assert.strictEqual(voice.jarvisSttBackendLabel('local_whisper'), 'Local Whisper');

        assert.strictEqual(voice.normalizeJarvisTtsBackend('kokoro'), voice.TTS_BACKEND_KOKORO);
        assert.strictEqual(voice.normalizeJarvisTtsBackend('kyutai-clone'), voice.TTS_BACKEND_KYUTAI);
        assert.strictEqual(voice.normalizeJarvisTtsBackend('custom_tts'), 'custom_tts');
        assert.strictEqual(voice.jarvisTtsBackendLabel('kokoro'), 'Kokoro');
        assert.strictEqual(voice.jarvisTtsBackendLabel('kyutai_clone'), 'Kyutai clone');
        assert.strictEqual(voice.jarvisTtsBackendLabel('custom_tts'), 'custom_tts');
        assert(voice.JARVIS_ENGLISH_VOICE_PATH_ERROR.includes('English local voice path'));
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
