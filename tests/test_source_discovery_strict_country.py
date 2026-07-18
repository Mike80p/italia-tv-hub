from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from src.discovery.client import (
    SourceDiscoveryClient,
)


def test_strict_mode_uses_only_country_playlist() -> None:
    calls: list[str] = []

    def fetch_json(
        url: str,
        headers: Mapping[str, str],
    ) -> Any:
        calls.append(url)
        raise AssertionError(
            "La modalità strict non deve "
            "chiamare GitHub"
        )

    client = SourceDiscoveryClient(
        github_token="token-presente",
        fetch_json=fetch_json,
        strict_country_only=True,
    )

    result = (
        client.discover_italian_sources()
    )

    assert calls == []
    assert len(result.sources) == 1
    assert (
        result.sources[0].url
        == (
            "https://iptv-org.github.io/"
            "iptv/countries/it.m3u"
        )
    )
    assert (
        result.sources[0].country
        == "IT"
    )
    assert (
        result.stats.curated_sources
        == 1
    )
    assert (
        result.stats.github_queries
        == 0
    )
    assert (
        result.stats.github_items
        == 0
    )
    assert (
        result.stats
        .github_token_used
        is False
    )
    assert result.errors == ()


def test_strict_mode_ignores_explicit_github_request() -> None:
    def fetch_json(
        url: str,
        headers: Mapping[str, str],
    ) -> Any:
        raise AssertionError(
            "GitHub deve restare escluso "
            "in modalità strict"
        )

    result = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
        strict_country_only=True,
    ).discover_italian_sources(
        include_github=True,
        github_queries=["italy"],
    )

    assert len(result.sources) == 1
    assert (
        result.stats.github_queries
        == 0
    )
    assert result.errors == ()


def test_normal_mode_keeps_legacy_default() -> None:
    result = SourceDiscoveryClient(
        github_token="",
        strict_country_only=False,
    ).discover_italian_sources()

    assert len(result.sources) == 2
    assert len(result.errors) == 1
    assert (
        "GITHUB_TOKEN"
        in result.errors[0].message
    )


def test_strict_country_only_must_be_boolean() -> None:
    with pytest.raises(
        TypeError,
        match="strict_country_only",
    ):
        SourceDiscoveryClient(
            strict_country_only="yes",
        )
