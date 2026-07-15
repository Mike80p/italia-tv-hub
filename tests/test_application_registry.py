from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import src.core.application as application_module
from src.core.application import Application
from src.models.channel import Channel
from src.models.source import Source
from src.registry.channel_registry import ChannelRegistry


def make_channel(
    name: str,
    stream_url: str,
    *,
    source_id: str,
    group: str = "Generali",
    tvg_id: str = "",
    tvg_name: str = "",
) -> Channel:
    return Channel(
        name,
        stream_url,
        group,
        tvg_id,
        tvg_name,
        "",
        source_id,
        {},
        [],
    )


class FakeDownloader:
    """
    Simula il download.

    Restituisce l'id della sorgente come contenuto, così il parser
    può riconoscere quale playlist deve simulare.
    """

    def __init__(self) -> None:
        self.requested_sources: list[Source] = []

    def fetch(self, source: Source) -> str:
        self.requested_sources.append(source)
        return source.id


class FakeParser:
    """
    Simula il parser M3U usando canali già preparati.
    """

    def __init__(
        self,
        channels_by_source: dict[str, list[Channel]],
    ) -> None:
        self.channels_by_source = channels_by_source
        self.calls: list[tuple[str, str]] = []

    def parse(
        self,
        content: str,
        source_id: str,
    ) -> list[Channel]:
        self.calls.append(
            (
                content,
                source_id,
            )
        )

        return list(
            self.channels_by_source.get(
                source_id,
                [],
            )
        )


class FakeMerger:
    """
    Registra i canali ricevuti dal merger.

    Non applica ulteriori modifiche perché in questo test vogliamo
    verificare la deduplicazione del Registry.
    """

    def __init__(self) -> None:
        self.received_batches: list[
            list[Channel]
        ] = []

    def merge(
        self,
        channels: list[Channel],
    ) -> list[Channel]:
        batch = list(channels)
        self.received_batches.append(batch)
        return batch


class FakeExporter:
    """
    Registra ciò che Application invia all'exporter.
    """

    def __init__(self) -> None:
        self.calls: list[
            tuple[Path, list[Channel]]
        ] = []

    def write(
        self,
        output_path: Path,
        channels: list[Channel],
    ) -> None:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        exported_channels = list(channels)

        self.calls.append(
            (
                output_path,
                exported_channels,
            )
        )

        output_path.write_text(
            "\n".join(
                channel.stream_url
                for channel in exported_channels
            ),
            encoding="utf-8",
        )


class HealthCheckerMustNotRun:
    """
    Il test disabilita l'Health Engine.

    Se Application tenta comunque di eseguirlo, il test fallisce.
    """

    def check_many(
        self,
        channels: list[Channel],
    ) -> list[Any]:
        raise AssertionError(
            "Health checker chiamato nonostante "
            "health_enabled=False"
        )


def build_application(
    root: Path,
    channels_by_source: dict[
        str,
        list[Channel],
    ],
) -> Application:
    """
    Costruisce Application senza eseguire __init__.

    In questo modo il test non dipende da:
    - configurazioni reali;
    - rete;
    - playlist esterne;
    - Health Engine reale;
    - filesystem del progetto.
    """

    application = Application.__new__(
        Application
    )

    application.root = root

    application.settings = SimpleNamespace(
        health_enabled=False,
        publish_only_online=False,
        output_file="output/italia-tv-hub.m3u",
        report_file="output/report.json",
        health_file="output/health.json",
    )

    application.downloader = FakeDownloader()

    application.parser = FakeParser(
        channels_by_source
    )

    application.merger = FakeMerger()
    application.registry = ChannelRegistry()
    application.exporter = FakeExporter()

    application.health_checker = (
        HealthCheckerMustNotRun()
    )

    return application


def test_application_uses_registry_before_merger(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_a = Source(
        id="source-a",
        name="Sorgente A",
        url="https://example.test/a.m3u",
        enabled=True,
        priority=10,
    )

    source_b = Source(
        id="source-b",
        name="Sorgente B",
        url="https://example.test/b.m3u",
        enabled=True,
        priority=20,
    )

    rai_1 = make_channel(
        "Rai 1",
        "https://stream.test/rai1",
        source_id="source-a",
        tvg_id="rai-1",
    )

    rai_2 = make_channel(
        "Rai 2",
        "https://stream.test/rai2",
        source_id="source-a",
        tvg_id="rai-2",
    )

    # Stesso stream_url di rai_1:
    # deve essere eliminato dal Registry.
    rai_1_duplicate = make_channel(
        "Rai Uno HD",
        "https://stream.test/rai1",
        source_id="source-b",
        tvg_id="rai-1-hd",
    )

    canale_5 = make_channel(
        "Canale 5",
        "https://stream.test/canale5",
        source_id="source-b",
        tvg_id="canale-5",
    )

    sources = [
        source_a,
        source_b,
    ]

    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: sources,
    )

    application = build_application(
        tmp_path,
        {
            "source-a": [
                rai_1,
                rai_2,
            ],
            "source-b": [
                rai_1_duplicate,
                canale_5,
            ],
        },
    )

    result = application.run()

    assert result == 0

    assert len(
        application.downloader.requested_sources
    ) == 2

    assert (
        application.downloader.requested_sources
        == sources
    )

    assert application.parser.calls == [
        (
            "source-a",
            "source-a",
        ),
        (
            "source-b",
            "source-b",
        ),
    ]

    # Il merger deve ricevere solo tre canali,
    # non i quattro canali inizialmente analizzati.
    assert len(
        application.merger.received_batches
    ) == 1

    merger_channels = (
        application.merger.received_batches[0]
    )

    assert merger_channels == [
        rai_1,
        rai_2,
        canale_5,
    ]

    assert rai_1_duplicate not in (
        merger_channels
    )

    assert len(application.registry) == 3

    assert application.registry.snapshot() == (
        rai_1,
        rai_2,
        canale_5,
    )

    assert len(
        application.exporter.calls
    ) == 1

    export_path, exported_channels = (
        application.exporter.calls[0]
    )

    assert export_path == (
        tmp_path
        / "output/italia-tv-hub.m3u"
    )

    assert exported_channels == [
        rai_1,
        rai_2,
        canale_5,
    ]

    assert export_path.exists()

    report_path = (
        tmp_path
        / "output/report.json"
    )

    health_path = (
        tmp_path
        / "output/health.json"
    )

    assert report_path.exists()
    assert health_path.exists()

    report = json.loads(
        report_path.read_text(
            encoding="utf-8",
        )
    )

    assert report["project"] == (
        "Italia TV Hub"
    )

    assert report["sources_enabled"] == 2
    assert report["sources_ok"] == 2
    assert report["sources_error"] == 0

    assert report["channels_parsed"] == 4
    assert report["channels_before_merge"] == 3

    assert (
        report[
            "registry_duplicates_removed"
        ]
        == 1
    )

    assert (
        report[
            "merger_duplicates_removed"
        ]
        == 0
    )

    assert report["duplicates_removed"] == 1
    assert report["channels"] == 3

    assert report["registry"] == {
        "channels": 3,
        "sources": 2,
        "groups": 1,
        "tvg_ids": 3,
    }

    assert report["sources"][0] == {
        "id": "source-a",
        "name": "Sorgente A",
        "status": "ok",
        "channels": 2,
        "registered": 2,
        "duplicates_skipped": 0,
    }

    assert report["sources"][1] == {
        "id": "source-b",
        "name": "Sorgente B",
        "status": "ok",
        "channels": 2,
        "registered": 1,
        "duplicates_skipped": 1,
    }


def test_second_run_does_not_accumulate_channels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Source(
        id="source-a",
        name="Sorgente A",
        url="https://example.test/a.m3u",
    )

    rai_1 = make_channel(
        "Rai 1",
        "https://stream.test/rai1",
        source_id="source-a",
        tvg_id="rai-1",
    )

    rai_2 = make_channel(
        "Rai 2",
        "https://stream.test/rai2",
        source_id="source-a",
        tvg_id="rai-2",
    )

    monkeypatch.setattr(
        application_module,
        "load_sources",
        lambda _: [source],
    )

    application = build_application(
        tmp_path,
        {
            "source-a": [
                rai_1,
                rai_2,
            ],
        },
    )

    first_result = application.run()
    second_result = application.run()

    assert first_result == 0
    assert second_result == 0

    # Se registry.clear() non funzionasse,
    # alla seconda esecuzione troveremmo dati accumulati.
    assert len(application.registry) == 2

    assert application.registry.snapshot() == (
        rai_1,
        rai_2,
    )

    assert len(
        application.merger.received_batches
    ) == 2

    assert (
        application.merger.received_batches[0]
        == [
            rai_1,
            rai_2,
        ]
    )

    assert (
        application.merger.received_batches[1]
        == [
            rai_1,
            rai_2,
        ]
    )

    assert len(
        application.exporter.calls
    ) == 2

    assert (
        application.exporter.calls[0][1]
        == [
            rai_1,
            rai_2,
        ]
    )

    assert (
        application.exporter.calls[1][1]
        == [
            rai_1,
            rai_2,
        ]
    )

    report_path = (
        tmp_path
        / "output/report.json"
    )

    report = json.loads(
        report_path.read_text(
            encoding="utf-8",
        )
    )

    assert report["channels_parsed"] == 2
    assert report["channels"] == 2
    assert report["duplicates_removed"] == 0