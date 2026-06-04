from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.agent_eval_harness import AgentEvalHarness, EvalConfig


DEFAULT_MODELS = [
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.5",
    "claude-haiku-4.5",
    "claude-sonnet-4.5",
    "claude-sonnet-4.6",
    "claude-opus-4.5",
]


def _resolve_path(raw: str, *, base: Path) -> Path:
    candidate = Path(raw)
    return (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or "")).strip("_").lower()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an agent eval scenario across multiple models.")
    parser.add_argument("--scenario-file", required=True, help="Path to the behavior suite JSON file.")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS, help="Models to evaluate.")
    parser.add_argument("--output-root", default="test_outputs/agent_eval/runs", help="Where to write reports.")
    parser.add_argument(
        "--workspace-root",
        default="test_outputs/agent_eval/workspaces/behavior_suite_runs",
        help="Per-model workspace root used for isolated copies of the scenario workspace.",
    )
    parser.add_argument("--runtime-root", default="test_outputs/agent_eval/runtime", help="Per-model runtime-home root.")
    parser.add_argument("--summary-file", default="", help="Optional explicit matrix summary path.")
    return parser


async def _run_matrix(args: argparse.Namespace) -> Dict[str, Any]:
    scenario_path = _resolve_path(args.scenario_file, base=REPO_ROOT)
    payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    base_config = EvalConfig.from_dict(payload, repo_root=REPO_ROOT)
    output_root = _resolve_path(args.output_root, base=REPO_ROOT)
    workspace_root = _resolve_path(args.workspace_root, base=REPO_ROOT)
    runtime_root = _resolve_path(args.runtime_root, base=REPO_ROOT)
    workspace_root.mkdir(parents=True, exist_ok=True)
    runtime_root.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_file": str(scenario_path),
        "models": [],
    }

    for model_name in args.models:
        model_slug = _slug(model_name)
        workspace_copy = workspace_root / model_slug
        runtime_home = runtime_root / model_slug
        if workspace_copy.exists():
            shutil.rmtree(workspace_copy)
        shutil.copytree(base_config.workspace, workspace_copy)

        config = EvalConfig.from_dict(payload, repo_root=REPO_ROOT)
        config.model = model_name
        config.workspace = workspace_copy
        config.profile = f"{config.profile}-{model_slug}"

        harness = AgentEvalHarness(
            repo_root=REPO_ROOT,
            config=config,
            runtime_home=runtime_home,
            output_root=output_root,
        )
        report = await harness.run()
        pass_count = sum(case["summary"]["pass_count"] for case in report["cases"])
        total_cases = sum(case["summary"]["repeat_count"] for case in report["cases"])
        failure_classifications = sorted(
            {
                classification
                for case in report["cases"]
                for classification in case["summary"].get("failure_classifications", [])
                if classification
            }
        )
        summary["models"].append(
            {
                "model": model_name,
                "profile": config.profile,
                "workspace": str(workspace_copy),
                "report_path": report["report_path"],
                "markdown_path": report["markdown_path"],
                "pass_count": pass_count,
                "total_cases": total_cases,
                "failure_classifications": failure_classifications,
            }
        )
    return summary


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = asyncio.run(_run_matrix(args))
    summary_path = (
        _resolve_path(args.summary_file, base=REPO_ROOT)
        if str(args.summary_file or "").strip()
        else _resolve_path(
            f"test_outputs/agent_eval/runs/matrix-summary-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json",
            base=REPO_ROOT,
        )
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Matrix summary: {summary_path}")
    for model_result in summary["models"]:
        print(
            f"- {model_result['model']}: {model_result['pass_count']}/{model_result['total_cases']} passed"
            f" | failures={','.join(model_result['failure_classifications']) or 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
