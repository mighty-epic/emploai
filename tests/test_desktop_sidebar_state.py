from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_sidebar_state_helpers_execute_with_typescript_transpile():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopSidebarState.ts', 'utf8');
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
          Number,
          Object,
          Set,
          String,
        });
        const sidebar = moduleRef.exports;

        assert.strictEqual(sidebar.normalizeWorkspacePath(' C:/Root/App// '), 'C:\\Root\\App');
        assert.strictEqual(sidebar.projectPathBasename('C:/Root/App'), 'App');
        assert.strictEqual(sidebar.projectPathHint('C:/Root/App'), 'C:\\Root');
        assert.strictEqual(sidebar.isAbsoluteWindowsPath('C:/Root/App'), true);
        assert.strictEqual(sidebar.isWorkspacePathAllowed('C:/Root/App/Sub', 'C:/Root/App'), true);
        assert.strictEqual(sidebar.isWorkspacePathAllowed('C:/Root/Other', 'C:/Root/App'), false);
        assert.strictEqual(sidebar.projectDisplayName('C:/Root/App', { displayName: 'Main App' }), 'Main App');

        const sessionProjectPaths = new Set(['C:\\Root\\Known']);
        assert.strictEqual(sidebar.shouldKeepSidebarProjectPath('C:/Root/Known', {
          allowedRoot: 'C:/Root/App',
          sessionProjectPaths,
        }), true);
        assert.strictEqual(sidebar.shouldKeepSidebarProjectPath('C:/Outside/Draft', {
          allowedRoot: 'C:/Root/App',
          sessionProjectPaths,
          draftProjectPath: 'C:/Outside/Draft',
        }), true);
        assert.strictEqual(sidebar.shouldKeepSidebarProjectPath('C:/Outside/Other', {
          allowedRoot: 'C:/Root/App',
          sessionProjectPaths,
        }), false);

        const coerced = sidebar.coerceSidebarState({
          version: 99,
          projectOrder: ['C:/Root/App/', '', 'C:/Root/Other'],
          projects: {
            'C:/Root/App/': {
              pinned: true,
              collapsed: false,
              displayName: 'App',
              hidden: true,
              recentActivity: Array.from({ length: 10 }, (_, index) => ({ id: `a-${index}`, message: 'm', timestamp: String(index) })),
            },
            '': { pinned: true },
          },
          sessionMeta: {
            sessA: { pinned: true, order: 2 },
            sessB: { pinned: false, order: 'bad' },
          },
          selectedProjectPath: 'C:/Root/App/',
          lastSelectedProjectPath: 'C:/Root/Other/',
        });
        assert.strictEqual(coerced.version, sidebar.DESKTOP_SIDEBAR_STATE_VERSION);
        assert.strictEqual(JSON.stringify(coerced.projectOrder), JSON.stringify(['C:\\Root\\App', 'C:\\Root\\Other']));
        assert.strictEqual(coerced.projects['C:\\Root\\App'].recentActivity.length, sidebar.DESKTOP_SIDEBAR_ACTIVITY_LIMIT);
        assert.strictEqual(coerced.sessionMeta.sessB.order, null);

        const ensured = sidebar.ensureSidebarProjectEntries(sidebar.createEmptySidebarState(), ['C:/Root/App', 'C:/Root/App', 'C:/Root/Other']);
        assert.strictEqual(JSON.stringify(ensured.projectOrder), JSON.stringify(['C:\\Root\\App', 'C:\\Root\\Other']));
        assert.strictEqual(Boolean(ensured.projects['C:\\Root\\App']), true);

        const managerIdentity = { identity_id: 'manager-1', role: 'manager' };
        const workerIdentity = { identity_id: 'worker-identity', role: 'worker', worker_id: 'worker-1' };
        assert.strictEqual(sidebar.sessionBelongsToFleetIdentity({ id: 's1', fleet_identity_id: 'manager-1' }, managerIdentity), true);
        assert.strictEqual(sidebar.sessionBelongsToFleetIdentity({ id: 's2', fleet_worker_id: 'worker-1' }, workerIdentity), true);
        assert.strictEqual(sidebar.sessionBelongsToFleetIdentity({ id: 's3', fleet_worker_id: 'worker-2' }, workerIdentity), false);
        assert.strictEqual(JSON.stringify(sidebar.fleetSessionCreateFields(workerIdentity)), JSON.stringify({
          fleet_identity_id: 'worker-identity',
          fleet_identity_role: 'worker',
          fleet_worker_id: 'worker-1',
        }));

        const sessions = [
          { id: 'later', name: 'Later', created_at: '2026-06-02T00:00:00.000Z' },
          { id: 'pinned', name: 'Pinned', created_at: '2026-06-01T00:00:00.000Z' },
          { id: 'ordered', name: 'Ordered', created_at: '2026-06-03T00:00:00.000Z' },
        ];
        const sortedIds = [...sessions].sort((left, right) => sidebar.sessionSidebarSortComparator(left, right, {
          pinned: { pinned: true },
          ordered: { order: 1 },
        })).map((session) => session.id);
        assert.strictEqual(JSON.stringify(sortedIds), JSON.stringify(['pinned', 'ordered', 'later']));
        assert.strictEqual(sidebar.existingSessionIdFrom(sessions, 'missing', ' ordered '), 'ordered');
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
