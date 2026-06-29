from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "mobile_app" / "client"


def test_mobile_chat_message_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/screens/chatMessages.ts', 'utf8');
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
          Date,
          Number,
          Set,
          String,
        });
        const chat = moduleRef.exports;

        const mapped = chat.toChatMessage({
          role: 'user',
          content: 'Hello',
          timestamp: '2026-06-01T00:00:00.000Z',
          display_label: 'You',
          channel: 'app',
        });
        assert.strictEqual(mapped.displayLabel, 'You');
        assert.strictEqual(mapped.channel, 'app');
        assert.strictEqual(chat.messagesMatch(
          { role: 'assistant', content: 'Working', timestamp: null },
          { role: 'assistant', content: 'Working on it now', timestamp: null },
        ), true);
        assert.strictEqual(chat.messagesMatch(
          { role: 'user', content: 'Hello', timestamp: null },
          { role: 'user', content: 'Hello there', timestamp: null },
        ), false);

        const freshTimestamp = new Date().toISOString();
        const serverMessages = [
          { role: 'user', content: 'Confirmed', timestamp: '2026-06-01T00:00:00.000Z' },
          { role: 'assistant', content: 'Working on it now', timestamp: '2026-06-01T00:00:01.000Z' },
        ];
        const previousMessages = [
          { role: 'user', content: 'Confirmed', pendingLocal: true, localSessionId: 'sess-1', timestamp: freshTimestamp },
          { role: 'assistant', content: 'Working', ephemeralLocal: true, localSessionId: 'sess-1', timestamp: freshTimestamp },
          { role: 'user', content: 'Queued fresh', pendingLocal: true, localSessionId: 'sess-1', timestamp: freshTimestamp },
          { role: 'user', content: 'Queued stale', pendingLocal: true, localSessionId: 'sess-1', timestamp: '2000-01-01T00:00:00.000Z' },
          { role: 'user', content: 'Other session', pendingLocal: true, localSessionId: 'sess-2', timestamp: freshTimestamp },
        ];
        const merged = chat.mergeSessionMessagesWithLocalState(serverMessages, previousMessages, 'sess-1', true);
        assert.strictEqual(
          JSON.stringify(merged.map((message) => message.content)),
          JSON.stringify(['Confirmed', 'Working on it now', 'Queued fresh']),
        );

        const live = chat.mergeLiveMessage(
          [{ role: 'assistant', content: 'Partial answer', ephemeralLocal: true, timestamp: freshTimestamp }],
          { role: 'assistant', content: 'Partial answer with more detail', timestamp: freshTimestamp },
        );
        assert.strictEqual(live.length, 1);
        assert.strictEqual(live[0].content, 'Partial answer with more detail');
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
