from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


PINNED_SOURCE_COMMIT = "86a6695d4cee1c9720e2be4fd8ae007f9b6d96ae"
CATALOG_SCHEMA_VERSION = 1
SOURCE_REPOSITORY = "https://github.com/msitarzewski/agency-agents"
SOURCE_LICENSE = "MIT"


def _frontmatter_and_body(content: str) -> tuple[Dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content
    boundary = content.find("\n---", 4)
    if boundary < 0:
        return {}, content
    metadata: Dict[str, str] = {}
    for line in content[4:boundary].splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata, content[boundary + 4 :].lstrip()


def _sections(body: str) -> Dict[str, list[str]]:
    result: Dict[str, list[str]] = {}
    current = "overview"
    result[current] = []
    for raw_line in body.splitlines():
        heading = re.match(r"^#{2,4}\s+(.+?)\s*$", raw_line)
        if heading:
            current = re.sub(r"[^\w\s-]+", "", heading.group(1)).strip().casefold()
            result.setdefault(current, [])
            continue
        result.setdefault(current, []).append(raw_line)
    return result


def _clean_bullet(line: str) -> str:
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return " ".join(text.split())


def _bullet_values(sections: Dict[str, list[str]], keywords: Iterable[str], *, limit: int = 36) -> list[str]:
    values: list[str] = []
    keyword_values = tuple(value.casefold() for value in keywords)
    for heading, lines in sections.items():
        if not any(keyword in heading for keyword in keyword_values):
            continue
        for line in lines:
            if not re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
                continue
            value = _clean_bullet(line)
            if len(value) < 4 or value in values:
                continue
            values.append(value[:500])
            if len(values) >= limit:
                return values
    return values


def _first_paragraph(sections: Dict[str, list[str]], keywords: Iterable[str]) -> str:
    keyword_values = tuple(value.casefold() for value in keywords)
    for heading, lines in sections.items():
        if not any(keyword in heading for keyword in keyword_values):
            continue
        paragraph: list[str] = []
        for line in lines:
            clean = line.strip()
            if not clean and paragraph:
                break
            if clean and not clean.startswith(("-", "*", "+", "```")):
                paragraph.append(clean)
        if paragraph:
            return " ".join(paragraph)[:1200]
    return ""


def _git_head(source_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    return str(completed.stdout or "").strip()


def _template_from_file(path: Path, *, source_root: Path, division: str, division_label: str) -> Dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    metadata, body = _frontmatter_and_body(content)
    sections = _sections(body)
    source_slug = path.stem
    title = metadata.get("name") or source_slug.replace("-", " ").title()
    description = metadata.get("description") or _first_paragraph(sections, ("identity", "overview"))
    mission_values = _bullet_values(sections, ("core mission", "mission"), limit=20)
    responsibilities = _bullet_values(
        sections,
        ("core mission", "responsibilities", "capabilities"),
        limit=40,
    )
    workflows = _bullet_values(sections, ("workflow", "process", "steps"), limit=36)
    deliverables = _bullet_values(sections, ("deliverable", "outputs"), limit=30)
    quality_gates = _bullet_values(sections, ("critical rules", "quality", "testing"), limit=30)
    success_measures = _bullet_values(sections, ("success metrics", "success measures"), limit=24)
    communication = _bullet_values(sections, ("communication style", "communication"), limit=20)
    memory_guidance = _bullet_values(sections, ("identity  memory", "learning  memory", "memory"), limit=20)
    search_parts = [
        title,
        division_label,
        description,
        metadata.get("vibe", ""),
        *mission_values,
        *responsibilities,
        *deliverables,
        *success_measures,
    ]
    return {
        "template_id": f"agency:{source_slug}",
        "source_slug": source_slug,
        "title": title,
        "division": division,
        "division_label": division_label,
        "version": 1,
        "source_commit": PINNED_SOURCE_COMMIT,
        "review_status": "experimental",
        "availability_status": "available",
        "purpose": description,
        "mission": mission_values or ([description] if description else []),
        "responsibilities": responsibilities,
        "non_responsibilities": [],
        "deliverables": deliverables,
        "inputs": [],
        "workflows": workflows,
        "handoffs": [],
        "quality_gates": quality_gates,
        "suggested_tools": [],
        "suggested_services": [],
        "success_measures": success_measures,
        "escalations": [],
        "memory_guidance": memory_guidance,
        "communication_contract": communication,
        "source_metadata": {
            "repository": SOURCE_REPOSITORY,
            "commit": PINNED_SOURCE_COMMIT,
            "original_file": path.relative_to(source_root).as_posix(),
            "license": SOURCE_LICENSE,
            "local_changes": False,
            "frontmatter": {
                "color": metadata.get("color"),
                "emoji": metadata.get("emoji"),
                "vibe": metadata.get("vibe"),
            },
        },
        "search_text": " ".join(str(value) for value in search_parts if value).casefold(),
    }


def build_catalog(source_root: Path, output_path: Path, imported_at: str) -> Dict[str, Any]:
    divisions_payload = json.loads((source_root / "divisions.json").read_text(encoding="utf-8"))
    divisions = dict(divisions_payload.get("divisions") or {})
    head = _git_head(source_root)
    if head and head != PINNED_SOURCE_COMMIT:
        raise RuntimeError(f"Expected agency-agents {PINNED_SOURCE_COMMIT}, found {head}")
    templates = []
    for division, division_meta in divisions.items():
        division_dir = source_root / division
        for path in sorted(division_dir.glob("*.md")):
            templates.append(
                _template_from_file(
                    path,
                    source_root=source_root,
                    division=division,
                    division_label=str(division_meta.get("label") or division.replace("-", " ").title()),
                )
            )
    if len(templates) != 245:
        raise RuntimeError(f"Expected 245 agency-agents roles at the pinned commit, parsed {len(templates)}")
    catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": PINNED_SOURCE_COMMIT,
            "license": SOURCE_LICENSE,
            "imported_at": imported_at,
        },
        "divisions": [
            {
                "division": division,
                "label": str(meta.get("label") or division.replace("-", " ").title()),
                "icon": meta.get("icon"),
                "color": meta.get("color"),
            }
            for division, meta in divisions.items()
        ],
        "templates": templates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the pinned local EmploAI job catalog from agency-agents.")
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument(
        "--imported-at",
        default=datetime.now(timezone.utc).isoformat(),
        help="ISO timestamp retained in source attribution.",
    )
    args = parser.parse_args()
    catalog = build_catalog(args.source_root.resolve(), args.output_path.resolve(), args.imported_at)
    print(f"Imported {len(catalog['templates'])} job templates across {len(catalog['divisions'])} divisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

