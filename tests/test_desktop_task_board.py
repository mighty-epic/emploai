from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_task_board_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopTaskBoard.ts', 'utf8');
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
        });
        const taskBoard = moduleRef.exports;

        assert.strictEqual(taskBoard.summarizeRuntimeStatus(null), 'Bootstrapping local runtime');
        assert.strictEqual(taskBoard.summarizeRuntimeStatus({ state: 'ready', mode: 'local' }), 'ready');
        assert.strictEqual(taskBoard.summarizeRuntimeStatus({ mode: 'cloud', degraded: true }), 'cloud · degraded');
        assert.strictEqual(taskBoard.summarizeRuntimeStatus({}), 'unknown');

        assert.strictEqual(taskBoard.taskBoardStatusLabel('completed'), 'Completed');
        assert.strictEqual(taskBoard.taskBoardStatusLabel('blocked'), 'Blocked');
        assert.strictEqual(taskBoard.taskBoardStatusLabel('interrupted'), 'Interrupted');
        assert.strictEqual(taskBoard.taskBoardStatusLabel('paused'), 'Paused');
        assert.strictEqual(taskBoard.taskBoardStatusLabel('active'), 'Active');
        assert.strictEqual(taskBoard.taskBoardStatusLabel(null), 'Active');

        assert.strictEqual(taskBoard.taskBoardStepPrefix('done'), '[x]');
        assert.strictEqual(taskBoard.taskBoardStepPrefix('in_progress'), '[>]');
        assert.strictEqual(taskBoard.taskBoardStepPrefix('blocked'), '[!]');
        assert.strictEqual(taskBoard.taskBoardStepPrefix('open'), '[ ]');

        const board = { task_id: 'task-1' };
        assert.strictEqual(taskBoard.resolveTaskBoardState(board, 'session-1', 'session-1'), board);
        assert.strictEqual(taskBoard.resolveTaskBoardState(null, 'session-2', 'session-1'), null);
        assert.strictEqual(taskBoard.resolveTaskBoardState(undefined, 'session-1', 'session-1'), null);

        const sorted = taskBoard.normalizeCompletedTaskBoards([
          { task_id: 'updated', updated_at: '2026-01-02T00:00:00.000Z' },
          { task_id: 'completed', completed_at: '2026-01-03T00:00:00.000Z', updated_at: '2026-01-01T00:00:00.000Z' },
          { task_id: 'collapsed', collapsed_completed_at: '2026-01-04T00:00:00.000Z' },
          { task_id: 'created', created_at: '2026-01-01T00:00:00.000Z' },
        ]).map((entry) => entry.task_id);
        assert.strictEqual(JSON.stringify(sorted), JSON.stringify(['collapsed', 'completed', 'updated', 'created']));

        assert.strictEqual(JSON.stringify(taskBoard.normalizeCompletedTaskBoards(null)), JSON.stringify([]));
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
