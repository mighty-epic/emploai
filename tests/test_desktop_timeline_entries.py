from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_timeline_entry_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopTimelineEntries.ts', 'utf8');
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
            if (id === '@/desktop/desktopMessages') {
              return {
                labelForMessage: (message) => message.displayLabel || (
                  message.role === 'assistant' ? 'Assistant' : message.role === 'system' ? 'System' : 'You'
                ),
              };
            }
            if (id === '@/desktop/conversationTimeline') {
              return {
                timelineEventTimestampValue: (event) => {
                  if (!event.timestamp) {
                    return null;
                  }
                  const numeric = Date.parse(event.timestamp);
                  return Number.isFinite(numeric) ? numeric : null;
                },
              };
            }
            throw new Error(`Unexpected runtime require: ${id}`);
          },
          Date,
          Number,
          String,
        });
        const timeline = moduleRef.exports;

        assert.strictEqual(timeline.messageTimestampValue({ role: 'user', content: '' }), null);
        assert.strictEqual(
          timeline.messageTimestampValue({ role: 'user', content: '', timestamp: '2026-06-01T00:00:00.000Z' }),
          Date.parse('2026-06-01T00:00:00.000Z'),
        );
        assert.strictEqual(timeline.messageTimestampValue({ role: 'user', content: '', timestamp: 'not-a-date' }), null);

        const entries = timeline.mergeTimelineEntries([
          {
            fullIndex: 0,
            message: {
              role: 'assistant',
              content: 'assistant later',
              timestamp: '2026-06-01T00:00:02.000Z',
              displayLabel: 'Helper',
              messageKey: 'm-later',
            },
          },
          {
            fullIndex: 1,
            message: {
              role: 'user',
              content: 'local draft',
              localOnly: true,
              timestamp: '2026-06-01T00:00:01.000Z',
            },
          },
          {
            fullIndex: 2,
            message: {
              role: 'user',
              content: 'pending user',
            },
          },
        ], [
          {
            id: 'event-mid',
            kind: 'tool_call',
            title: 'Tool Ran',
            content: 'pytest',
            tone: 'warn',
            timestamp: '2026-06-01T00:00:01.500Z',
          },
          {
            kind: 'note',
            content: 'untimed event',
          },
        ]);

        assert.strictEqual(JSON.stringify(entries.map((entry) => entry.id)), JSON.stringify([
          'event-mid',
          'm-later',
          'message-pending-2',
          'event-pending-1',
        ]));
        assert.strictEqual(entries[0].eyebrow, 'tool call');
        assert.strictEqual(entries[1].label, 'Helper');
        assert.strictEqual(entries[1].sourceMessageIndex, 0);
        assert.strictEqual(entries[2].label, 'You');
        assert.strictEqual(entries[2].tone, 'neutral');
        assert.strictEqual(entries[3].label, 'Event');
        assert.strictEqual(entries[3].body, 'untimed event');
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
