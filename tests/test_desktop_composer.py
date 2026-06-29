from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_composer_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopComposer.ts', 'utf8');
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
          String,
        });
        const composer = moduleRef.exports;

        assert.strictEqual(composer.getCommandSuggestionQuery('hello'), null);
        assert.strictEqual(composer.getCommandSuggestionQuery('   /Mo'), 'mo');
        assert.strictEqual(composer.getCommandSuggestionQuery('/model'), 'model');
        assert.strictEqual(composer.getCommandSuggestionQuery('/model gpt'), null);
        assert.strictEqual(composer.getCommandSuggestionQuery('/model\nnext'), null);
        assert.strictEqual(composer.getCommandSuggestionQuery('/'), '');

        assert.strictEqual(composer.parseComposerSlashCommand('hello'), null);
        assert.strictEqual(composer.parseComposerSlashCommand('/'), null);
        assert.strictEqual(JSON.stringify(composer.parseComposerSlashCommand(' /MODEL gpt-5 mini ')), JSON.stringify({
          name: 'model',
          rawArgs: 'gpt-5 mini',
        }));
        assert.strictEqual(JSON.stringify(composer.parseComposerSlashCommand('/tools')), JSON.stringify({
          name: 'tools',
          rawArgs: '',
        }));
        assert.strictEqual(JSON.stringify(composer.parseComposerSlashCommand('/run\tpytest -q')), JSON.stringify({
          name: 'run',
          rawArgs: 'pytest -q',
        }));
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
