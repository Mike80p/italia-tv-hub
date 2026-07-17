from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.settings import Settings


def write_settings(
    path: Path,
    payload: dict[str, object],
) -> None:
    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )


def legacy_payload() -> dict[str, object]:
    return {
        "output_file": (
            "output/playlist.m3u"
        ),
        "report_file": (
            "output/report.json"
        ),
        "health_file": (
            "output/health.json"
        ),
        "request_timeout_seconds": 20,
        "retry_count": 2,
        "user_agent": "test-agent",
        "health_enabled": False,
        "health_timeout_seconds": 10,
        "health_max_workers": 4,
        "publish_only_online": False,
    }


def test_legacy_settings_remain_compatible(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "settings.json"
    )

    write_settings(
        path,
        legacy_payload(),
    )

    settings = Settings.load(
        path
    )

    assert settings.epg_enabled is False
    assert (
        settings.epg_file
        == "output/epg.xml"
    )
    assert (
        settings.epg_report_file
        == "output/epg-report.json"
    )
    assert settings.epg_public_url == ""
    assert (
        settings.epg_timeout_seconds
        == 30
    )
    assert settings.epg_sources == ()


def test_epg_settings_are_loaded(
    tmp_path: Path,
) -> None:
    payload = legacy_payload()

    payload.update(
        {
            "epg_enabled": True,
            "epg_file": (
                "output/epg.xml"
            ),
            "epg_report_file": (
                "output/epg-report.json"
            ),
            "epg_public_url": (
                "https://example.test/"
                "epg.xml"
            ),
            "epg_timeout_seconds": 45,
            "epg_sources": [
                (
                    "https://example.test/"
                    "first.xml"
                ),
                (
                    "https://example.test/"
                    "second.xml.gz"
                ),
            ],
        }
    )

    path = (
        tmp_path
        / "settings.json"
    )

    write_settings(
        path,
        payload,
    )

    settings = Settings.load(
        path
    )

    assert settings.epg_enabled is True
    assert (
        settings.epg_timeout_seconds
        == 45
    )
    assert settings.epg_sources == (
        (
            "https://example.test/"
            "first.xml"
        ),
        (
            "https://example.test/"
            "second.xml.gz"
        ),
    )


def test_duplicate_epg_sources_are_removed(
    tmp_path: Path,
) -> None:
    payload = legacy_payload()

    payload["epg_sources"] = [
        "https://example.test/epg.xml",
        " https://example.test/epg.xml ",
        "",
    ]

    path = (
        tmp_path
        / "settings.json"
    )

    write_settings(
        path,
        payload,
    )

    settings = Settings.load(
        path
    )

    assert settings.epg_sources == (
        "https://example.test/epg.xml",
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        ("true", True),
        ("false", False),
        (1, True),
        (0, False),
    ],
)
def test_boolean_values_are_normalized(
    tmp_path: Path,
    value: object,
    expected: bool,
) -> None:
    payload = legacy_payload()
    payload["epg_enabled"] = value

    if expected:
        payload[
            "epg_public_url"
        ] = (
            "https://example.test/"
            "epg.xml"
        )

    path = (
        tmp_path
        / "settings.json"
    )

    write_settings(
        path,
        payload,
    )

    settings = Settings.load(
        path
    )

    assert (
        settings.epg_enabled
        is expected
    )


def test_enabled_epg_requires_public_url(
    tmp_path: Path,
) -> None:
    payload = legacy_payload()
    payload["epg_enabled"] = True

    path = (
        tmp_path
        / "settings.json"
    )

    write_settings(
        path,
        payload,
    )

    with pytest.raises(
        ValueError,
        match="epg_public_url",
    ):
        Settings.load(
            path
        )


def test_invalid_epg_timeout_is_rejected(
    tmp_path: Path,
) -> None:
    payload = legacy_payload()
    payload[
        "epg_timeout_seconds"
    ] = 0

    path = (
        tmp_path
        / "settings.json"
    )

    write_settings(
        path,
        payload,
    )

    with pytest.raises(
        ValueError,
        match="epg_timeout_seconds",
    ):
        Settings.load(
            path
        )


def test_direct_construction_remains_compatible() -> None:
    settings = Settings(
        "output/playlist.m3u",
        "output/report.json",
        "output/health.json",
        20,
        2,
        "test-agent",
        False,
        10,
        4,
        False,
    )

    assert settings.epg_enabled is False
    assert settings.epg_sources == ()
