from __future__ import annotations

from dataclasses import dataclass, field

from src.exporter.m3u import M3UExporter


@dataclass
class FakeChannel:
    name: str
    stream_url: str
    group: str = ""
    tvg_id: str = ""
    tvg_name: str = ""
    logo: str = ""
    source_id: str = "italy_public"
    attributes: dict[str, str] = field(
        default_factory=dict
    )
    extra_directives: list[str] = field(
        default_factory=list
    )


def test_rai_channels_are_grouped_together() -> None:
    channel = FakeChannel(
        name="Rai 1 HD",
        stream_url=(
            "https://stream.test/rai1.m3u8"
        ),
        group="General",
    )

    assert (
        M3UExporter.category_for(channel)
        == "RAI"
    )


def test_focus_is_grouped_under_mediaset() -> None:
    channel = FakeChannel(
        name="Focus (720p)",
        stream_url=(
            "https://stream.test/focus.m3u8"
        ),
        group="Documentary",
    )

    assert (
        M3UExporter.category_for(channel)
        == "MEDIASET"
    )


def test_dmax_is_grouped_under_discovery() -> None:
    channel = FakeChannel(
        name="DMAX HD",
        stream_url=(
            "https://stream.test/dmax.m3u8"
        ),
        group="Entertainment",
    )

    assert (
        M3UExporter.category_for(channel)
        == "DISCOVERY"
    )


def test_discovery_brand_channels_are_easy_to_find() -> None:
    expected = {
        "Nove": "DISCOVERY",
        "Real Time": "DISCOVERY",
        "Giallo": "DISCOVERY",
        "Food Network": "DISCOVERY",
        "Motor Trend": "DISCOVERY",
        "K2": "DISCOVERY",
        "Frisbee": "DISCOVERY",
    }

    for name, category in expected.items():
        channel = FakeChannel(
            name=name,
            stream_url=(
                "https://stream.test/"
                f"{name.casefold().replace(' ', '-')}"
            ),
        )

        assert (
            M3UExporter.category_for(
                channel
            )
            == category
        )


def test_pluto_channels_have_a_dedicated_category() -> None:
    channel = FakeChannel(
        name="Pluto TV Cinema Italiano",
        stream_url=(
            "https://stream.test/pluto.m3u8"
        ),
        source_id="pluto_it",
        group="Movies",
    )

    assert (
        M3UExporter.category_for(channel)
        == "PLUTO TV"
    )


def test_generic_groups_are_translated_to_clear_categories() -> None:
    channels = {
        "Canale News": FakeChannel(
            name="Canale News",
            stream_url="https://test/news",
            group="News",
        ),
        "Canale Sport": FakeChannel(
            name="Canale Sport",
            stream_url="https://test/sport",
            group="Sports",
        ),
        "Canale Film": FakeChannel(
            name="Canale Film",
            stream_url="https://test/film",
            group="Movies",
        ),
        "Canale Kids": FakeChannel(
            name="Canale Kids",
            stream_url="https://test/kids",
            group="Kids",
        ),
    }

    assert (
        M3UExporter.category_for(
            channels["Canale News"]
        )
        == "NEWS"
    )

    assert (
        M3UExporter.category_for(
            channels["Canale Sport"]
        )
        == "SPORT"
    )

    assert (
        M3UExporter.category_for(
            channels["Canale Film"]
        )
        == "FILM"
    )

    assert (
        M3UExporter.category_for(
            channels["Canale Kids"]
        )
        == "BAMBINI"
    )


def test_render_overrides_group_title_but_preserves_metadata() -> None:
    channel = FakeChannel(
        name="Focus",
        stream_url=(
            "https://stream.test/focus.m3u8"
        ),
        group="Documentary",
        tvg_id="focus.it",
        tvg_name="Focus",
        logo="https://images.test/focus.png",
        attributes={
            "custom": "value",
        },
        extra_directives=[
            "#EXTVLCOPT:http-referrer=https://example.test"
        ],
    )

    rendered = M3UExporter().render(
        [channel]
    )

    assert (
        'group-title="MEDIASET"'
        in rendered
    )

    assert 'tvg-id="focus.it"' in rendered
    assert 'tvg-name="Focus"' in rendered

    assert (
        'tvg-logo="https://images.test/focus.png"'
        in rendered
    )

    assert 'custom="value"' in rendered

    assert (
        "#EXTVLCOPT:http-referrer="
        "https://example.test"
        in rendered
    )

    assert (
        "https://stream.test/focus.m3u8"
        in rendered
    )


def test_channels_are_sorted_by_category_then_name() -> None:
    channels = [
        FakeChannel(
            name="DMAX",
            stream_url="https://test/dmax",
        ),
        FakeChannel(
            name="Rai 2",
            stream_url="https://test/rai2",
        ),
        FakeChannel(
            name="Canale 5",
            stream_url="https://test/canale5",
        ),
        FakeChannel(
            name="Rai 1",
            stream_url="https://test/rai1",
        ),
    ]

    rendered = M3UExporter().render(
        channels
    )

    rai_1_position = rendered.index(
        ",Rai 1"
    )
    rai_2_position = rendered.index(
        ",Rai 2"
    )
    canale_5_position = rendered.index(
        ",Canale 5"
    )
    dmax_position = rendered.index(
        ",DMAX"
    )

    assert (
        rai_1_position
        < rai_2_position
        < canale_5_position
        < dmax_position
    )
