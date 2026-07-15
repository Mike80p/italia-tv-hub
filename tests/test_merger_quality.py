from __future__ import annotations

import pytest

from src.merger.merger import ChannelMerger
from src.models.channel import Channel


def make_channel(
    name: str,
    stream_url: str,
    *,
    source_id: str = "source-a",
    group: str = "Generali",
    tvg_id: str = "",
    tvg_name: str = "",
    logo: str = "",
    attributes: dict[str, str] | None = None,
    directives: list[str] | None = None,
) -> Channel:
    return Channel(
        name=name,
        stream_url=stream_url,
        group=group,
        tvg_id=tvg_id,
        tvg_name=tvg_name,
        logo=logo,
        source_id=source_id,
        attributes=attributes or {},
        extra_directives=directives or [],
    )


def test_better_source_priority_wins():
    low_priority = make_channel(
        "Rai 1",
        "https://low.test/rai1.m3u8",
        source_id="low",
        tvg_id="rai-1",
    )

    high_priority = make_channel(
        "Rai 1",
        "https://high.test/rai1.m3u8",
        source_id="high",
        tvg_id="rai-1",
    )

    merger = ChannelMerger()

    result = merger.merge(
        [
            low_priority,
            high_priority,
        ],
        source_priorities={
            "low": 100,
            "high": 10,
        },
    )

    assert result == [
        high_priority
    ]


def test_4k_wins_over_sd_with_same_priority():
    sd = make_channel(
        "Rai 1 SD",
        "https://stream.test/rai1-sd.m3u8",
        source_id="source-a",
    )

    ultra_hd = make_channel(
        "Rai 1 4K",
        "https://stream.test/rai1-4k.m3u8",
        source_id="source-b",
    )

    result = ChannelMerger().merge(
        [
            sd,
            ultra_hd,
        ],
        source_priorities={
            "source-a": 10,
            "source-b": 10,
        },
    )

    assert result == [
        ultra_hd
    ]


def test_richer_metadata_wins():
    basic = make_channel(
        "Canale 5",
        "https://a.test/canale5",
        source_id="source-a",
    )

    rich = make_channel(
        "Canale 5",
        "https://b.test/canale5",
        source_id="source-b",
        tvg_id="canale-5",
        tvg_name="Canale 5",
        logo="https://logo.test/5.png",
        attributes={
            "group-title": "Generali",
        },
    )

    result = ChannelMerger().merge(
        [
            basic,
            rich,
        ],
        source_priorities={
            "source-a": 10,
            "source-b": 10,
        },
    )

    assert result == [rich]


def test_health_score_has_highest_priority():
    trusted = make_channel(
        "Rai 2",
        "https://trusted.test/rai2",
        source_id="trusted",
        tvg_id="rai-2",
    )

    stable = make_channel(
        "Rai 2",
        "https://stable.test/rai2",
        source_id="secondary",
        tvg_id="rai-2",
    )

    result = ChannelMerger().merge(
        [
            trusted,
            stable,
        ],
        source_priorities={
            "trusted": 1,
            "secondary": 100,
        },
        health_scores={
            trusted.stream_url: 20,
            stable.stream_url: 95,
        },
    )

    assert result == [stable]


def test_transitive_duplicates_form_one_group():
    first = make_channel(
        "Rai 1",
        "https://stream.test/shared",
        source_id="source-a",
    )

    second = make_channel(
        "Rai Uno",
        "https://stream.test/shared",
        source_id="source-b",
        tvg_id="rai-1",
    )

    third = make_channel(
        "Rai Uno HD",
        "https://stream.test/other",
        source_id="source-c",
        tvg_id="rai-1",
    )

    result = ChannelMerger().merge_detailed(
        [
            first,
            second,
            third,
        ]
    )

    assert len(result.channels) == 1
    assert result.stats.duplicates_removed == 2
    assert result.stats.duplicate_groups == 1


def test_regional_channels_are_not_merged():
    puglia = make_channel(
        "Rai 3 TGR Puglia",
        "https://stream.test/puglia",
    )

    lazio = make_channel(
        "Rai 3 TGR Lazio",
        "https://stream.test/lazio",
    )

    result = ChannelMerger().merge(
        [
            puglia,
            lazio,
        ]
    )

    assert len(result) == 2
    assert {channel.stream_url for channel in result} == {
    puglia.stream_url,
    lazio.stream_url,
}


def test_generic_names_are_not_used_as_identity():
    first = make_channel(
        "Live",
        "https://a.test/live",
    )

    second = make_channel(
        "Live",
        "https://b.test/live",
    )

    result = ChannelMerger().merge(
        [
            first,
            second,
        ]
    )

    assert len(result) == 2


def test_identical_url_is_deduplicated():
    first = make_channel(
        "Rai 1",
        "HTTPS://EXAMPLE.TEST:443/rai1",
    )

    duplicate = make_channel(
        "Rai Uno",
        "https://example.test/rai1",
    )

    result = ChannelMerger().merge_detailed(
        [
            first,
            duplicate,
        ]
    )

    assert len(result.channels) == 1
    assert result.stats.url_collisions == 1
    assert result.stats.duplicates_removed == 1


def test_output_is_sorted_by_group_and_name():
    rai = make_channel(
        "Rai 1",
        "https://stream.test/rai1",
        group="Generali",
    )

    news = make_channel(
        "Sky TG24",
        "https://stream.test/sky",
        group="News",
    )

    sport = make_channel(
        "Eurosport",
        "https://stream.test/euro",
        group="Sport",
    )

    result = ChannelMerger().merge(
        [
            sport,
            news,
            rai,
        ]
    )

    assert result == [
        rai,
        news,
        sport,
    ]


def test_detailed_result_contains_decision():
    sd = make_channel(
        "Rai 1 SD",
        "http://stream.test/rai1-sd",
    )

    hd = make_channel(
        "Rai 1 HD",
        "https://stream.test/rai1-hd.m3u8",
    )

    result = ChannelMerger().merge_detailed(
        [
            sd,
            hd,
        ]
    )

    assert len(result.decisions) == 1

    decision = result.decisions[0]

    assert (
        decision.selected.stream_url
        == hd.stream_url
    )

    assert decision.duplicates_removed == 1

    assert decision.reason == (
        "higher_video_quality"
    )


def test_quality_suffix_is_removed_only_for_identity():
    plain = make_channel(
        "Italia 1",
        "https://stream.test/italia1",
    )

    hd = make_channel(
        "Italia 1 HD",
        "https://stream.test/italia1-hd",
    )

    different = make_channel(
        "Italia 2",
        "https://stream.test/italia2",
    )

    result = ChannelMerger().merge(
        [
            plain,
            hd,
            different,
        ]
    )

    assert len(result) == 2
    assert different in result


def test_invalid_channel_object_is_rejected():
    merger = ChannelMerger()

    with pytest.raises(
        TypeError,
        match="Channel",
    ):
        merger.merge(
            [
                object()
            ]  # type: ignore[list-item]
        )