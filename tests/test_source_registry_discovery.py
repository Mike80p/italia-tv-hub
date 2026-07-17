from __future__ import annotations

import pytest

from src.catalog.source_registry import SourceRegistry
from src.models.source import Source


def make_source(
    source_id: str,
    url: str,
    *,
    enabled: bool = True,
    priority: int = 100,
    kind: str = "playlist",
    country: str = "",
    language: str = "",
    tags: tuple[str, ...] = (),
    discovery_enabled: bool = False,
    discovery_mode: str = "static",
    trust_score: int = 50,
) -> Source:
    return Source(
        id=source_id,
        name=source_id or "invalid",
        url=url,
        enabled=enabled,
        priority=priority,
        kind=kind,
        country=country,
        language=language,
        tags=tags,
        discovery_enabled=discovery_enabled,
        discovery_mode=discovery_mode,
        trust_score=trust_score,
    )


def test_legacy_priority_order_is_unchanged() -> None:
    registry = SourceRegistry(
        [
            make_source(
                "late",
                "https://example.test/late.m3u",
                priority=100,
            ),
            make_source(
                "first",
                "https://example.test/first.m3u",
                priority=10,
            ),
            make_source(
                "same-priority",
                "https://example.test/same.m3u",
                priority=100,
            ),
        ]
    )

    assert [
        source.id
        for source in registry.snapshot()
    ] == [
        "first",
        "late",
        "same-priority",
    ]


def test_equivalent_remote_urls_are_deduplicated() -> None:
    registry = SourceRegistry()

    first = make_source(
        "first",
        "HTTPS://Example.TEST:443/list.m3u#section",
    )

    duplicate = make_source(
        "duplicate",
        "https://example.test/list.m3u",
    )

    assert registry.add(first) is True
    assert registry.add(duplicate) is False
    assert len(registry) == 1

    assert registry.get_by_url(
        "https://EXAMPLE.test:443/list.m3u#x"
    ) is first


def test_searches_italian_discovery_sources_by_tags() -> None:
    rai = make_source(
        "rai-discovery",
        "https://example.test/rai",
        priority=30,
        kind="repository",
        country="Italy",
        language="Italian",
        tags=("it", "rai"),
        discovery_enabled=True,
        discovery_mode="search",
        trust_score=80,
    )

    mediaset = make_source(
        "mediaset-discovery",
        "https://example.test/mediaset",
        priority=40,
        kind="api",
        country="IT",
        language="it",
        tags=("it", "mediaset"),
        discovery_enabled=True,
        discovery_mode="api",
        trust_score=75,
    )

    foreign = make_source(
        "foreign",
        "https://example.test/foreign",
        kind="repository",
        country="US",
        language="en",
        tags=("rai",),
        discovery_enabled=True,
        discovery_mode="search",
        trust_score=95,
    )

    registry = SourceRegistry(
        [mediaset, foreign, rai]
    )

    result = registry.italian_sources(
        tags=["rai", "focus"],
        discovery_only=True,
    )

    assert result == (rai,)


def test_tag_search_uses_or_semantics() -> None:
    source = make_source(
        "italian",
        "https://example.test/italian",
        kind="catalog",
        country="IT",
        language="it",
        tags=("rai", "mediaset"),
    )

    registry = SourceRegistry([source])

    assert registry.search(
        tags=["dmax", "mediaset"],
    ) == (source,)


def test_unclassified_sources_are_excluded_by_default() -> None:
    source = make_source(
        "unknown-country",
        "https://example.test/unknown",
        kind="repository",
        discovery_enabled=True,
        discovery_mode="search",
    )

    registry = SourceRegistry([source])

    assert registry.search(country="IT") == ()

    assert registry.search(
        country="IT",
        match_unclassified=True,
    ) == (source,)


def test_discovery_ranking_uses_priority_then_trust() -> None:
    lower_trust = make_source(
        "lower-trust",
        "https://example.test/lower",
        priority=20,
        kind="api",
        discovery_enabled=True,
        discovery_mode="api",
        trust_score=60,
    )

    higher_trust = make_source(
        "higher-trust",
        "https://example.test/higher",
        priority=20,
        kind="repository",
        discovery_enabled=True,
        discovery_mode="search",
        trust_score=90,
    )

    better_priority = make_source(
        "better-priority",
        "https://example.test/better",
        priority=10,
        kind="catalog",
        discovery_enabled=True,
        discovery_mode="api",
        trust_score=50,
    )

    registry = SourceRegistry(
        [lower_trust, higher_trust, better_priority]
    )

    assert registry.discovery_sources() == (
        better_priority,
        higher_trust,
        lower_trust,
    )


def test_minimum_trust_score_filters_sources() -> None:
    trusted = make_source(
        "trusted",
        "https://example.test/trusted",
        kind="api",
        discovery_enabled=True,
        discovery_mode="api",
        trust_score=80,
    )

    weak = make_source(
        "weak",
        "https://example.test/weak",
        kind="repository",
        discovery_enabled=True,
        discovery_mode="search",
        trust_score=40,
    )

    registry = SourceRegistry([weak, trusted])

    assert registry.discovery_sources(
        min_trust_score=70,
    ) == (trusted,)


def test_stats_include_discovery_and_kind_counts() -> None:
    static = make_source(
        "static",
        "playlist.m3u",
        trust_score=80,
    )

    discovery = make_source(
        "discovery",
        "https://example.test/api",
        kind="api",
        discovery_enabled=True,
        discovery_mode="api",
        trust_score=75,
    )

    registry = SourceRegistry([static, discovery])
    stats = registry.stats()

    assert stats.total == 2
    assert stats.discovery == 1
    assert stats.static == 1
    assert stats.trusted == 2
    assert stats.to_dict()["kinds"] == {
        "api": 1,
        "playlist": 1,
    }


def test_setters_preserve_discovery_metadata() -> None:
    source = make_source(
        "discovery",
        "https://example.test/api",
        kind="api",
        country="IT",
        language="it",
        tags=("rai",),
        discovery_enabled=True,
        discovery_mode="api",
        trust_score=70,
    )

    registry = SourceRegistry([source])

    registry.set_priority("discovery", 5)
    registry.set_enabled("discovery", False)
    updated = registry.set_trust_score(
        "discovery",
        95,
    )

    assert updated is not None
    assert updated.priority == 5
    assert updated.enabled is False
    assert updated.trust_score == 95
    assert updated.country == "IT"
    assert updated.tags == ("rai",)


def test_invalid_minimum_trust_is_rejected() -> None:
    registry = SourceRegistry()

    with pytest.raises(
        ValueError,
        match="min_trust_score",
    ):
        registry.search(min_trust_score=101)


def test_strict_false_records_invalid_source() -> None:
    invalid = make_source("", "playlist.m3u")

    result = SourceRegistry().add_many(
        [invalid],
        strict=False,
    )

    assert result.invalid == 1
    assert result.inserted == 0
    assert "incompleta" in (
        result.errors[0].message.casefold()
    )
