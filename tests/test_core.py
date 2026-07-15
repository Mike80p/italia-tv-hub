from __future__ import annotations

import json
import re
from pathlib import Path

from src.core.application import Application


ROOT = Path(__file__).resolve().parents[1]
PLAYLIST_PATH = ROOT / "output/playlist.m3u"
REPORT_PATH = ROOT / "output/report.json"


def test_application_contract() -> None:
    assert isinstance(
        Application.VERSION,
        str,
    )

    assert re.fullmatch(
        r"\d+\.\d+\.\d+",
        Application.VERSION,
    )

    assert callable(
        Application.run
    )


def test_published_playlist_is_valid() -> None:
    assert PLAYLIST_PATH.exists()
    assert PLAYLIST_PATH.is_file()

    playlist_text = (
        PLAYLIST_PATH.read_text(
            encoding="utf-8",
        )
    )

    assert playlist_text.startswith(
        "#EXTM3U"
    )

    channel_count = playlist_text.count(
        "#EXTINF:"
    )

    assert channel_count > 0


def test_published_report_matches_playlist() -> None:
    assert REPORT_PATH.exists()
    assert REPORT_PATH.is_file()

    report = json.loads(
        REPORT_PATH.read_text(
            encoding="utf-8",
        )
    )

    playlist_text = (
        PLAYLIST_PATH.read_text(
            encoding="utf-8",
        )
    )

    channel_count = playlist_text.count(
        "#EXTINF:"
    )

    assert report["project"] == (
        "Italia TV Hub"
    )

    assert isinstance(
        report["version"],
        str,
    )

    assert re.fullmatch(
        r"\d+\.\d+\.\d+",
        report["version"],
    )

    assert report["channels"] == (
        channel_count
    )

    assert report["channels"] > 0
