from __future__ import annotations

from src.epg.matcher import (
    EPGChannel,
    EPGChannelMatcher,
)
from src.models.channel import Channel


def make_channel(
    name: str,
    *,
    tvg_id: str = "",
    tvg_name: str = "",
) -> Channel:
    return Channel(
        name=name,
        stream_url=(
            "https://universal.test/"
            + str(
                abs(
                    hash(
                        (
                            name,
                            tvg_id,
                            tvg_name,
                        )
                    )
                )
            )
            + ".m3u8"
        ),
        tvg_id=tvg_id,
        tvg_name=tvg_name,
        source_id="test",
    )


def test_all_country_and_quality_suffixes_are_normalized() -> None:
    playlist = [
        make_channel(
            "Pluto TV Anime",
            tvg_id=(
                "PlutoTVAnime.de@IT"
            ),
        ),
        make_channel(
            "Rai 1",
            tvg_id="Rai1.it@SD",
        ),
        make_channel(
            "WaterBear",
            tvg_id="WaterBear.ch@HD",
        ),
    ]

    epg = [
        EPGChannel(
            "PlutoTVAnime.it",
            ("Pluto TV Anime",),
        ),
        EPGChannel(
            "Rai1.it",
            ("Rai 1",),
        ),
        EPGChannel(
            "WaterBear.tv",
            ("WaterBear",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 3

    assert all(
        match.method
        == "normalized_tvg_id"
        for match in result.matches
    )


def test_generic_local_channel_quality_is_removed() -> None:
    playlist = [
        make_channel(
            "Tele Bari Due HD"
        )
    ]

    epg = [
        EPGChannel(
            "TeleBari2.it",
            ("Tele Bari 2",),
        )
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 1
    assert (
        result.matches[0]
        .epg_channel
        .channel_id
        == "TeleBari2.it"
    )


def test_locale_and_media_words_are_optional_for_all_channels() -> None:
    playlist = [
        make_channel(
            "Food Network Italia HD"
        ),
        make_channel(
            "Warner Channel"
        ),
    ]

    epg = [
        EPGChannel(
            "FoodNetwork.it",
            ("Food Network",),
        ),
        EPGChannel(
            "WarnerTV.it",
            ("Warner TV",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 2


def test_regional_name_inside_brackets_is_preserved() -> None:
    playlist = [
        make_channel(
            "Rai 3 [Puglia] HD"
        )
    ]

    epg = [
        EPGChannel(
            "Rai3Puglia.it",
            ("Rai 3 Puglia",),
        ),
        EPGChannel(
            "Rai3Lombardia.it",
            ("Rai 3 Lombardia",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 1
    assert (
        result.matches[0]
        .epg_channel
        .channel_id
        == "Rai3Puglia.it"
    )


def test_plus_version_is_not_collapsed_into_base_channel() -> None:
    playlist = [
        make_channel(
            "Rai Sport + HD"
        )
    ]

    epg = [
        EPGChannel(
            "RaiSport.it",
            ("Rai Sport",),
        ),
        EPGChannel(
            "RaiSportPlus.it",
            ("Rai Sport +",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 1
    assert (
        result.matches[0]
        .epg_channel
        .channel_id
        == "RaiSportPlus.it"
    )


def test_radio_italia_does_not_collapse_to_generic_radio() -> None:
    playlist = [
        make_channel(
            "Radio Italia"
        )
    ]

    epg = [
        EPGChannel(
            "RadioItalia.it",
            ("Radio Italia",),
        ),
        EPGChannel(
            "RadioNews.it",
            ("Radio",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 1
    assert (
        result.matches[0]
        .epg_channel
        .channel_id
        == "RadioItalia.it"
    )


def test_technical_brackets_are_removed_but_locations_are_not() -> None:
    matcher = EPGChannelMatcher()

    assert (
        matcher.normalize_name(
            "Italia 2 (480p) "
            "[Geo-blocked]"
        )
        == "italia2"
    )

    assert (
        matcher.normalize_name(
            "TeleSud [Bari] HD"
        )
        == "telesudbari"
    )


def test_different_local_channels_remain_distinct() -> None:
    playlist = [
        make_channel(
            "Tele Bari"
        )
    ]

    epg = [
        EPGChannel(
            "TeleBari.it",
            ("Tele Bari",),
        ),
        EPGChannel(
            "TeleFoggia.it",
            ("Tele Foggia",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 1
    assert (
        result.matches[0]
        .epg_channel
        .channel_id
        == "TeleBari.it"
    )
