from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "mobile_app" / "client"


def test_mobile_chat_timeline_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/screens/chatTimeline.ts', 'utf8');
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
          JSON,
          Number,
          Object,
          Set,
          String,
        });
        const timeline = moduleRef.exports;

        assert.strictEqual(
          JSON.stringify(timeline.mergeToolLogEntries(['alpha', ' beta ', 'alpha', '', 'beta'])),
          JSON.stringify(['alpha', 'beta']),
        );
        assert.strictEqual(timeline.formatConfigValue({ enabled: true }), '{"enabled":true}');
        assert.strictEqual(timeline.formatLogLine('Disk warning', 'warn'), '[warn] Disk warning');
        assert.strictEqual(timeline.isUserVisibleRuntimeMessage('Planner verifier says retry'), false);
        assert.strictEqual(timeline.isUserVisibleRuntimeMessage('Running tests'), true);

        const visible = {
          id: 'evt-1',
          kind: 'tool',
          title: 'Tests',
          content: 'Passed',
          timestamp: '2026-06-01T00:00:00.000Z',
          metadata: {},
        };
        const internal = {
          id: 'evt-2',
          kind: 'runtime',
          title: 'Planner verifier',
          content: 'Candidate final: maybe',
          timestamp: '2026-06-01T00:00:01.000Z',
          metadata: { visibility: 'internal' },
        };
        assert.strictEqual(timeline.isUserVisibleTimelineEvent(visible), true);
        assert.strictEqual(timeline.isUserVisibleTimelineEvent(internal), false);
        assert.strictEqual(
          JSON.stringify(timeline.timelineEventsToLogLines([visible, internal])),
          JSON.stringify(['[Tests] Passed']),
        );
        assert.strictEqual(
          JSON.stringify(timeline.mergeTimelineEvents([visible], [{ ...visible }, internal])),
          JSON.stringify([visible]),
        );

        const toolEvent = timeline.realtimeToolEventToTimelineEvent(
          { tool_name: 'pytest', tool_result: { ok: true }, duration_ms: 12 },
          'sess-1',
        );
        assert.strictEqual(toolEvent.kind, 'tool');
        assert.strictEqual(toolEvent.title, 'pytest');
        assert(toolEvent.content.includes('pytest'));

        const logEvent = timeline.realtimeLogEventToTimelineEvent(
          { type: 'status', payload: { message: 'Running', level: 'warn' } },
          'sess-1',
        );
        assert.strictEqual(logEvent.kind, 'status');
        assert.strictEqual(logEvent.content, '[warn] Running');
        assert.strictEqual(timeline.realtimeLogEventToTimelineEvent({ type: 'log', message: 'candidate final: draft' }, 'sess-1'), null);
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
