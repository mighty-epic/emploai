from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_voice_audio_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopVoiceAudio.ts', 'utf8');
        const output = ts.transpileModule(source, {
          compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2020,
          },
        }).outputText;
        const moduleRef = { exports: {} };
        function FakeAudioContext() {
          this.sampleRate = 48000;
        }
        vm.runInNewContext(output, {
          module: moduleRef,
          exports: moduleRef.exports,
          require: (id) => {
            throw new Error(`Unexpected runtime require: ${id}`);
          },
          ArrayBuffer,
          DataView,
          Float32Array,
          Math,
          String,
          Uint8Array,
          AudioContext: FakeAudioContext,
          btoa: (value) => Buffer.from(value, 'binary').toString('base64'),
        });
        const audio = moduleRef.exports;

        const firstGate = audio.createVoiceGateState();
        const secondGate = audio.createVoiceGateState();
        assert.strictEqual(firstGate.pendingSampleCount, 0);
        assert.strictEqual(firstGate.recording, false);
        assert.notStrictEqual(firstGate.pendingFrames, secondGate.pendingFrames);

        assert.strictEqual(audio.bytesToBase64(new Uint8Array([72, 105])), 'SGk=');

        const merged = audio.concatFloat32([
          new Float32Array([1, 2]),
          new Float32Array([3]),
        ]);
        assert.strictEqual(JSON.stringify(Array.from(merged)), JSON.stringify([1, 2, 3]));

        const gate = audio.createVoiceGateState();
        gate.pendingFrames.push(new Float32Array([1, 2]), new Float32Array([3, 4, 5]));
        gate.pendingSampleCount = 5;
        const frame = audio.takeGateFrame(gate, 3);
        assert.strictEqual(JSON.stringify(Array.from(frame)), JSON.stringify([1, 2, 3]));
        assert.strictEqual(gate.pendingSampleCount, 2);
        assert.strictEqual(JSON.stringify(Array.from(gate.pendingFrames[0])), JSON.stringify([4, 5]));
        assert.strictEqual(audio.takeGateFrame(gate, 3), null);

        assert.strictEqual(audio.samplesDbfs(new Float32Array([])), -120);
        assert.strictEqual(audio.samplesDbfs(new Float32Array([0, 0])), -120);
        assert(Math.abs(audio.samplesDbfs(new Float32Array([1, 1])) - 0) < 0.000001);
        assert(Math.abs(audio.samplesDbfs(new Float32Array([0.5, 0.5])) + 6.0205999) < 0.0001);

        const wav = audio.encodePcm16Wav(new Float32Array([-1, 0, 1]), 16000);
        const view = new DataView(wav);
        const ascii = (start, length) => String.fromCharCode(...new Uint8Array(wav, start, length));
        assert.strictEqual(ascii(0, 4), 'RIFF');
        assert.strictEqual(ascii(8, 4), 'WAVE');
        assert.strictEqual(ascii(12, 4), 'fmt ');
        assert.strictEqual(ascii(36, 4), 'data');
        assert.strictEqual(view.getUint32(24, true), 16000);
        assert.strictEqual(view.getUint32(40, true), 6);
        assert.strictEqual(view.getInt16(44, true), -32768);
        assert.strictEqual(view.getInt16(46, true), 0);
        assert.strictEqual(view.getInt16(48, true), 32767);

        const context = audio.createAudioContext();
        assert.strictEqual(context.sampleRate, 48000);
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


def test_desktop_status_number_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopStatusNumbers.ts', 'utf8');
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
          Math,
          Number,
        });
        const numbers = moduleRef.exports;

        assert.strictEqual(numbers.finiteStatusNumber('42'), 42);
        assert.strictEqual(numbers.finiteStatusNumber('nope'), null);
        assert.strictEqual(numbers.finiteStatusNumber(Infinity), null);
        assert.strictEqual(numbers.formatStatusNumber(1234.6), '1,235');
        assert.strictEqual(numbers.formatStatusNumber(null), '0');
        assert.strictEqual(numbers.formatStatusNumber(undefined), '-');
        assert.strictEqual(numbers.clampUsagePercent(-10), 0);
        assert.strictEqual(numbers.clampUsagePercent(42.5), 42.5);
        assert.strictEqual(numbers.clampUsagePercent(110), 100);
        assert.strictEqual(numbers.clampUsagePercent(undefined), 0);
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
