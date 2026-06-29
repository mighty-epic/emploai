from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_conversation_timeline_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/conversationTimeline.ts', 'utf8');
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
          Object,
          Set,
          String,
        });
        const timeline = moduleRef.exports;

        const toolEvent = timeline.createLocalToolTimelineEvent({
          tool_name: 'screenshot',
          tool_args: {
            path: 'C:/Work/demo.png',
            image_base64: 'x'.repeat(200),
          },
          tool_result: { error: 'Capture failed' },
          duration_ms: 12.4,
          timestamp: '2026-06-01T00:00:00.000Z',
        });
        assert.strictEqual(toolEvent.kind, 'tool');
        assert.strictEqual(toolEvent.tone, 'error');
        assert.ok(toolEvent.content.includes('path: C:/Work/demo.png'));
        assert.ok(!toolEvent.content.includes('image_base64'));
        assert.ok(toolEvent.content.includes('Error: Capture failed'));

        const sorted = timeline.normalizeTimelineEvents([
          { id: 'later', kind: 'note', title: 'Later', content: '', timestamp: '2026-06-01T00:01:00.000Z' },
          { id: 'earlier', kind: 'note', title: 'Earlier', content: '', timestamp: '2026-06-01T00:00:00.000Z' },
          { id: 'earlier', kind: 'note', title: 'Duplicate', content: '', timestamp: '2026-06-01T00:02:00.000Z' },
        ]);
        assert.strictEqual(JSON.stringify(sorted.map((event) => event.id)), JSON.stringify(['earlier', 'later']));

        const previousTool = {
          id: '',
          kind: 'tool',
          title: 'Tool local',
          content: 'local()',
          tone: 'accent',
          timestamp: '2026-06-01T00:05:00.000Z',
        };
        const merged = timeline.mergeTimelineEventState(
          [previousTool],
          [{ id: 'server', kind: 'note', title: 'Server', content: '', timestamp: '2026-06-01T00:00:00.000Z' }],
        );
        assert.strictEqual(JSON.stringify(merged.map((event) => event.title)), JSON.stringify(['Server', 'Tool local']));
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
