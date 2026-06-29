"""Safely operate the Kraitos launch campaign through Postiz.

The script is dry-run by default. It validates the schedule seed, replaces
integration placeholders from environment variables, and only calls Postiz when
--schedule is passed explicitly.
"""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "marketing_assets" / "postiz_schedule_seed.json"
DEFAULT_LOG = ROOT / "marketing_assets" / "schedule_log.json"
DEFAULT_UPLOAD_LOG = ROOT / "marketing_assets" / "media_upload_log.json"
DEFAULT_MEASUREMENT_LOG = ROOT / "marketing_assets" / "measurement_log.json"
DEFAULT_BASE_URL = "http://localhost:4007"
DEFAULT_MIN_FREE_GB = 5.0
PLACEHOLDER_RE = re.compile(r"POSTIZ_[A-Z0-9_]+")
QUICK_VIDEO_PLATFORMS = ("instagram", "facebook", "tiktok", "youtube")
QUICK_VIDEO_INTEGRATIONS = {
    "instagram": "POSTIZ_INSTAGRAM_INTEGRATION_ID",
    "facebook": "POSTIZ_FACEBOOK_INTEGRATION_ID",
    "tiktok": "POSTIZ_TIKTOK_INTEGRATION_ID",
    "youtube": "POSTIZ_YOUTUBE_INTEGRATION_ID",
}
QUICK_VIDEO_ALT = "Kraitos short-form video showing a desktop AI operator layer for real computer tasks."


class OperatorError(RuntimeError):
    """Expected user-correctable operator failure."""


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise OperatorError(f"{name} must be a number, got: {raw}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or schedule Kraitos launch payloads through Postiz."
    )
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--upload-log", type=Path, default=DEFAULT_UPLOAD_LOG)
    parser.add_argument("--measurement-log", type=Path, default=DEFAULT_MEASUREMENT_LOG)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("POSTIZ_BASE_URL", DEFAULT_BASE_URL),
        help="Postiz base URL. Defaults to POSTIZ_BASE_URL or local docker port.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("POSTIZ_API_KEY"),
        help="Postiz API key. Defaults to POSTIZ_API_KEY.",
    )
    parser.add_argument(
        "--label",
        action="append",
        help="Payload label to include. Repeat for multiple labels.",
    )
    parser.add_argument(
        "--integration",
        action="append",
        default=[],
        metavar="PLACEHOLDER=ID",
        help="Replace an integration placeholder, e.g. POSTIZ_X_INTEGRATION_ID=abc.",
    )
    parser.add_argument(
        "--placeholder",
        action="append",
        default=[],
        metavar="PLACEHOLDER=VALUE",
        help="Replace any POSTIZ_* seed placeholder, e.g. POSTIZ_MEDIA_ID=abc.",
    )
    parser.add_argument(
        "--list-integrations",
        action="store_true",
        help="Fetch connected Postiz integrations and exit.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate campaign readiness without calling Postiz.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print a no-network campaign operations status report.",
    )
    parser.add_argument(
        "--audit-marketing",
        action="store_true",
        help="Check marketing asset consistency without calling external services.",
    )
    parser.add_argument(
        "--audit-links",
        action="store_true",
        help="Check campaign outbound links with HEAD requests. Does not download media/installers.",
    )
    parser.add_argument(
        "--export-preview",
        type=Path,
        help="Write resolved, validated Postiz payloads to a local JSON file without calling Postiz.",
    )
    parser.add_argument(
        "--record-published",
        metavar="LABEL",
        help="Record a manually published post URL in the schedule log without calling Postiz.",
    )
    parser.add_argument(
        "--published-url",
        help="Live post URL to use with --record-published.",
    )
    parser.add_argument(
        "--published-at",
        help="Published timestamp for --record-published. Defaults to now in UTC.",
    )
    parser.add_argument(
        "--platform",
        help="Platform override for --record-published. Defaults to the payload settings type.",
    )
    parser.add_argument(
        "--record-metrics",
        metavar="LABEL",
        help="Record a manual metrics snapshot for a seeded post without calling external services.",
    )
    parser.add_argument(
        "--metric",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Metric to record with --record-metrics. Repeat for multiple metrics.",
    )
    parser.add_argument(
        "--observed-at",
        help="Observation timestamp for --record-metrics. Defaults to now in UTC.",
    )
    parser.add_argument(
        "--source",
        help="Metrics source, e.g. x-analytics, linkedin, netlify, github.",
    )
    parser.add_argument(
        "--notes",
        help="Optional note for --record-metrics.",
    )
    parser.add_argument(
        "--upload-media",
        action="append",
        metavar="MEDIA_LABEL",
        help="Preview/upload a media asset from the seed mediaAssets list.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Actually upload selected --upload-media assets. Without this flag, dry-run only.",
    )
    parser.add_argument(
        "--quick-video",
        type=Path,
        help=(
            "Ready-made video file to publish immediately to vertical socials. "
            "Dry-run by default; use --publish-now for live upload and posting."
        ),
    )
    parser.add_argument(
        "--quick-platform",
        action="append",
        default=[],
        metavar="PLATFORM",
        help=(
            "Quick video platform: instagram, facebook, tiktok, youtube, or all. "
            "Repeat for multiple platforms. Defaults to all vertical platforms."
        ),
    )
    parser.add_argument(
        "--quick-caption",
        help=(
            "Caption/description for quick video posts. Use {url} to place the "
            "tracked link explicitly; otherwise the link is appended."
        ),
    )
    parser.add_argument(
        "--quick-title",
        default="Kraitos: desktop AI operator",
        help="Title used for TikTok and YouTube quick video posts.",
    )
    parser.add_argument(
        "--quick-url",
        default="https://kraitos.app/",
        help="Landing URL to UTM-tag per platform for quick video posts.",
    )
    parser.add_argument(
        "--publish-now",
        action="store_true",
        help="With --quick-video, upload the video and publish now. Without this flag, dry-run only.",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Actually POST schedule payloads. Without this flag, dry-run only.",
    )
    parser.add_argument(
        "--allow-past",
        action="store_true",
        help="Allow scheduling payloads with dates earlier than now.",
    )
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=env_float("KRAITOS_MIN_FREE_GB", DEFAULT_MIN_FREE_GB),
        help="Minimum local free disk space required for live upload/schedule actions.",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OperatorError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OperatorError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def disk_free_gb(path: Path) -> tuple[str, float]:
    check_path = path if path.exists() else ROOT
    usage = shutil.disk_usage(check_path)
    drive = check_path.anchor or str(check_path)
    return drive, usage.free / (1024**3)


def ensure_min_free_space(path: Path, min_free_gb: float) -> None:
    drive, free_gb = disk_free_gb(path)
    if free_gb < min_free_gb:
        raise OperatorError(
            f"Refusing live Postiz action: {drive} has {free_gb:.2f} GB free, "
            f"below the configured {min_free_gb:.2f} GB minimum."
        )
    print(f"Disk guard: {drive} has {free_gb:.2f} GB free; minimum is {min_free_gb:.2f} GB.")


def log_entry_count(path: Path) -> int:
    if not path.exists():
        return 0
    log = read_json(path)
    if not isinstance(log, dict):
        raise OperatorError(f"Log has unexpected shape: {path}")
    entries = log.get("entries", [])
    if not isinstance(entries, list):
        raise OperatorError(f"Log entries must be a list: {path}")
    return len(entries)


def is_local_base_url(base_url: str) -> bool:
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def required_marketing_docs() -> list[Path]:
    return [
        ROOT / "marketing_assets" / "kraitos_manual_publish_pack.md",
        ROOT / "marketing_assets" / "kraitos_engagement_playbook.md",
        ROOT / "marketing_assets" / "kraitos_measurement_plan.md",
        ROOT / "marketing_assets" / "kraitos_real_task_demo_brief.md",
        ROOT / "marketing_assets" / "kraitos_vertical_video_distribution.md",
        ROOT / "marketing_assets" / "kraitos_content_calendar.md",
        ROOT / "marketing_assets" / "postiz_launch_runbook.md",
    ]


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def placeholder_overrides(items: list[str], integrations: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in integrations + items:
        if "=" not in item:
            raise OperatorError(f"Placeholder replacements must be PLACEHOLDER=VALUE, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not PLACEHOLDER_RE.fullmatch(key):
            raise OperatorError(f"Invalid placeholder name: {key}")
        if not value:
            raise OperatorError(f"Replacement value for {key} is empty")
        overrides[key] = value
    for key, value in os.environ.items():
        if PLACEHOLDER_RE.fullmatch(key) and value:
            overrides.setdefault(key, value)
    return overrides


def replace_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: replace_placeholders(v, replacements) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_placeholders(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def find_placeholders(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(find_placeholders(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_placeholders(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        for match in PLACEHOLDER_RE.findall(value):
            found.append(f"{path}: {match}")
    return found


def parse_post_date(payload: dict[str, Any]) -> datetime:
    raw_date = payload.get("body", {}).get("date")
    if not isinstance(raw_date, str):
        raise OperatorError(f"Payload {payload.get('label')} is missing body.date")
    normalized = raw_date.replace("Z", "+00:00")
    try:
        date = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OperatorError(f"Invalid ISO date for {payload.get('label')}: {raw_date}") from exc
    if date.tzinfo is None:
        raise OperatorError(f"Date must include timezone for {payload.get('label')}: {raw_date}")
    return date.astimezone(timezone.utc)


def parse_datetime_arg(raw_date: str, field_name: str) -> datetime:
    normalized = raw_date.replace("Z", "+00:00")
    try:
        date = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OperatorError(f"Invalid ISO date for {field_name}: {raw_date}") from exc
    if date.tzinfo is None:
        raise OperatorError(f"{field_name} must include timezone: {raw_date}")
    return date.astimezone(timezone.utc)


def validate_payload(payload: dict[str, Any], allow_past: bool) -> list[str]:
    warnings: list[str] = []
    label = payload.get("label")
    if not label:
        raise OperatorError("Every payload needs a label")
    if payload.get("endpoint") != "/public/v1/posts":
        raise OperatorError(f"{label}: endpoint must be /public/v1/posts")
    if payload.get("method") != "POST":
        raise OperatorError(f"{label}: method must be POST")
    body = payload.get("body")
    if not isinstance(body, dict):
        raise OperatorError(f"{label}: body must be an object")
    if body.get("type") not in {"draft", "schedule", "now", "update"}:
        raise OperatorError(f"{label}: body.type is invalid")
    if body.get("type") == "schedule":
        post_date = parse_post_date(payload)
        if post_date < datetime.now(timezone.utc) and not allow_past:
            raise OperatorError(
                f"{label}: scheduled date is in the past ({post_date.isoformat()}); "
                "use --allow-past to override"
            )
    posts = body.get("posts")
    if not isinstance(posts, list) or not posts:
        raise OperatorError(f"{label}: body.posts must be a non-empty list")
    for index, post in enumerate(posts):
        post_type = post.get("settings", {}).get("__type")
        integration_id = post.get("integration", {}).get("id")
        if not isinstance(integration_id, str) or not integration_id:
            raise OperatorError(f"{label}: posts[{index}].integration.id is required")
        values = post.get("value")
        if not isinstance(values, list) or not values:
            raise OperatorError(f"{label}: posts[{index}].value must be non-empty")
        for value_index, value in enumerate(values):
            content = value.get("content")
            if not isinstance(content, str) or not content.strip():
                raise OperatorError(f"{label}: posts[{index}].value[{value_index}].content is required")
            if post_type == "x" and len(content) > 280:
                warnings.append(
                    f"{label}: posts[{index}].value[{value_index}] is {len(content)} characters; "
                    "review X length before scheduling"
                )
    if len(posts) > 1:
        warnings.append(f"{label}: multiple channel posts will be scheduled as one group")
    return warnings


def postiz_request(
    base_url: str,
    api_key: str,
    method: str,
    endpoint: str,
    body: dict[str, Any] | None = None,
) -> Any:
    url = base_url.rstrip("/") + endpoint
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OperatorError(f"Postiz HTTP {exc.code} for {method} {endpoint}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OperatorError(f"Could not reach Postiz at {url}: {exc}") from exc
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def postiz_upload_file(base_url: str, api_key: str, file_path: Path) -> Any:
    if not file_path.exists():
        raise OperatorError(f"Media file not found: {file_path}")
    if not file_path.is_file():
        raise OperatorError(f"Media path is not a file: {file_path}")

    boundary = f"----KraitosPostizBoundary{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    filename = file_path.name

    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            file_bytes,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    request = urllib.request.Request(
        base_url.rstrip("/") + "/public/v1/upload",
        data=body,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OperatorError(f"Postiz HTTP {exc.code} for POST /public/v1/upload: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OperatorError(f"Could not reach Postiz upload endpoint: {exc}") from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def append_schedule_log(path: Path, campaign: str, entries: list[dict[str, Any]]) -> None:
    log = read_json(path) if path.exists() else {"campaign": campaign, "entries": []}
    if not isinstance(log, dict) or not isinstance(log.get("entries"), list):
        raise OperatorError(f"Schedule log has unexpected shape: {path}")
    log.setdefault("campaign", campaign)
    log["entries"].extend(entries)
    write_json(path, log)


def append_media_upload_log(path: Path, campaign: str, entries: list[dict[str, Any]]) -> None:
    log = read_json(path) if path.exists() else {"campaign": campaign, "entries": []}
    if not isinstance(log, dict) or not isinstance(log.get("entries"), list):
        raise OperatorError(f"Media upload log has unexpected shape: {path}")
    log.setdefault("campaign", campaign)
    log["entries"].extend(entries)
    write_json(path, log)


def append_measurement_log(path: Path, campaign: str, entries: list[dict[str, Any]]) -> None:
    log = read_json(path) if path.exists() else {"campaign": campaign, "entries": []}
    if not isinstance(log, dict) or not isinstance(log.get("entries"), list):
        raise OperatorError(f"Measurement log has unexpected shape: {path}")
    log.setdefault("campaign", campaign)
    log["entries"].extend(entries)
    write_json(path, log)


def write_preview_export(
    path: Path,
    campaign: str,
    base_url: str,
    payloads: list[dict[str, Any]],
    warnings: list[str],
    min_free_gb: float,
) -> None:
    ensure_min_free_space(path.parent, min_free_gb)
    path.parent.mkdir(parents=True, exist_ok=True)
    export = {
        "campaign": campaign,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "postizBaseUrl": base_url,
        "mode": "preview-export",
        "warnings": warnings,
        "payloads": payloads,
    }
    write_json(path, export)
    print(f"Exported preview: {path}")


def validate_public_url(raw_url: str, field_name: str) -> str:
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OperatorError(f"{field_name} must be an http(s) URL, got: {raw_url}")
    return raw_url


def slugify(value: str, fallback: str = "video") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def quick_video_platforms(raw_platforms: list[str]) -> list[str]:
    if not raw_platforms:
        return list(QUICK_VIDEO_PLATFORMS)

    normalized = [platform.strip().lower() for platform in raw_platforms]
    if "all" in normalized:
        return list(QUICK_VIDEO_PLATFORMS)

    invalid = sorted({platform for platform in normalized if platform not in QUICK_VIDEO_PLATFORMS})
    if invalid:
        raise OperatorError(
            "Unsupported quick video platform(s): "
            + ", ".join(invalid)
            + ". Use instagram, facebook, tiktok, youtube, or all."
        )

    selected: list[str] = []
    for platform in normalized:
        if platform not in selected:
            selected.append(platform)
    return selected


def tracked_quick_video_url(base_url: str, platform: str, content_slug: str) -> str:
    validate_public_url(base_url, "--quick-url")
    parsed = urllib.parse.urlparse(base_url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["utm_source"] = platform
    query["utm_medium"] = "social"
    query["utm_campaign"] = "kraitos_quick_video"
    query["utm_content"] = content_slug
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def quick_video_content(platform: str, caption: str | None, url: str) -> str:
    if caption:
        if "{url}" in caption:
            return caption.replace("{url}", url)
        return caption.rstrip() + "\n\n" + url

    if platform == "instagram":
        return (
            "Kraitos, formerly EmploAI.\n\n"
            "A desktop AI agent that can operate your computer with you in control: "
            "browser, desktop, terminal, memory, and scheduled jobs.\n\n"
            "Download the Windows MSI:\n"
            f"{url}\n\n"
            "#Kraitos #AIAgent #Automation #SelfHosted #DesktopAI"
        )
    if platform == "facebook":
        return (
            "Kraitos is the new name for EmploAI.\n\n"
            "It is a desktop AI agent for real computer work: browser state, desktop input, "
            "terminal commands, memory, logs, and scheduled jobs, with the human still in control.\n\n"
            "Download the Windows MSI:\n"
            f"{url}"
        )
    if platform == "tiktok":
        return (
            "Kraitos is a desktop AI agent that can operate your computer with you in control. "
            f"Download the Windows MSI: {url} #Kraitos #AIAgent #Automation"
        )
    if platform == "youtube":
        return (
            "Kraitos is the new name for EmploAI: a desktop AI agent that can operate your "
            "computer with you in control.\n\n"
            "It connects model reasoning to browser state, desktop input, terminal commands, "
            "files, logs, memory, and scheduled jobs.\n\n"
            "Download the Windows MSI:\n"
            f"{url}\n\n"
            "#Shorts #Kraitos #AIAgent #Automation"
        )
    raise OperatorError(f"Unsupported quick video platform: {platform}")


def quick_video_settings(platform: str, title: str) -> dict[str, Any]:
    if platform == "instagram":
        return {"__type": "instagram", "post_type": "post"}
    if platform == "facebook":
        return {"__type": "facebook", "post_type": "post"}
    if platform == "tiktok":
        return {
            "__type": "tiktok",
            "title": title[:90],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "duet": True,
            "stitch": True,
            "comment": True,
            "autoAddMusic": "no",
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "content_posting_method": "DIRECT_POST",
        }
    if platform == "youtube":
        youtube_title = title if "#Shorts" in title else f"{title} #Shorts"
        return {
            "__type": "youtube",
            "title": youtube_title[:100],
            "type": "public",
            "selfDeclaredMadeForKids": "no",
            "tags": [
                {"value": "kraitos", "label": "kraitos"},
                {"value": "ai agent", "label": "ai agent"},
                {"value": "desktop automation", "label": "desktop automation"},
                {"value": "self hosted", "label": "self hosted"},
            ],
        }
    raise OperatorError(f"Unsupported quick video platform: {platform}")


def build_quick_video_payloads(
    platforms: list[str],
    replacements: dict[str, str],
    media: dict[str, str],
    caption: str | None,
    title: str,
    base_landing_url: str,
    content_slug: str,
    timestamp_slug: str,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payloads: list[dict[str, Any]] = []

    for platform in platforms:
        integration_placeholder = QUICK_VIDEO_INTEGRATIONS[platform]
        integration_id = replacements.get(integration_placeholder, integration_placeholder)
        url = tracked_quick_video_url(base_landing_url, platform, content_slug)
        label = f"quick-{platform}-{content_slug}-{timestamp_slug}"
        payloads.append(
            {
                "label": label,
                "endpoint": "/public/v1/posts",
                "method": "POST",
                "body": {
                    "type": "now",
                    "shortLink": False,
                    "date": now,
                    "tags": [
                        {"value": "kraitos-quick-video", "label": "Kraitos quick video"},
                        {"value": "vertical-video", "label": "Vertical video"},
                    ],
                    "posts": [
                        {
                            "integration": {"id": integration_id},
                            "value": [
                                {
                                    "content": quick_video_content(platform, caption, url),
                                    "image": [
                                        {
                                            "id": media["id"],
                                            "path": media["path"],
                                            "alt": QUICK_VIDEO_ALT,
                                        }
                                    ],
                                }
                            ],
                            "settings": quick_video_settings(platform, title),
                        }
                    ],
                },
            }
        )

    return payloads


def collect_campaign_urls(seed: dict[str, Any]) -> list[tuple[str, str]]:
    urls: dict[str, str] = {}

    tracking = seed.get("tracking", {})
    if isinstance(tracking, dict):
        for group_name, group in tracking.items():
            if group_name == "campaign":
                continue
            if isinstance(group, dict):
                for label, url in group.items():
                    if isinstance(url, str) and url:
                        urls[url] = f"tracking.{group_name}.{label}"

    payloads = seed.get("payloads", [])
    if isinstance(payloads, list):
        for payload in payloads:
            label = payload.get("label", "<unknown>")
            values = payload.get("body", {}).get("posts", [])
            for post_index, post in enumerate(values):
                for value_index, value in enumerate(post.get("value", [])):
                    content = value.get("content", "")
                    if not isinstance(content, str):
                        continue
                    for match in re.findall(r"https?://[^\s)>\"]+", content):
                        urls.setdefault(match, f"payload.{label}.post{post_index}.value{value_index}")

    return sorted((context, url) for url, context in urls.items())


def audit_single_url(url: str, timeout: int = 12) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={
            "User-Agent": "KraitosLinkAudit/1.0",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.geturl()
    except urllib.error.HTTPError as exc:
        if exc.code not in {403, 405}:
            return exc.code, url
        fallback = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": "KraitosLinkAudit/1.0",
                "Accept": "text/html,*/*;q=0.8",
                "Range": "bytes=0-0",
            },
        )
        with urllib.request.urlopen(fallback, timeout=timeout) as response:
            return response.status, response.geturl()


def parse_metric_value(raw_value: str) -> int | float | str:
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def parse_metrics(items: list[str]) -> dict[str, int | float | str]:
    metrics: dict[str, int | float | str] = {}
    for item in items:
        if "=" not in item:
            raise OperatorError(f"Metrics must be KEY=VALUE, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise OperatorError(f"Metric key is empty in: {item}")
        if not value:
            raise OperatorError(f"Metric value for {key} is empty")
        metrics[key] = parse_metric_value(value)
    return metrics


def selected_payloads(seed: dict[str, Any], labels: list[str] | None) -> list[dict[str, Any]]:
    payloads = seed.get("payloads")
    if not isinstance(payloads, list):
        raise OperatorError("Seed must contain a payloads list")
    if not labels:
        return payloads
    label_set = set(labels)
    selected = [payload for payload in payloads if payload.get("label") in label_set]
    missing = sorted(label_set - {payload.get("label") for payload in selected})
    if missing:
        raise OperatorError(f"Unknown payload label(s): {', '.join(missing)}")
    return selected


def selected_media_assets(seed: dict[str, Any], labels: list[str]) -> list[dict[str, Any]]:
    assets = seed.get("mediaAssets")
    if not isinstance(assets, list):
        raise OperatorError("Seed must contain a mediaAssets list for --upload-media")
    label_set = set(labels)
    selected = [asset for asset in assets if asset.get("label") in label_set]
    missing = sorted(label_set - {asset.get("label") for asset in selected})
    if missing:
        raise OperatorError(f"Unknown media label(s): {', '.join(missing)}")
    return selected


def handle_record_published(
    seed: dict[str, Any],
    campaign: str,
    label: str,
    published_url: str | None,
    published_at: str | None,
    platform: str | None,
    log: Path,
    min_free_gb: float,
) -> int:
    if not published_url:
        raise OperatorError("--published-url is required with --record-published")

    payload = selected_payloads(seed, [label])[0]
    url = validate_public_url(published_url, "--published-url")
    published_time = (
        parse_datetime_arg(published_at, "--published-at")
        if published_at
        else datetime.now(timezone.utc)
    )
    posts = payload.get("body", {}).get("posts", [])
    inferred_platform = "unknown"
    if posts:
        inferred_platform = posts[0].get("settings", {}).get("__type", "unknown")

    ensure_min_free_space(log.parent, min_free_gb)

    entry = {
        "label": label,
        "source": "manual",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "publishedAt": published_time.isoformat(),
        "platform": platform or inferred_platform,
        "publishedUrl": url,
        "requestDate": payload.get("body", {}).get("date"),
        "note": "Recorded after manual publication fallback; no Postiz API call was made.",
    }
    append_schedule_log(log, campaign, [entry])

    print(f"Recorded manual publication: {label}")
    print(f"  platform: {entry['platform']}")
    print(f"  url: {url}")
    print(f"Updated schedule log: {log}")
    return 0


def handle_record_metrics(
    seed: dict[str, Any],
    campaign: str,
    label: str,
    metric_items: list[str],
    observed_at: str | None,
    source: str | None,
    notes: str | None,
    measurement_log: Path,
    min_free_gb: float,
) -> int:
    if not metric_items:
        raise OperatorError("--metric KEY=VALUE is required with --record-metrics")

    payload = selected_payloads(seed, [label])[0]
    metrics = parse_metrics(metric_items)
    observed_time = (
        parse_datetime_arg(observed_at, "--observed-at")
        if observed_at
        else datetime.now(timezone.utc)
    )
    posts = payload.get("body", {}).get("posts", [])
    inferred_platform = "unknown"
    if posts:
        inferred_platform = posts[0].get("settings", {}).get("__type", "unknown")

    ensure_min_free_space(measurement_log.parent, min_free_gb)

    entry = {
        "label": label,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "observedAt": observed_time.isoformat(),
        "platform": inferred_platform,
        "source": source or inferred_platform,
        "requestDate": payload.get("body", {}).get("date"),
        "metrics": metrics,
    }
    if notes:
        entry["notes"] = notes

    append_measurement_log(measurement_log, campaign, [entry])

    print(f"Recorded metrics: {label}")
    print(f"  source: {entry['source']}")
    print(f"  metrics: {', '.join(f'{key}={value}' for key, value in metrics.items())}")
    print(f"Updated measurement log: {measurement_log}")
    return 0


def handle_preflight(
    seed: dict[str, Any],
    campaign: str,
    labels: list[str] | None,
    replacements: dict[str, str],
    base_url: str,
    api_key: str | None,
    schedule_log: Path,
    upload_log: Path,
    measurement_log: Path,
    min_free_gb: float,
    allow_past: bool,
) -> int:
    payloads = copy.deepcopy(selected_payloads(seed, labels))
    payloads = replace_placeholders(payloads, replacements)

    unresolved = find_placeholders(payloads)
    warnings: list[str] = []
    dates: list[datetime] = []
    for payload in payloads:
        warnings.extend(validate_payload(payload, allow_past))
        dates.append(parse_post_date(payload))

    assets = seed.get("mediaAssets", [])
    if assets is None:
        assets = []
    if not isinstance(assets, list):
        raise OperatorError("Seed mediaAssets must be a list when present")

    drive, free_gb = disk_free_gb(ROOT)
    schedule_entries = log_entry_count(schedule_log)
    upload_entries = log_entry_count(upload_log)
    measurement_entries = log_entry_count(measurement_log)

    print(f"Campaign: {campaign}")
    print(f"Postiz: {base_url}")
    print("Mode: PREFLIGHT")
    print(f"Disk: {drive} has {free_gb:.2f} GB free; live-action minimum is {min_free_gb:.2f} GB")
    if free_gb < min_free_gb:
        print("  - live upload/schedule would be blocked by the disk guard")
    if not api_key:
        print("  - POSTIZ_API_KEY is not set; live API actions are unavailable")
    if is_local_base_url(base_url):
        print("  - base URL is local; this no-network preflight does not prove Postiz is running")

    print(f"\nPayloads: {len(payloads)} selected")
    for payload in payloads:
        label = payload["label"]
        date = payload["body"]["date"]
        post_count = len(payload["body"]["posts"])
        content_count = sum(len(post["value"]) for post in payload["body"]["posts"])
        print(f"  - {label}: {date}, {post_count} channel(s), {content_count} post item(s)")

    if dates:
        print(f"Date range: {min(dates).isoformat()} to {max(dates).isoformat()}")

    print(f"\nMedia assets: {len(assets)}")
    for asset in assets:
        label = asset.get("label", "<missing-label>")
        local_path = Path(asset.get("localPath", ""))
        status = "missing"
        size = ""
        if local_path.exists() and local_path.is_file():
            status = "found"
            size = f", {local_path.stat().st_size} bytes"
        print(f"  - {label}: {status}{size} ({local_path})")

    print(
        f"\nLogs: {schedule_entries} scheduled entries, "
        f"{upload_entries} media upload entries, {measurement_entries} measurement entries"
    )

    if unresolved:
        print("\nUnresolved placeholders:")
        for item in unresolved:
            print(f"  - {item}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    ready = bool(api_key) and not unresolved and free_gb >= min_free_gb
    print(f"\nLocal campaign checks passed: {'yes' if ready else 'no'}")
    if ready:
        print("Postiz reachability and real credentials still need to be verified before live actions.")
    return 0


def handle_status(
    seed: dict[str, Any],
    campaign: str,
    labels: list[str] | None,
    replacements: dict[str, str],
    base_url: str,
    api_key: str | None,
    schedule_log: Path,
    upload_log: Path,
    measurement_log: Path,
    min_free_gb: float,
    allow_past: bool,
) -> int:
    payloads = copy.deepcopy(selected_payloads(seed, labels))
    payloads = replace_placeholders(payloads, replacements)

    unresolved = find_placeholders(payloads)
    warnings: list[str] = []
    dated_payloads: list[tuple[datetime, str]] = []
    channel_counts: dict[str, int] = {}
    content_blob = json.dumps(payloads)
    for payload in payloads:
        warnings.extend(validate_payload(payload, allow_past))
        dated_payloads.append((parse_post_date(payload), payload["label"]))
        for post in payload["body"]["posts"]:
            channel = post.get("settings", {}).get("__type", "unknown")
            channel_counts[channel] = channel_counts.get(channel, 0) + 1

    assets = seed.get("mediaAssets", [])
    if assets is None:
        assets = []
    if not isinstance(assets, list):
        raise OperatorError("Seed mediaAssets must be a list when present")

    drive, free_gb = disk_free_gb(ROOT)
    now = datetime.now(timezone.utc)
    future = sorted((item for item in dated_payloads if item[0] >= now), key=lambda item: item[0])
    past = sorted((item for item in dated_payloads if item[0] < now), key=lambda item: item[0])
    schedule_entries = log_entry_count(schedule_log)
    upload_entries = log_entry_count(upload_log)
    measurement_entries = log_entry_count(measurement_log)

    required_docs = required_marketing_docs()

    print(f"Campaign: {campaign}")
    print("Mode: STATUS")
    print(f"Postiz base URL: {base_url} ({'local' if is_local_base_url(base_url) else 'remote'})")
    print(f"API key present: {'yes' if api_key else 'no'}")
    print(f"Disk: {drive} has {free_gb:.2f} GB free; live-action minimum is {min_free_gb:.2f} GB")
    print(f"Payloads: {len(payloads)} selected")
    print("Channels: " + ", ".join(f"{key}={value}" for key, value in sorted(channel_counts.items())))
    print(f"UTM links in selected payloads: {content_blob.count('utm_campaign=')}")

    if dated_payloads:
        first_date = min(date for date, _label in dated_payloads)
        last_date = max(date for date, _label in dated_payloads)
        print(f"Schedule window: {first_date.isoformat()} to {last_date.isoformat()}")
    if future:
        next_date, next_label = future[0]
        hours = (next_date - now).total_seconds() / 3600
        print(f"Next scheduled payload: {next_label} at {next_date.isoformat()} ({hours:.1f}h from now)")
    if past:
        print(f"Past scheduled payloads: {len(past)}")

    print(f"Unresolved placeholders: {len(unresolved)}")
    if unresolved:
        for item in unresolved:
            print(f"  - {item}")

    print(f"Validation warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  - {warning}")

    print("\nMedia assets:")
    for asset in assets:
        label = asset.get("label", "<missing-label>")
        local_path = Path(asset.get("localPath", ""))
        status = "missing"
        size = ""
        if local_path.exists() and local_path.is_file():
            status = "found"
            size = f", {local_path.stat().st_size} bytes"
        print(f"  - {label}: {status}{size}")

    print(
        f"\nLogs: {schedule_entries} scheduled entries, "
        f"{upload_entries} media upload entries, {measurement_entries} measurement entries"
    )
    print("Docs:")
    for doc in required_docs:
        print(f"  - {doc.name}: {'found' if doc.exists() else 'missing'}")

    automation_ready = bool(api_key) and not unresolved and not warnings and free_gb >= min_free_gb
    fallback_ready = (ROOT / "marketing_assets" / "kraitos_manual_publish_pack.md").exists()
    print(f"\nAutomation readiness: {'ready for API verification' if automation_ready else 'not ready'}")
    print(f"Manual fallback readiness: {'ready' if fallback_ready else 'missing'}")
    return 0


def handle_audit_marketing(
    seed: dict[str, Any],
    campaign: str,
    schedule_log: Path,
    upload_log: Path,
    measurement_log: Path,
    allow_past: bool,
) -> int:
    payloads = selected_payloads(seed, None)
    issues: list[str] = []
    warnings: list[str] = []

    labels = [str(payload.get("label", "")) for payload in payloads]
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    for label in duplicate_labels:
        issues.append(f"Duplicate payload label: {label}")

    for payload in payloads:
        warnings.extend(validate_payload(payload, allow_past))

    docs = {path.name: path for path in required_marketing_docs()}
    docs["README.md"] = ROOT / "marketing_assets" / "README.md"
    docs["rendered_assets.md"] = ROOT / "marketing_assets" / "rendered_assets.md"

    doc_texts = {name: read_text_if_exists(path) for name, path in docs.items()}
    for name, path in docs.items():
        if not path.exists():
            issues.append(f"Required marketing doc missing: {path}")

    manual_pack = doc_texts.get("kraitos_manual_publish_pack.md", "")
    content_calendar = doc_texts.get("kraitos_content_calendar.md", "")
    measurement_plan = doc_texts.get("kraitos_measurement_plan.md", "")

    for label in labels:
        if label not in manual_pack:
            issues.append(f"Manual publish pack missing payload label: {label}")
        if label not in content_calendar:
            issues.append(f"Content calendar missing payload label: {label}")

    tracking = seed.get("tracking", {})
    tracking_urls: list[tuple[str, str]] = []
    if isinstance(tracking, dict):
        for group_name, group in tracking.items():
            if group_name == "campaign":
                continue
            if group is None:
                continue
            if not isinstance(group, dict):
                issues.append(f"tracking.{group_name} must be an object")
                continue
            for label, url in group.items():
                if str(label) not in labels:
                    issues.append(f"Tracking URL references unknown label: {label}")
                if not isinstance(url, str) or not url:
                    issues.append(f"Tracking URL for {label} is empty or invalid")
                    continue
                tracking_urls.append((str(label), url))
    else:
        issues.append("Seed tracking must be an object")

    payload_blob = json.dumps(payloads)
    for label, url in tracking_urls:
        if url not in payload_blob:
            issues.append(f"Tracking URL for {label} is not used in payload content")
        if url not in measurement_plan:
            issues.append(f"Measurement plan missing tracking URL for {label}")
        if url not in manual_pack:
            issues.append(f"Manual publish pack missing tracking URL for {label}")

    assets = seed.get("mediaAssets", [])
    if assets is None:
        assets = []
    if not isinstance(assets, list):
        issues.append("Seed mediaAssets must be a list when present")
    else:
        for asset in assets:
            label = asset.get("label", "<missing-label>") if isinstance(asset, dict) else "<invalid>"
            local_path = Path(asset.get("localPath", "")) if isinstance(asset, dict) else Path("")
            if not local_path.exists() or not local_path.is_file():
                issues.append(f"Media asset missing for {label}: {local_path}")

    for log_path in (schedule_log, upload_log, measurement_log):
        try:
            log_entry_count(log_path)
        except OperatorError as exc:
            issues.append(str(exc))

    print(f"Campaign: {campaign}")
    print("Mode: MARKETING AUDIT")
    print(f"Payloads: {len(payloads)}")
    print(f"Tracking URLs: {len(tracking_urls)}")
    print(f"Required docs: {sum(1 for path in docs.values() if path.exists())}/{len(docs)} found")
    print(f"Issues: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")
    print(f"Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  - {warning}")

    if issues or warnings:
        raise OperatorError("Marketing audit failed")
    print("Marketing audit passed.")
    return 0


def handle_audit_links(seed: dict[str, Any]) -> int:
    urls = collect_campaign_urls(seed)
    if not urls:
        raise OperatorError("No campaign URLs found to audit")

    issues: list[str] = []

    print("Mode: LINK AUDIT")
    print(f"URLs: {len(urls)}")
    print("Method: HEAD with tiny GET fallback for 403/405 responses")

    for context, url in urls:
        try:
            status, final_url = audit_single_url(url)
        except urllib.error.URLError as exc:
            issues.append(f"{context}: could not reach {url}: {exc}")
            print(f"  - FAIL {context}: {url} ({exc})")
            continue
        except TimeoutError as exc:
            issues.append(f"{context}: timeout for {url}: {exc}")
            print(f"  - FAIL {context}: {url} (timeout)")
            continue

        ok = 200 <= status < 400
        state = "OK" if ok else "FAIL"
        suffix = f" -> {final_url}" if final_url != url else ""
        print(f"  - {state} {context}: {status} {url}{suffix}")
        if not ok:
            issues.append(f"{context}: HTTP {status} for {url}")

    if issues:
        print(f"\nIssues: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        raise OperatorError("Link audit failed")

    print("\nLink audit passed.")
    return 0


def handle_quick_video(
    campaign: str,
    video_path: Path,
    raw_platforms: list[str],
    replacements: dict[str, str],
    base_url: str,
    api_key: str | None,
    publish_now: bool,
    caption: str | None,
    title: str,
    landing_url: str,
    schedule_log: Path,
    upload_log: Path,
    min_free_gb: float,
) -> int:
    video_path = video_path.expanduser()
    if not video_path.is_absolute():
        video_path = (Path.cwd() / video_path).resolve()
    else:
        video_path = video_path.resolve()

    if not video_path.exists() or not video_path.is_file():
        raise OperatorError(f"--quick-video file not found: {video_path}")

    mime_type = mimetypes.guess_type(video_path.name)[0] or ""
    warnings: list[str] = []
    if not mime_type.startswith("video/"):
        warnings.append(f"{video_path.name}: MIME type is {mime_type or 'unknown'}; verify this is a video file")

    platforms = quick_video_platforms(raw_platforms)
    content_slug = slugify(video_path.stem)
    timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()
    dry_media = {
        "id": "POSTIZ_UPLOADED_QUICK_VIDEO_ID",
        "path": "POSTIZ_UPLOADED_QUICK_VIDEO_PATH",
    }
    payloads = build_quick_video_payloads(
        platforms,
        replacements,
        dry_media,
        caption,
        title,
        landing_url,
        content_slug,
        timestamp_slug,
    )

    unresolved = [
        item
        for item in find_placeholders(payloads)
        if "POSTIZ_UPLOADED_QUICK_VIDEO_" not in item
    ]
    for payload in payloads:
        warnings.extend(validate_payload(payload, allow_past=True))

    print(f"Campaign: {campaign}")
    print(f"Postiz: {base_url}")
    print(f"Mode: {'QUICK VIDEO PUBLISH NOW' if publish_now else 'QUICK VIDEO DRY RUN'}")
    print(f"Video: {video_path} ({video_path.stat().st_size} bytes)")
    print(f"Platforms: {', '.join(platforms)}")
    print("The video will be uploaded from its current path; it will not be copied into the repo.")

    if unresolved:
        print("\nUnresolved integration placeholders:")
        for item in unresolved:
            print(f"  - {item}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    print("\nResolved post preview:")
    for payload in payloads:
        platform = payload["body"]["posts"][0]["settings"]["__type"]
        content = payload["body"]["posts"][0]["value"][0]["content"]
        print(f"  - {payload['label']}: {platform}, {len(content)} characters")
        print(f"    url: {tracked_quick_video_url(landing_url, platform, content_slug)}")

    if not publish_now:
        print("\nDry-run complete. Pass --publish-now to upload the video and publish immediately.")
        return 0

    if unresolved:
        raise OperatorError("Refusing to publish quick video with unresolved integration placeholders")
    if not api_key:
        raise OperatorError("POSTIZ_API_KEY or --api-key is required with --publish-now")

    ensure_min_free_space(ROOT, min_free_gb)

    upload_response = postiz_upload_file(base_url, api_key, video_path)
    media_id = upload_response.get("id")
    media_path = upload_response.get("path")
    if not media_id or not media_path:
        raise OperatorError(f"Postiz upload did not return id and path: {upload_response}")

    append_media_upload_log(
        upload_log,
        campaign,
        [
            {
                "label": f"quick-video:{video_path.name}",
                "uploadedAt": datetime.now(timezone.utc).isoformat(),
                "postizBaseUrl": base_url,
                "localPath": str(video_path),
                "response": upload_response,
                "usedForPlatforms": platforms,
            }
        ],
    )

    live_payloads = build_quick_video_payloads(
        platforms,
        replacements,
        {"id": str(media_id), "path": str(media_path)},
        caption,
        title,
        landing_url,
        content_slug,
        timestamp_slug,
    )

    log_entries: list[dict[str, Any]] = []
    for payload in live_payloads:
        response = postiz_request(
            base_url,
            api_key,
            payload["method"],
            payload["endpoint"],
            payload["body"],
        )
        platform = payload["body"]["posts"][0]["settings"]["__type"]
        log_entries.append(
            {
                "label": payload["label"],
                "source": "quick-video",
                "publishedAt": datetime.now(timezone.utc).isoformat(),
                "platform": platform,
                "postizBaseUrl": base_url,
                "endpoint": payload["endpoint"],
                "requestType": payload["body"]["type"],
                "requestDate": payload["body"]["date"],
                "localVideoPath": str(video_path),
                "response": response,
            }
        )
        print(f"Published quick video to {platform}: {payload['label']}")

    append_schedule_log(schedule_log, campaign, log_entries)
    print(f"Updated media upload log: {upload_log}")
    print(f"Updated schedule log: {schedule_log}")
    return 0


def handle_upload_media(
    seed: dict[str, Any],
    campaign: str,
    labels: list[str],
    base_url: str,
    api_key: str | None,
    upload: bool,
    upload_log: Path,
    min_free_gb: float,
) -> int:
    assets = selected_media_assets(seed, labels)
    print(f"Campaign: {campaign}")
    print(f"Postiz: {base_url}")
    print(f"Mode: {'UPLOAD' if upload else 'UPLOAD DRY RUN'}")
    print(f"Media: {', '.join(asset['label'] for asset in assets)}")

    for asset in assets:
        local_path = Path(asset.get("localPath", ""))
        if not local_path.exists():
            raise OperatorError(f"{asset.get('label')}: localPath not found: {local_path}")
        placeholders = asset.get("postizUploadPlaceholders", {})
        print(
            f"  - {asset['label']}: {local_path} "
            f"({local_path.stat().st_size} bytes, placeholders: "
            f"{placeholders.get('id')}, {placeholders.get('path')})"
        )

    if not upload:
        print("\nUpload dry-run complete. Pass --upload only after reviewing the file list.")
        return 0

    ensure_min_free_space(ROOT, min_free_gb)

    if not api_key:
        raise OperatorError("POSTIZ_API_KEY or --api-key is required when --upload is used")

    entries: list[dict[str, Any]] = []
    for asset in assets:
        local_path = Path(asset["localPath"])
        response = postiz_upload_file(base_url, api_key, local_path)
        placeholders = asset.get("postizUploadPlaceholders", {})
        entries.append(
            {
                "label": asset["label"],
                "uploadedAt": datetime.now(timezone.utc).isoformat(),
                "postizBaseUrl": base_url,
                "localPath": str(local_path),
                "response": response,
                "placeholderHints": {
                    placeholders.get("id", "POSTIZ_MEDIA_ID"): response.get("id"),
                    placeholders.get("path", "POSTIZ_MEDIA_PATH"): response.get("path"),
                },
            }
        )
        print(f"Uploaded {asset['label']}")
        if response.get("id") and response.get("path"):
            print(
                "  schedule placeholders: "
                f"--placeholder {placeholders.get('id')}={response['id']} "
                f"--placeholder {placeholders.get('path')}={response['path']}"
            )

    append_media_upload_log(upload_log, campaign, entries)
    print(f"Updated media upload log: {upload_log}")
    return 0


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    seed = read_json(args.seed)
    if not isinstance(seed, dict):
        raise OperatorError("Seed root must be an object")
    campaign = seed.get("campaign", "kraitos-rename-launch")

    if args.export_preview and args.schedule:
        raise OperatorError("Use preview export and scheduling as separate reviewed steps")
    if args.publish_now and not args.quick_video:
        raise OperatorError("--publish-now is only valid with --quick-video")

    if args.quick_video:
        conflicting = [
            args.record_published,
            args.record_metrics,
            args.list_integrations,
            args.preflight,
            args.status,
            args.audit_marketing,
            args.audit_links,
            args.export_preview,
            args.upload_media,
            args.schedule,
        ]
        if any(conflicting):
            raise OperatorError("Use --quick-video as a separate operation")
        replacements = placeholder_overrides(args.placeholder, args.integration)
        return handle_quick_video(
            campaign,
            args.quick_video,
            args.quick_platform,
            replacements,
            base_url,
            args.api_key,
            args.publish_now,
            args.quick_caption,
            args.quick_title,
            args.quick_url,
            args.log,
            args.upload_log,
            args.min_free_gb,
        )

    if args.record_published:
        if args.schedule or args.upload_media or args.export_preview:
            raise OperatorError("Use manual publication recording as a separate step")
        return handle_record_published(
            seed,
            campaign,
            args.record_published,
            args.published_url,
            args.published_at,
            args.platform,
            args.log,
            args.min_free_gb,
        )

    if args.record_metrics:
        if args.schedule or args.upload_media or args.export_preview:
            raise OperatorError("Use metrics recording as a separate step")
        return handle_record_metrics(
            seed,
            campaign,
            args.record_metrics,
            args.metric,
            args.observed_at,
            args.source,
            args.notes,
            args.measurement_log,
            args.min_free_gb,
        )

    if args.list_integrations:
        if not args.api_key:
            raise OperatorError("POSTIZ_API_KEY or --api-key is required for --list-integrations")
        integrations = postiz_request(base_url, args.api_key, "GET", "/public/v1/integrations")
        print(json.dumps(integrations, indent=2))
        return 0

    if args.preflight:
        replacements = placeholder_overrides(args.placeholder, args.integration)
        return handle_preflight(
            seed,
            campaign,
            args.label,
            replacements,
            base_url,
            args.api_key,
            args.log,
            args.upload_log,
            args.measurement_log,
            args.min_free_gb,
            args.allow_past,
        )

    if args.status:
        replacements = placeholder_overrides(args.placeholder, args.integration)
        return handle_status(
            seed,
            campaign,
            args.label,
            replacements,
            base_url,
            args.api_key,
            args.log,
            args.upload_log,
            args.measurement_log,
            args.min_free_gb,
            args.allow_past,
        )

    if args.audit_marketing:
        return handle_audit_marketing(
            seed,
            campaign,
            args.log,
            args.upload_log,
            args.measurement_log,
            args.allow_past,
        )

    if args.audit_links:
        return handle_audit_links(seed)

    if args.upload_media:
        if args.schedule:
            raise OperatorError("Use media upload and scheduling as separate reviewed steps")
        if args.export_preview:
            raise OperatorError("Use media upload and preview export as separate reviewed steps")
        return handle_upload_media(
            seed,
            campaign,
            args.upload_media,
            base_url,
            args.api_key,
            args.upload,
            args.upload_log,
            args.min_free_gb,
        )

    replacements = placeholder_overrides(args.placeholder, args.integration)
    payloads = copy.deepcopy(selected_payloads(seed, args.label))
    payloads = replace_placeholders(payloads, replacements)

    unresolved = find_placeholders(payloads)
    warnings: list[str] = []
    for payload in payloads:
        warnings.extend(validate_payload(payload, args.allow_past))

    print(f"Campaign: {campaign}")
    print(f"Postiz: {base_url}")
    print(f"Mode: {'SCHEDULE' if args.schedule else 'DRY RUN'}")
    print(f"Payloads: {', '.join(payload['label'] for payload in payloads)}")

    if unresolved:
        print("\nUnresolved placeholders:")
        for item in unresolved:
            print(f"  - {item}")
        if args.schedule:
            raise OperatorError("Refusing to schedule with unresolved placeholders")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    print("\nResolved request preview:")
    for payload in payloads:
        label = payload["label"]
        date = payload["body"]["date"]
        post_count = len(payload["body"]["posts"])
        content_count = sum(len(post["value"]) for post in payload["body"]["posts"])
        print(f"  - {label}: {date}, {post_count} channel(s), {content_count} post item(s)")

    if args.export_preview:
        if unresolved:
            raise OperatorError("Refusing to export preview with unresolved placeholders")
        write_preview_export(args.export_preview, campaign, base_url, payloads, warnings, args.min_free_gb)

    if not args.schedule:
        print("\nDry-run complete. Pass --schedule only after reviewing the preview.")
        return 0

    ensure_min_free_space(ROOT, args.min_free_gb)

    if not args.api_key:
        raise OperatorError("POSTIZ_API_KEY or --api-key is required when --schedule is used")

    log_entries: list[dict[str, Any]] = []
    for payload in payloads:
        response = postiz_request(
            base_url,
            args.api_key,
            payload["method"],
            payload["endpoint"],
            payload["body"],
        )
        log_entries.append(
            {
                "label": payload["label"],
                "scheduledAt": datetime.now(timezone.utc).isoformat(),
                "postizBaseUrl": base_url,
                "endpoint": payload["endpoint"],
                "requestDate": payload["body"]["date"],
                "response": response,
            }
        )
        print(f"Scheduled {payload['label']}")

    append_schedule_log(args.log, campaign, log_entries)
    print(f"Updated schedule log: {args.log}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OperatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
