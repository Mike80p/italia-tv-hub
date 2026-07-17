from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Iterable

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

            if (
                not name
                or name in seen
            ):
                continue

            seen.add(
                name
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
    Abbina i canali della playlist ai canali XMLTV.

    Ordine di affidabilità:

    1. `tvg-id` identico;
    2. `tvg-id` normalizzato;
    3. nome identico normalizzato;
    4. alias italiano controllato;
    5. somiglianza testuale conservativa.

    Le corrispondenze ambigue non vengono accettate.
    """

    EXACT_ID_SCORE = 100.0
    NORMALIZED_ID_SCORE = 97.0
    EXACT_NAME_SCORE = 92.0
    ALIAS_SCORE = 89.0
    SIMILARITY_MINIMUM = 86.0

    QUALITY_WORDS = {
        "4k",
        "uhd",
        "fhd",
        "fullhd",
        "full",
        "hd",
        "sd",
        "1080p",
        "720p",
        "576p",
        "480p",
        "live",
        "stream",
        "italia",
        "italy",
        "it",
    }

    ITALIAN_ALIASES = {
        "rai1": {
            "rai1",
            "raiuno",
            "rai1hd",
        },
        "rai2": {
            "rai2",
            "raidue",
            "rai2hd",
        },
        "rai3": {
            "rai3",
            "raitre",
            "rai3hd",
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
            "raisportpiu",
        },
        "canale5": {
            "canale5",
            "canale5hd",
        },
        "italia1": {
            "italia1",
            "italiauno",
            "italia1hd",
        },
        "rete4": {
            "rete4",
            "retequattro",
            "rete4hd",
        },
        "mediaset20": {
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
            "nove9",
            "canale9",
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
        "warner tv": {
            "warnertv",
        },
        "tv8": {
            "tv8",
        },
        "cielo": {
            "cielo",
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

        alias_index: dict[
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

            exact_id_index[
                exact_id
            ].append(
                epg_channel
            )

            normalized_id = (
                self.normalize_identifier(
                    epg_channel.channel_id
                )
            )

            if normalized_id:
                normalized_id_index[
                    normalized_id
                ].append(
                    epg_channel
                )

            keys: list[
                str
            ] = []

            for name in (
                *epg_channel.display_names,
                epg_channel.channel_id,
            ):
                normalized_name = (
                    self.normalize_name(
                        name
                    )
                )

                if (
                    normalized_name
                    and normalized_name
                    not in keys
                ):
                    keys.append(
                        normalized_name
                    )

                if normalized_name:
                    exact_name_index[
                        normalized_name
                    ].append(
                        epg_channel
                    )

                canonical = (
                    self._canonical_alias(
                        normalized_name
                    )
                )

                if canonical:
                    alias_index[
                        canonical
                    ].append(
                        epg_channel
                    )

            epg_search_keys[
                epg_channel.channel_id
            ] = tuple(
                keys
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
                    alias_index=(
                        alias_index
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

        method_counts = defaultdict(
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
        alias_index: dict[
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

            normalized_id = (
                self.normalize_identifier(
                    tvg_id
                )
            )

            if normalized_id:
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
                        lambda item: (
                            self
                            .normalize_identifier(
                                item.channel_id
                            )
                        )
                    ),
                )

        playlist_names = self._playlist_names(
            channel
        )

        for playlist_name in playlist_names:
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
                    lambda item: (
                        playlist_name
                    )
                ),
            )

            canonical = (
                self._canonical_alias(
                    playlist_name
                )
            )

            if canonical:
                self._add_matches(
                    destination=(
                        matches_by_id
                    ),
                    playlist_channel=(
                        channel
                    ),
                    epg_candidates=(
                        alias_index.get(
                            canonical,
                            (),
                        )
                    ),
                    score=(
                        self.ALIAS_SCORE
                    ),
                    method="alias",
                    playlist_key=(
                        canonical
                    ),
                    epg_key_getter=(
                        lambda item: (
                            canonical
                        )
                    ),
                )

        if matches_by_id:
            return list(
                matches_by_id.values()
            )

        for playlist_name in (
            playlist_names
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
        epg_key_getter,
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
    def _playlist_names(
        cls,
        channel: Channel,
    ) -> tuple[str, ...]:
        values = (
            channel.tvg_name,
            channel.name,
            channel.tvg_id,
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
    def normalize_identifier(
        cls,
        value: object,
    ) -> str:
        text = str(
            value
            if value is not None
            else ""
        ).strip().casefold()

        text = re.sub(
            r"\.(it|com|tv|eu|org)$",
            "",
            text,
        )

        return cls.normalize_name(
            text
        )

    @classmethod
    def normalize_name(
        cls,
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

        text = text.casefold()
        text = text.replace(
            "&",
            " e ",
        )

        text = re.sub(
            r"[\(\[].*?[\)\]]",
            " ",
            text,
        )

        tokens = re.findall(
            r"[a-z0-9]+",
            text,
        )

        tokens = [
            token
            for token in tokens
            if token
            not in cls.QUALITY_WORDS
        ]

        return "".join(
            tokens
        )

    def _canonical_alias(
        self,
        normalized_name: str,
    ) -> str:
        return (
            self._alias_to_canonical
            .get(
                normalized_name,
                "",
            )
        )

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
                normalized = (
                    cls.normalize_name(
                        alias
                    )
                )

                if normalized:
                    result[
                        normalized
                    ] = canonical_key

        return result

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

        if length_ratio < 0.72:
            return 0.0

        return round(
            ratio * 100.0,
            2,
        )
