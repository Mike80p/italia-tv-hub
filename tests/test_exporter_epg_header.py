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
    source_id: str = ""
    attributes: dict[str, str] = field(
        default_factory=dict
    )
    extra_directives: tuple[str, ...] = ()


def test_default_header_remains_backward_compatible() -> None:
    rendered = M3UExporter().render(
        []
    )

    assert rendered == "#EXTM3U\n"


def test_epg_url_is_added_to_m3u_header() -> None:
    exporter = M3UExporter(
        epg_url=(
            "https://raw.githubusercontent.com/"
            "Mike80p/italia-tv-hub/main/"
            "output/epg.xml"
        )
    )

    rendered = exporter.render(
        []
    )

    assert rendered == (
        '#EXTM3U url-tvg="'
        "https://raw.githubusercontent.com/"
        "Mike80p/italia-tv-hub/main/"
        'output/epg.xml"\n'
    )


def test_empty_epg_url_keeps_simple_header() -> None:
    rendered = M3UExporter(
        epg_url="   "
    ).render(
        []
    )

    assert rendered == "#EXTM3U\n"


def test_epg_url_quotes_are_safely_escaped() -> None:
    rendered = M3UExporter(
        epg_url=(
            'https://example.test/"epg".xml'
        )
    ).render(
        []
    )

    assert rendered.startswith(
        '#EXTM3U url-tvg="'
        "https://example.test/"
        "'epg'.xml"
        '"\n'
    )


def test_channel_export_still_works_with_epg_header() -> None:
    channel = FakeChannel(
        name="Rai 1 HD",
        stream_url=(
            "https://example.test/rai1.m3u8"
        ),
        tvg_id="Rai1.it",
        tvg_name="Rai 1",
        source_id="italy",
    )

    rendered = M3UExporter(
        epg_url=(
            "https://example.test/epg.xml"
        )
    ).render(
        [channel]
    )

    lines = rendered.splitlines()

    assert lines[0] == (
        '#EXTM3U url-tvg="'
        'https://example.test/epg.xml"'
    )

    assert (
        'tvg-id="Rai1.it"'
        in lines[1]
    )

    assert (
        'tvg-name="Rai 1"'
        in lines[1]
    )

    assert (
        'group-title="RAI"'
        in lines[1]
    )

    assert lines[2] == (
        "https://example.test/rai1.m3u8"
    )
