from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_tool_pack_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopToolPacks.ts', 'utf8');
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
          Array,
          String,
        });
        const toolPacks = moduleRef.exports;

        assert.strictEqual(toolPacks.TOOL_PACK_DEFINITIONS.length, 7);
        assert.strictEqual(toolPacks.toolPackLabel('interactive_desktop'), 'Interactive Desktop');
        assert.strictEqual(toolPacks.toolPackLabel('unknown_pack'), 'unknown_pack');

        const firstDefault = toolPacks.defaultToolPackIds();
        firstDefault.pop();
        assert.strictEqual(toolPacks.defaultToolPackIds().length, 7);
        assert.strictEqual(toolPacks.defaultToolPackIds().includes('app_runtime'), true);

        assert.strictEqual(
          JSON.stringify(toolPacks.toggleToolPackId(['workspace_read'], 'workspace_read')),
          JSON.stringify([]),
        );
        assert.strictEqual(
          JSON.stringify(toolPacks.toggleToolPackId(['workspace_read'], 'web_research')),
          JSON.stringify(['workspace_read', 'web_research']),
        );
        assert.strictEqual(toolPacks.toggleToolPackId(null, 'workspace_read').includes('workspace_read'), false);

        assert.strictEqual(
          JSON.stringify(toolPacks.enabledToolPackIdsFrom([], ['workspace_read'])),
          JSON.stringify(['workspace_read']),
        );
        assert.strictEqual(toolPacks.enabledToolPackIdsFrom([], null).length, 7);
        assert.strictEqual(
          JSON.stringify(toolPacks.availableToolPackIdsFrom([], ['workspace_read'])),
          JSON.stringify([]),
        );
        assert.strictEqual(
          JSON.stringify(toolPacks.availableToolPackIdsFrom(null, ['workspace_read'])),
          JSON.stringify(['workspace_read']),
        );

        assert.strictEqual(toolPacks.formatToolPackLockReason(null), null);
        assert.strictEqual(
          toolPacks.formatToolPackLockReason('owned by chat sess1234', [{ id: 'sess1234', name: 'Main Chat' }]),
          'owned by chat "Main Chat"',
        );
        assert.strictEqual(
          toolPacks.formatToolPackLockReason('owned by chat missing1234', [{ id: 'sess1234', name: 'Main Chat' }]),
          'owned by chat missing1234',
        );
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
