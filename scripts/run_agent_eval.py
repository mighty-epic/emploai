from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.agent_eval_harness import AgentEvalHarness, EvalCase, EvalConfig, sample_config_payload, stable_eval_user_id


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the real app agent runtime against prompt suites without launching the desktop shell."
    )
    parser.add_argument("--scenario-file", help="Path to a JSON scenario file.")
    parser.add_argument("--prompt", action="append", default=[], help="Ad-hoc prompt to evaluate. Repeat for multiple cases.")
    parser.add_argument("--setup-message", action="append", default=[], help="Warmup message(s) sent before each ad-hoc prompt.")
    parser.add_argument("--workspace", default=".", help="Workspace to evaluate against.")
    parser.add_argument("--model", default="gpt-5.4-mini", help="Model to use for ad-hoc prompts.")
    parser.add_argument("--variant", default="standard", help="Model variant to use for ad-hoc prompts.")
    parser.add_argument("--planner-model", default=None, help="Optional planner model override.")
    parser.add_argument(
        "--final-quality-guard",
        choices=["off", "nli", "planner"],
        default=None,
        help="Enable hidden final-answer retry verification for the run.",
    )
    parser.add_argument(
        "--max-auto-continues",
        type=int,
        default=None,
        help="Maximum hidden retry continuations allowed by the final-quality guard.",
    )
    parser.add_argument("--tool-packs", default="", help="Comma-separated enabled tool packs for ad-hoc prompts.")
    parser.add_argument("--repeat", type=int, default=1, help="How many times to run each case.")
    parser.add_argument("--profile", default="", help="Stable profile name used for isolated runtime state.")
    parser.add_argument("--user-id", type=int, default=None, help="Optional explicit synthetic user id for the eval runtime.")
    parser.add_argument("--runtime-home", default="", help="Optional explicit runtime home for isolated eval state.")
    parser.add_argument("--output-root", default="test_outputs/agent_eval/runs", help="Where to write reports.")
    parser.add_argument("--fresh-runtime", action="store_true", help="Delete the eval runtime home before running.")
    parser.add_argument("--shared-session", action="store_true", help="Reuse one session across cases instead of starting fresh each time.")
    parser.add_argument("--arm-task-board", action="store_true", help="Arm long-task mode for the measured prompt(s).")
    parser.add_argument("--write-sample-config", default="", help="Write a sample scenario JSON file and exit.")
    return parser


def _repo_root() -> Path:
    return REPO_ROOT


def _resolve_path(raw: str, *, base: Path) -> Path:
    candidate = Path(raw)
    return (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()


def _tool_pack_list(raw: str) -> List[str] | None:
    parts = [part.strip() for part in str(raw or "").split(",")]
    items = [part for part in parts if part]
    return items or None


def _build_config_from_cli(args: argparse.Namespace, *, repo_root: Path) -> EvalConfig:
    if args.scenario_file:
        scenario_path = _resolve_path(args.scenario_file, base=repo_root)
        payload = json.loads(scenario_path.read_text(encoding="utf-8"))
        config = EvalConfig.from_dict(payload, repo_root=repo_root)
    else:
        prompts = [str(item).strip() for item in args.prompt if str(item).strip()]
        if not prompts:
            raise SystemExit("Provide --scenario-file or at least one --prompt.")
        cases = [
            EvalCase(
                name=f"prompt-{index + 1}",
                prompt=prompt,
                setup_messages=list(args.setup_message),
            )
            for index, prompt in enumerate(prompts)
        ]
        config = EvalConfig(
            name="agent-eval",
            profile=str(args.profile or "default").strip() or "default",
            workspace=_resolve_path(args.workspace, base=repo_root),
            model=str(args.model).strip() or "gpt-5.4-mini",
            variant=str(args.variant).strip() or "standard",
            planner_model=str(args.planner_model).strip() if args.planner_model else None,
            final_quality_guard=(
                str(args.final_quality_guard).strip().lower()
                if args.final_quality_guard
                else ("planner" if args.planner_model else None)
            ),
            final_quality_max_auto_continues=args.max_auto_continues,
            enabled_tool_packs=_tool_pack_list(args.tool_packs),
            repeat=max(1, int(args.repeat or 1)),
            fresh_runtime=bool(args.fresh_runtime),
            fresh_session_per_case=not bool(args.shared_session),
            capture_prompt_snapshot=True,
            task_board_armed_next_turn=bool(args.arm_task_board),
            cases=cases,
            user_id=args.user_id,
        )

    if args.user_id is not None:
        config.user_id = int(args.user_id)
    if args.repeat is not None and int(args.repeat or 1) > 0:
        config.repeat = max(1, int(args.repeat))
    if args.fresh_runtime:
        config.fresh_runtime = True
    if args.shared_session:
        config.fresh_session_per_case = False
    if args.arm_task_board:
        config.task_board_armed_next_turn = True
    if str(args.profile or "").strip():
        config.profile = str(args.profile).strip() or config.profile
    if args.final_quality_guard:
        config.final_quality_guard = str(args.final_quality_guard).strip().lower()
    elif args.planner_model and config.final_quality_guard is None:
        config.final_quality_guard = "planner"
    if args.max_auto_continues is not None:
        config.final_quality_max_auto_continues = int(args.max_auto_continues)
    return config


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    repo_root = _repo_root()

    if args.write_sample_config:
        target = _resolve_path(args.write_sample_config, base=repo_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(sample_config_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote sample agent eval config to: {target}")
        return 0

    config = _build_config_from_cli(args, repo_root=repo_root)
    runtime_home = (
        _resolve_path(args.runtime_home, base=repo_root)
        if str(args.runtime_home or "").strip()
        else (repo_root / "test_outputs" / "agent_eval" / "runtime" / config.profile).resolve()
    )
    output_root = _resolve_path(args.output_root, base=repo_root)

    harness = AgentEvalHarness(
        repo_root=repo_root,
        config=config,
        runtime_home=runtime_home,
        output_root=output_root,
    )
    report = asyncio.run(harness.run())
    report_path = Path(report["report_path"])
    markdown_path = Path(report["markdown_path"])
    print(f"Agent eval complete for profile '{config.profile}' (user_id {config.user_id or stable_eval_user_id(config.profile)}).")
    print(
        "Final quality guard: "
        f"{report['config'].get('effective_final_quality_guard') or 'off'} "
        f"(max auto-continues: {report['config'].get('effective_final_quality_max_auto_continues') or 'default'})"
    )
    print(f"JSON report: {report_path}")
    print(f"Markdown report: {markdown_path}")
    for case_report in report["cases"]:
        summary = case_report["summary"]
        print(
            f"- {case_report['name']}: "
            f"{summary['pass_count']}/{summary['repeat_count']} passed | "
            f"avg total {summary.get('avg_total_duration_ms', 'n/a')}ms | "
            f"avg first delta {summary.get('avg_time_to_first_delta_ms', 'n/a')}ms"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Agent eval interrupted.", file=sys.stderr)
        raise SystemExit(130)
