from __future__ import annotations

import json
from pathlib import Path

from src.health.publish_policy import (
    apply_publish_policy,
    is_hard_failure,
)


def test_403_is_uncertain_not_hard_failure() -> None:
    assert is_hard_failure(
        {
            "classification_reason": "http_error",
            "http_status": 403,
        }
    ) is False


def test_404_is_hard_failure() -> None:
    assert is_hard_failure(
        {
            "classification_reason": "http_error",
            "http_status": 404,
        }
    ) is True


def test_drm_and_expired_token_are_hard_failures() -> None:
    assert is_hard_failure(
        {
            "classification_reason": "hls_drm_detected",
        }
    ) is True

    assert is_hard_failure(
        {
            "classification_reason": "token_expired",
        }
    ) is True


def test_publish_policy_removes_only_hard_failures(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    output.mkdir()

    playlist = (
        "#EXTM3U\n"
        "#EXTINF:-1,Good\n"
        "https://tv.test/good.m3u8\n"
        "#EXTINF:-1,Geo\n"
        "https://tv.test/geo.m3u8\n"
        "#EXTINF:-1,Dead\n"
        "https://tv.test/dead.m3u8\n"
        "#EXTINF:-1,DRM\n"
        "https://tv.test/drm.m3u8\n"
    )

    (output / "playlist.m3u").write_text(
        playlist,
        encoding="utf-8",
    )
    (output / "playlist_samsung.m3u").write_text(
        playlist,
        encoding="utf-8",
    )

    health = {
        "enabled": True,
        "channels": [
            {
                "stream_url": (
                    "https://tv.test/good.m3u8"
                ),
                "status": "online",
                "classification_reason": (
                    "hls_segment_verified"
                ),
                "http_status": 200,
            },
            {
                "stream_url": (
                    "https://tv.test/geo.m3u8"
                ),
                "status": "offline",
                "classification_reason": (
                    "http_error"
                ),
                "http_status": 403,
            },
            {
                "stream_url": (
                    "https://tv.test/dead.m3u8"
                ),
                "status": "offline",
                "classification_reason": (
                    "http_error"
                ),
                "http_status": 404,
            },
            {
                "stream_url": (
                    "https://tv.test/drm.m3u8"
                ),
                "status": "offline",
                "classification_reason": (
                    "hls_drm_detected"
                ),
                "http_status": 200,
            },
        ],
    }

    (output / "health.json").write_text(
        json.dumps(health),
        encoding="utf-8",
    )

    report = apply_publish_policy(tmp_path)

    assert report["enabled"] is True

    filtered = (
        output / "playlist.m3u"
    ).read_text(encoding="utf-8")

    assert "good.m3u8" in filtered
    assert "geo.m3u8" in filtered
    assert "dead.m3u8" not in filtered
    assert "drm.m3u8" not in filtered

    stats = report["files"][0]
    assert stats["entries_seen"] == 4
    assert stats["entries_published"] == 2
    assert stats["hard_failures_removed"] == 2
    assert stats["uncertain_kept"] == 1


def test_disabled_health_does_not_modify_playlist(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    output.mkdir()

    playlist_path = output / "playlist.m3u"
    original = (
        "#EXTM3U\n"
        "#EXTINF:-1,Channel\n"
        "https://tv.test/live.m3u8\n"
    )
    playlist_path.write_text(
        original,
        encoding="utf-8",
    )

    (output / "health.json").write_text(
        json.dumps(
            {
                "enabled": False,
                "channels": [],
            }
        ),
        encoding="utf-8",
    )

    report = apply_publish_policy(tmp_path)

    assert report["enabled"] is False
    assert report["reason"] == "health_disabled"
    assert (
        playlist_path.read_text(
            encoding="utf-8"
        )
        == original
    )
