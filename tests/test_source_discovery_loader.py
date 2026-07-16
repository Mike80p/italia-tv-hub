from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.catalog.loader import load_sources


def write_json(
    path: Path,
    payload: object,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_loads_legacy_source_with_defaults(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "legacy.json",
        {
            "sources": [
                {
                    "id": "italy_public",
                    "name": "Italy Public",
                    "url": (
                        "https://example.test/"
                        "italy.m3u"
                    ),
                    "enabled": True,
                    "priority": 25,
                }
            ]
        },
    )

    sources = load_sources(
        tmp_path
    )

    assert len(sources) == 1

    source = sources[0]

    assert source.id == "italy_public"
    assert source.enabled is True
    assert source.priority == 25
    assert source.kind == "playlist"
    assert source.country == ""
    assert source.language == ""
    assert source.tags == ()
    assert source.discovery_enabled is False
    assert source.discovery_mode == "static"
    assert source.trust_score == 50
    assert source.refresh_hours == 24
    assert source.origin == ""


def test_loads_and_normalizes_discovery_fields(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "discovery.json",
        {
            "sources": [
                {
                    "id": "github_it",
                    "name": "GitHub Italia",
                    "url": (
                        "https://github.com/"
                        "example/repository"
                    ),
                    "enabled": True,
                    "priority": 40,
                    "kind": "Repository",
                    "country": "Italy",
                    "language": "Italian",
                    "tags": [
                        "IT",
                        "Rai",
                        "Mediaset",
                        "rai",
                    ],
                    "discovery_enabled": True,
                    "discovery_mode": "Search",
                    "trust_score": 75,
                    "refresh_hours": 12,
                    "origin": "GitHub Search",
                }
            ]
        },
    )

    source = load_sources(
        tmp_path
    )[0]

    assert source.kind == "repository"
    assert source.country == "IT"
    assert source.language == "it"

    assert source.tags == (
        "it",
        "rai",
        "mediaset",
    )

    assert source.discovery_enabled is True
    assert source.discovery_mode == "search"
    assert source.trust_score == 75
    assert source.refresh_hours == 12
    assert source.origin == "GitHub Search"

    source.validate()


def test_files_are_loaded_in_filename_order(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "b.json",
        {
            "sources": [
                {
                    "id": "second",
                    "name": "Second",
                    "url": "second.m3u",
                }
            ]
        },
    )

    write_json(
        tmp_path / "a.json",
        {
            "sources": [
                {
                    "id": "first",
                    "name": "First",
                    "url": "first.m3u",
                }
            ]
        },
    )

    sources = load_sources(
        tmp_path
    )

    assert [
        source.id
        for source in sources
    ] == [
        "first",
        "second",
    ]


def test_multiple_sources_in_same_file_keep_order(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "sources.json",
        {
            "sources": [
                {
                    "id": "one",
                    "name": "One",
                    "url": "one.m3u",
                },
                {
                    "id": "two",
                    "name": "Two",
                    "url": "two.m3u",
                },
            ]
        },
    )

    assert [
        source.id
        for source in load_sources(
            tmp_path
        )
    ] == [
        "one",
        "two",
    ]


def test_missing_directory_returns_empty_list(
    tmp_path: Path,
) -> None:
    missing = (
        tmp_path
        / "missing"
    )

    assert load_sources(
        missing
    ) == []


def test_non_directory_path_is_rejected(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "sources.json"
    )

    path.write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="non è una cartella",
    ):
        load_sources(
            path
        )


def test_invalid_json_reports_filename_and_position(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "broken.json"
    )

    path.write_text(
        '{"sources": [}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            r"JSON non valido in broken\.json: "
            r"riga 1, colonna"
        ),
    ):
        load_sources(
            tmp_path
        )


def test_top_level_must_be_object(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "invalid.json",
        [],
    )

    with pytest.raises(
        ValueError,
        match="atteso oggetto JSON",
    ):
        load_sources(
            tmp_path
        )


def test_sources_field_must_be_list(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "invalid.json",
        {
            "sources": {}
        },
    )

    with pytest.raises(
        ValueError,
        match="attesa lista",
    ):
        load_sources(
            tmp_path
        )


def test_each_source_must_be_object(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "invalid.json",
        {
            "sources": [
                "not-an-object"
            ]
        },
    )

    with pytest.raises(
        ValueError,
        match=(
            r"invalid\.json, elemento 1"
        ),
    ):
        load_sources(
            tmp_path
        )


def test_missing_sources_field_is_empty(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "empty.json",
        {},
    )

    assert load_sources(
        tmp_path
    ) == []


def test_loader_does_not_hide_model_validation_errors(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "invalid-source.json",
        {
            "sources": [
                {
                    "id": "invalid source id",
                    "name": "Invalid",
                    "url": "playlist.m3u",
                }
            ]
        },
    )

    source = load_sources(
        tmp_path
    )[0]

    with pytest.raises(
        ValueError,
        match="ID sorgente",
    ):
        source.validate()
