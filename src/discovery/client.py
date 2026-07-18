from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from src.models.source import Source


JsonFetcher = Callable[
    [
        str,
        Mapping[str, str],
    ],
    Any,
]


SUPPORTED_PLAYLIST_SUFFIXES = (
    ".m3u",
    ".m3u8",
    ".txt",
)

RAW_GITHUB_HOSTS = {
    "raw.githubusercontent.com",
}

DEFAULT_ITALIAN_TAGS = (
    "it",
    "italia",
    "italian",
    "rai",
    "mediaset",
    "dmax",
    "focus",
    "nove",
)

DEFAULT_GITHUB_QUERIES = (
    '"tvg-country=\\"IT\\"" extension:m3u',
    '"tvg-language=\\"Italian\\"" extension:m3u',
    '"group-title=\\"Italy\\"" extension:m3u',
    '"Rai 1" extension:m3u',
    '"Canale 5" extension:m3u',
)

SAFE_IDENTIFIER_PATTERN = re.compile(
    r"[^a-z0-9._-]+"
)


class DiscoveryRequestError(
    RuntimeError
):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            message
        )

        self.status_code = (
            status_code
        )


@dataclass(
    frozen=True,
    slots=True,
)
class DiscoveryError:
    provider: str
    query: str
    message: str
    status_code: int | None = None

    def to_dict(
        self,
    ) -> dict[str, object]:
        return asdict(
            self
        )


@dataclass(
    frozen=True,
    slots=True,
)
class DiscoveryStats:
    curated_sources: int
    github_queries: int
    github_items: int
    accepted_sources: int
    duplicates_skipped: int
    rejected_items: int
    errors: int
    github_token_used: bool

    def to_dict(
        self,
    ) -> dict[str, object]:
        return asdict(
            self
        )


@dataclass(
    frozen=True,
    slots=True,
)
class DiscoveryBatchResult:
    sources: tuple[
        Source,
        ...,
    ]
    errors: tuple[
        DiscoveryError,
        ...,
    ]
    stats: DiscoveryStats

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "stats": (
                self.stats.to_dict()
            ),
            "errors": [
                error.to_dict()
                for error in self.errors
            ],
            "sources": [
                source.to_dict()
                for source in self.sources
            ],
        }


class SourceDiscoveryClient:
    """
    Ricerca controllata di playlist italiane pubbliche.

    Con `strict_country_only=True`:

    - usa soltanto la playlist per paese Italia;
    - esclude la raccolta basata unicamente sulla lingua;
    - disattiva la ricerca GitHub anche quando GITHUB_TOKEN è presente.

    Provider disponibili in modalità normale:

    - playlist IPTV-org per paese Italia;
    - playlist IPTV-org per lingua italiana;
    - GitHub Code Search, soltanto quando è disponibile un token.

    Il client non scarica né pubblica direttamente i canali. Produce
    oggetti Source che devono essere elaborati dalla pipeline normale:
    download, parser, deduplicazione, Health/Tizen check e ranking.
    """

    GITHUB_SEARCH_URL = (
        "https://api.github.com/"
        "search/code"
    )

    GITHUB_API_VERSION = (
        "2022-11-28"
    )

    def __init__(
        self,
        *,
        github_token: str | None = None,
        user_agent: str = (
            "Italia-TV-Hub/"
            "Source-Discovery"
        ),
        timeout_seconds: int = 20,
        max_results_per_query: int = 5,
        fetch_json: (
            JsonFetcher
            | None
        ) = None,
        strict_country_only: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds deve essere "
                "maggiore di zero"
            )

        if (
            max_results_per_query <= 0
            or max_results_per_query > 30
        ):
            raise ValueError(
                "max_results_per_query deve "
                "essere compreso tra 1 e 30"
            )

        if not isinstance(
            strict_country_only,
            bool,
        ):
            raise TypeError(
                "strict_country_only deve "
                "essere booleano"
            )

        self.strict_country_only = (
            strict_country_only
        )

        self.github_token = (
            github_token
            if github_token is not None
            else os.environ.get(
                "GITHUB_TOKEN",
                "",
            )
        ).strip()

        self.user_agent = (
            str(user_agent).strip()
            or (
                "Italia-TV-Hub/"
                "Source-Discovery"
            )
        )

        self.timeout_seconds = (
            timeout_seconds
        )

        self.max_results_per_query = (
            max_results_per_query
        )

        self._fetch_json_override = (
            fetch_json
        )

    def discover_italian_sources(
        self,
        *,
        tags: (
            Iterable[object]
            | str
            | None
        ) = None,
        include_github: bool | None = None,
        github_queries: (
            Iterable[str]
            | None
        ) = None,
    ) -> DiscoveryBatchResult:
        """
        Restituisce sorgenti candidate per contenuti italiani.

        Le sorgenti curate vengono sempre incluse. La ricerca GitHub
        è facoltativa e non blocca il risultato in caso di errore.
        """

        if (
            include_github is not None
            and not isinstance(
                include_github,
                bool,
            )
        ):
            raise TypeError(
                "include_github deve essere "
                "booleano oppure None"
            )

        effective_include_github = (
            False
            if self.strict_country_only
            else (
                True
                if include_github is None
                else include_github
            )
        )

        normalized_tags = (
            self._normalize_tags(
                tags
                if tags is not None
                else DEFAULT_ITALIAN_TAGS
            )
        )

        curated = list(
            self._curated_italian_sources(
                normalized_tags,
                strict_country_only=(
                    self.strict_country_only
                ),
            )
        )

        sources: list[
            Source
        ] = []

        seen_urls: set[
            str
        ] = set()

        duplicates_skipped = 0

        for source in curated:
            normalized_url = (
                self._normalize_url(
                    source.url
                )
            )

            if normalized_url in seen_urls:
                duplicates_skipped += 1
                continue

            seen_urls.add(
                normalized_url
            )

            sources.append(
                source
            )

        errors: list[
            DiscoveryError
        ] = []

        github_query_count = 0
        github_items = 0
        rejected_items = 0

        if effective_include_github:
            queries = (
                tuple(
                    query.strip()
                    for query
                    in (
                        github_queries
                        if github_queries
                        is not None
                        else DEFAULT_GITHUB_QUERIES
                    )
                    if str(
                        query
                    ).strip()
                )
            )

            if not self.github_token:
                errors.append(
                    DiscoveryError(
                        provider="github",
                        query="",
                        message=(
                            "GITHUB_TOKEN assente: "
                            "ricerca GitHub saltata"
                        ),
                    )
                )

            else:
                for query in queries:
                    github_query_count += 1

                    try:
                        items = (
                            self._search_github(
                                query
                            )
                        )

                    except (
                        DiscoveryRequestError
                    ) as exc:
                        errors.append(
                            DiscoveryError(
                                provider=(
                                    "github"
                                ),
                                query=query,
                                message=str(
                                    exc
                                ),
                                status_code=(
                                    exc.status_code
                                ),
                            )
                        )

                        continue

                    github_items += len(
                        items
                    )

                    for item in items:
                        try:
                            source = (
                                self._source_from_github_item(
                                    item=item,
                                    tags=(
                                        normalized_tags
                                    ),
                                )
                            )

                        except (
                            DiscoveryRequestError
                        ) as exc:
                            errors.append(
                                DiscoveryError(
                                    provider=(
                                        "github"
                                    ),
                                    query=query,
                                    message=str(
                                        exc
                                    ),
                                    status_code=(
                                        exc.status_code
                                    ),
                                )
                            )

                            continue

                        if source is None:
                            rejected_items += 1
                            continue

                        normalized_url = (
                            self._normalize_url(
                                source.url
                            )
                        )

                        if (
                            normalized_url
                            in seen_urls
                        ):
                            duplicates_skipped += 1
                            continue

                        seen_urls.add(
                            normalized_url
                        )

                        sources.append(
                            source
                        )

        sources.sort(
            key=lambda source: (
                source.priority,
                -source.trust_score,
                source.id,
            )
        )

        return DiscoveryBatchResult(
            sources=tuple(
                sources
            ),
            errors=tuple(
                errors
            ),
            stats=DiscoveryStats(
                curated_sources=len(
                    curated
                ),
                github_queries=(
                    github_query_count
                ),
                github_items=(
                    github_items
                ),
                accepted_sources=len(
                    sources
                ),
                duplicates_skipped=(
                    duplicates_skipped
                ),
                rejected_items=(
                    rejected_items
                ),
                errors=len(
                    errors
                ),
                github_token_used=bool(
                    self.github_token
                    and effective_include_github
                ),
            ),
        )

    @staticmethod
    def _curated_italian_sources(
        tags: tuple[str, ...],
        *,
        strict_country_only: bool = False,
    ) -> tuple[
        Source,
        ...,
    ]:
        common_tags = (
            SourceDiscoveryClient
            ._normalize_tags(
                (
                    *tags,
                    "iptv_org",
                    "public",
                )
            )
        )

        country_source = Source(
                id=(
                    "discovery_iptv_org_"
                    "country_it"
                ),
                name=(
                    "IPTV-org Italia "
                    "per paese"
                ),
                url=(
                    "https://"
                    "iptv-org.github.io/"
                    "iptv/countries/"
                    "it.m3u"
                ),
                enabled=True,
                priority=20,
                kind="playlist",
                country="IT",
                language="it",
                tags=common_tags,
                discovery_enabled=True,
                discovery_mode="country",
                trust_score=90,
                refresh_hours=6,
                origin="iptv-org/iptv",
            )

        language_source = Source(
                id=(
                    "discovery_iptv_org_"
                    "language_ita"
                ),
                name=(
                    "IPTV-org Italiano "
                    "per lingua"
                ),
                url=(
                    "https://"
                    "iptv-org.github.io/"
                    "iptv/languages/"
                    "ita.m3u"
                ),
                enabled=True,
                priority=25,
                kind="playlist",
                country="IT",
                language="it",
                tags=common_tags,
                discovery_enabled=True,
                discovery_mode="language",
                trust_score=85,
                refresh_hours=6,
                origin="iptv-org/iptv",
            )

        if strict_country_only:
            return (
                country_source,
            )

        return (
            country_source,
            language_source,
        )

    def _search_github(
        self,
        query: str,
    ) -> tuple[
        Mapping[str, Any],
        ...,
    ]:
        parameters = urllib.parse.urlencode(
            {
                "q": query,
                "per_page": (
                    self.max_results_per_query
                ),
                "page": 1,
            }
        )

        url = (
            f"{self.GITHUB_SEARCH_URL}"
            f"?{parameters}"
        )

        payload = self._fetch_json(
            url,
            self._github_headers(),
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise DiscoveryRequestError(
                "Risposta GitHub non valida"
            )

        raw_items = payload.get(
            "items",
            [],
        )

        if not isinstance(
            raw_items,
            list,
        ):
            raise DiscoveryRequestError(
                "Campo items GitHub "
                "non valido"
            )

        return tuple(
            item
            for item in raw_items
            if isinstance(
                item,
                dict,
            )
        )

    def _source_from_github_item(
        self,
        *,
        item: Mapping[str, Any],
        tags: tuple[str, ...],
    ) -> Source | None:
        content_api_url = str(
            item.get(
                "url",
                "",
            )
        ).strip()

        path = str(
            item.get(
                "path",
                "",
            )
        ).strip()

        if (
            not content_api_url
            or not path
        ):
            return None

        if not self._is_playlist_path(
            path
        ):
            return None

        payload = self._fetch_json(
            content_api_url,
            self._github_headers(),
        )

        if not isinstance(
            payload,
            dict,
        ):
            return None

        download_url = str(
            payload.get(
                "download_url",
                "",
            )
        ).strip()

        if not self._is_safe_github_raw_url(
            download_url
        ):
            return None

        repository = item.get(
            "repository",
            {},
        )

        repository_name = ""

        if isinstance(
            repository,
            dict,
        ):
            repository_name = str(
                repository.get(
                    "full_name",
                    "",
                )
            ).strip()

        source_id = (
            "discovery_github_"
            + self._stable_hash(
                download_url
            )
        )

        display_name = (
            repository_name
            or "repository"
        )

        return Source(
            id=source_id,
            name=(
                "GitHub "
                f"{display_name}/"
                f"{path}"
            ),
            url=download_url,
            enabled=True,
            priority=200,
            kind="playlist",
            country="IT",
            language="it",
            tags=self._normalize_tags(
                (
                    *tags,
                    "github",
                    "discovered",
                )
            ),
            discovery_enabled=True,
            discovery_mode="search",
            trust_score=35,
            refresh_hours=24,
            origin=(
                repository_name
                or "github"
            ),
        )

    def _fetch_json(
        self,
        url: str,
        headers: Mapping[
            str,
            str,
        ],
    ) -> Any:
        if (
            self._fetch_json_override
            is not None
        ):
            return (
                self._fetch_json_override(
                    url,
                    headers,
                )
            )

        request = urllib.request.Request(
            url,
            headers=dict(
                headers
            ),
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=(
                    self.timeout_seconds
                ),
            ) as response:
                data = response.read()

        except urllib.error.HTTPError as exc:
            message = (
                "GitHub HTTP "
                f"{exc.code}"
            )

            try:
                error_payload = json.loads(
                    exc.read().decode(
                        "utf-8",
                        errors="replace",
                    )
                )

                if isinstance(
                    error_payload,
                    dict,
                ):
                    detail = str(
                        error_payload.get(
                            "message",
                            "",
                        )
                    ).strip()

                    if detail:
                        message += (
                            f": {detail}"
                        )

            except (
                json.JSONDecodeError,
                OSError,
            ):
                pass

            raise DiscoveryRequestError(
                message,
                status_code=exc.code,
            ) from exc

        except urllib.error.URLError as exc:
            raise DiscoveryRequestError(
                "Errore rete Discovery: "
                f"{exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise DiscoveryRequestError(
                "Timeout Discovery"
            ) from exc

        try:
            return json.loads(
                data.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise DiscoveryRequestError(
                "Risposta JSON non valida"
            ) from exc

    def _github_headers(
        self,
    ) -> dict[str, str]:
        headers = {
            "Accept": (
                "application/vnd.github+json"
            ),
            "User-Agent": (
                self.user_agent
            ),
            "X-GitHub-Api-Version": (
                self.GITHUB_API_VERSION
            ),
        }

        if self.github_token:
            headers[
                "Authorization"
            ] = (
                "Bearer "
                f"{self.github_token}"
            )

        return headers

    @staticmethod
    def _is_playlist_path(
        path: str,
    ) -> bool:
        lowered = (
            urllib.parse
            .urlsplit(
                str(path)
            )
            .path
            .casefold()
        )

        return lowered.endswith(
            SUPPORTED_PLAYLIST_SUFFIXES
        )

    @staticmethod
    def _is_safe_github_raw_url(
        url: str,
    ) -> bool:
        if not url:
            return False

        try:
            parts = (
                urllib.parse
                .urlsplit(
                    url
                )
            )
        except ValueError:
            return False

        if (
            parts.scheme.casefold()
            != "https"
        ):
            return False

        if (
            (
                parts.hostname
                or ""
            ).casefold()
            not in RAW_GITHUB_HOSTS
        ):
            return False

        return (
            SourceDiscoveryClient
            ._is_playlist_path(
                parts.path
            )
        )

    @staticmethod
    def _stable_hash(
        value: str,
    ) -> str:
        return hashlib.sha256(
            value.encode(
                "utf-8"
            )
        ).hexdigest()[
            :16
        ]

    @staticmethod
    def _normalize_url(
        value: str,
    ) -> str:
        normalized = str(
            value
        ).strip()

        try:
            parts = (
                urllib.parse
                .urlsplit(
                    normalized
                )
            )
        except ValueError:
            return normalized

        if not parts.scheme:
            return normalized

        hostname = (
            parts.hostname.casefold()
            if parts.hostname
            else ""
        )

        port = parts.port

        scheme = (
            parts.scheme.casefold()
        )

        if (
            port is not None
            and not (
                scheme == "http"
                and port == 80
            )
            and not (
                scheme == "https"
                and port == 443
            )
        ):
            hostname = (
                f"{hostname}:{port}"
            )

        return (
            urllib.parse
            .urlunsplit(
                (
                    scheme,
                    hostname,
                    parts.path,
                    parts.query,
                    "",
                )
            )
        )

    @staticmethod
    def _normalize_tags(
        values: (
            Iterable[object]
            | str
        ),
    ) -> tuple[str, ...]:
        if isinstance(
            values,
            str,
        ):
            candidates: Iterable[
                object
            ] = re.split(
                r"[,;|]",
                values,
            )
        else:
            candidates = values

        normalized: list[
            str
        ] = []

        seen: set[
            str
        ] = set()

        for value in candidates:
            tag = (
                str(value)
                .strip()
                .casefold()
                .replace("-", "_")
                .replace(" ", "_")
            )

            tag = (
                SAFE_IDENTIFIER_PATTERN
                .sub(
                    "_",
                    tag,
                )
                .strip("_")
            )

            if (
                not tag
                or tag in seen
            ):
                continue

            seen.add(
                tag
            )

            normalized.append(
                tag
            )

        return tuple(
            normalized
        )
