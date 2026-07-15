import pytest

from src.catalog.source_registry import (
    SourceRegistry,
)
from src.models.source import Source


def make_source(
    source_id: str,
    name: str,
    url: str,
    *,
    enabled: bool = True,
    priority: int = 100,
) -> Source:
    return Source(
        id=source_id,
        name=name,
        url=url,
        enabled=enabled,
        priority=priority,
    )


def test_sources_are_ordered_by_priority():
    low_priority = make_source(
        "low",
        "Bassa priorità",
        "https://example.test/low.m3u",
        priority=100,
    )

    high_priority = make_source(
        "high",
        "Alta priorità",
        "https://example.test/high.m3u",
        priority=10,
    )

    medium_priority = make_source(
        "medium",
        "Media priorità",
        "https://example.test/medium.m3u",
        priority=50,
    )

    registry = SourceRegistry(
        [
            low_priority,
            high_priority,
            medium_priority,
        ]
    )

    assert registry.snapshot() == (
        high_priority,
        medium_priority,
        low_priority,
    )


def test_same_priority_keeps_insertion_order():
    first = make_source(
        "first",
        "Prima",
        "https://example.test/first.m3u",
        priority=10,
    )

    second = make_source(
        "second",
        "Seconda",
        "https://example.test/second.m3u",
        priority=10,
    )

    registry = SourceRegistry(
        [
            first,
            second,
        ]
    )

    assert registry.snapshot() == (
        first,
        second,
    )


def test_enabled_and_disabled_sources():
    enabled = make_source(
        "enabled",
        "Abilitata",
        "https://example.test/enabled.m3u",
        enabled=True,
    )

    disabled = make_source(
        "disabled",
        "Disabilitata",
        "https://example.test/disabled.m3u",
        enabled=False,
    )

    registry = SourceRegistry(
        [
            enabled,
            disabled,
        ]
    )

    assert registry.enabled_sources() == (
        enabled,
    )

    assert registry.disabled_sources() == (
        disabled,
    )


def test_duplicate_id_is_skipped_case_insensitively():
    first = make_source(
        "rai",
        "Rai",
        "https://example.test/rai.m3u",
    )

    duplicate = make_source(
        " RAI ",
        "Rai alternativa",
        "https://example.test/rai-alt.m3u",
    )

    registry = SourceRegistry([first])

    assert registry.add(duplicate) is False
    assert len(registry) == 1
    assert registry.get("RAI") is first


def test_duplicate_url_is_skipped():
    first = make_source(
        "source-a",
        "Sorgente A",
        "https://example.test/list.m3u",
    )

    duplicate = make_source(
        "source-b",
        "Sorgente B",
        " https://example.test/list.m3u ",
    )

    registry = SourceRegistry([first])

    assert registry.add(duplicate) is False
    assert registry.snapshot() == (first,)


def test_upsert_updates_source_and_url_index():
    original = make_source(
        "rai",
        "Rai",
        "https://example.test/old.m3u",
        priority=100,
    )

    updated = make_source(
        "RAI",
        "Rai aggiornata",
        "https://example.test/new.m3u",
        priority=10,
    )

    registry = SourceRegistry([original])

    assert registry.upsert(updated) is True
    assert registry.get("rai") is updated

    assert registry.get_by_url(
        original.url
    ) is None

    assert registry.get_by_url(
        updated.url
    ) is updated


def test_upsert_rejects_url_owned_by_another_source():
    first = make_source(
        "first",
        "Prima",
        "https://example.test/first.m3u",
    )

    second = make_source(
        "second",
        "Seconda",
        "https://example.test/second.m3u",
    )

    conflicting_update = make_source(
        "first",
        "Prima aggiornata",
        second.url,
    )

    registry = SourceRegistry(
        [
            first,
            second,
        ]
    )

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        registry.upsert(
            conflicting_update
        )

    assert registry.get("first") is first
    assert registry.get("second") is second


def test_set_enabled_updates_frozen_source():
    source = make_source(
        "rai",
        "Rai",
        "https://example.test/rai.m3u",
        enabled=True,
    )

    registry = SourceRegistry([source])

    updated = registry.set_enabled(
        "RAI",
        False,
    )

    assert updated is not None
    assert updated.enabled is False

    assert registry.enabled_sources() == ()
    assert registry.disabled_sources() == (
        updated,
    )


def test_set_priority_changes_order():
    first = make_source(
        "first",
        "Prima",
        "https://example.test/first.m3u",
        priority=10,
    )

    second = make_source(
        "second",
        "Seconda",
        "https://example.test/second.m3u",
        priority=100,
    )

    registry = SourceRegistry(
        [
            first,
            second,
        ]
    )

    updated = registry.set_priority(
        "second",
        1,
    )

    assert updated is not None

    assert registry.snapshot() == (
        updated,
        first,
    )


def test_remove_updates_id_and_url_indexes():
    source = make_source(
        "rai",
        "Rai",
        "https://example.test/rai.m3u",
    )

    registry = SourceRegistry([source])

    removed = registry.remove("RAI")

    assert removed is source
    assert registry.get("rai") is None

    assert registry.get_by_url(
        source.url
    ) is None

    assert registry.remove("rai") is None


def test_registry_stats():
    remote_enabled = make_source(
        "remote-enabled",
        "Remota abilitata",
        "https://example.test/one.m3u",
        enabled=True,
    )

    remote_disabled = make_source(
        "remote-disabled",
        "Remota disabilitata",
        "http://example.test/two.m3u",
        enabled=False,
    )

    local_enabled = make_source(
        "local-enabled",
        "Locale abilitata",
        "config/local.m3u",
        enabled=True,
    )

    registry = SourceRegistry(
        [
            remote_enabled,
            remote_disabled,
            local_enabled,
        ]
    )

    stats = registry.stats()

    assert stats.total == 3
    assert stats.enabled == 2
    assert stats.disabled == 1
    assert stats.remote == 2
    assert stats.local == 1


def test_add_many_reports_results():
    existing = make_source(
        "existing",
        "Esistente",
        "https://example.test/existing.m3u",
    )

    duplicate = make_source(
        "EXISTING",
        "Duplicata",
        "https://example.test/duplicate.m3u",
    )

    new = make_source(
        "new",
        "Nuova",
        "https://example.test/new.m3u",
    )

    registry = SourceRegistry([existing])

    result = registry.add_many(
        [
            duplicate,
            new,
        ]
    )

    assert result.inserted == 1
    assert result.replaced == 0
    assert result.skipped == 1
    assert result.invalid == 0
    assert result.changed == 1
    assert result.processed == 2


def test_non_strict_batch_collects_invalid_sources():
    valid = make_source(
        "valid",
        "Valida",
        "https://example.test/valid.m3u",
    )

    invalid = make_source(
        "",
        "Non valida",
        "https://example.test/invalid.m3u",
    )

    registry = SourceRegistry()

    result = registry.add_many(
        [
            valid,
            invalid,
        ],
        strict=False,
    )

    assert result.inserted == 1
    assert result.invalid == 1
    assert len(result.errors) == 1

    assert result.errors[0].source_id == (
        "<unknown>"
    )

    assert "incompleta" in (
        result.errors[0].message.lower()
    )

    assert registry.snapshot() == (
        valid,
    )


def test_strict_batch_rejects_invalid_source():
    invalid = make_source(
        "",
        "Non valida",
        "https://example.test/invalid.m3u",
    )

    registry = SourceRegistry()

    with pytest.raises(ValueError):
        registry.add_many(
            [invalid],
            strict=True,
        )

    assert len(registry) == 0


def test_contains_iteration_and_clear():
    first = make_source(
        "first",
        "Prima",
        "https://example.test/first.m3u",
        priority=20,
    )

    second = make_source(
        "second",
        "Seconda",
        "https://example.test/second.m3u",
        priority=10,
    )

    registry = SourceRegistry(
        [
            first,
            second,
        ]
    )

    assert first in registry
    assert "FIRST" in registry
    assert "missing" not in registry

    assert tuple(registry) == (
        second,
        first,
    )

    registry.clear()

    assert len(registry) == 0
    assert bool(registry) is False
    assert registry.snapshot() == ()