from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from src.epg.generator import (
    EPGGenerator,
)
from src.epg.matcher import (
    EPGChannel,
)
from src.epg.xmltv import (
    XMLTVDocument,
    XMLTVProgramme,
    XMLTVStats,
)
from src.models.channel import Channel


def make_stats(
    *,
    channels: int,
    programmes: int,
) -> XMLTVStats:
    return XMLTVStats(
        compressed=False,
        input_bytes=100,
        xml_bytes=100,
        channels_found=channels,
        channels_created=channels,
        channel_duplicates=0,
        programmes_found=programmes,
        programmes_created=programmes,
        programme_duplicates=0,
        programmes_skipped=0,
        issue_count=0,
    )


def make_document(
    *,
    channels: tuple[
        EPGChannel,
        ...,
    ],
    programmes: tuple[
        XMLTVProgramme,
        ...,
    ],
    source_url: str = (
        "https://example.test/epg.xml"
    ),
) -> XMLTVDocument:
    return XMLTVDocument(
        channels=channels,
        programmes=programmes,
        issues=(),
        stats=make_stats(
            channels=len(
                channels
            ),
            programmes=len(
                programmes
            ),
        ),
        source_url=source_url,
    )


def make_playlist_channel(
    name: str,
    *,
    tvg_id: str = "",
    tvg_name: str = "",
    logo: str = "",
    suffix: str = "",
) -> Channel:
    return Channel(
        name=name,
        stream_url=(
            "https://stream.test/"
            + name.replace(
                " ",
                "-"
            )
            + suffix
            + ".m3u8"
        ),
        tvg_id=tvg_id,
        tvg_name=tvg_name,
        logo=logo,
        source_id="test",
    )


def test_generates_filtered_xmltv() -> None:
    playlist = (
        make_playlist_channel(
            "Rai 1",
            tvg_id="Rai1.it",
        ),
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
            ),
            EPGChannel(
                "Canale5.it",
                ("Canale 5",),
            ),
        ),
        programmes=(
            XMLTVProgramme(
                "Rai1.it",
                "20260718120000 +0200",
                "20260718123000 +0200",
                "TG1",
            ),
            XMLTVProgramme(
                "Canale5.it",
                "20260718120000 +0200",
                "20260718130000 +0200",
                "Programma Mediaset",
            ),
        ),
    )

    result = EPGGenerator().generate(
        playlist,
        (document,),
    )

    root = ET.fromstring(
        result.xml_text
    )

    channels = root.findall(
        "channel"
    )

    programmes = root.findall(
        "programme"
    )

    assert len(
        channels
    ) == 1

    assert (
        channels[0].attrib["id"]
        == "Rai1.it"
    )

    assert len(
        programmes
    ) == 1

    assert (
        programmes[0]
        .attrib["channel"]
        == "Rai1.it"
    )

    assert (
        programmes[0]
        .findtext("title")
        == "TG1"
    )


def test_multiple_playlist_streams_share_one_epg_channel() -> None:
    playlist = (
        make_playlist_channel(
            "Rai 1 HD",
            tvg_id="Rai1.it",
            suffix="-hd",
        ),
        make_playlist_channel(
            "Rai 1 SD",
            tvg_id="Rai1.it",
            suffix="-sd",
        ),
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
            ),
        ),
        programmes=(),
    )

    result = EPGGenerator().generate(
        playlist,
        (document,),
    )

    assert (
        result.stats
        .matched_playlist_channels
        == 2
    )

    assert (
        result.stats.output_channels
        == 1
    )


def test_duplicate_programmes_across_documents_are_removed() -> None:
    programme_basic = XMLTVProgramme(
        "Rai1.it",
        "20260718120000 +0200",
        "20260718123000 +0200",
        "TG1",
    )

    programme_rich = XMLTVProgramme(
        "rai1.it",
        "20260718120000 +0200",
        "20260718123000 +0200",
        "TG1",
        description="Telegiornale",
        categories=("News",),
    )

    first = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
            ),
        ),
        programmes=(
            programme_basic,
        ),
        source_url=(
            "https://example.test/a.xml"
        ),
    )

    second = make_document(
        channels=(
            EPGChannel(
                "rai1.it",
                ("Rai Uno",),
            ),
        ),
        programmes=(
            programme_rich,
        ),
        source_url=(
            "https://example.test/b.xml"
        ),
    )

    playlist = (
        make_playlist_channel(
            "Rai 1",
            tvg_id="Rai1.it",
        ),
    )

    result = EPGGenerator().generate(
        playlist,
        (
            first,
            second,
        ),
    )

    assert (
        result.stats
        .programme_duplicates_removed
        == 1
    )

    assert (
        result.stats.output_programmes
        == 1
    )

    assert (
        result.output_programmes[0]
        .description
        == "Telegiornale"
    )

    assert (
        result.output_channels[0]
        .display_names
        == (
            "Rai 1",
            "Rai Uno",
        )
    )


def test_apply_matches_updates_playlist_metadata() -> None:
    playlist_channel = (
        make_playlist_channel(
            "Rai Uno HD"
        )
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
                icon_url=(
                    "https://example.test/"
                    "rai1.png"
                ),
            ),
        ),
        programmes=(),
    )

    result = EPGGenerator().generate(
        (
            playlist_channel,
        ),
        (
            document,
        ),
    )

    updated = (
        EPGGenerator.apply_matches(
            result
        )
    )

    assert updated == 1

    assert (
        playlist_channel.tvg_id
        == "Rai1.it"
    )

    assert (
        playlist_channel.tvg_name
        == "Rai 1"
    )

    assert (
        playlist_channel.logo
        == (
            "https://example.test/"
            "rai1.png"
        )
    )


def test_existing_name_and_logo_are_not_overwritten() -> None:
    playlist_channel = (
        make_playlist_channel(
            "Rai 1",
            tvg_id="Rai1.it",
            tvg_name="Nome personalizzato",
            logo=(
                "https://example.test/"
                "custom.png"
            ),
        )
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
                icon_url=(
                    "https://example.test/"
                    "epg.png"
                ),
            ),
        ),
        programmes=(),
    )

    result = EPGGenerator().generate(
        (
            playlist_channel,
        ),
        (
            document,
        ),
    )

    EPGGenerator.apply_matches(
        result
    )

    assert (
        playlist_channel.tvg_name
        == "Nome personalizzato"
    )

    assert (
        playlist_channel.logo
        == (
            "https://example.test/"
            "custom.png"
        )
    )


def test_unmatched_channels_are_excluded_from_xml() -> None:
    playlist = (
        make_playlist_channel(
            "Canale locale sconosciuto"
        ),
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
            ),
        ),
        programmes=(),
    )

    result = EPGGenerator().generate(
        playlist,
        (
            document,
        ),
    )

    root = ET.fromstring(
        result.xml_text
    )

    assert root.findall(
        "channel"
    ) == []

    assert (
        result.stats
        .unmatched_playlist_channels
        == 1
    )


def test_channels_without_programmes_are_counted() -> None:
    playlist = (
        make_playlist_channel(
            "Rai 1",
            tvg_id="Rai1.it",
        ),
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
            ),
        ),
        programmes=(),
    )

    result = EPGGenerator().generate(
        playlist,
        (
            document,
        ),
    )

    assert (
        result.stats
        .channels_without_programmes
        == 1
    )


def test_write_creates_epg_and_json_report(
    tmp_path: Path,
) -> None:
    playlist = (
        make_playlist_channel(
            "Rai 1",
            tvg_id="Rai1.it",
        ),
    )

    document = make_document(
        channels=(
            EPGChannel(
                "Rai1.it",
                ("Rai 1",),
            ),
        ),
        programmes=(),
    )

    generator = EPGGenerator()

    result = generator.generate(
        playlist,
        (
            document,
        ),
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

    generator.write(
        epg_path,
        report_path,
        result,
    )

    assert epg_path.exists()
    assert report_path.exists()

    report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        report["stats"]
        ["output_channels"]
        == 1
    )


def test_special_characters_are_escaped_by_xml_writer() -> None:
    playlist = (
        make_playlist_channel(
            "Rai & Cultura",
            tvg_id="RaiCultura.it",
        ),
    )

    document = make_document(
        channels=(
            EPGChannel(
                "RaiCultura.it",
                ("Rai & Cultura",),
            ),
        ),
        programmes=(
            XMLTVProgramme(
                "RaiCultura.it",
                "20260718120000 +0200",
                "",
                "Arte < Storia",
                description="A & B",
            ),
        ),
    )

    result = EPGGenerator().generate(
        playlist,
        (
            document,
        ),
    )

    assert (
        "Rai &amp; Cultura"
        in result.xml_text
    )

    assert (
        "Arte &lt; Storia"
        in result.xml_text
    )

    ET.fromstring(
        result.xml_text
    )


def test_invalid_input_types_are_rejected() -> None:
    generator = EPGGenerator()

    try:
        generator.generate(
            ("not-channel",),
            (),
        )
    except TypeError as exc:
        assert (
            "playlist_channels"
            in str(exc)
        )
    else:
        raise AssertionError(
            "TypeError non sollevato"
        )

    try:
        generator.generate(
            (),
            ("not-document",),
        )
    except TypeError as exc:
        assert "documents" in str(
            exc
        )
    else:
        raise AssertionError(
            "TypeError non sollevato"
        )
