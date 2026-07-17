from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.core.application import Application
from src.epg.downloader import (
    EPGDownloadAttempt,
    EPGDownloadError,
    EPGDownloadResult,
)
from src.epg.generator import EPGGenerator
from src.epg.xmltv import XMLTVParser
from src.models.channel import Channel


SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="Rai1.it">
    <display-name>Rai 1</display-name>
    <icon src="https://example.test/rai1.png" />
  </channel>
  <programme
    channel="Rai1.it"
    start="20260718120000 +0200"
    stop="20260718123000 +0200"
  >
    <title>TG1</title>
    <desc>Telegiornale</desc>
    <category>News</category>
  </programme>
</tv>
"""


class SuccessfulDownloader:
    def fetch(
        self,
        source_url: str,
    ) -> EPGDownloadResult:
        attempt = EPGDownloadAttempt(
            attempt_number=1,
            status="ok",
            elapsed_ms=1,
            bytes_read=len(
                SAMPLE_XML
            ),
            http_status=200,
            final_url=source_url,
            content_type=(
                "application/xml"
            ),
            retryable=False,
        )

        return EPGDownloadResult(
            source_url=source_url,
            final_url=source_url,
            data=SAMPLE_XML,
            content_type=(
                "application/xml"
            ),
            compressed=False,
            attempt_count=1,
            total_elapsed_ms=1,
            bytes_downloaded=len(
                SAMPLE_XML
            ),
            http_status=200,
            attempts=(
                attempt,
            ),
        )


class FailingDownloader:
    def fetch(
        self,
        source_url: str,
    ) -> EPGDownloadResult:
        raise EPGDownloadError(
            "Errore HTTP EPG 404",
            source_url=source_url,
            status_code=404,
            retryable=False,
        )


def build_application(
    tmp_path: Path,
    *,
    downloader: object,
    enabled: bool = True,
) -> Application:
    application = Application.__new__(
        Application
    )

    application.root = tmp_path

    application.settings = (
        SimpleNamespace(
            epg_enabled=enabled,
            epg_file=(
                "output/epg.xml"
            ),
            epg_report_file=(
                "output/epg-report.json"
            ),
            epg_public_url=(
                "https://raw.example.test/"
                "epg.xml"
            ),
            epg_sources=(
                "https://source.test/"
                "italy.xml",
            ),
        )
    )

    application.epg_downloader = (
        downloader
    )

    application.epg_parser = (
        XMLTVParser()
    )

    application.epg_generator = (
        EPGGenerator()
    )

    return application


def test_application_generates_epg_and_updates_channel(
    tmp_path: Path,
) -> None:
    application = build_application(
        tmp_path,
        downloader=(
            SuccessfulDownloader()
        ),
    )

    channel = Channel(
        name="Rai Uno HD",
        stream_url=(
            "https://stream.test/"
            "rai1.m3u8"
        ),
    )

    diagnostics = (
        application._build_epg_output(
            [channel]
        )
    )

    epg_path = (
        tmp_path
        / "output"
        / "epg.xml"
    )

    report_path = (
        tmp_path
        / "output"
        / "epg-report.json"
    )

    assert (
        diagnostics["status"]
        == "generated"
    )

    assert (
        diagnostics[
            "sources_successful"
        ]
        == 1
    )

    assert (
        diagnostics[
            "channels_matched"
        ]
        == 1
    )

    assert (
        diagnostics["programmes"]
        == 1
    )

    assert (
        channel.tvg_id
        == "Rai1.it"
    )

    assert epg_path.exists()
    assert report_path.exists()

    xml_text = epg_path.read_text(
        encoding="utf-8"
    )

    assert (
        '<channel id="Rai1.it">'
        in xml_text
    )

    report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        report["status"]
        == "generated"
    )


def test_first_failure_creates_valid_empty_epg(
    tmp_path: Path,
) -> None:
    application = build_application(
        tmp_path,
        downloader=(
            FailingDownloader()
        ),
    )

    diagnostics = (
        application._build_epg_output(
            []
        )
    )

    epg_path = (
        tmp_path
        / "output"
        / "epg.xml"
    )

    assert (
        diagnostics["status"]
        == "empty_generated"
    )

    assert epg_path.exists()

    xml_text = epg_path.read_text(
        encoding="utf-8"
    )

    assert "<tv" in xml_text


def test_failure_preserves_previous_epg(
    tmp_path: Path,
) -> None:
    application = build_application(
        tmp_path,
        downloader=(
            FailingDownloader()
        ),
    )

    epg_path = (
        tmp_path
        / "output"
        / "epg.xml"
    )

    epg_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    previous_content = (
        '<?xml version="1.0" '
        'encoding="UTF-8"?>\n'
        '<tv><channel id="Old.it" />'
        "</tv>\n"
    )

    epg_path.write_text(
        previous_content,
        encoding="utf-8",
    )

    diagnostics = (
        application._build_epg_output(
            []
        )
    )

    assert (
        diagnostics["status"]
        == "previous_preserved"
    )

    assert (
        epg_path.read_text(
            encoding="utf-8"
        )
        == previous_content
    )


def test_disabled_epg_does_not_create_file(
    tmp_path: Path,
) -> None:
    application = build_application(
        tmp_path,
        downloader=(
            SuccessfulDownloader()
        ),
        enabled=False,
    )

    diagnostics = (
        application._build_epg_output(
            []
        )
    )

    assert (
        diagnostics["status"]
        == "disabled"
    )

    assert not (
        tmp_path
        / "output"
        / "epg.xml"
    ).exists()
