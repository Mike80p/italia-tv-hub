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
            "https://example.test/"
            + name.replace(
                " ",
                "-"
            )
            + ".m3u8"
        ),
        tvg_id=tvg_id,
        tvg_name=tvg_name,
        source_id="test",
    )


def test_exact_tvg_id_has_highest_priority() -> None:
    playlist = [
        make_channel(
            "Rai Uno HD",
            tvg_id="Rai1.it",
        )
    ]

    epg = [
        EPGChannel(
            "Rai1.it",
            ("Rai 1",),
        ),
        EPGChannel(
            "RaiUno.it",
            ("Rai Uno",),
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
        == "Rai1.it"
    )
    assert (
        result.matches[0].method
        == "exact_tvg_id"
    )
    assert (
        result.matches[0].score
        == 100.0
    )


def test_normalized_tvg_id_matches_domain_suffix() -> None:
    playlist = [
        make_channel(
            "Canale 5",
            tvg_id="Canale5",
        )
    ]

    epg = [
        EPGChannel(
            "Canale5.it",
            ("Canale 5",),
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
        result.matches[0].method
        == "normalized_tvg_id"
    )


def test_exact_normalized_name_match() -> None:
    playlist = [
        make_channel(
            "Rai News 24 HD"
        )
    ]

    epg = [
        EPGChannel(
            "RaiNews24.it",
            ("Rai News 24",),
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
        result.matches[0].method
        == "exact_name"
    )


def test_italian_alias_match() -> None:
    playlist = [
        make_channel(
            "Rai Uno"
        )
    ]

    epg = [
        EPGChannel(
            "Rai1.it",
            ("Rai 1",),
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
        result.matches[0].method
        == "alias"
    )


def test_tvg_name_is_considered_before_display_name() -> None:
    playlist = [
        make_channel(
            "Canale generico",
            tvg_name="Real Time",
        )
    ]

    epg = [
        EPGChannel(
            "RealTime.it",
            ("Real Time",),
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
        == "RealTime.it"
    )


def test_similarity_match_is_conservative() -> None:
    playlist = [
        make_channel(
            "Food Network Italia"
        )
    ]

    epg = [
        EPGChannel(
            "FoodNetwork.it",
            ("Food Network",),
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


def test_unrelated_names_remain_unmatched() -> None:
    playlist = [
        make_channel(
            "Canale Locale Bari"
        )
    ]

    epg = [
        EPGChannel(
            "Rai1.it",
            ("Rai 1",),
        )
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 0
    assert result.stats.unmatched == 1
    assert (
        result.unmatched[0].name
        == "Canale Locale Bari"
    )


def test_equal_best_candidates_are_marked_ambiguous() -> None:
    playlist = [
        make_channel(
            "Rai 3"
        )
    ]

    epg = [
        EPGChannel(
            "Rai3Nord.it",
            ("Rai 3",),
        ),
        EPGChannel(
            "Rai3Sud.it",
            ("Rai 3",),
        ),
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.matched == 0
    assert result.stats.ambiguous == 1
    assert (
        len(
            result.ambiguous[0]
            .candidates
        )
        == 2
    )


def test_duplicate_display_names_inside_epg_channel_are_removed() -> None:
    channel = EPGChannel(
        "Nove.it",
        (
            "Nove",
            "Nove",
            " ",
        ),
    )

    assert channel.display_names == (
        "Nove",
    )


def test_epg_channel_uses_id_when_display_name_is_missing() -> None:
    channel = EPGChannel(
        "DMAX.it",
        (),
    )

    assert channel.display_names == (
        "DMAX.it",
    )


def test_batch_statistics_and_lookup_map() -> None:
    playlist = [
        make_channel(
            "Rai 1",
            tvg_id="Rai1.it",
        ),
        make_channel(
            "Sconosciuto"
        ),
    ]

    epg = [
        EPGChannel(
            "Rai1.it",
            ("Rai 1",),
        )
    ]

    result = (
        EPGChannelMatcher()
        .match_channels(
            playlist,
            epg,
        )
    )

    assert result.stats.playlist_channels == 2
    assert result.stats.epg_channels == 1
    assert result.stats.matched == 1
    assert result.stats.unmatched == 1
    assert (
        result.stats.coverage_percent
        == 50.0
    )

    lookup = (
        result.match_by_stream_url()
    )

    assert (
        playlist[0].stream_url
        in lookup
    )


def test_invalid_similarity_threshold_is_rejected() -> None:
    try:
        EPGChannelMatcher(
            similarity_minimum=101
        )
    except ValueError as exc:
        assert (
            "similarity_minimum"
            in str(exc)
        )
    else:
        raise AssertionError(
            "ValueError non sollevato"
        )
