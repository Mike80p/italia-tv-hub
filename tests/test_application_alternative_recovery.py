from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.core.application as application_module
from src.catalog.source_registry import SourceRegistry
from src.core.application import Application
from src.health.checker import HealthResult
from src.merger.merger import ChannelMerger
from src.models.channel import Channel
from src.models.source import Source
from src.registry.channel_registry import ChannelRegistry


PRIMARY_URL = "https://primary.test/rai1.m3u8"
BACKUP_URL = "https://backup.test/rai1.m3u8"


def make_channel(
    name: str,
    stream_url: str,
    source_id: str,
    *,
    tvg_id: str = "rai-1",
) -> Channel:
    return Channel(
        name,
        stream_url,
        "RAI",
        tvg_id,
        name,
        "",
        source_id,
        {},
        [],
    )


class FakeDownloader:
    def clear_history(self) -> None:
        pass

    def fetch(
        self,
        source: Source,
    ) -> str:
        return "#EXTM3U\n"


class FakeParser:
    def __init__(
        self,
        channel_by_source: dict[
            str,
            Channel,
        ],
    ) -> None:
        self.channel_by_source = (
            channel_by_source
        )

    def parse(
        self,
        content: str,
        source_id: str,
    ) -> list[Channel]:
        channel = (
            self.channel_by_source.get(
                source_id
            )
        )

        return (
            [channel]
            if channel is not None
            else []
        )


class FakeHealthChecker:
    def __init__(
        self,
        statuses: dict[
            str,
            tuple[str, int],
        ],
    ) -> None:
        self.statuses = statuses
        self.checked_urls: list[
            str
        ] = []

    def check_many(
        self,
        channels: list[Channel],
    ) -> list[HealthResult]:
        results: list[
            HealthResult
        ] = []

        for channel in channels:
            self.checked_urls.append(
                channel.stream_url
            )

            status, score = (
                self.statuses[
                    channel.stream_url
                ]
            )

            results.append(
                HealthResult(
                    name=channel.name,
                    stream_url=(
                        channel.stream_url
                    ),
                    source_id=(
                        channel.source_id
                    ),
                    status=status,
                    http_status=(
                        200
                        if status
                        != "offline"
                        else 404
                    ),
                    response_ms=10,
                    content_type=(
                        "application/"
                        "vnd.apple.mpegurl"
                        if status
                        != "offline"
                        else ""
                    ),
                    final_url=(
                        channel.stream_url
                    ),
                    error=(
                        ""
                        if status
                        != "offline"
                        else "HTTPError 404"
                    ),
                    health_score=score,
                    classification_reason=(
                        "hls_signature"
                        if status
                        != "offline"
                        else "http_error"
                    ),
                    bytes_read=(
                        128
                        if status
                        != "offline"
                        else 0
                    ),
                    redirected=False,
                    error_type=(
                        ""
                        if status
                        != "offline"
                        else "HTTPError"
                    ),
                )
            )

        return results


class HealthCheckerMustNotRun:
    def check_many(self, channels):
        raise AssertionError(
            "Health checker non previsto"
        )


class FakeExporter:
    def write(
        self,
        output_path: Path,
        channels: list[Channel],
    ) -> None:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            "\n".join(
                channel.stream_url
                for channel in channels
            ),
            encoding="utf-8",
        )


def build_application(
    root: Path,
    *,
    channel_by_source: dict[
        str,
        Channel,
    ],
    health_checker,
    health_enabled: bool = True,
    publish_only_online: bool = True,
) -> Application:
    application = Application.__new__(
        Application
    )

    application.root = root

    application.settings = SimpleNamespace(
        health_enabled=health_enabled,
        publish_only_online=(
            publish_only_online
        ),
        output_file=(
            "output/playlist.m3u"
        ),
        report_file=(
            "output/report.json"
        ),
        health_file=(
            "output/health.json"
        ),
    )

    application.downloader = (
        FakeDownloader()
    )

    application.parser = FakeParser(
        channel_by_source
    )

    application.merger = (
        ChannelMerger()
    )

    application.source_registry = (
        SourceRegistry()
    )

    application.registry = (
        ChannelRegistry()
    )

    application.exporter = (
        FakeExporter()
    )

    application.health_checker = (
        health_checker
    )

    return application


def sources() -> list[Source]:
    return [
        Source(
            id="primary",
            name="Primary",
            url=(
                "https://source.test/"
                "primary.m3u"
            ),
            enabled=True,
            priority=10,
        ),
        Source(
            id="backup",
            name="Backup",
            url=(
                "https://source.test/"
                "backup.m3u"
            ),
            enabled=True,
            priority=20,
        ),
    ]


def read_report(
    root: Path,
) -> dict[str, object]:
    return json.loads(
        (
            root
            / "output/report.json"
        ).read_text(
            encoding="utf-8"
        )
    )


def test_offline_primary_is_recovered_from_online_alternative(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: sources(),
    )

    primary = make_channel(
        "Rai 1",
        PRIMARY_URL,
        "primary",
    )

    backup = make_channel(
        "Rai 1 HD",
        BACKUP_URL,
        "backup",
    )

    checker = FakeHealthChecker(
        {
            PRIMARY_URL: (
                "offline",
                0,
            ),
            BACKUP_URL: (
                "online",
                95,
            ),
        }
    )

    application = build_application(
        tmp_path,
        channel_by_source={
            "primary": primary,
            "backup": backup,
        },
        health_checker=checker,
    )

    assert application.run() == 0

    output = (
        tmp_path
        / "output/playlist.m3u"
    ).read_text(
        encoding="utf-8"
    )

    assert BACKUP_URL in output
    assert PRIMARY_URL not in output

    report = read_report(
        tmp_path
    )

    assert (
        report[
            "alternative_recovery_enabled"
        ]
        is True
    )

    assert (
        report[
            "recovered_from_alternative"
        ]
        == 1
    )

    assert (
        report[
            "all_candidates_failed"
        ]
        == 0
    )

    assert (
        report[
            "candidate_streams_checked"
        ]
        == 2
    )

    assert report["channels"] == 1

    assert (
        report["merger"][
            "health_ranking"
        ]
        is True
    )


def test_all_failed_group_is_removed_when_publish_only_online(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: sources(),
    )

    checker = FakeHealthChecker(
        {
            PRIMARY_URL: (
                "offline",
                0,
            ),
            BACKUP_URL: (
                "offline",
                0,
            ),
        }
    )

    application = build_application(
        tmp_path,
        channel_by_source={
            "primary": make_channel(
                "Rai 1",
                PRIMARY_URL,
                "primary",
            ),
            "backup": make_channel(
                "Rai 1 HD",
                BACKUP_URL,
                "backup",
            ),
        },
        health_checker=checker,
    )

    assert application.run() == 0

    report = read_report(
        tmp_path
    )

    assert report["channels"] == 0

    assert (
        report[
            "all_candidates_failed"
        ]
        == 1
    )

    assert (
        report[
            "channels_filtered_unavailable"
        ]
        == 1
    )


def test_better_online_alternative_can_upgrade_primary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: sources(),
    )

    checker = FakeHealthChecker(
        {
            PRIMARY_URL: (
                "online",
                65,
            ),
            BACKUP_URL: (
                "online",
                98,
            ),
        }
    )

    application = build_application(
        tmp_path,
        channel_by_source={
            "primary": make_channel(
                "Rai 1",
                PRIMARY_URL,
                "primary",
            ),
            "backup": make_channel(
                "Rai 1 HD",
                BACKUP_URL,
                "backup",
            ),
        },
        health_checker=checker,
    )

    assert application.run() == 0

    report = read_report(
        tmp_path
    )

    assert (
        report[
            "upgraded_to_better_alternative"
        ]
        == 1
    )

    assert (
        report[
            "recovered_from_alternative"
        ]
        == 0
    )

    output = (
        tmp_path
        / "output/playlist.m3u"
    ).read_text(
        encoding="utf-8"
    )

    assert output == BACKUP_URL


def test_identical_url_is_checked_only_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: sources(),
    )

    checker = FakeHealthChecker(
        {
            PRIMARY_URL: (
                "online",
                90,
            ),
        }
    )

    application = build_application(
        tmp_path,
        channel_by_source={
            "primary": make_channel(
                "Rai 1",
                PRIMARY_URL,
                "primary",
            ),
            "backup": make_channel(
                "Rai 1 HD",
                PRIMARY_URL,
                "backup",
            ),
        },
        health_checker=checker,
    )

    assert application.run() == 0

    assert checker.checked_urls == [
        PRIMARY_URL
    ]

    report = read_report(
        tmp_path
    )

    assert (
        report[
            "candidate_streams_checked"
        ]
        == 1
    )


def test_health_disabled_keeps_primary_source_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: sources(),
    )

    application = build_application(
        tmp_path,
        channel_by_source={
            "primary": make_channel(
                "Rai 1",
                PRIMARY_URL,
                "primary",
            ),
            "backup": make_channel(
                "Rai 1 HD",
                BACKUP_URL,
                "backup",
            ),
        },
        health_checker=(
            HealthCheckerMustNotRun()
        ),
        health_enabled=False,
        publish_only_online=False,
    )

    assert application.run() == 0

    output = (
        tmp_path
        / "output/playlist.m3u"
    ).read_text(
        encoding="utf-8"
    )

    assert output == PRIMARY_URL

    report = read_report(
        tmp_path
    )

    assert (
        report[
            "alternative_recovery_enabled"
        ]
        is False
    )

    assert (
        report[
            "candidate_streams_checked"
        ]
        == 0
    )
