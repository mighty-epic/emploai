from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_realtime_protocol_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopRealtimeProtocol.ts', 'utf8');
        const output = ts.transpileModule(source, {
          compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
        }).outputText;
        const moduleRef = { exports: {} };
        vm.runInNewContext(output, {
          module: moduleRef,
          exports: moduleRef.exports,
          require: (id) => { throw new Error(`Unexpected runtime require: ${id}`); },
          Date,
          Error,
          JSON,
          Math,
          Number,
          Object,
          Set,
          String,
        });
        const protocol = moduleRef.exports;

        const event = protocol.parseDesktopRealtimeEvent(JSON.stringify({
          type: 'assistant_delta',
          session_id: ' sess-1 ',
          payload: { delta: 'hello' },
        }));
        assert.strictEqual(event.type, 'assistant_delta');
        assert.strictEqual(event.session_id, 'sess-1');
        assert.strictEqual(protocol.realtimeEventMatchesSession(event, 'sess-1'), true);
        assert.strictEqual(protocol.realtimeEventMatchesSession(event, 'sess-2'), false);
        assert.throws(() => protocol.parseDesktopRealtimeEvent('[]'));
        assert.throws(() => protocol.parseDesktopRealtimeEvent('{'));
        assert.strictEqual(protocol.shouldReconnectChatSocket(1006), true);
        assert.strictEqual(protocol.shouldReconnectChatSocket(4401), false);
        assert.strictEqual(protocol.chatReconnectDelayMs(0, 1000, 0.5), 1000);
        assert.strictEqual(protocol.chatReconnectDelayMs(3, 1000, 0.5), 8000);
        const messageId = protocol.createClientMessageId('desktop client', 1000, 0.5);
        assert.ok(messageId.startsWith('desktop-client:'));
        assert.ok(messageId.length <= 128);
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
