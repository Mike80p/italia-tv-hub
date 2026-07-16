from __future__ import annotations

import pytest

from src.merger.merger import (
    CandidateGroupResult,
    ChannelMerger,
    MergeResult,
)
from src.models.channel import Channel


def make_channel(
    name: str,
    stream_url: str,
    *,
    group: str = "Generali",
    tvg_id: str = "",
    tvg_name: str = "",
    logo: str = "",
    source_id: str = "source-a",
    attributes: dict[str, str] | None = None,
    extra_directives: list[str] | None = None,
) -> Channel:
    return Channel(
        name,
        stream_url,
        group,
        tvg_id,
        tvg_name,
        logo,
        source_id,
        attributes or {},
        extra_directives or [],
    )


def test_group_candidates_preserves_all_alternatives() -> None:
    first = make_channel(
        "Rai 1 HD",
        "https://a.test/rai1.m3u8",
        tvg_id="rai-1.it",
        source_id="source-a",
    )

    second = make_channel(
        "Rai 1",
        "https://b.test/rai1.m3u8",
        tvg_id="rai-1.it",
        source_id="source-b",
    )

    result = ChannelMerger().group_candidates(
        [first, second],
        source_priorities={
            "source-a": 10,
            "source-b": 20,
        },
    )

    assert isinstance(
        result,
        CandidateGroupResult,
    )

    assert len(result.groups) == 1

    group = result.groups[0]

    assert group.is_duplicate is True
    assert group.size == 2

    assert {
        channel.stream_url
        for channel in group.channels
    } == {
        first.stream_url,
        second.stream_url,
    }

    assert len(
        group.alternative_channels
    ) == 1

    assert (
        result.stats
        .alternative_candidates
        == 1
    )


def test_group_candidates_keeps_singletons() -> None:
    rai = make_channel(
        "Rai 1",
        "https://test/rai1.m3u8",
    )

    mediaset = make_channel(
        "Canale 5",
        "https://test/canale5.m3u8",
    )

    result = ChannelMerger().group_candidates(
        [rai, mediaset]
    )

    assert len(result.groups) == 2
    assert all(
        not group.is_duplicate
        for group in result.groups
    )

    assert (
        result.stats.singleton_groups
        == 2
    )

    assert (
        result.stats.duplicate_groups
        == 0
    )


def test_transitive_candidate_groups_are_preserved() -> None:
    first = make_channel(
        "Rai Uno",
        "https://a.test/live.m3u8",
        tvg_id="rai-one",
    )

    bridge = make_channel(
        "Rai 1",
        "https://a.test/live.m3u8",
        tvg_id="rai-1",
    )

    third = make_channel(
        "Rai 1 HD",
        "https://c.test/live.m3u8",
        tvg_id="rai-1",
    )

    result = ChannelMerger().group_candidates(
        [first, bridge, third]
    )

    assert len(result.groups) == 1
    assert result.groups[0].size == 3

    assert (
        result.stats
        .alternative_candidates
        == 2
    )


def test_health_scores_reorder_alternatives() -> None:
    preferred_by_source = make_channel(
        "Rai 1",
        "https://preferred.test/rai1.m3u8",
        source_id="primary",
    )

    working_alternative = make_channel(
        "Rai 1 HD",
        "https://backup.test/rai1.m3u8",
        source_id="backup",
    )

    initial = ChannelMerger().group_candidates(
        [
            preferred_by_source,
            working_alternative,
        ],
        source_priorities={
            "primary": 10,
            "backup": 20,
        },
    )

    assert (
        initial.groups[0]
        .preferred_channel
        .stream_url
        == preferred_by_source.stream_url
    )

    checked = ChannelMerger().group_candidates(
        [
            preferred_by_source,
            working_alternative,
        ],
        source_priorities={
            "primary": 10,
            "backup": 20,
        },
        health_scores={
            preferred_by_source.stream_url: 0,
            working_alternative.stream_url: 95,
        },
    )

    assert (
        checked.groups[0]
        .preferred_channel
        .stream_url
        == working_alternative.stream_url
    )

    assert (
        checked.groups[0]
        .preferred_candidate
        .health_score
        == 95
    )


def test_merge_remains_backward_compatible() -> None:
    first = make_channel(
        "Rai 1",
        "https://a.test/rai1.m3u8",
        source_id="primary",
    )

    second = make_channel(
        "Rai 1 HD",
        "https://b.test/rai1.m3u8",
        source_id="backup",
    )

    merger = ChannelMerger()

    merged = merger.merge(
        [first, second],
        source_priorities={
            "primary": 10,
            "backup": 20,
        },
    )

    detailed = merger.merge_detailed(
        [first, second],
        source_priorities={
            "primary": 10,
            "backup": 20,
        },
    )

    assert isinstance(
        detailed,
        MergeResult,
    )

    assert len(merged) == 1
    assert len(detailed.channels) == 1

    assert (
        merged[0].stream_url
        == detailed.channels[0].stream_url
    )

    assert (
        detailed.stats
        .duplicates_removed
        == 1
    )


def test_group_result_exposes_all_channels_without_deduplication() -> None:
    first = make_channel(
        "Rai 1",
        "https://a.test/rai1.m3u8",
    )

    second = make_channel(
        "Rai 1 HD",
        "https://b.test/rai1.m3u8",
    )

    third = make_channel(
        "Canale 5",
        "https://c.test/canale5.m3u8",
    )

    result = ChannelMerger().group_candidates(
        [first, second, third]
    )

    assert len(result.channels) == 3
    assert len(
        result.preferred_channels
    ) == 2


def test_candidate_group_diagnostics_are_serializable() -> None:
    first = make_channel(
        "Rai 1",
        "https://a.test/rai1.m3u8",
        tvg_id="rai-1",
    )

    second = make_channel(
        "Rai 1 HD",
        "https://b.test/rai1.m3u8",
        tvg_id="rai-1",
    )

    payload = (
        ChannelMerger()
        .group_candidates(
            [first, second]
        )
        .to_dict()
    )

    assert payload["stats"][
        "groups"
    ] == 1

    assert payload["stats"][
        "alternative_candidates"
    ] == 1

    assert payload["groups"][0][
        "size"
    ] == 2

    assert payload["groups"][0][
        "is_duplicate"
    ] is True

    assert len(
        payload["groups"][0][
            "alternatives"
        ]
    ) == 1


def test_generic_names_are_not_grouped_by_name() -> None:
    first = make_channel(
        "Live",
        "https://a.test/live.m3u8",
    )

    second = make_channel(
        "Live HD",
        "https://b.test/live.m3u8",
    )

    result = ChannelMerger().group_candidates(
        [first, second]
    )

    assert len(result.groups) == 2


def test_invalid_candidate_type_is_rejected() -> None:
    with pytest.raises(
        TypeError,
        match="Channel instances",
    ):
        ChannelMerger().group_candidates(
            [object()]
        )


def test_empty_candidate_groups_have_zero_stats() -> None:
    result = ChannelMerger().group_candidates(
        []
    )

    assert result.groups == ()
    assert result.channels == ()
    assert result.preferred_channels == ()

    assert result.stats.to_dict() == {
        "input_channels": 0,
        "groups": 0,
        "singleton_groups": 0,
        "duplicate_groups": 0,
        "alternative_candidates": 0,
        "url_collisions": 0,
        "tvg_id_collisions": 0,
        "name_collisions": 0,
    }
