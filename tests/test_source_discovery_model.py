from __future__ import annotations

from pathlib import Path

import pytest

from src.models.source import Source


def test_old_positional_constructor_remains_compatible() -> None:
    source = Source(
        "italy_public",
        "Italy Public",
        "https://example.test/it.m3u",
        True,
        25,
    )

    source.validate()

    assert source.id == "italy_public"
    assert source.enabled is True
    assert source.priority == 25
    assert source.kind == "playlist"
    assert source.discovery_enabled is False
    assert source.discovery_mode == "static"


def test_discovery_metadata_are_normalized() -> None:
    source = Source(
        id="github_it",
        name="GitHub Italia",
        url="https://github.com/example/repo",
        kind="Repository",
        country="Italy",
        language="Italian",
        tags=[
            "IT",
            "Rai",
            "Mediaset",
            "rai",
        ],
        discovery_enabled=True,
        discovery_mode="Search",
        trust_score=75,
        refresh_hours=12,
        origin="GitHub Search",
    )

    source.validate()

    assert source.kind == "repository"
    assert source.country == "IT"
    assert source.language == "it"
    assert source.tags == (
        "it",
        "rai",
        "mediaset",
    )
    assert source.discovery_mode == "search"


def test_discovery_source_detection() -> None:
    static = Source(
        "static",
        "Static",
        "playlist.m3u",
    )

    repository = Source(
        "github",
        "GitHub",
        "https://github.com/example/repo",
        kind="repository",
    )

    explicit = Source(
        "api_it",
        "API Italia",
        "https://example.test/api",
        discovery_enabled=True,
        discovery_mode="api",
    )

    assert static.is_discovery_source() is False
    assert repository.is_discovery_source() is True
    assert explicit.is_discovery_source() is True


def test_github_source_detection() -> None:
    assert Source(
        "one",
        "One",
        "https://github.com/example/repo",
    ).is_github_source() is True

    assert Source(
        "two",
        "Two",
        "https://raw.githubusercontent.com/example/repo/main/list.m3u",
    ).is_github_source() is True

    assert Source(
        "three",
        "Three",
        "https://example.test/list.m3u",
    ).is_github_source() is False


def test_local_path_keeps_old_relative_behavior(
    tmp_path: Path,
) -> None:
    source = Source(
        "local",
        "Local",
        "samples/sample.m3u",
    )

    assert source.local_path(
        tmp_path
    ) == (
        tmp_path
        / "samples"
        / "sample.m3u"
    ).resolve()


def test_remote_source_has_no_local_path(
    tmp_path: Path,
) -> None:
    source = Source(
        "remote",
        "Remote",
        "https://example.test/list.m3u",
    )

    with pytest.raises(
        ValueError,
        match="remota",
    ):
        source.local_path(
            tmp_path
        )


def test_matches_country_language_and_tags() -> None:
    source = Source(
        "italian_catalog",
        "Italian Catalog",
        "https://example.test/catalog",
        kind="catalog",
        country="IT",
        language="it",
        tags=(
            "italia",
            "rai",
            "mediaset",
        ),
    )

    assert source.matches(
        country="Italy",
        language="Italian",
        tags=["rai"],
    ) is True

    assert source.matches(
        country="US",
    ) is False

    assert source.matches(
        tags=["sport"],
    ) is False


def test_to_dict_is_json_friendly() -> None:
    source = Source(
        "italy",
        "Italy",
        "https://example.test/list.m3u",
        tags=(
            "it",
            "rai",
        ),
    )

    payload = source.to_dict()

    assert payload["tags"] == [
        "it",
        "rai",
    ]

    assert payload["country"] == ""


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            Source(
                "bad id",
                "Bad",
                "playlist.m3u",
            ),
            "ID sorgente",
        ),
        (
            Source(
                "bad_scheme",
                "Bad",
                "ftp://example.test/list.m3u",
            ),
            "Schema",
        ),
        (
            Source(
                "bad_remote",
                "Bad",
                "https:///list.m3u",
            ),
            "URL remoto",
        ),
        (
            Source(
                "bad_kind",
                "Bad",
                "playlist.m3u",
                kind="unknown",
            ),
            "Tipo sorgente",
        ),
        (
            Source(
                "bad_trust",
                "Bad",
                "playlist.m3u",
                trust_score=101,
            ),
            "trust_score",
        ),
        (
            Source(
                "bad_refresh",
                "Bad",
                "playlist.m3u",
                refresh_hours=0,
            ),
            "refresh_hours",
        ),
        (
            Source(
                "bad_discovery",
                "Bad",
                "playlist.m3u",
                discovery_enabled=True,
                discovery_mode="static",
            ),
            "discovery_mode static",
        ),
    ],
)
def test_invalid_sources_are_rejected(
    source: Source,
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        source.validate()
