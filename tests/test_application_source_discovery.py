from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.core.application as application_module
from src.catalog.source_registry import SourceRegistry
from src.core.application import Application
from src.discovery.client import (
    DiscoveryBatchResult,
    DiscoveryStats,
)
from src.models.channel import Channel
from src.models.source import Source
from src.registry.channel_registry import ChannelRegistry


DISCOVERED_URL = (
    "https://raw.githubusercontent.com/"
    "example/italian-tv/main/italy.m3u"
)


class FakeDiscoveryClient:
    def discover_italian_sources(
        self,
    ) -> DiscoveryBatchResult:
        source = Source(
            id="discovery-test-source",
            name="Discovery test source",
            url=DISCOVERED_URL,
            enabled=True,
            priority=200,
            kind="playlist",
            country="IT",
            language="it",
            tags=(
                "italia",
                "github",
            ),
            discovery_enabled=True,
            discovery_mode="search",
            trust_score=35,
            refresh_hours=24,
            origin="example/italian-tv",
        )

        return DiscoveryBatchResult(
            sources=(source,),
            errors=(),
            stats=DiscoveryStats(
                curated_sources=0,
                github_queries=1,
                github_items=1,
                accepted_sources=1,
                duplicates_skipped=0,
                rejected_items=0,
                errors=0,
                github_token_used=True,
            ),
        )


class FakeDownloader:
    def clear_history(self) -> None:
        pass

    def fetch(
        self,
        source: Source,
    ) -> str:
        assert source.id == (
            "discovery-test-source"
        )

        return (
            "#EXTM3U\n"
            "#EXTINF:-1,Rai Discovery Test\n"
            "https://stream.test/rai.m3u8\n"
        )


class FakeParser:
    def parse(
        self,
        content: str,
        source_id: str,
    ) -> list[Channel]:
        assert "#EXTM3U" in content

        return [
            Channel(
                "Rai Discovery Test",
                "https://stream.test/rai.m3u8",
                "RAI",
                "RaiDiscoveryTest.it",
                "Rai Discovery Test",
                "",
                source_id,
                {},
                [],
            )
        ]


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
            "#EXTM3U\n"
            + "\n".join(
                channel.stream_url
                for channel in channels
            )
            + "\n",
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

    application.downloader = FakeDownloader()
    application.parser = FakeParser()
    application.merger = FakeMerger()
    application.source_registry = (
        SourceRegistry()
    )
    application.registry = (
        ChannelRegistry()
    )
    application.discovery_client = (
        FakeDiscoveryClient()
    )
    application.exporter = FakeExporter()
    application.health_checker = (
        HealthCheckerMustNotRun()
    )

    return application


def test_application_registers_and_processes_discovered_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: [],
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

    assert report[
        "configured_sources_loaded"
    ] == 0

    assert report[
        "discovery_sources_found"
    ] == 1

    assert report[
        "discovery_sources_inserted"
    ] == 1

    assert report[
        "discovery_github_token_used"
    ] is True

    assert report["sources_total"] == 1
    assert report["channels"] == 1

    assert report["sources"][0][
        "id"
    ] == "discovery-test-source"

    discovery_report = json.loads(
        (
            tmp_path
            / "output/discovered-sources.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert discovery_report[
        "registration"
    ]["inserted"] == 1

    assert discovery_report[
        "sources"
    ][0]["url"] == DISCOVERED_URL


def test_missing_discovery_client_remains_legacy_compatible(
    tmp_path: Path,
) -> None:
    application = Application.__new__(
        Application
    )

    application.root = tmp_path

    result = application._discover_sources()

    assert result.sources == ()
    assert result.errors == ()
    assert (
        result.stats.accepted_sources
        == 0
    )
