"""Local skill authoring helpers.

This is the local-first equivalent of Hermes' learn workflow: take a repeated
interactive workflow and turn it into a user-owned SKILL.md package.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def slugify_skill_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-_")
    if not slug:
        raise ValueError("Skill name is required")
    if slug in {".", ".."} or len(slug) > 80:
        raise ValueError("Skill name is invalid")
    return slug


def _one_line(value: str, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:180] or fallback


def _skill_body(*, title: str, description: str, workflow: str, source: str = "desktop") -> str:
    workflow = str(workflow or "").strip()
    if not workflow:
        raise ValueError("Workflow instructions are required")
    return (
        f"---\n"
        f"name: {slugify_skill_name(title)}\n"
        f"description: {_one_line(description, fallback='Reusable local desktop workflow.')}\n"
        f"metadata:\n"
        f"  emploai:\n"
        f"    source: {source}\n"
        f"    local_first: true\n"
        f"---\n\n"
        f"# {title.strip()}\n\n"
        f"## When To Use\n\n"
        f"Use this skill when the user asks for this workflow or a close variation of it.\n\n"
        f"## Interactive Workflow\n\n"
        f"{workflow}\n\n"
        f"## EmploAI Runtime Notes\n\n"
        f"- Keep the desktop/runtime state visible and verified when the workflow touches apps, browsers, files, or terminals.\n"
        f"- Prefer existing EmploAI tools and local files over external services.\n"
        f"- Store durable lessons in local memory only when they will help future runs.\n"
        f"- Do not store raw secrets in this skill.\n"
    )


def workflow_from_recent_messages(messages: Iterable[Dict[str, Any]], *, limit: int = 8) -> str:
    """Build a draft workflow from recent chat messages.

    This intentionally does not summarize with an LLM. It preserves the recent
    interaction as source material so the user/agent can refine the generated
    skill locally.
    """
    usable: list[dict[str, Any]] = []
    for message in messages or []:
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        usable.append({"role": role, "content": content})
    recent = usable[-max(1, int(limit)):]
    if not recent:
        raise ValueError("No recent chat messages are available to learn from")

    lines = [
        "This skill was drafted from recent local chat history. Refine it as the workflow becomes clearer.",
        "",
        "### Recent Interaction Source",
    ]
    for item in recent:
        content = item["content"]
        if len(content) > 1200:
            content = content[:1175].rstrip() + "\n... (truncated)"
        lines.append(f"- **{item['role'].title()}:** {content}")

    lines.extend(
        [
            "",
            "### Reusable Procedure",
            "- Identify the user's target outcome from the latest request.",
            "- Reuse the relevant steps, checks, files, tools, and verification habits from the recent interaction above.",
            "- Keep each desktop, browser, terminal, or file action verified before moving to the next step.",
            "- Save only durable lessons back to local memory.",
        ]
    )
    return "\n".join(lines)


def create_local_skill(
    skills_dir: Path,
    *,
    name: str,
    description: Optional[str] = None,
    workflow: str,
    source: str = "desktop",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Create a local skill package with a SKILL.md file."""
    skills_dir = Path(skills_dir).expanduser().resolve()
    skill_name = slugify_skill_name(name)
    skill_dir = skills_dir / skill_name
    try:
        skill_dir.relative_to(skills_dir)
    except ValueError as exc:
        raise ValueError("Skill path escaped the skills directory") from exc

    if skill_dir.exists() and not overwrite:
        raise FileExistsError(f"Skill already exists: {skill_name}")

    skill_dir.mkdir(parents=True, exist_ok=True)
    body = _skill_body(
        title=skill_name,
        description=description or f"Reusable local workflow: {skill_name}.",
        workflow=workflow,
        source=source,
    )
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(body, encoding="utf-8")
    return {
        "name": skill_name,
        "path": str(skill_dir),
        "skill_file": str(skill_path),
        "description": _one_line(description or f"Reusable local workflow: {skill_name}.", fallback="Reusable local desktop workflow."),
    }
