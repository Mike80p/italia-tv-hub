from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.discovery.client import (
    DiscoveryRequestError,
    SourceDiscoveryClient,
)


def test_curated_discovery_works_without_external_calls() -> None:
    client = SourceDiscoveryClient(
        github_token="",
    )

    result = (
        client.discover_italian_sources(
            include_github=False
        )
    )

    assert len(
        result.sources
    ) == 2

    assert [
        source.url
        for source in result.sources
    ] == [
        (
            "https://iptv-org.github.io/"
            "iptv/countries/it.m3u"
        ),
        (
            "https://iptv-org.github.io/"
            "iptv/languages/ita.m3u"
        ),
    ]

    assert all(
        source.country == "IT"
        for source in result.sources
    )

    assert all(
        source.language == "it"
        for source in result.sources
    )

    assert result.errors == ()
    assert (
        result.stats.curated_sources
        == 2
    )


def test_missing_github_token_is_non_fatal() -> None:
    client = SourceDiscoveryClient(
        github_token="",
    )

    result = (
        client.discover_italian_sources()
    )

    assert len(
        result.sources
    ) == 2

    assert len(
        result.errors
    ) == 1

    assert (
        "GITHUB_TOKEN"
        in result.errors[0].message
    )

    assert (
        result.stats
        .github_queries
        == 0
    )


def test_github_search_adds_safe_raw_playlists() -> None:
    search_url_calls: list[
        str
    ] = []

    def fetch_json(
        url: str,
        headers: Mapping[
            str,
            str,
        ],
    ) -> Any:
        assert (
            headers[
                "Authorization"
            ]
            == "Bearer token"
        )

        if (
            "/search/code?"
            in url
        ):
            search_url_calls.append(
                url
            )

            return {
                "items": [
                    {
                        "path": (
                            "lists/italy.m3u"
                        ),
                        "url": (
                            "https://api.github.com/"
                            "repos/acme/tv/contents/"
                            "lists/italy.m3u"
                        ),
                        "repository": {
                            "full_name": (
                                "acme/tv"
                            )
                        },
                    }
                ]
            }

        return {
            "download_url": (
                "https://raw.githubusercontent.com/"
                "acme/tv/main/lists/italy.m3u"
            )
        }

    client = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
        max_results_per_query=3,
    )

    result = (
        client.discover_italian_sources(
            github_queries=[
                (
                    '"tvg-country=\\"IT\\"" '
                    "extension:m3u"
                )
            ]
        )
    )

    assert len(
        search_url_calls
    ) == 1

    assert len(
        result.sources
    ) == 3

    discovered = result.sources[
        -1
    ]

    assert (
        discovered.origin
        == "acme/tv"
    )

    assert (
        discovered.discovery_mode
        == "search"
    )

    assert (
        discovered.trust_score
        == 35
    )

    assert (
        "github"
        in discovered.tags
    )

    assert (
        result.stats.github_items
        == 1
    )


def test_duplicate_github_urls_are_skipped() -> None:
    call_count = 0

    def fetch_json(
        url: str,
        headers: Mapping[
            str,
            str,
        ],
    ) -> Any:
        nonlocal call_count

        if (
            "/search/code?"
            in url
        ):
            return {
                "items": [
                    {
                        "path": "italy.m3u",
                        "url": (
                            "https://api.github.com/"
                            f"contents/{call_count}"
                        ),
                        "repository": {
                            "full_name": "acme/tv"
                        },
                    },
                    {
                        "path": "italy.m3u",
                        "url": (
                            "https://api.github.com/"
                            f"contents/{call_count + 1}"
                        ),
                        "repository": {
                            "full_name": "acme/tv"
                        },
                    },
                ]
            }

        call_count += 1

        return {
            "download_url": (
                "https://raw.githubusercontent.com/"
                "acme/tv/main/italy.m3u"
            )
        }

    result = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
    ).discover_italian_sources(
        github_queries=["italy extension:m3u"]
    )

    assert len(
        result.sources
    ) == 3

    assert (
        result.stats
        .duplicates_skipped
        == 1
    )


def test_unsafe_or_non_playlist_items_are_rejected() -> None:
    def fetch_json(
        url: str,
        headers: Mapping[
            str,
            str,
        ],
    ) -> Any:
        if (
            "/search/code?"
            in url
        ):
            return {
                "items": [
                    {
                        "path": "README.md",
                        "url": (
                            "https://api.github.com/"
                            "contents/readme"
                        ),
                    },
                    {
                        "path": "italy.m3u",
                        "url": (
                            "https://api.github.com/"
                            "contents/italy"
                        ),
                    },
                ]
            }

        return {
            "download_url": (
                "https://example.test/"
                "italy.m3u"
            )
        }

    result = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
    ).discover_italian_sources(
        github_queries=["italy"]
    )

    assert len(
        result.sources
    ) == 2

    assert (
        result.stats
        .rejected_items
        == 2
    )


def test_github_request_errors_do_not_remove_curated_sources() -> None:
    def fetch_json(
        url: str,
        headers: Mapping[
            str,
            str,
        ],
    ) -> Any:
        raise DiscoveryRequestError(
            "rate limit",
            status_code=403,
        )

    result = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
    ).discover_italian_sources(
        github_queries=["italy"]
    )

    assert len(
        result.sources
    ) == 2

    assert len(
        result.errors
    ) == 1

    assert (
        result.errors[0]
        .status_code
        == 403
    )


def test_discovered_source_ids_are_deterministic() -> None:
    content_url = (
        "https://raw.githubusercontent.com/"
        "acme/tv/main/italy.m3u"
    )

    def fetch_json(
        url: str,
        headers: Mapping[
            str,
            str,
        ],
    ) -> Any:
        if (
            "/search/code?"
            in url
        ):
            return {
                "items": [
                    {
                        "path": "italy.m3u",
                        "url": (
                            "https://api.github.com/"
                            "contents/italy"
                        ),
                        "repository": {
                            "full_name": "acme/tv"
                        },
                    }
                ]
            }

        return {
            "download_url": content_url
        }

    first = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
    ).discover_italian_sources(
        github_queries=["italy"]
    ).sources[-1]

    second = SourceDiscoveryClient(
        github_token="token",
        fetch_json=fetch_json,
    ).discover_italian_sources(
        github_queries=["italy"]
    ).sources[-1]

    assert first.id == second.id
    assert first.url == content_url


def test_invalid_constructor_values_are_rejected() -> None:
    try:
        SourceDiscoveryClient(
            timeout_seconds=0
        )
    except ValueError as exc:
        assert "timeout_seconds" in str(
            exc
        )
    else:
        raise AssertionError(
            "ValueError non sollevato"
        )

    try:
        SourceDiscoveryClient(
            max_results_per_query=31
        )
    except ValueError as exc:
        assert (
            "max_results_per_query"
            in str(exc)
        )
    else:
        raise AssertionError(
            "ValueError non sollevato"
        )
