from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_message_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopMessages.ts', 'utf8');
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
          JSON,
          Map,
          Number,
          String,
        });
        const messages = moduleRef.exports;

        const sessionMessages = [
          {
            role: 'assistant',
            content: 'Hello',
            timestamp: '2026-06-01T00:00:00.000Z',
            display_label: 'Helper',
            channel: 'app',
            source_format: 'app_text',
            raw: { message_id: 'server-1' },
          },
          {
            role: 'assistant',
            content: 'Hello',
            timestamp: '2026-06-01T00:00:01.000Z',
            display_label: 'Helper',
            channel: 'app',
            source_format: 'app_text',
            raw: { message_id: 'server-1' },
          },
        ];
        const mapped = messages.toDesktopMessages(sessionMessages);
        assert.strictEqual(mapped[0].messageKey, 'message:server-1#1');
        assert.strictEqual(mapped[1].messageKey, 'message:server-1#2');
        assert.strictEqual(messages.toLiveDesktopMessage(sessionMessages[0], mapped).messageKey, 'message:server-1#3');
        const clientMessage = messages.toDesktopMessages([{
          role: 'user',
          content: 'Reliable delivery',
          raw: { client_message_id: 'desktop:message-1' },
        }])[0];
        assert.strictEqual(clientMessage.messageKey, 'message:desktop:message-1#1');
        assert.strictEqual(clientMessage.clientMessageId, 'desktop:message-1');
        assert.strictEqual(messages.labelForMessage(mapped[0]), 'Helper');
        assert.strictEqual(messages.labelForMessage({ role: 'user', content: '' }), 'You');
        assert.strictEqual(messages.labelForMessage({ role: 'system', content: '' }), 'System');

        const referenceContent = `## Agent Tools Explained\n\n${'Useful tool categories. '.repeat(70)}\n\n- workspace\n- browser`;
        const referenceMessage = { role: 'assistant', content: referenceContent };
        assert.strictEqual(messages.extractReferenceTitle(referenceContent, 'Fallback'), 'Agent Tools Explained');
        assert(messages.summarizeReferenceContent(referenceContent).length <= 132);
        assert.strictEqual(messages.isReferenceSidebarMessage(referenceMessage, 'Toolset Overview'), true);
        assert.strictEqual(messages.isReferenceSidebarMessage({ ...referenceMessage, pending: true }, 'Toolset Overview'), false);

        assert.strictEqual(messages.summarizeToolPayload(undefined), 'Tool activity');
        assert.strictEqual(
          messages.summarizeToolPayload({ tool_name: 'pytest', tool_result: { ok: true }, duration_ms: 12.4 }),
          'pytest -> {"ok":true} (12ms)',
        );
        assert.strictEqual(messages.summarizeToolPayload({ formatted: 'Already formatted' }), 'Already formatted');
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
