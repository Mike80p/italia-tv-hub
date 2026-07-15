import pytest

from src.models.channel import Channel
from src.registry.channel_registry import ChannelRegistry


def make_channel(
    name: str,
    stream_url: str,
    *,
    group: str = "Generali",
    tvg_id: str = "",
    tvg_name: str = "",
    source_id: str = "source-a",
) -> Channel:
    return Channel(
        name,
        stream_url,
        group,
        tvg_id,
        tvg_name,
        "",
        source_id,
        {},
        [],
    )


def test_add_and_snapshot_keep_insertion_order():
    first = make_channel(
        "Rai 1",
        "https://example.test/rai1",
    )

    second = make_channel(
        "Canale 5",
        "https://example.test/canale5",
    )

    registry = ChannelRegistry()

    assert registry.add(first) is True
    assert registry.add(second) is True

    assert registry.snapshot() == (
        first,
        second,
    )

    assert len(registry) == 2


def test_duplicate_url_is_skipped_even_when_name_changes():
    first = make_channel(
        "Rai 1",
        "https://example.test/live",
    )

    duplicate = make_channel(
        "Rai Uno",
        " https://example.test/live ",
    )

    registry = ChannelRegistry([first])

    assert registry.add(duplicate) is False
    assert registry.snapshot() == (first,)


def test_upsert_replaces_same_url_and_refreshes_indexes():
    old = make_channel(
        "Rai 1",
        "https://example.test/rai1",
        group="Generali",
        tvg_id="rai-1",
        source_id="old-source",
    )

    new = make_channel(
        "Rai Uno HD",
        "https://example.test/rai1",
        group="HD",
        tvg_id="rai-1-hd",
        source_id="new-source",
    )

    registry = ChannelRegistry([old])

    assert registry.upsert(new) is True
    assert registry.snapshot() == (new,)

    assert registry.find_by_name("rai 1") == ()
    assert registry.find_by_source("old-source") == ()
    assert registry.find_by_group("generali") == ()
    assert registry.find_by_tvg_id("rai-1") == ()

    assert registry.find_by_name(
        "RAI UNO HD"
    ) == (new,)

    assert registry.find_by_source(
        "NEW-SOURCE"
    ) == (new,)

    assert registry.find_by_group(
        "hd"
    ) == (new,)

    assert registry.find_by_tvg_id(
        "rai-1-hd"
    ) == (new,)


def test_same_name_with_different_urls_is_allowed():
    first = make_channel(
        "Rai 1",
        "https://a.test/rai1",
    )

    second = make_channel(
        " rai   1 ",
        "https://b.test/rai1",
    )

    registry = ChannelRegistry(
        [first, second]
    )

    assert registry.find_by_name(
        "RAI 1"
    ) == (
        first,
        second,
    )


def test_indexes_are_case_insensitive_and_whitespace_normalized():
    channel = make_channel(
        "  Rai   News 24 ",
        "https://example.test/rainews",
        group="  News   Italia ",
        tvg_id=" RAI-NEWS-24 ",
        source_id=" Main Source ",
    )

    registry = ChannelRegistry([channel])

    assert registry.find_by_name(
        "rai news 24"
    ) == (channel,)

    assert registry.find_by_group(
        "NEWS ITALIA"
    ) == (channel,)

    assert registry.find_by_tvg_id(
        "rai-news-24"
    ) == (channel,)

    assert registry.find_by_source(
        "main source"
    ) == (channel,)


def test_add_many_reports_inserted_replaced_and_skipped():
    existing = make_channel(
        "Rai 1",
        "https://example.test/rai1",
    )

    replacement = make_channel(
        "Rai Uno",
        "https://example.test/rai1",
    )

    new = make_channel(
        "Rai 2",
        "https://example.test/rai2",
    )

    registry = ChannelRegistry([existing])

    result = registry.add_many(
        [replacement, new],
        replace=False,
    )

    assert result.inserted == 1
    assert result.replaced == 0
    assert result.skipped == 1
    assert result.changed == 1

    result = registry.add_many(
        [replacement],
        replace=True,
    )

    assert result.inserted == 0
    assert result.replaced == 1
    assert result.skipped == 0
    assert result.changed == 1

    assert registry.get_by_url(
        existing.stream_url
    ) is replacement


def test_replace_can_change_url_and_preserves_position():
    first = make_channel(
        "Rai 1",
        "https://old.test/rai1",
    )

    second = make_channel(
        "Rai 2",
        "https://example.test/rai2",
    )

    replacement = make_channel(
        "Rai 1 HD",
        "https://new.test/rai1",
    )

    registry = ChannelRegistry(
        [first, second]
    )

    assert registry.replace(
        first.stream_url,
        replacement,
    ) is True

    assert registry.snapshot() == (
        replacement,
        second,
    )

    assert registry.get_by_url(
        first.stream_url
    ) is None

    assert registry.get_by_url(
        replacement.stream_url
    ) is replacement


def test_replace_rejects_url_owned_by_another_channel():
    first = make_channel(
        "Rai 1",
        "https://example.test/rai1",
    )

    second = make_channel(
        "Rai 2",
        "https://example.test/rai2",
    )

    conflict = make_channel(
        "Rai 1 Alt",
        second.stream_url,
    )

    registry = ChannelRegistry(
        [first, second]
    )

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        registry.replace(
            first.stream_url,
            conflict,
        )

    assert registry.snapshot() == (
        first,
        second,
    )


def test_remove_by_url_updates_all_indexes():
    channel = make_channel(
        "Rai 1",
        "https://example.test/rai1",
        group="Generali",
        tvg_id="rai-1",
        source_id="source-a",
    )

    registry = ChannelRegistry([channel])

    removed = registry.remove_by_url(
        " https://example.test/rai1 "
    )

    assert removed is channel

    assert registry.remove_by_url(
        channel.stream_url
    ) is None

    assert registry.find_by_name(
        "rai 1"
    ) == ()

    assert registry.find_by_group(
        "generali"
    ) == ()

    assert registry.find_by_tvg_id(
        "rai-1"
    ) == ()

    assert registry.find_by_source(
        "source-a"
    ) == ()

    assert len(registry) == 0


def test_remove_source_removes_only_matching_channels():
    first = make_channel(
        "Rai 1",
        "https://a.test/1",
        source_id="source-a",
    )

    second = make_channel(
        "Rai 2",
        "https://a.test/2",
        source_id="source-a",
    )

    third = make_channel(
        "Canale 5",
        "https://b.test/5",
        source_id="source-b",
    )

    registry = ChannelRegistry(
        [first, second, third]
    )

    assert registry.remove_source(
        "SOURCE-A"
    ) == (
        first,
        second,
    )

    assert registry.snapshot() == (
        third,
    )


def test_search_uses_main_metadata_fields():
    first = make_channel(
        "Rai 1",
        "https://example.test/rai1",
        group="Generali",
        tvg_id="rai-1",
        tvg_name="Rai Uno",
        source_id="italia",
    )

    second = make_channel(
        "Sky TG24",
        "https://example.test/skytg24",
        group="News",
        tvg_id="sky-tg24",
        source_id="satellite",
    )

    registry = ChannelRegistry(
        [first, second]
    )

    assert registry.search(
        "uno"
    ) == (first,)

    assert registry.search(
        "news"
    ) == (second,)

    assert registry.search(
        "italia"
    ) == (first,)

    assert registry.search("") == (
        first,
        second,
    )


def test_contains_and_iteration():
    first = make_channel(
        "Rai 1",
        "https://example.test/rai1",
    )

    second = make_channel(
        "Rai 2",
        "https://example.test/rai2",
    )

    registry = ChannelRegistry(
        [first, second]
    )

    assert first in registry
    assert first.stream_url in registry

    assert (
        "https://example.test/not-found"
        not in registry
    )

    assert tuple(registry) == (
        first,
        second,
    )


def test_stats_and_clear():
    first = make_channel(
        "Rai 1",
        "https://example.test/rai1",
        group="Generali",
        tvg_id="rai-1",
        source_id="source-a",
    )

    second = make_channel(
        "Canale 5",
        "https://example.test/canale5",
        group="Generali",
        tvg_id="canale-5",
        source_id="source-b",
    )

    registry = ChannelRegistry(
        [first, second]
    )

    stats = registry.stats()

    assert stats.channels == 2
    assert stats.sources == 2
    assert stats.groups == 1
    assert stats.tvg_ids == 2

    registry.clear()

    assert registry.snapshot() == ()
    assert registry.stats().channels == 0
    assert bool(registry) is False


def test_channel_model_rejects_empty_name():
    with pytest.raises(ValueError):
        make_channel(
            "",
            "https://example.test/live",
        )


def test_channel_model_rejects_empty_url():
    with pytest.raises(ValueError):
        make_channel(
            "Rai 1",
            "   ",
        )


def test_registry_rejects_non_channel_objects():
    registry = ChannelRegistry()

    with pytest.raises(
        TypeError,
        match="Channel",
    ):
        registry.add(
            object()  # type: ignore[arg-type]
        )