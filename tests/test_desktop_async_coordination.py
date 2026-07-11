from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_async_coordination_latest_wins_and_single_flight():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopAsyncCoordination.ts', 'utf8');
        const output = ts.transpileModule(source, {
          compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
        }).outputText;
        const moduleRef = { exports: {} };
        vm.runInNewContext(output, {
          module: moduleRef,
          exports: moduleRef.exports,
          require: (id) => { throw new Error(`Unexpected runtime require: ${id}`); },
          Promise,
        });

        (async () => {
          const coordination = moduleRef.exports;
          const gate = coordination.createLatestRequestGate();
          const firstId = gate.begin();
          const secondId = gate.begin();
          assert.strictEqual(gate.isCurrent(firstId), false);
          assert.strictEqual(gate.isCurrent(secondId), true);
          gate.invalidate();
          assert.strictEqual(gate.isCurrent(secondId), false);

          const queue = coordination.createLatestAsyncQueue();
          let releaseFirst;
          const calls = [];
          const first = queue.schedule(async () => {
            calls.push('first-start');
            await new Promise((resolve) => { releaseFirst = resolve; });
            calls.push('first-end');
            return 'first';
          });
          await Promise.resolve();
          const second = queue.schedule(async () => {
            calls.push('second');
            return 'second';
          });
          releaseFirst();
          assert.strictEqual((await first).status, 'superseded');
          const secondResult = await second;
          assert.strictEqual(secondResult.status, 'completed');
          assert.strictEqual(secondResult.value, 'second');
          assert.deepStrictEqual(calls, ['first-start', 'first-end', 'second']);

          let operationCount = 0;
          let releaseSingleFlight;
          const singleFlight = coordination.createAsyncSingleFlight();
          const operation = () => {
            operationCount += 1;
            return new Promise((resolve) => { releaseSingleFlight = resolve; });
          };
          const one = singleFlight.run(operation);
          const two = singleFlight.run(operation);
          assert.strictEqual(singleFlight.active(), true);
          assert.strictEqual(operationCount, 0);
          await Promise.resolve();
          assert.strictEqual(operationCount, 1);
          releaseSingleFlight('done');
          assert.strictEqual(await one, 'done');
          assert.strictEqual(await two, 'done');
          await Promise.resolve();
          assert.strictEqual(singleFlight.active(), false);
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
