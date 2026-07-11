from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_audio_capture_uses_worklet_and_cleans_up_connections():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopAudioCapture.ts', 'utf8');
        const output = ts.transpileModule(source, {
          compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
        }).outputText;
        const moduleRef = { exports: {} };
        const calls = [];
        let workletNode = null;

        class FakeAudioWorkletNode {
          constructor(context, name, options) {
            this.context = context;
            this.name = name;
            this.options = options;
            this.port = { onmessage: null };
            workletNode = this;
          }
          connect(target) { calls.push(['node-connect', target]); }
          disconnect() { calls.push(['node-disconnect']); }
        }
        class FakeBlob {
          constructor(parts, options) { this.parts = parts; this.options = options; }
        }
        const fakeUrl = {
          createObjectURL(blob) { calls.push(['create-url', blob]); return 'blob:worklet'; },
          revokeObjectURL(url) { calls.push(['revoke-url', url]); },
        };
        vm.runInNewContext(output, {
          module: moduleRef,
          exports: moduleRef.exports,
          require: (id) => { throw new Error(`Unexpected runtime require: ${id}`); },
          ArrayBuffer,
          AudioWorkletNode: FakeAudioWorkletNode,
          Blob: FakeBlob,
          Error,
          Float32Array,
          URL: fakeUrl,
        });

        (async () => {
          const gain = {
            gain: { value: 1 },
            connect(target) { calls.push(['gain-connect', target]); },
            disconnect() { calls.push(['gain-disconnect']); },
          };
          const context = {
            audioWorklet: {
              async addModule(url) { calls.push(['add-module', url]); },
            },
            createGain() { return gain; },
            destination: { kind: 'destination' },
          };
          const mediaSource = {
            connect(target) { calls.push(['source-connect', target]); },
            disconnect(target) { calls.push(['source-disconnect', target]); },
          };
          const received = [];
          const handle = await moduleRef.exports.createDesktopAudioCapture(
            context,
            mediaSource,
            (samples) => received.push(Array.from(samples)),
          );

          assert.strictEqual(workletNode.name, moduleRef.exports.DESKTOP_AUDIO_CAPTURE_PROCESSOR_NAME);
          assert.strictEqual(gain.gain.value, 0);
          assert.deepStrictEqual(calls.find((call) => call[0] === 'add-module'), ['add-module', 'blob:worklet']);
          assert.deepStrictEqual(calls.find((call) => call[0] === 'revoke-url'), ['revoke-url', 'blob:worklet']);

          workletNode.port.onmessage({ data: new Float32Array([0.25, -0.5]).buffer });
          assert.deepStrictEqual(received, [[0.25, -0.5]]);
          handle.stop();
          handle.stop();
          assert.strictEqual(workletNode.port.onmessage, null);
          assert.strictEqual(calls.filter((call) => call[0] === 'source-disconnect').length, 1);
          assert.strictEqual(calls.filter((call) => call[0] === 'node-disconnect').length, 1);
          assert.strictEqual(calls.filter((call) => call[0] === 'gain-disconnect').length, 1);
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
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
