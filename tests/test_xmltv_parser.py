from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from src.epg.xmltv import (
    XMLTVParseError,
    XMLTVParser,
)


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<tv generator-info-name="test">
  <channel id="Rai1.it">
    <display-name lang="en">Rai One</display-name>
    <display-name lang="it">Rai 1</display-name>
    <icon src="https://example.test/rai1.png" />
  </channel>
  <channel id="Canale5.it">
    <display-name>Canale 5</display-name>
  </channel>
  <programme
    start="20260718120000 +0200"
    stop="20260718123000 +0200"
    channel="Rai1.it"
  >
    <title lang="it">TG1</title>
    <desc lang="it">Telegiornale</desc>
    <category>News</category>
    <episode-num system="xmltv_ns">0.0.</episode-num>
  </programme>
</tv>
"""


def test_parse_basic_xmltv_document() -> None:
    document = XMLTVParser().parse_text(
        SAMPLE_XML,
        source_url=(
            "https://example.test/epg.xml"
        ),
    )

    assert (
        document.stats.channels_found
        == 2
    )

    assert (
        document.stats.channels_created
        == 2
    )

    assert (
        document.stats.programmes_created
        == 1
    )

    assert (
        document.channels[1]
        .display_names[1]
        == "Rai 1"
    )

    programme = (
        document.programmes[0]
    )

    assert programme.title == "TG1"
    assert (
        programme.description
        == "Telegiornale"
    )

    assert programme.categories == (
        "News",
    )

    assert (
        programme.source_url
        == "https://example.test/epg.xml"
    )


def test_gzip_is_detected_by_magic_bytes() -> None:
    compressed = gzip.compress(
        SAMPLE_XML.encode(
            "utf-8"
        )
    )

    document = XMLTVParser().parse_bytes(
        compressed,
        filename="guide.dat",
    )

    assert (
        document.stats.compressed
        is True
    )

    assert (
        document.stats.xml_bytes
        > document.stats.input_bytes
    )


def test_gzip_is_detected_by_filename() -> None:
    compressed = gzip.compress(
        SAMPLE_XML.encode(
            "utf-8"
        )
    )

    document = XMLTVParser().parse_bytes(
        compressed,
        filename="guide.xml.gz",
    )

    assert (
        document.stats.compressed
        is True
    )


def test_parse_file_reads_xml_and_uses_path_as_source(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "guide.xml"
    )

    path.write_text(
        SAMPLE_XML,
        encoding="utf-8",
    )

    document = XMLTVParser().parse_file(
        path
    )

    assert (
        document.source_url
        == str(path)
    )


def test_duplicate_channels_are_merged() -> None:
    xml = """<tv>
      <channel id="Rai1.it">
        <display-name>Rai 1</display-name>
      </channel>
      <channel id="rai1.it">
        <display-name>Rai Uno</display-name>
        <icon src="https://example.test/logo.png" />
      </channel>
    </tv>"""

    document = XMLTVParser().parse_text(
        xml
    )

    assert (
        document.stats.channels_created
        == 1
    )

    assert (
        document.stats.channel_duplicates
        == 1
    )

    assert (
        document.channels[0]
        .display_names
        == (
            "Rai 1",
            "Rai Uno",
        )
    )

    assert (
        document.channels[0]
        .icon_url
        == "https://example.test/logo.png"
    )


def test_duplicate_programmes_are_removed() -> None:
    xml = """<tv>
      <channel id="Rai1.it">
        <display-name>Rai 1</display-name>
      </channel>
      <programme
        channel="Rai1.it"
        start="20260718120000 +0200"
        stop="20260718123000 +0200"
      >
        <title>TG1</title>
      </programme>
      <programme
        channel="Rai1.it"
        start="20260718120000 +0200"
        stop="20260718123000 +0200"
      >
        <title>TG1</title>
      </programme>
    </tv>"""

    document = XMLTVParser().parse_text(
        xml
    )

    assert (
        document.stats.programmes_created
        == 1
    )

    assert (
        document.stats.programme_duplicates
        == 1
    )


def test_invalid_programmes_are_skipped_and_reported() -> None:
    xml = """<tv>
      <programme
        channel=""
        start="bad"
      >
        <title></title>
      </programme>
      <programme
        channel="Rai1.it"
        start="20260718120000 +0200"
      >
        <title>TG1</title>
      </programme>
    </tv>"""

    document = XMLTVParser().parse_text(
        xml
    )

    assert (
        document.stats.programmes_created
        == 1
    )

    assert (
        document.stats.programmes_skipped
        == 1
    )

    assert len(
        document.issues
    ) == 1


def test_missing_channel_id_is_reported() -> None:
    xml = """<tv>
      <channel>
        <display-name>Senza ID</display-name>
      </channel>
    </tv>"""

    document = XMLTVParser().parse_text(
        xml
    )

    assert (
        document.stats.channels_created
        == 0
    )

    assert (
        document.stats.issue_count
        == 1
    )

    assert (
        document.issues[0].kind
        == "channel_missing_id"
    )


def test_non_tv_root_is_rejected() -> None:
    with pytest.raises(
        XMLTVParseError,
        match="radice",
    ):
        XMLTVParser().parse_text(
            "<root />"
        )


def test_invalid_xml_is_rejected() -> None:
    with pytest.raises(
        XMLTVParseError,
        match="non valido",
    ):
        XMLTVParser().parse_text(
            "<tv>"
        )


def test_doctype_and_entities_are_rejected() -> None:
    xml = """<!DOCTYPE tv [
      <!ENTITY xxe SYSTEM "file:///etc/passwd">
    ]>
    <tv />"""

    with pytest.raises(
        XMLTVParseError,
        match="DTD",
    ):
        XMLTVParser().parse_text(
            xml
        )


def test_invalid_gzip_is_rejected() -> None:
    with pytest.raises(
        XMLTVParseError,
        match="GZIP",
    ):
        XMLTVParser().parse_bytes(
            b"not-gzip",
            filename="guide.xml.gz",
        )


def test_input_size_limit_is_enforced() -> None:
    parser = XMLTVParser(
        max_input_bytes=10
    )

    with pytest.raises(
        XMLTVParseError,
        match="troppo grande",
    ):
        parser.parse_bytes(
            b"<tv></tv>" + b"x" * 20
        )


def test_decompressed_size_limit_is_enforced() -> None:
    compressed = gzip.compress(
        (
            "<tv>"
            + " " * 1000
            + "</tv>"
        ).encode(
            "utf-8"
        )
    )

    parser = XMLTVParser(
        max_xml_bytes=100
    )

    with pytest.raises(
        XMLTVParseError,
        match="limite decompresso",
    ):
        parser.parse_bytes(
            compressed
        )


def test_programmes_by_channel_is_sorted() -> None:
    xml = """<tv>
      <programme
        channel="Rai1.it"
        start="20260718130000 +0200"
      >
        <title>Secondo</title>
      </programme>
      <programme
        channel="Rai1.it"
        start="20260718120000 +0200"
      >
        <title>Primo</title>
      </programme>
    </tv>"""

    document = XMLTVParser().parse_text(
        xml
    )

    grouped = (
        document.programmes_by_channel()
    )

    assert [
        item.title
        for item in grouped[
            "Rai1.it"
        ]
    ] == [
        "Primo",
        "Secondo",
    ]


def test_invalid_constructor_limits_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="max_programmes",
    ):
        XMLTVParser(
            max_programmes=0
        )
