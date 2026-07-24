from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from local_agent_runtime.cron_scheduler import CronScheduler


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "desktop_app" / "renderer_client"


def test_desktop_automation_helpers_validate_and_scope_records():
    script = textwrap.dedent(
        r"""
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');
        const ts = require('./node_modules/typescript');

        const source = fs.readFileSync('src/desktop/desktopAutomations.ts', 'utf8');
        const output = ts.transpileModule(source, {
          compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
        }).outputText;
        const moduleRef = { exports: {} };
        vm.runInNewContext(output, {
          module: moduleRef,
          exports: moduleRef.exports,
          require: (id) => { throw new Error(`Unexpected runtime require: ${id}`); },
          Set, Date, Intl, Object, String, Number, JSON, Array, RegExp,
        });
        const automation = moduleRef.exports;

        const invalid = automation.emptyAutomationDraft();
        invalid.intervalAmount = 'nope';
        const errors = automation.validateAutomationDraft(invalid);
        assert.ok(errors.name);
        assert.ok(errors.prompt);
        assert.ok(errors.intervalAmount);

        const draft = automation.emptyAutomationDraft();
        draft.name = 'Morning brief';
        draft.prompt = 'Summarize project status.';
        draft.scheduleMode = 'daily';
        draft.dailyTime = '08:30';
        draft.targetIdentityId = 'manager-1';
        draft.model = 'openai/gpt-5.6';
        draft.toolPacksText = 'scheduler, browser_isolated, scheduler';
        assert.strictEqual(automation.buildAutomationSchedule(draft), 'every day at 08:30');
        assert.deepStrictEqual(Array.from(automation.splitAutomationToolPacks(draft.toolPacksText)), ['scheduler', 'browser_isolated']);
        const payload = automation.automationPayloadFromDraft(draft);
        assert.strictEqual(payload.metadata.cloud_mirror_policy, undefined);
        assert.strictEqual(payload.chat_target, 'new');
        assert.strictEqual(payload.target_identity_id, 'manager-1');
        assert.strictEqual(payload.model, 'openai/gpt-5.6');

        draft.chatMode = 'existing';
        draft.targetChatId = 'chat-1';
        const existingPayload = automation.automationPayloadFromDraft(draft);
        assert.strictEqual(existingPayload.chat_target, 'existing');
        assert.strictEqual(existingPayload.session_id, 'chat-1');
        assert.strictEqual(existingPayload.model, null);

        const next = automation.previewAutomationNextRun(draft, new Date('2026-07-12T07:00:00'));
        assert.strictEqual(next.getHours(), 8);
        assert.strictEqual(next.getMinutes(), 30);

        const job = {
          id: 'job-1', automation_id: 'job-1', name: 'Morning brief', prompt: 'Status',
          schedule: 'every day at 08:30', enabled: true, target_chat_id: 'chat-1',
          origin_enabled_tool_packs: [],
        };
        const restored = automation.draftFromAutomation(job);
        assert.strictEqual(restored.scheduleMode, 'daily');
        assert.strictEqual(restored.dailyTime, '08:30');
        assert.strictEqual(automation.processWaitMatchesAutomation({ session_id: 'chat-1', metadata: {} }, job), true);
        assert.strictEqual(automation.processWaitMatchesAutomation({ session_id: 'other', metadata: {} }, job), false);
        assert.strictEqual(automation.plannerContractMatchesAutomation({ session_id: 'other', contract: { automation_id: 'job-1' } }, job), true);
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


def test_scheduler_add_is_immediately_visible_and_update_preserves_history(tmp_path: Path):
    scheduler = CronScheduler(job_store=str(tmp_path / "jobs.json"))
    job_id = scheduler.add_job(
        name="Original",
        prompt="Original prompt",
        interval_seconds=3600,
        schedule_text="every 1 hour",
        job_id="job-1",
    )

    job = scheduler.get_job(job_id)
    assert job is not None
    job.created_at = 100.0
    job.last_run = 200.0
    job.run_count = 7
    job.error_count = 2

    assert scheduler.update_job(
        job_id,
        name="Updated",
        prompt="Updated prompt",
        schedule_text="in 20 minutes",
        interval_seconds=1200,
        origin_session_id="chat-2",
        origin_model="openai/gpt-5.6",
        origin_variant="high",
    ) is True

    updated = scheduler.get_job(job_id)
    assert updated is not None
    assert updated.name == "Updated"
    assert updated.prompt == "Updated prompt"
    assert updated.one_time is True
    assert updated.created_at == 100.0
    assert updated.last_run == 200.0
    assert updated.run_count == 7
    assert updated.error_count == 2
    assert updated.origin_session_id == "chat-2"
    assert updated.origin_model == "openai/gpt-5.6"
    assert updated.origin_variant == "high"


def test_automation_edit_contract_is_exposed_without_cloud_metadata():
    api_source = (CLIENT_DIR / "src/lib/appApi.ts").read_text(encoding="utf-8")
    route_source = (ROOT / "app_backend/app_server_routes_events.py").read_text(encoding="utf-8")
    screen_source = (CLIENT_DIR / "src/desktop/DesktopAutomationsScreen.tsx").read_text(encoding="utf-8")

    assert "export async function updateJob" in api_source
    assert '@app.put("/api/app/automations/{job_id}"' in route_source
    assert "scheduler.update_job(" in route_source
    assert "cloud_mirror_policy" not in screen_source
    assert "Sign in first" not in screen_source
    assert "processWaitMatchesAutomation" in screen_source
    assert "plannerContractMatchesAutomation" in screen_source
    assert "isLocalAuthorizationFailure" in screen_source
    assert "Local runtime connection expired. Refresh to reconnect." in screen_source
    assert "applyWorkspace(await requestWorkspace(refreshed.apiBaseUrl, refreshed.accessToken))" in screen_source


def test_automation_workspace_exposes_accessible_state_and_bounded_lists():
    editor_source = (CLIENT_DIR / "src/desktop/DesktopAutomationEditor.tsx").read_text(encoding="utf-8")
    list_source = (CLIENT_DIR / "src/desktop/DesktopAutomationList.tsx").read_text(encoding="utf-8")
    detail_source = (CLIENT_DIR / "src/desktop/DesktopAutomationDetail.tsx").read_text(encoding="utf-8")
    screen_source = (CLIENT_DIR / "src/desktop/DesktopAutomationsScreen.tsx").read_text(encoding="utf-8")
    styles_source = (CLIENT_DIR / "src/desktop/DesktopAutomations.styles.ts").read_text(encoding="utf-8")

    assert "FlatList" in list_source
    assert 'accessibilityLabel="Search automations"' in list_source
    assert 'accessibilityRole="radio"' in list_source
    assert "accessibilityState={{ checked: selected }}" in list_source
    assert "accessibilityState={{ selected }}" in list_source
    assert 'accessibilityLiveRegion="polite"' in screen_source
    assert "window.scrollTo({ top: 0, left: 0, behavior: 'auto' })" in screen_source
    assert "height: '100vh'" in styles_source
    assert "editor: { flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden' }" in styles_source
    assert 'accessibilityLabel="Automation name"' in editor_source
    assert 'accessibilityLabel="Automation task"' in editor_source
    assert 'accessibilityRole="tab"' in detail_source
