from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


HARD_FAILURE_REASONS = frozenset(
    {
        "country_mismatch",
        "hls_drm_detected",
        "hls_invalid_media_segment",
        "hls_no_media_segment",
        "hls_segment_token_expired",
        "hls_unsupported_codec",
        "non_media_payload",
        "token_expired",
    }
)

HARD_HTTP_STATUSES = frozenset({404, 410})


@dataclass(frozen=True, slots=True)
class PublishPolicyStats:
    file: str
    entries_seen: int
    entries_published: int
    hard_failures_removed: int
    uncertain_kept: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_hard_failure(result: dict[str, Any]) -> bool:
    reason = str(
        result.get("classification_reason", "")
    ).strip()

    if reason in HARD_FAILURE_REASONS:
        return True

    http_status = _as_int(result.get("http_status"))
    segment_status = _as_int(
        result.get("segment_http_status")
    )

    if reason == "http_error":
        return http_status in HARD_HTTP_STATUSES

    if reason == "hls_segment_http_error":
        return segment_status in HARD_HTTP_STATUSES

    return False


def _result_by_url(
    health_document: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    channels = health_document.get("channels", [])
    if not isinstance(channels, list):
        return {}

    result: dict[str, dict[str, Any]] = {}
    for item in channels:
        if not isinstance(item, dict):
            continue
        url = str(item.get("stream_url", "")).strip()
        if url:
            result[url] = item
    return result


def _entry_url(lines: list[str]) -> str:
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _split_playlist(
    text: str,
) -> tuple[list[str], list[list[str]]]:
    header: list[str] = []
    entries: list[list[str]] = []
    current: list[str] | None = None

    for line in text.splitlines():
        if line.startswith("#EXTINF:"):
            if current is not None:
                entries.append(current)
            current = [line]
            continue

        if current is None:
            header.append(line)
        else:
            current.append(line)

    if current is not None:
        entries.append(current)

    return header, entries


def filter_playlist_file(
    playlist_path: Path,
    health_document: dict[str, Any],
) -> PublishPolicyStats:
    if not playlist_path.exists():
        return PublishPolicyStats(
            file=str(playlist_path),
            entries_seen=0,
            entries_published=0,
            hard_failures_removed=0,
            uncertain_kept=0,
        )

    text = playlist_path.read_text(
        encoding="utf-8-sig"
    )
    header, entries = _split_playlist(text)
    health_by_url = _result_by_url(
        health_document
    )

    published: list[list[str]] = []
    removed = 0
    uncertain_kept = 0

    for entry in entries:
        url = _entry_url(entry)
        health = health_by_url.get(url)

        if health is not None and is_hard_failure(
            health
        ):
            removed += 1
            continue

        if (
            health is not None
            and str(health.get("status", ""))
            != "online"
        ):
            uncertain_kept += 1

        published.append(entry)

    output_lines = list(header)
    for entry in published:
        output_lines.extend(entry)

    output = "\n".join(output_lines).rstrip() + "\n"
    playlist_path.write_text(
        output,
        encoding="utf-8",
        newline="\n",
    )

    return PublishPolicyStats(
        file=str(playlist_path),
        entries_seen=len(entries),
        entries_published=len(published),
        hard_failures_removed=removed,
        uncertain_kept=uncertain_kept,
    )


def apply_publish_policy(
    root: Path,
) -> dict[str, object]:
    health_path = root / "output/health.json"
    report_path = (
        root / "output/publish-policy.json"
    )

    if not health_path.exists():
        report = {
            "enabled": False,
            "reason": "health_report_missing",
            "files": [],
        }
        report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return report

    health_document = json.loads(
        health_path.read_text(
            encoding="utf-8-sig"
        )
    )

    if not health_document.get("enabled", False):
        report = {
            "enabled": False,
            "reason": "health_disabled",
            "files": [],
        }
        report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return report

    stats = [
        filter_playlist_file(
            root / "output/playlist.m3u",
            health_document,
        ),
        filter_playlist_file(
            root / "output/playlist_samsung.m3u",
            health_document,
        ),
    ]

    report = {
        "enabled": True,
        "policy": (
            "remove_only_demonstrated_hard_failures"
        ),
        "hard_failure_reasons": sorted(
            HARD_FAILURE_REASONS
        ),
        "hard_http_statuses": sorted(
            HARD_HTTP_STATUSES
        ),
        "files": [
            item.to_dict()
            for item in stats
        ],
    }

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return report
