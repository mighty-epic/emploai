from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_model_provider_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/modelProviders.ts', 'utf8');
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
          Map,
          Number,
          RegExp,
          String,
        });
        const providers = moduleRef.exports;
        const catalog = [
          { provider: 'anthropic', models: ['claude-sonnet-4.5', 'claude-haiku'] },
          { provider: 'openai', models: ['gpt-5.4-mini', 'gpt-5.4'] },
          { provider: 'google', models: ['gemini-2.5-pro'] },
        ];

        assert.strictEqual(providers.preferredModelFromGroups(catalog), 'gpt-5.4-mini');
        assert.strictEqual(
          providers.preferredModelFromGroups([{ provider: 'nvidia', models: ['google/diffusiongemma-26b-a4b-it', 'mistralai/ministral-14b-instruct-2512'] }]),
          'mistralai/ministral-14b-instruct-2512',
        );
        assert.strictEqual(providers.modelProviderKey(' OpenAI '), 'openai');
        assert.strictEqual(
          JSON.stringify(providers.filterModelGroupsByConfiguredProviders(catalog, [
            { provider: 'OpenAI', models: ['gpt-5.4-mini'] },
          ])),
          JSON.stringify([
            { provider: 'openai', models: ['gpt-5.4-mini'] },
          ]),
        );
        assert.strictEqual(
          JSON.stringify(providers.filterModelsByConfiguredList(
            ['claude-sonnet-4.5', 'gpt-5.4-mini', 'gemini-2.5-pro'],
            ['gpt-5.4-mini'],
          )),
          JSON.stringify(['gpt-5.4-mini']),
        );
        assert.strictEqual(providers.modelExistsInGroups('gpt-5.4-mini', catalog), true);
        assert.strictEqual(providers.modelExistsInGroups('claude-opus-4.5', [
          { provider: 'openai', models: ['gpt-5.4-mini'] },
        ]), false);
        assert.strictEqual(providers.providerForModelName('claude-opus-4.5', catalog), 'anthropic');
        assert.strictEqual(providers.providerForModelName('google/diffusiongemma-26b-a4b-it', catalog), 'nvidia');
        assert.strictEqual(providers.providerForModelName('mistralai/ministral-14b-instruct-2512', catalog), 'nvidia');
        assert.strictEqual(providers.providerForModelName('vendor/custom-model', catalog), 'vendor');

        const grouped = providers.groupPlannerModelsByProvider(
          ['gemini-2.5-flash', 'claude-haiku', 'openrouter/mistral', 'google/diffusiongemma-26b-a4b-it', 'gpt-5.4-mini'],
          catalog,
        );
        assert.strictEqual(
          JSON.stringify(grouped.map((group) => [group.provider, group.models])),
          JSON.stringify([
            ['openai', ['gpt-5.4-mini']],
            ['anthropic', ['claude-haiku']],
            ['google', ['gemini-2.5-flash']],
            ['nvidia', ['google/diffusiongemma-26b-a4b-it']],
            ['openrouter', ['openrouter/mistral']],
          ]),
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
