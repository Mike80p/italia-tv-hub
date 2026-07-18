from __future__ import annotations

import pytest

from src.models.channel import Channel
from src.pluto.alternatives import (
    PlutoAlternativeGenerator,
)


def make_channel(
    name: str,
    url: str,
    *,
    tvg_id: str = "",
    source_id: str = "pluto_it",
) -> Channel:
    return Channel(
        name=name,
        stream_url=url,
        group="PLUTO TV",
        tvg_id=tvg_id,
        tvg_name=name,
        logo=(
            "https://images.pluto.tv/"
            "logo.png"
        ),
        source_id=source_id,
        attributes={
            "tvg-country": "IT",
        },
        extra_directives=[
            "#EXTVLCOPT:http-referrer="
            "https://pluto.tv/",
        ],
    )


def direct_url(
    channel_id: str,
) -> str:
    return (
        "https://cfd-v4-service-"
        "channel-stitcher-use1-1."
        "prd.pluto.tv/v2/stitch/"
        "hls/channel/"
        f"{channel_id}/master.m3u8"
        "?jwt=test"
    )


def test_generates_jmp2_candidate_and_keeps_original() -> None:
    channel_id = (
        "60940a07d88ba90007b9cb71"
    )

    original = make_channel(
        "16 Anni e Incinta",
        direct_url(
            channel_id
        ),
        tvg_id=channel_id,
    )

    result = (
        PlutoAlternativeGenerator()
        .expand(
            [original]
        )
    )

    assert len(result.channels) == 2
    assert (
        result.channels[0]
        is original
    )

    alternative = (
        result.generated_channels[0]
    )

    assert (
        alternative.stream_url
        == (
            "https://jmp2.uk/"
            "plu-60940a07d88ba90007b9cb71"
            ".m3u8"
        )
    )

    assert (
        alternative.source_id
        == "pluto_jmp2"
    )

    assert (
        alternative.tvg_id
        == original.tvg_id
    )

    assert (
        alternative.group
        == original.group
    )

    assert (
        alternative.attributes[
            "tvg-country"
        ]
        == "IT"
    )

    assert (
        alternative.attributes[
            "generated-alternative"
        ]
        == "jmp2"
    )

    assert (
        result.stats
        .generated_alternatives
        == 1
    )


def test_existing_jmp2_url_prevents_duplicate() -> None:
    channel_id = (
        "608aa17fb9f4490007e6419a"
    )

    direct = make_channel(
        "Pluto TV Film",
        direct_url(
            channel_id
        ),
        tvg_id=channel_id,
    )

    existing = make_channel(
        "Pluto TV Film",
        (
            "https://jmp2.uk/"
            f"plu-{channel_id}.m3u8"
        ),
        tvg_id=channel_id,
        source_id="italy_public",
    )

    result = (
        PlutoAlternativeGenerator()
        .expand(
            [
                direct,
                existing,
            ]
        )
    )

    assert len(result.channels) == 2
    assert (
        result.stats
        .generated_alternatives
        == 0
    )

    assert (
        result.stats
        .skipped_duplicate_urls
        == 1
    )

    assert (
        result.stats
        .existing_resolver_channels
        == 1
    )


def test_non_pluto_channel_is_unchanged() -> None:
    rai = make_channel(
        "Rai 1",
        (
            "https://example.test/"
            "rai1.m3u8"
        ),
        tvg_id="Rai1.it",
        source_id="italy_public",
    )

    result = (
        PlutoAlternativeGenerator()
        .expand(
            [rai]
        )
    )

    assert result.channels == (
        rai,
    )

    assert (
        result.stats
        .direct_pluto_channels
        == 0
    )


def test_extracts_id_from_url_even_with_complex_jwt() -> None:
    channel_id = (
        "66c35c0c92b1af0008c8e83a"
    )

    channel = make_channel(
        "Horror Club",
        direct_url(
            channel_id
        )
        + "&audioLanguage=it",
    )

    assert (
        PlutoAlternativeGenerator
        .extract_channel_id(
            channel
        )
        == channel_id
    )


def test_preserves_same_group_identity_for_merger() -> None:
    channel_id = (
        "608030eff4b6f70007e1684c"
    )

    original = make_channel(
        "Pluto TV Sport",
        direct_url(
            channel_id
        ),
        tvg_id=channel_id,
    )

    result = (
        PlutoAlternativeGenerator()
        .expand(
            [original]
        )
    )

    alternative = (
        result.generated_channels[0]
    )

    assert (
        alternative.name
        == original.name
    )

    assert (
        alternative.tvg_name
        == original.tvg_name
    )

    assert (
        alternative.tvg_id
        == original.tvg_id
    )


def test_invalid_channel_id_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="ID Pluto",
    ):
        (
            PlutoAlternativeGenerator
            .build_resolver_url(
                "not-valid"
            )
        )


def test_invalid_input_type_is_rejected() -> None:
    with pytest.raises(
        TypeError,
        match="non Channel",
    ):
        (
            PlutoAlternativeGenerator()
            .expand(
                [
                    "not-a-channel",
                ]
            )
        )


def test_multiple_direct_duplicates_generate_one_url() -> None:
    channel_id = (
        "62e7fb67478a5b0007e6c50c"
    )

    first = make_channel(
        "Pluto TV Western",
        direct_url(
            channel_id
        ),
        tvg_id=channel_id,
    )

    second = make_channel(
        "Pluto TV Western HD",
        direct_url(
            channel_id
        )
        + "&quality=hd",
        tvg_id=channel_id,
    )

    result = (
        PlutoAlternativeGenerator()
        .expand(
            [
                first,
                second,
            ]
        )
    )

    assert (
        result.stats
        .generated_alternatives
        == 1
    )

    assert (
        result.stats
        .skipped_duplicate_urls
        == 1
    )
