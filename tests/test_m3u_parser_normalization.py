from __future__ import annotations

import pytest

from src.parser.m3u import M3UParser


def test_standard_playlist_is_parsed():
    parser = M3UParser()

    text = """
#EXTM3U
#EXTINF:-1 tvg-id="rai-1" tvg-name="Rai 1" group-title="Generali",Rai 1
https://stream.test/rai1
"""

    channels = parser.parse(
        text,
        "source-a",
    )

    assert len(channels) == 1

    channel = channels[0]

    assert channel.name == "Rai 1"
    assert channel.stream_url == (
        "https://stream.test/rai1"
    )
    assert channel.group == "Generali"
    assert channel.tvg_id == "rai-1"
    assert channel.tvg_name == "Rai 1"
    assert channel.source_id == "source-a"


def test_text_fields_are_normalized():
    parser = M3UParser()

    text = """
#EXTINF:-1 tvg-name="  Rai   Uno  " group-title="  Canali   TV  ",  Rai    1
  https://stream.test/rai1
"""

    channel = parser.parse(
        text,
        " source-a ",
    )[0]

    assert channel.name == "Rai 1"
    assert channel.tvg_name == "Rai Uno"
    assert channel.group == "Canali TV"
    assert channel.source_id == "source-a"


def test_single_quoted_and_unquoted_attributes():
    parser = M3UParser()

    text = """
#EXTINF:-1 tvg-id='rai-1' tvg-name=RaiUno group-title='Generali',Rai 1
https://stream.test/rai1
"""

    channel = parser.parse(
        text,
        "source-a",
    )[0]

    assert channel.tvg_id == "rai-1"
    assert channel.tvg_name == "RaiUno"
    assert channel.group == "Generali"


def test_comma_inside_quoted_attribute_is_supported():
    parser = M3UParser()

    text = """
#EXTINF:-1 group-title="News, Italia" tvg-id="news-1",Rai News 24
https://stream.test/news
"""

    channel = parser.parse(
        text,
        "source-a",
    )[0]

    assert channel.name == "Rai News 24"
    assert channel.group == "News, Italia"


def test_extgrp_is_used_when_group_title_is_missing():
    parser = M3UParser()

    text = """
#EXTINF:-1 tvg-id="rai-1",Rai 1
#EXTGRP:Generali Italia
https://stream.test/rai1
"""

    channel = parser.parse(
        text,
        "source-a",
    )[0]

    assert channel.group == (
        "Generali Italia"
    )

    assert "#EXTGRP:Generali Italia" in (
        channel.extra_directives
    )


def test_tvg_name_is_fallback_for_empty_display_name():
    parser = M3UParser()

    text = """
#EXTINF:-1 tvg-name="Rai Uno",
https://stream.test/rai1
"""

    channel = parser.parse(
        text,
        "source-a",
    )[0]

    assert channel.name == "Rai Uno"
    assert channel.tvg_name == "Rai Uno"


def test_missing_name_is_reported():
    parser = M3UParser()

    text = """
#EXTINF:-1,
https://stream.test/unknown
"""

    result = parser.parse_detailed(
        text,
        "source-a",
    )

    assert result.channels == ()
    assert result.stats.missing_name == 1
    assert result.stats.skipped_records == 1

    assert result.issues[0].code == (
        "missing_name"
    )


def test_malformed_extinf_is_reported():
    parser = M3UParser()

    text = """
#EXTINF:-1 tvg-id="rai-1"
https://stream.test/rai1
"""

    result = parser.parse_detailed(
        text,
        "source-a",
    )

    assert result.channels == ()
    assert result.stats.malformed_extinf == 1
    assert result.stats.skipped_records == 1

    assert result.issues[0].code == (
        "malformed_extinf"
    )


def test_record_without_url_at_end_is_reported():
    parser = M3UParser()

    text = """
#EXTM3U
#EXTINF:-1,Rai 1
"""

    result = parser.parse_detailed(
        text,
        "source-a",
    )

    assert result.channels == ()
    assert result.stats.missing_url == 1
    assert result.stats.skipped_records == 1

    assert result.issues[0].code == (
        "missing_url"
    )


def test_new_extinf_abandons_previous_record():
    parser = M3UParser()

    text = """
#EXTINF:-1,Rai 1
#EXTINF:-1,Rai 2
https://stream.test/rai2
"""

    result = parser.parse_detailed(
        text,
        "source-a",
    )

    assert len(result.channels) == 1
    assert result.channels[0].name == "Rai 2"

    assert (
        result.stats.abandoned_records
        == 1
    )

    assert (
        result.stats.skipped_records
        == 1
    )

    assert result.issues[0].code == (
        "abandoned_record"
    )


def test_orphan_stream_url_is_reported():
    parser = M3UParser()

    text = """
#EXTM3U
https://stream.test/orphan
"""

    result = parser.parse_detailed(
        text,
        "source-a",
    )

    assert result.channels == ()
    assert result.stats.orphan_lines == 1

    assert result.issues[0].code == (
        "orphan_line"
    )


def test_extra_directives_are_preserved():
    parser = M3UParser()

    text = """
#EXTINF:-1,Rai 1
#EXTVLCOPT:http-referrer=https://example.test
#KODIPROP:inputstream.adaptive.manifest_type=hls
https://stream.test/rai1
"""

    channel = parser.parse(
        text,
        "source-a",
    )[0]

    assert channel.extra_directives == [
        (
            "#EXTVLCOPT:http-referrer="
            "https://example.test"
        ),
        (
            "#KODIPROP:inputstream.adaptive."
            "manifest_type=hls"
        ),
    ]


def test_crlf_line_endings_are_supported():
    parser = M3UParser()

    text = (
        "#EXTM3U\r\n"
        "#EXTINF:-1,Rai 1\r\n"
        "https://stream.test/rai1\r\n"
    )

    channels = parser.parse(
        text,
        "source-a",
    )

    assert len(channels) == 1
    assert channels[0].name == "Rai 1"


def test_quoted_stream_url_is_cleaned():
    parser = M3UParser()

    text = """
#EXTINF:-1,Rai 1
"https://stream.test/rai1"
"""

    channel = parser.parse(
        text,
        "source-a",
    )[0]

    assert channel.stream_url == (
        "https://stream.test/rai1"
    )


def test_parse_updates_last_result():
    parser = M3UParser()

    text = """
#EXTINF:-1,Rai 1
https://stream.test/rai1
"""

    channels = parser.parse(
        text,
        "source-a",
    )

    assert len(channels) == 1
    assert parser.last_result is not None

    assert (
        parser.last_result.stats
        .channels_created
        == 1
    )

    assert (
        parser.last_result.channels[0]
        is channels[0]
    )


@pytest.mark.parametrize(
    "text,source_id,error_type",
    [
        (
            None,
            "source-a",
            TypeError,
        ),
        (
            "#EXTM3U",
            None,
            TypeError,
        ),
    ],
)
def test_invalid_arguments_are_rejected(
    text,
    source_id,
    error_type,
):
    parser = M3UParser()

    with pytest.raises(error_type):
        parser.parse_detailed(
            text,
            source_id,
        )