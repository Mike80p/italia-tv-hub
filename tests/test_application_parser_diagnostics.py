from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.core.application as application_module
from src.catalog.source_registry import SourceRegistry
from src.core.application import Application
from src.downloader.client import (
    DownloadAttempt,
    DownloadResult,
)
from src.models.channel import Channel
from src.models.source import Source
from src.parser.m3u import M3UParser
from src.registry.channel_registry import ChannelRegistry


PLAYLIST_WITH_ISSUES = """
#EXTM3U
#EXTINF:-1 tvg-id="rai-1" group-title="Generali",Rai 1
https://stream.test/rai1
#EXTINF:-1,
https://stream.test/missing-name
https://stream.test/orphan
#EXTINF:-1,Rai 2
"""


class FakeDetailedDownloader:
    def clear_history(self) -> None:
        pass

    def fetch_detailed(
        self,
        source: Source,
    ) -> DownloadResult:
        payload = PLAYLIST_WITH_ISSUES.encode(
            "utf-8"
        )

        return DownloadResult(
            source_id=source.id,
            requested_url=source.url,
            final_url=source.url,
            content=PLAYLIST_WITH_ISSUES,
            bytes_downloaded=len(payload),
            encoding="utf-8",
            content_type=(
                "application/x-mpegurl"
            ),
            http_status=200,
            attempts=(
                DownloadAttempt(
                    number=1,
                    status="success",
                    elapsed_ms=4,
                    http_status=200,
                ),
            ),
            total_elapsed_ms=4,
            is_remote=True,
        )


class FakeMerger:
    def merge(
        self,
        channels: list[Channel],
    ) -> list[Channel]:
        return list(channels)


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


class HealthCheckerMustNotRun:
    def check_many(self, channels):
        raise AssertionError(
            "Health checker non previsto"
        )


class LegacyParser:
    def parse(
        self,
        content: str,
        source_id: str,
    ) -> list[Channel]:
        return [
            Channel(
                "Rai 1",
                "https://stream.test/rai1",
                "Generali",
                "rai-1",
                "Rai 1",
                "",
                source_id,
                {},
                [],
            )
        ]


def build_application(
    root: Path,
    parser,
) -> Application:
    application = Application.__new__(
        Application
    )

    application.root = root

    application.settings = SimpleNamespace(
        health_enabled=False,
        publish_only_online=False,
        output_file="output/playlist.m3u",
        report_file="output/report.json",
        health_file="output/health.json",
    )

    application.downloader = (
        FakeDetailedDownloader()
    )

    application.parser = parser
    application.merger = FakeMerger()

    application.source_registry = (
        SourceRegistry()
    )

    application.registry = (
        ChannelRegistry()
    )

    application.exporter = FakeExporter()

    application.health_checker = (
        HealthCheckerMustNotRun()
    )

    return application


def test_application_writes_parser_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Source(
        id="test-source",
        name="Test source",
        url=(
            "https://example.test/"
            "playlist.m3u"
        ),
    )

    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: [source],
    )

    application = build_application(
        tmp_path,
        M3UParser(),
    )

    assert application.run() == 0

    report = json.loads(
        (
            tmp_path
            / "output/report.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert report["version"] == "0.8.0"
    assert report["channels"] == 1

    source_result = report["sources"][0]

    assert source_result["status"] == "ok"
    assert source_result["channels"] == 1

    parser_stats = source_result[
        "parser_stats"
    ]

    assert parser_stats[
        "extinf_records"
    ] == 3

    assert parser_stats[
        "channels_created"
    ] == 1

    assert parser_stats[
        "missing_name"
    ] == 1

    assert parser_stats[
        "missing_url"
    ] == 1

    assert parser_stats[
        "orphan_lines"
    ] == 1

    assert parser_stats[
        "skipped_records"
    ] == 2

    assert source_result[
        "parser_issue_count"
    ] == 3

    issue_codes = {
        issue["code"]
        for issue in source_result[
            "parser_issues"
        ]
    }

    assert issue_codes == {
        "missing_name",
        "missing_url",
        "orphan_line",
    }

    assert (
        report[
            "parser_sources_processed"
        ]
        == 1
    )

    assert (
        report[
            "parser_extinf_records"
        ]
        == 3
    )

    assert (
        report[
            "parser_channels_created"
        ]
        == 1
    )

    assert (
        report[
            "parser_skipped_records"
        ]
        == 2
    )

    assert (
        report["parser_issue_count"]
        == 3
    )

    assert report["parser_summary"][
        "missing_name"
    ] == 1

    assert report["parser_summary"][
        "missing_url"
    ] == 1

    assert report["parser_summary"][
        "orphan_lines"
    ] == 1


def test_legacy_parser_remains_supported(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Source(
        id="legacy-source",
        name="Legacy source",
        url=(
            "https://example.test/"
            "legacy.m3u"
        ),
    )

    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: [source],
    )

    application = build_application(
        tmp_path,
        LegacyParser(),
    )

    assert application.run() == 0

    report = json.loads(
        (
            tmp_path
            / "output/report.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    source_result = report["sources"][0]

    assert source_result["channels"] == 1
    assert "parser_stats" not in source_result

    assert (
        report[
            "parser_sources_processed"
        ]
        == 0
    )

    assert (
        report[
            "parser_issue_count"
        ]
        == 0
    )

    assert report["channels"] == 1