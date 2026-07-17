from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Callable, Iterable

from src.models.channel import Channel


@dataclass(
    frozen=True,
    slots=True,
)
class EPGChannel:
    """
    Canale letto da una guida XMLTV.

    `channel_id` corrisponde all'attributo XML:

        <channel id="Rai1.it">

    `display_names` contiene uno o più elementi:

        <display-name>Rai 1</display-name>
    """

    channel_id: str
    display_names: tuple[str, ...]
    icon_url: str = ""
    source_url: str = ""

    def __post_init__(
        self,
    ) -> None:
        channel_id = str(
            self.channel_id
        ).strip()

        if not channel_id:
            raise ValueError(
                "ID canale EPG vuoto"
            )

        normalized_names: list[
            str
        ] = []

        seen: set[
            str
        ] = set()

        for value in self.display_names:
            name = str(
                value
            ).strip()

            folded = name.casefold()

            if (
                not name
                or folded in seen
            ):
                continue

            seen.add(
                folded
            )

            normalized_names.append(
                name
            )

        if not normalized_names:
            normalized_names.append(
                channel_id
            )

        object.__setattr__(
            self,
            "channel_id",
            channel_id,
        )

        object.__setattr__(
            self,
            "display_names",
            tuple(
                normalized_names
            ),
        )

        object.__setattr__(
            self,
            "icon_url",
            str(
                self.icon_url
            ).strip(),
        )

        object.__setattr__(
            self,
            "source_url",
            str(
                self.source_url
            ).strip(),
        )

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
class EPGMatch:
    playlist_channel: Channel
    epg_channel: EPGChannel
    score: float
    method: str
    playlist_key: str
    epg_key: str

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "playlist_channel": {
                "name": (
                    self.playlist_channel
                    .name
                ),
                "tvg_id": (
                    self.playlist_channel
                    .tvg_id
                ),
                "tvg_name": (
                    self.playlist_channel
                    .tvg_name
                ),
                "stream_url": (
                    self.playlist_channel
                    .stream_url
                ),
                "source_id": (
                    self.playlist_channel
                    .source_id
                ),
            },
            "epg_channel": (
                self.epg_channel
                .to_dict()
            ),
            "score": self.score,
            "method": self.method,
            "playlist_key": (
                self.playlist_key
            ),
            "epg_key": self.epg_key,
        }


@dataclass(
    frozen=True,
    slots=True,
)
class EPGAmbiguousMatch:
    playlist_channel: Channel
    candidates: tuple[
        EPGMatch,
        ...,
    ]

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "playlist_channel": {
                "name": (
                    self.playlist_channel
                    .name
                ),
                "tvg_id": (
                    self.playlist_channel
                    .tvg_id
                ),
                "tvg_name": (
                    self.playlist_channel
                    .tvg_name
                ),
                "stream_url": (
                    self.playlist_channel
                    .stream_url
                ),
            },
            "candidates": [
                candidate.to_dict()
                for candidate
                in self.candidates
            ],
        }


@dataclass(
    frozen=True,
    slots=True,
)
class EPGMatchStats:
    playlist_channels: int
    epg_channels: int
    matched: int
    unmatched: int
    ambiguous: int
    matched_by_tvg_id: int
    matched_by_name: int
    matched_by_alias: int
    matched_by_similarity: int
    coverage_percent: float

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
class EPGMatchBatchResult:
    matches: tuple[
        EPGMatch,
        ...,
    ]
    unmatched: tuple[
        Channel,
        ...,
    ]
    ambiguous: tuple[
        EPGAmbiguousMatch,
        ...,
    ]
    stats: EPGMatchStats

    def match_by_stream_url(
        self,
    ) -> dict[
        str,
        EPGMatch,
    ]:
        return {
            match.playlist_channel
            .stream_url: match
            for match in self.matches
        }

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "stats": (
                self.stats.to_dict()
            ),
            "matches": [
                match.to_dict()
                for match in self.matches
            ],
            "unmatched": [
                {
                    "name": channel.name,
                    "tvg_id": channel.tvg_id,
                    "tvg_name": (
                        channel.tvg_name
                    ),
                    "stream_url": (
                        channel.stream_url
                    ),
                    "source_id": (
                        channel.source_id
                    ),
                }
                for channel
                in self.unmatched
            ],
            "ambiguous": [
                item.to_dict()
                for item
                in self.ambiguous
            ],
        }


class EPGChannelMatcher:
    """
    Abbina tutti i canali della playlist ai canali XMLTV.

    La normalizzazione è generica e non dipende solo da una lista
    manuale di emittenti. Gestisce automaticamente:

    - suffissi ID come `.it@SD`, `.de@IT`, `@HD`, `@4K`;
    - qualità, risoluzioni, codec, backup e indicazioni geo-blocked;
    - punteggiatura, accenti, maiuscole e separatori;
    - numeri scritti in lettere, come Uno/1, Due/2 e Nove/9;
    - varianti con o senza TV, Channel, Network, Italia o Italy;
    - alias italiani controllati per i casi realmente particolari.

    Località, versioni regionali e simbolo `+` vengono conservati.
    Le corrispondenze ambigue non vengono accettate.
    """

    EXACT_ID_SCORE = 100.0
    NORMALIZED_ID_SCORE = 97.0
    EXACT_NAME_SCORE = 92.0
    ALIAS_SCORE = 89.0
    SIMILARITY_MINIMUM = 86.0

    # Compatibilità con il nome della costante esposto in precedenza.
    QUALITY_WORDS = {
        "144p",
        "240p",
        "270p",
        "288p",
        "300p",
        "360p",
        "404p",
        "432p",
        "480p",
        "540p",
        "576p",
        "720p",
        "900p",
        "1080p",
        "1440p",
        "2160p",
        "4k",
        "8k",
        "uhd",
        "fhd",
        "fullhd",
        "full",
        "hd",
        "sd",
        "hq",
        "lq",
        "hevc",
        "h265",
        "h264",
        "av1",
        "mpeg2",
        "mpeg4",
    }

    HARD_TECHNICAL_WORDS = (
        QUALITY_WORDS
        | {
            "backup",
            "mirror",
            "fallback",
            "test",
            "demo",
            "source",
            "server",
            "feed",
            "geo",
            "blocked",
            "geoblocked",
            "geolocked",
            "only",
        }
    )

    BRACKET_TECHNICAL_WORDS = (
        HARD_TECHNICAL_WORDS
        | {
            "it",
            "ita",
            "italian",
            "italiano",
            "italy",
            "eu",
            "europe",
            "international",
            "intl",
        }
    )

    SOFT_MEDIA_WORDS = {
        "tv",
        "television",
        "televisione",
        "channel",
        "canale",
        "network",
        "rete",
    }

    LOCALE_WORDS = {
        "italia",
        "italy",
        "italiano",
        "italiana",
        "italian",
    }

    IDENTIFIER_TAGS = {
        "144p",
        "240p",
        "270p",
        "288p",
        "300p",
        "360p",
        "404p",
        "432p",
        "480p",
        "540p",
        "576p",
        "720p",
        "900p",
        "1080p",
        "1440p",
        "2160p",
        "4k",
        "8k",
        "uhd",
        "fhd",
        "fullhd",
        "hd",
        "sd",
        "hq",
        "lq",
        "hevc",
        "h265",
        "h264",
        "av1",
        "backup",
        "mirror",
        "fallback",
        "test",
        "it",
        "ita",
        "italy",
        "italian",
        "de",
        "ger",
        "germany",
        "fr",
        "fra",
        "france",
        "es",
        "spa",
        "spain",
        "uk",
        "gb",
        "gbr",
        "us",
        "usa",
        "ch",
        "che",
        "at",
        "aut",
        "eu",
        "europe",
        "intl",
        "international",
    }

    NUMBER_WORDS = {
        "zero": "0",
        "uno": "1",
        "one": "1",
        "due": "2",
        "two": "2",
        "tre": "3",
        "three": "3",
        "quattro": "4",
        "four": "4",
        "cinque": "5",
        "five": "5",
        "sei": "6",
        "six": "6",
        "sette": "7",
        "seven": "7",
        "otto": "8",
        "eight": "8",
        "nove": "9",
        "nine": "9",
        "dieci": "10",
        "ten": "10",
        "undici": "11",
        "eleven": "11",
        "dodici": "12",
        "twelve": "12",
        "tredici": "13",
        "thirteen": "13",
        "quattordici": "14",
        "fourteen": "14",
        "quindici": "15",
        "fifteen": "15",
        "sedici": "16",
        "sixteen": "16",
        "diciassette": "17",
        "seventeen": "17",
        "diciotto": "18",
        "eighteen": "18",
        "diciannove": "19",
        "nineteen": "19",
        "venti": "20",
        "twenty": "20",
    }

    ITALIAN_ALIASES = {
        "rai1": {
            "rai1",
            "raiuno",
        },
        "rai2": {
            "rai2",
            "raidue",
        },
        "rai3": {
            "rai3",
            "raitre",
        },
        "rainews24": {
            "rainews24",
            "rainews",
            "rai24",
        },
        "raimovie": {
            "raimovie",
        },
        "raipremium": {
            "raipremium",
        },
        "raigulp": {
            "raigulp",
        },
        "raiyoyo": {
            "raiyoyo",
        },
        "raistoria": {
            "raistoria",
        },
        "raiscuola": {
            "raiscuola",
        },
        "raisport": {
            "raisport",
        },
        "raisportplus": {
            "raisportplus",
            "raisportpiu",
            "raisport+",
        },
        "canale5": {
            "canale5",
            "channel5",
        },
        "italia1": {
            "italia1",
            "italiauno",
        },
        "rete4": {
            "rete4",
            "retequattro",
        },
        "mediaset20": {
            "20",
            "20mediaset",
            "mediaset20",
            "ventimediaset",
        },
        "italia2": {
            "italia2",
            "mediasetitalia2",
        },
        "tgcom24": {
            "tgcom24",
            "mediasettgcom24",
        },
        "la5": {
            "la5",
        },
        "iris": {
            "iris",
        },
        "cine34": {
            "cine34",
        },
        "focus": {
            "focus",
            "focustv",
        },
        "topcrime": {
            "topcrime",
        },
        "mediasetextra": {
            "mediasetextra",
        },
        "boing": {
            "boing",
        },
        "cartoonito": {
            "cartoonito",
        },
        "nove": {
            "nove",
            "9",
            "nove9",
            "canale9",
            "channel9",
        },
        "dmax": {
            "dmax",
        },
        "realtime": {
            "realtime",
        },
        "giallo": {
            "giallo",
        },
        "foodnetwork": {
            "foodnetwork",
        },
        "motortrend": {
            "motortrend",
        },
        "k2": {
            "k2",
        },
        "frisbee": {
            "frisbee",
        },
        "warnertv": {
            "warner",
            "warnertv",
        },
        "tv8": {
            "tv8",
        },
        "cielo": {
            "cielo",
            "cielotv",
        },
        "skytg24": {
            "skytg24",
        },
        "la7": {
            "la7",
        },
        "la7d": {
            "la7d",
        },
    }

    def __init__(
        self,
        *,
        similarity_minimum: float = (
            SIMILARITY_MINIMUM
        ),
    ) -> None:
        if not (
            0.0
            <= similarity_minimum
            <= 100.0
        ):
            raise ValueError(
                "similarity_minimum deve "
                "essere compreso tra 0 e 100"
            )

        self.similarity_minimum = float(
            similarity_minimum
        )

        self._alias_to_canonical = (
            self._build_alias_index()
        )

    def match_channels(
        self,
        playlist_channels: Iterable[
            Channel
        ],
        epg_channels: Iterable[
            EPGChannel
        ],
    ) -> EPGMatchBatchResult:
        playlist = tuple(
            playlist_channels
        )

        epg = tuple(
            epg_channels
        )

        if any(
            not isinstance(
                channel,
                Channel,
            )
            for channel in playlist
        ):
            raise TypeError(
                "playlist_channels contiene "
                "elementi non Channel"
            )

        if any(
            not isinstance(
                channel,
                EPGChannel,
            )
            for channel in epg
        ):
            raise TypeError(
                "epg_channels contiene elementi "
                "non EPGChannel"
            )

        exact_id_index: dict[
            str,
            list[EPGChannel],
        ] = defaultdict(
            list
        )

        normalized_id_index: dict[
            str,
            list[EPGChannel],
        ] = defaultdict(
            list
        )

        exact_name_index: dict[
            str,
            list[EPGChannel],
        ] = defaultdict(
            list
        )

        universal_name_index: dict[
            str,
            list[EPGChannel],
        ] = defaultdict(
            list
        )

        epg_search_keys: dict[
            str,
            tuple[str, ...],
        ] = {}

        for epg_channel in epg:
            exact_id = (
                epg_channel.channel_id
                .strip()
                .casefold()
            )

            self._append_unique(
                exact_id_index[
                    exact_id
                ],
                epg_channel,
            )

            for normalized_id in (
                self.identifier_variants(
                    epg_channel.channel_id
                )
            ):
                self._append_unique(
                    normalized_id_index[
                        normalized_id
                    ],
                    epg_channel,
                )

            search_keys: list[
                str
            ] = []

            for name in (
                *epg_channel.display_names,
                epg_channel.channel_id,
            ):
                strict_name = (
                    self.normalize_name(
                        name
                    )
                )

                if strict_name:
                    self._append_unique(
                        exact_name_index[
                            strict_name
                        ],
                        epg_channel,
                    )

                for variant in (
                    self.name_variants(
                        name
                    )
                ):
                    if variant not in search_keys:
                        search_keys.append(
                            variant
                        )

                    self._append_unique(
                        universal_name_index[
                            variant
                        ],
                        epg_channel,
                    )

                for identifier_key in (
                    self.identifier_variants(
                        name
                    )
                ):
                    if (
                        identifier_key
                        and identifier_key
                        not in search_keys
                    ):
                        search_keys.append(
                            identifier_key
                        )

            epg_search_keys[
                epg_channel.channel_id
            ] = tuple(
                search_keys
            )

        matches: list[
            EPGMatch
        ] = []

        unmatched: list[
            Channel
        ] = []

        ambiguous: list[
            EPGAmbiguousMatch
        ] = []

        for channel in playlist:
            candidates = (
                self._candidate_matches(
                    channel=channel,
                    epg_channels=epg,
                    exact_id_index=(
                        exact_id_index
                    ),
                    normalized_id_index=(
                        normalized_id_index
                    ),
                    exact_name_index=(
                        exact_name_index
                    ),
                    universal_name_index=(
                        universal_name_index
                    ),
                    epg_search_keys=(
                        epg_search_keys
                    ),
                )
            )

            if not candidates:
                unmatched.append(
                    channel
                )
                continue

            candidates.sort(
                key=lambda item: (
                    -item.score,
                    item.epg_channel
                    .channel_id
                    .casefold(),
                )
            )

            highest_score = (
                candidates[0].score
            )

            top_candidates = tuple(
                candidate
                for candidate
                in candidates
                if candidate.score
                == highest_score
            )

            unique_top_ids = {
                candidate
                .epg_channel
                .channel_id
                .casefold()
                for candidate
                in top_candidates
            }

            if len(
                unique_top_ids
            ) > 1:
                ambiguous.append(
                    EPGAmbiguousMatch(
                        playlist_channel=(
                            channel
                        ),
                        candidates=(
                            top_candidates
                        ),
                    )
                )
                continue

            matches.append(
                candidates[0]
            )

        method_counts: dict[
            str,
            int,
        ] = defaultdict(
            int
        )

        for match in matches:
            method_counts[
                match.method
            ] += 1

        playlist_count = len(
            playlist
        )

        coverage = (
            round(
                len(matches)
                / playlist_count
                * 100.0,
                2,
            )
            if playlist_count
            else 0.0
        )

        return EPGMatchBatchResult(
            matches=tuple(
                matches
            ),
            unmatched=tuple(
                unmatched
            ),
            ambiguous=tuple(
                ambiguous
            ),
            stats=EPGMatchStats(
                playlist_channels=(
                    playlist_count
                ),
                epg_channels=len(
                    epg
                ),
                matched=len(
                    matches
                ),
                unmatched=len(
                    unmatched
                ),
                ambiguous=len(
                    ambiguous
                ),
                matched_by_tvg_id=(
                    method_counts[
                        "exact_tvg_id"
                    ]
                    + method_counts[
                        "normalized_tvg_id"
                    ]
                ),
                matched_by_name=(
                    method_counts[
                        "exact_name"
                    ]
                ),
                matched_by_alias=(
                    method_counts[
                        "alias"
                    ]
                ),
                matched_by_similarity=(
                    method_counts[
                        "similarity"
                    ]
                ),
                coverage_percent=(
                    coverage
                ),
            ),
        )

    def _candidate_matches(
        self,
        *,
        channel: Channel,
        epg_channels: tuple[
            EPGChannel,
            ...,
        ],
        exact_id_index: dict[
            str,
            list[EPGChannel],
        ],
        normalized_id_index: dict[
            str,
            list[EPGChannel],
        ],
        exact_name_index: dict[
            str,
            list[EPGChannel],
        ],
        universal_name_index: dict[
            str,
            list[EPGChannel],
        ],
        epg_search_keys: dict[
            str,
            tuple[str, ...],
        ],
    ) -> list[
        EPGMatch
    ]:
        matches_by_id: dict[
            str,
            EPGMatch,
        ] = {}

        tvg_id = (
            channel.tvg_id
            .strip()
        )

        if tvg_id:
            exact_key = (
                tvg_id.casefold()
            )

            self._add_matches(
                destination=matches_by_id,
                playlist_channel=channel,
                epg_candidates=(
                    exact_id_index.get(
                        exact_key,
                        (),
                    )
                ),
                score=(
                    self.EXACT_ID_SCORE
                ),
                method="exact_tvg_id",
                playlist_key=exact_key,
                epg_key_getter=lambda item: (
                    item.channel_id
                    .casefold()
                ),
            )

            for normalized_id in (
                self.identifier_variants(
                    tvg_id
                )
            ):
                self._add_matches(
                    destination=(
                        matches_by_id
                    ),
                    playlist_channel=(
                        channel
                    ),
                    epg_candidates=(
                        normalized_id_index
                        .get(
                            normalized_id,
                            (),
                        )
                    ),
                    score=(
                        self
                        .NORMALIZED_ID_SCORE
                    ),
                    method=(
                        "normalized_tvg_id"
                    ),
                    playlist_key=(
                        normalized_id
                    ),
                    epg_key_getter=(
                        lambda item, key=(
                            normalized_id
                        ): key
                    ),
                )

        playlist_strict_names = (
            self._playlist_strict_names(
                channel
            )
        )

        for playlist_name in (
            playlist_strict_names
        ):
            self._add_matches(
                destination=(
                    matches_by_id
                ),
                playlist_channel=channel,
                epg_candidates=(
                    exact_name_index.get(
                        playlist_name,
                        (),
                    )
                ),
                score=(
                    self.EXACT_NAME_SCORE
                ),
                method="exact_name",
                playlist_key=(
                    playlist_name
                ),
                epg_key_getter=(
                    lambda item, key=(
                        playlist_name
                    ): key
                ),
            )

        universal_names = (
            self._playlist_name_variants(
                channel
            )
        )

        for playlist_name in (
            universal_names
        ):
            canonical = (
                self._canonical_alias(
                    playlist_name
                )
            )

            search_key = (
                canonical
                or playlist_name
            )

            candidates = list(
                universal_name_index.get(
                    playlist_name,
                    (),
                )
            )

            if canonical:
                for candidate in (
                    universal_name_index.get(
                        canonical,
                        (),
                    )
                ):
                    self._append_unique(
                        candidates,
                        candidate,
                    )

            self._add_matches(
                destination=(
                    matches_by_id
                ),
                playlist_channel=(
                    channel
                ),
                epg_candidates=(
                    candidates
                ),
                score=(
                    self.ALIAS_SCORE
                ),
                method="alias",
                playlist_key=(
                    search_key
                ),
                epg_key_getter=(
                    lambda item, key=(
                        search_key
                    ): key
                ),
            )

        if matches_by_id:
            return list(
                matches_by_id.values()
            )

        similarity_playlist_keys = tuple(
            key
            for key in universal_names
            if self._is_informative_key(
                key
            )
        )

        for playlist_name in (
            similarity_playlist_keys
        ):
            for epg_channel in (
                epg_channels
            ):
                for epg_key in (
                    epg_search_keys.get(
                        epg_channel
                        .channel_id,
                        (),
                    )
                ):
                    if not self._is_informative_key(
                        epg_key
                    ):
                        continue

                    score = (
                        self._similarity_score(
                            playlist_name,
                            epg_key,
                        )
                    )

                    if (
                        score
                        < self
                        .similarity_minimum
                    ):
                        continue

                    candidate = EPGMatch(
                        playlist_channel=(
                            channel
                        ),
                        epg_channel=(
                            epg_channel
                        ),
                        score=score,
                        method="similarity",
                        playlist_key=(
                            playlist_name
                        ),
                        epg_key=epg_key,
                    )

                    existing = (
                        matches_by_id.get(
                            epg_channel
                            .channel_id
                            .casefold()
                        )
                    )

                    if (
                        existing is None
                        or candidate.score
                        > existing.score
                    ):
                        matches_by_id[
                            epg_channel
                            .channel_id
                            .casefold()
                        ] = candidate

        return list(
            matches_by_id.values()
        )

    @staticmethod
    def _append_unique(
        destination: list[
            EPGChannel
        ],
        channel: EPGChannel,
    ) -> None:
        channel_key = (
            channel.channel_id
            .casefold()
        )

        if any(
            item.channel_id.casefold()
            == channel_key
            for item in destination
        ):
            return

        destination.append(
            channel
        )

    @staticmethod
    def _add_matches(
        *,
        destination: dict[
            str,
            EPGMatch,
        ],
        playlist_channel: Channel,
        epg_candidates: Iterable[
            EPGChannel
        ],
        score: float,
        method: str,
        playlist_key: str,
        epg_key_getter: Callable[
            [EPGChannel],
            object,
        ],
    ) -> None:
        for epg_channel in (
            epg_candidates
        ):
            key = (
                epg_channel
                .channel_id
                .casefold()
            )

            candidate = EPGMatch(
                playlist_channel=(
                    playlist_channel
                ),
                epg_channel=(
                    epg_channel
                ),
                score=score,
                method=method,
                playlist_key=(
                    playlist_key
                ),
                epg_key=str(
                    epg_key_getter(
                        epg_channel
                    )
                ),
            )

            existing = destination.get(
                key
            )

            if (
                existing is None
                or candidate.score
                > existing.score
            ):
                destination[
                    key
                ] = candidate

    @classmethod
    def _playlist_strict_names(
        cls,
        channel: Channel,
    ) -> tuple[str, ...]:
        values = (
            channel.tvg_name,
            channel.name,
        )

        names: list[
            str
        ] = []

        for value in values:
            normalized = (
                cls.normalize_name(
                    value
                )
            )

            if (
                normalized
                and normalized
                not in names
            ):
                names.append(
                    normalized
                )

        return tuple(
            names
        )

    @classmethod
    def _playlist_name_variants(
        cls,
        channel: Channel,
    ) -> tuple[str, ...]:
        values = (
            channel.tvg_name,
            channel.name,
        )

        variants: list[
            str
        ] = []

        for value in values:
            for variant in (
                cls.name_variants(
                    value
                )
            ):
                if variant not in variants:
                    variants.append(
                        variant
                    )

        if channel.tvg_id:
            for variant in (
                cls.identifier_variants(
                    channel.tvg_id
                )
            ):
                if variant not in variants:
                    variants.append(
                        variant
                    )

        return tuple(
            variants
        )

    @classmethod
    def normalize_identifier(
        cls,
        value: object,
    ) -> str:
        variants = (
            cls.identifier_variants(
                value
            )
        )

        return (
            variants[0]
            if variants
            else ""
        )

    @classmethod
    def identifier_variants(
        cls,
        value: object,
    ) -> tuple[str, ...]:
        text = cls._fold_text(
            value
        ).strip()

        if not text:
            return ()

        text = text.split(
            "?",
            1,
        )[0].split(
            "#",
            1,
        )[0].strip()

        raw_candidates = [
            text,
        ]

        stripped = text

        while True:
            updated = re.sub(
                (
                    r"@("
                    + "|".join(
                        sorted(
                            (
                                re.escape(
                                    item
                                )
                                for item
                                in cls.IDENTIFIER_TAGS
                            ),
                            key=len,
                            reverse=True,
                        )
                    )
                    + r")$"
                ),
                "",
                stripped,
            )

            if updated == stripped:
                break

            stripped = updated.rstrip(
                "._-|:/ "
            )

        stripped = re.sub(
            (
                r"(?:[._|:/-])("
                + "|".join(
                    sorted(
                        (
                            re.escape(
                                item
                            )
                            for item
                            in cls.QUALITY_WORDS
                        ),
                        key=len,
                        reverse=True,
                    )
                )
                + r")$"
            ),
            "",
            stripped,
        ).rstrip(
            "._-|:/ "
        )

        # I tvg-id pubblici usano frequentemente il dominio/codice
        # paese come semplice namespace: Rai1.it, Channel.de@IT.
        without_namespace = re.sub(
            r"\.[a-z]{2,3}$",
            "",
            stripped,
        )

        raw_candidates.extend(
            [
                stripped,
                without_namespace,
            ]
        )

        variants: list[
            str
        ] = []

        for candidate in raw_candidates:
            normalized = (
                cls.normalize_name(
                    candidate
                )
            )

            if (
                normalized
                and normalized
                not in variants
            ):
                variants.append(
                    normalized
                )

            for name_variant in (
                cls.name_variants(
                    candidate
                )
            ):
                if name_variant not in variants:
                    variants.append(
                        name_variant
                    )

        return tuple(
            variants
        )

    @classmethod
    def normalize_name(
        cls,
        value: object,
    ) -> str:
        """
        Normalizzazione stretta.

        I numeri scritti in lettere vengono conservati qui, così
        "Rai Uno" resta un alias di "Rai 1" e non viene classificato
        come nome identico. La conversione Uno/1 viene applicata
        nelle varianti universali.
        """

        tokens = cls._name_tokens(
            value,
            convert_numbers=False,
        )

        return "".join(
            tokens
        )

    @classmethod
    def name_variants(
        cls,
        value: object,
    ) -> tuple[str, ...]:
        strict_tokens = (
            cls._name_tokens(
                value,
                convert_numbers=False,
            )
        )

        numeric_tokens = (
            cls._name_tokens(
                value,
                convert_numbers=True,
            )
        )

        if not strict_tokens:
            return ()

        base_variants: list[
            tuple[str, ...]
        ] = [
            strict_tokens,
        ]

        if (
            numeric_tokens
            and numeric_tokens
            not in base_variants
        ):
            base_variants.append(
                numeric_tokens
            )

        token_variants: list[
            tuple[str, ...]
        ] = []

        for tokens in base_variants:
            candidates = [
                tokens,
                cls._remove_soft_media_tokens(
                    tokens
                ),
                cls._remove_locale_tokens(
                    tokens
                ),
            ]

            locale_relaxed = (
                cls._remove_locale_tokens(
                    tokens
                )
            )

            if locale_relaxed:
                candidates.append(
                    cls._remove_soft_media_tokens(
                        locale_relaxed
                    )
                )

            for candidate in candidates:
                if (
                    candidate
                    and candidate
                    not in token_variants
                ):
                    token_variants.append(
                        candidate
                    )

        results: list[
            str
        ] = []

        for variant_tokens in (
            token_variants
        ):
            key = "".join(
                variant_tokens
            )

            if (
                key
                and key not in results
            ):
                results.append(
                    key
                )

            canonical = (
                cls._static_alias_key(
                    key
                )
            )

            if (
                canonical
                and canonical
                not in results
            ):
                results.append(
                    canonical
                )

        return tuple(
            results
        )

    @classmethod
    def _name_tokens(
        cls,
        value: object,
        *,
        convert_numbers: bool,
    ) -> tuple[str, ...]:
        text = cls._fold_text(
            value
        )

        if not text:
            return ()

        text = text.replace(
            "&",
            " e ",
        )

        text = text.replace(
            "+",
            " plus ",
        )

        text = re.sub(
            r"\bpiu\b",
            " plus ",
            text,
        )

        text = cls._remove_technical_brackets(
            text
        )

        raw_tokens = re.findall(
            r"[a-z0-9]+",
            text,
        )

        tokens: list[
            str
        ] = []

        for token in raw_tokens:
            mapped = (
                cls.NUMBER_WORDS.get(
                    token,
                    token,
                )
                if convert_numbers
                else token
            )

            if mapped in (
                cls.HARD_TECHNICAL_WORDS
            ):
                continue

            tokens.append(
                mapped
            )

        return tuple(
            tokens
        )

    @classmethod
    def _remove_technical_brackets(
        cls,
        text: str,
    ) -> str:
        pattern = re.compile(
            r"(\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\})"
        )

        def replace(
            match: re.Match[str],
        ) -> str:
            content = (
                match.group(0)[1:-1]
            )

            tokens = re.findall(
                r"[a-z0-9]+",
                content,
            )

            if (
                tokens
                and all(
                    (
                        token
                        in cls
                        .BRACKET_TECHNICAL_WORDS
                    )
                    or bool(
                        re.fullmatch(
                            r"\d{3,4}p",
                            token,
                        )
                    )
                    for token in tokens
                )
            ):
                return " "

            return (
                " "
                + content
                + " "
            )

        previous = text

        while True:
            current = pattern.sub(
                replace,
                previous,
            )

            if current == previous:
                return current

            previous = current

    @classmethod
    def _remove_soft_media_tokens(
        cls,
        tokens: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(tokens) <= 1:
            return tokens

        remaining = tuple(
            token
            for token in tokens
            if token
            not in cls.SOFT_MEDIA_WORDS
        )

        if not remaining:
            return tokens

        # Evita di ridurre Canale 5 a una chiave troppo generica "5".
        if all(
            token.isdigit()
            for token in remaining
        ):
            return tokens

        if sum(
            len(token)
            for token in remaining
        ) < 3:
            return tokens

        return remaining

    @classmethod
    def _remove_locale_tokens(
        cls,
        tokens: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(tokens) <= 1:
            return tokens

        remaining = tuple(
            token
            for token in tokens
            if token
            not in cls.LOCALE_WORDS
        )

        if not remaining:
            return tokens

        # "Italia 1" e "Radio Italia" non devono diventare "1" o
        # soltanto "radio": in questi casi Italia è parte del nome.
        if all(
            token.isdigit()
            for token in remaining
        ):
            return tokens

        if set(
            remaining
        ).issubset(
            cls.SOFT_MEDIA_WORDS
            | {
                "radio",
            }
        ):
            return tokens

        return remaining

    def _canonical_alias(
        self,
        normalized_name: str,
    ) -> str:
        return (
            self._alias_to_canonical
            .get(
                normalized_name,
                ""
            )
        )

    @classmethod
    def _static_alias_key(
        cls,
        normalized_name: str,
    ) -> str:
        for (
            canonical,
            aliases,
        ) in cls.ITALIAN_ALIASES.items():
            canonical_key = (
                cls.normalize_name(
                    canonical
                )
            )

            for alias in (
                canonical,
                *aliases,
            ):
                alias_key = (
                    cls.normalize_name(
                        alias
                    )
                )

                if (
                    alias_key
                    == normalized_name
                ):
                    return canonical_key

        return ""

    @classmethod
    def _build_alias_index(
        cls,
    ) -> dict[str, str]:
        result: dict[
            str,
            str,
        ] = {}

        for (
            canonical,
            aliases,
        ) in cls.ITALIAN_ALIASES.items():
            canonical_key = (
                cls.normalize_name(
                    canonical
                )
            )

            for alias in (
                canonical,
                *aliases,
            ):
                for normalized in (
                    cls.name_variants(
                        alias
                    )
                ):
                    if normalized:
                        result[
                            normalized
                        ] = canonical_key

        return result

    @staticmethod
    def _fold_text(
        value: object,
    ) -> str:
        text = unicodedata.normalize(
            "NFKD",
            str(
                value
                if value is not None
                else ""
            ),
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(
                character
            )
        )

        return text.casefold()

    @staticmethod
    def _is_informative_key(
        key: str,
    ) -> bool:
        if not key:
            return False

        if key.isdigit():
            return len(key) >= 2

        return len(key) >= 4

    @staticmethod
    def _similarity_score(
        left: str,
        right: str,
    ) -> float:
        if (
            not left
            or not right
        ):
            return 0.0

        if left == right:
            return 100.0

        ratio = SequenceMatcher(
            None,
            left,
            right,
        ).ratio()

        shorter = min(
            len(left),
            len(right),
        )

        longer = max(
            len(left),
            len(right),
        )

        length_ratio = (
            shorter / longer
            if longer
            else 0.0
        )

        if length_ratio < 0.75:
            return 0.0

        prefix_bonus = (
            0.02
            if (
                left.startswith(
                    right
                )
                or right.startswith(
                    left
                )
            )
            else 0.0
        )

        return round(
            min(
                1.0,
                ratio + prefix_bonus,
            )
            * 100.0,
            2,
        )
