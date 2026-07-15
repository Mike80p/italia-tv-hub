from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.core.application as application_module
from src.catalog.source_registry import SourceRegistry
from src.core.application import Application
from src.downloader.client import (
    DownloadAttempt,
    DownloadError,
    DownloadResult,
)
from src.models.channel import Channel
from src.models.source import Source
from src.registry.channel_registry import ChannelRegistry


def make_channel(
    name: str,
    stream_url: str,
    source_id: str,
) -> Channel:
    return Channel(
        name,
        stream_url,
        "Generali",
        "",
        "",
        "",
        source_id,
        {},
        [],
    )


class FakeDetailedDownloader:
    def __init__(self) -> None:
        self.history_cleared = False

    def clear_history(self) -> None:
        self.history_cleared = True

    def fetch_detailed(
        self,
        source: Source,
    ) -> DownloadResult:
        if source.id == "broken":
            attempts = (
                DownloadAttempt(
                    number=1,
                    status="error",
                    elapsed_ms=15,
                    http_status=503,
                    error_type="HTTPError",
                    error_message=(
                        "Service Unavailable"
                    ),
                ),
                DownloadAttempt(
                    number=2,
                    status="error",
                    elapsed_ms=20,
                    http_status=503,
                    error_type="HTTPError",
                    error_message=(
                        "Service Unavailable"
                    ),
                ),
            )

            raise DownloadError(
                "Download fallito per broken",
                source_id=source.id,
                url=source.url,
                attempts=attempts,
                status_code=503,
                retryable=True,
            )

        attempts = (
            DownloadAttempt(
                number=1,
                status="error",
                elapsed_ms=10,
                error_type="URLError",
                error_message="temporary",
            ),
            DownloadAttempt(
                number=2,
                status="success",
                elapsed_ms=25,
                http_status=200,
            ),
        )

        content = (
            "#EXTM3U\n"
            "#EXTINF:-1,Rai 1\n"
            "https://stream.test/rai1\n"
        )

        return DownloadResult(
            source_id=source.id,
            requested_url=source.url,
            final_url=(
                "https://cdn.test/final.m3u"
            ),
            content=content,
            bytes_downloaded=len(
                content.encode("utf-8")
            ),
            encoding="utf-8",
            content_type=(
                "application/x-mpegurl"
            ),
            http_status=200,
            attempts=attempts,
            total_elapsed_ms=35,
            is_remote=True,
        )


class FakeParser:
    def parse(
        self,
        content: str,
        source_id: str,
    ) -> list[Channel]:
        if source_id == "working":
            return [
                make_channel(
                    "Rai 1",
                    "https://stream.test/rai1",
                    source_id,
                )
            ]

        return []


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


def build_application(
    root: Path,
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

    application.parser = FakeParser()
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


def test_application_writes_success_download_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    working = Source(
        id="working",
        name="Working source",
        url=(
            "https://example.test/"
            "working.m3u"
        ),
        priority=10,
    )

    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: [working],
    )

    application = build_application(
        tmp_path
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

    assert (
        application.downloader
        .history_cleared
        is True
    )

    source_result = report["sources"][0]

    assert source_result["status"] == "ok"
    assert source_result["attempt_count"] == 2
    assert source_result["download_ms"] == 35

    assert (
        source_result[
            "bytes_downloaded"
        ]
        > 0
    )

    assert source_result["http_status"] == 200

    assert source_result["final_url"] == (
        "https://cdn.test/final.m3u"
    )

    assert source_result["retryable"] is False

    assert len(
        source_result[
            "download_attempts"
        ]
    ) == 2

    assert report["downloads_attempted"] == 1
    assert report["downloads_successful"] == 1
    assert report["downloads_failed"] == 0
    assert report["download_attempts_total"] == 2
    assert report["download_retries_total"] == 1


def test_application_writes_failed_download_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    broken = Source(
        id="broken",
        name="Broken source",
        url=(
            "https://example.test/"
            "broken.m3u"
        ),
        priority=10,
    )

    working = Source(
        id="working",
        name="Working source",
        url=(
            "https://example.test/"
            "working.m3u"
        ),
        priority=20,
    )

    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: [
            broken,
            working,
        ],
    )

    application = build_application(
        tmp_path
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

    broken_result = report["sources"][0]

    assert broken_result["id"] == "broken"
    assert broken_result["status"] == "error"
    assert broken_result["attempt_count"] == 2
    assert broken_result["download_ms"] == 35

    assert (
        broken_result["http_status"]
        == 503
    )

    assert (
        broken_result["retryable"]
        is True
    )

    assert len(
        broken_result[
            "download_attempts"
        ]
    ) == 2

    assert report["downloads_attempted"] == 2
    assert report["downloads_successful"] == 1
    assert report["downloads_failed"] == 1
    assert report["download_attempts_total"] == 4
    assert report["download_retries_total"] == 2

    # Il fallimento di una sorgente non deve
    # interrompere le sorgenti successive.
    assert report["channels"] == 1