from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from src.models.channel import Channel


QUALITY_PATTERN = re.compile(
    r"\b(?:"
    r"4k|uhd|"
    r"fhd|full\s*hd|1080p|1080i|"
    r"hd|720p|"
    r"sd|576p|480p"
    r")\b",
    re.IGNORECASE,
)

NON_ALPHANUMERIC_PATTERN = re.compile(
    r"[^a-z0-9]+"
)

GENERIC_NAMES = {
    "tv",
    "live",
    "stream",
    "channel",
    "canale",
}

IDENTITY_TYPE_ORDER = {
    "tvg_id": 0,
    "name": 1,
    "url": 2,
}


@dataclass(frozen=True, slots=True)
class CandidateScore:
    index: int
    name: str
    stream_url: str
    source_id: str
    health_score: float
    source_priority: int
    quality_score: int
    metadata_score: int
    transport_score: int

    @property
    def rank(
        self,
    ) -> tuple[
        float,
        int,
        int,
        int,
        int,
        int,
    ]:
        """
        Ordine di selezione:

        1. stabilità/Health Score;
        2. priorità sorgente più bassa;
        3. qualità video;
        4. completezza metadati;
        5. protocollo/trasporto;
        6. ordine originale.
        """

        return (
            self.health_score,
            -self.source_priority,
            self.quality_score,
            self.metadata_score,
            self.transport_score,
            -self.index,
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "stream_url": self.stream_url,
            "source_id": self.source_id,
            "health_score": self.health_score,
            "source_priority": self.source_priority,
            "quality_score": self.quality_score,
            "metadata_score": self.metadata_score,
            "transport_score": self.transport_score,
        }


@dataclass(frozen=True, slots=True)
class CandidateGroup:
    """
    Gruppo di possibili flussi dello stesso canale.

    `channels` e `candidates` hanno lo stesso ordine: il primo
    elemento è il candidato preferito con i punteggi disponibili
    al momento della costruzione del gruppo.

    Nessun candidato viene eliminato. L'applicazione può quindi
    controllare tutti gli URL e ricostruire il ranking usando i
    relativi Health Score.
    """

    group_id: str
    identity_keys: tuple[str, ...]
    channels: tuple[Channel, ...]
    candidates: tuple[CandidateScore, ...]

    def __post_init__(
        self,
    ) -> None:
        if not self.channels:
            raise ValueError(
                "CandidateGroup richiede "
                "almeno un canale"
            )

        if (
            len(self.channels)
            != len(self.candidates)
        ):
            raise ValueError(
                "channels e candidates devono "
                "avere la stessa lunghezza"
            )

    @property
    def size(
        self,
    ) -> int:
        return len(self.channels)

    @property
    def is_duplicate(
        self,
    ) -> bool:
        return self.size > 1

    @property
    def preferred_channel(
        self,
    ) -> Channel:
        return self.channels[0]

    @property
    def preferred_candidate(
        self,
    ) -> CandidateScore:
        return self.candidates[0]

    @property
    def alternative_channels(
        self,
    ) -> tuple[Channel, ...]:
        return self.channels[1:]

    @property
    def alternative_candidates(
        self,
    ) -> tuple[CandidateScore, ...]:
        return self.candidates[1:]

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "identity_keys": list(
                self.identity_keys
            ),
            "size": self.size,
            "is_duplicate": (
                self.is_duplicate
            ),
            "preferred": (
                self.preferred_candidate
                .to_dict()
            ),
            "alternatives": [
                candidate.to_dict()
                for candidate
                in self.alternative_candidates
            ],
        }


@dataclass(frozen=True, slots=True)
class CandidateGroupStats:
    input_channels: int
    groups: int
    singleton_groups: int
    duplicate_groups: int
    alternative_candidates: int
    url_collisions: int
    tvg_id_collisions: int
    name_collisions: int

    def to_dict(
        self,
    ) -> dict[str, int]:
        return {
            "input_channels": self.input_channels,
            "groups": self.groups,
            "singleton_groups": (
                self.singleton_groups
            ),
            "duplicate_groups": (
                self.duplicate_groups
            ),
            "alternative_candidates": (
                self.alternative_candidates
            ),
            "url_collisions": (
                self.url_collisions
            ),
            "tvg_id_collisions": (
                self.tvg_id_collisions
            ),
            "name_collisions": (
                self.name_collisions
            ),
        }


@dataclass(frozen=True, slots=True)
class CandidateGroupResult:
    groups: tuple[CandidateGroup, ...]
    stats: CandidateGroupStats

    @property
    def channels(
        self,
    ) -> tuple[Channel, ...]:
        """
        Tutti i canali originali, ordinati per gruppo e ranking.

        Questa proprietà non deduplica: serve per sottoporre
        ogni alternativa al controllo Health/Tizen.
        """

        return tuple(
            channel
            for group in self.groups
            for channel in group.channels
        )

    @property
    def preferred_channels(
        self,
    ) -> tuple[Channel, ...]:
        return tuple(
            group.preferred_channel
            for group in self.groups
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "stats": self.stats.to_dict(),
            "groups": [
                group.to_dict()
                for group in self.groups
            ],
        }


@dataclass(frozen=True, slots=True)
class MergeDecision:
    selected: CandidateScore
    discarded: tuple[CandidateScore, ...]
    reason: str

    @property
    def duplicates_removed(
        self,
    ) -> int:
        return len(self.discarded)

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "selected": self.selected.to_dict(),
            "discarded": [
                candidate.to_dict()
                for candidate in self.discarded
            ],
            "reason": self.reason,
            "duplicates_removed": (
                self.duplicates_removed
            ),
        }


@dataclass(frozen=True, slots=True)
class MergeStats:
    input_channels: int
    output_channels: int
    duplicate_groups: int
    duplicates_removed: int
    url_collisions: int
    tvg_id_collisions: int
    name_collisions: int

    def to_dict(
        self,
    ) -> dict[str, int]:
        return {
            "input_channels": self.input_channels,
            "output_channels": self.output_channels,
            "duplicate_groups": (
                self.duplicate_groups
            ),
            "duplicates_removed": (
                self.duplicates_removed
            ),
            "url_collisions": (
                self.url_collisions
            ),
            "tvg_id_collisions": (
                self.tvg_id_collisions
            ),
            "name_collisions": (
                self.name_collisions
            ),
        }


@dataclass(frozen=True, slots=True)
class MergeResult:
    channels: tuple[Channel, ...]
    decisions: tuple[MergeDecision, ...]
    stats: MergeStats

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "stats": self.stats.to_dict(),
            "decisions": [
                decision.to_dict()
                for decision in self.decisions
            ],
        }


class ChannelMerger:
    """
    Deduplicazione qualitativa e gestione delle alternative.

    I canali sono collegati in gruppi transitivi quando condividono
    almeno una delle seguenti identità:

    - URL normalizzato;
    - tvg-id normalizzato;
    - nome normalizzato senza indicatori HD/SD/4K.

    `group_candidates()` conserva tutti i possibili flussi.
    `merge()` e `merge_detailed()` mantengono il comportamento
    precedente e restituiscono un solo candidato per gruppo.
    """

    DEFAULT_SOURCE_PRIORITY = 100

    def merge(
        self,
        channels: Iterable[Channel],
        *,
        source_priorities: (
            Mapping[str, int] | None
        ) = None,
        health_scores: (
            Mapping[str, float] | None
        ) = None,
    ) -> list[Channel]:
        """
        Metodo compatibile con il codice precedente.
        """

        result = self.merge_detailed(
            channels,
            source_priorities=source_priorities,
            health_scores=health_scores,
        )

        return list(result.channels)

    def group_candidates(
        self,
        channels: Iterable[Channel],
        *,
        source_priorities: (
            Mapping[str, int] | None
        ) = None,
        health_scores: (
            Mapping[str, float] | None
        ) = None,
    ) -> CandidateGroupResult:
        """
        Costruisce i gruppi di candidati senza eliminare alternative.

        L'ordine interno di ogni gruppo rispetta lo stesso ranking
        usato da `merge_detailed()`. Dopo un controllo Health/Tizen
        è sufficiente richiamare questo metodo passando i nuovi
        `health_scores` per ottenere il candidato funzionante in cima.
        """

        channel_list = self._validated_channels(
            channels
        )

        priorities = self._normalize_priorities(
            source_priorities
        )

        normalized_health = (
            self._normalize_health_scores(
                health_scores
            )
        )

        if not channel_list:
            return CandidateGroupResult(
                groups=(),
                stats=CandidateGroupStats(
                    input_channels=0,
                    groups=0,
                    singleton_groups=0,
                    duplicate_groups=0,
                    alternative_candidates=0,
                    url_collisions=0,
                    tvg_id_collisions=0,
                    name_collisions=0,
                ),
            )

        (
            clusters,
            collisions,
        ) = self._build_clusters(
            channel_list
        )

        groups: list[CandidateGroup] = []

        for indices in clusters:
            ranked_pairs = sorted(
                (
                    (
                        self._evaluate(
                            channel_list[index],
                            index,
                            priorities,
                            normalized_health,
                        ),
                        channel_list[index],
                    )
                    for index in indices
                ),
                key=lambda pair: (
                    pair[0].rank
                ),
                reverse=True,
            )

            candidates = tuple(
                pair[0]
                for pair in ranked_pairs
            )

            grouped_channels = tuple(
                pair[1]
                for pair in ranked_pairs
            )

            identity_keys = (
                self._cluster_identity_keys(
                    grouped_channels
                )
            )

            groups.append(
                CandidateGroup(
                    group_id=(
                        self._group_id(
                            identity_keys,
                            candidates[0],
                        )
                    ),
                    identity_keys=(
                        identity_keys
                    ),
                    channels=grouped_channels,
                    candidates=candidates,
                )
            )

        groups.sort(
            key=self._candidate_group_sort_key
        )

        duplicate_groups = sum(
            1
            for group in groups
            if group.is_duplicate
        )

        alternative_candidates = sum(
            group.size - 1
            for group in groups
        )

        return CandidateGroupResult(
            groups=tuple(groups),
            stats=CandidateGroupStats(
                input_channels=len(
                    channel_list
                ),
                groups=len(groups),
                singleton_groups=(
                    len(groups)
                    - duplicate_groups
                ),
                duplicate_groups=(
                    duplicate_groups
                ),
                alternative_candidates=(
                    alternative_candidates
                ),
                url_collisions=(
                    collisions["url"]
                ),
                tvg_id_collisions=(
                    collisions["tvg_id"]
                ),
                name_collisions=(
                    collisions["name"]
                ),
            ),
        )

    def merge_detailed(
        self,
        channels: Iterable[Channel],
        *,
        source_priorities: (
            Mapping[str, int] | None
        ) = None,
        health_scores: (
            Mapping[str, float] | None
        ) = None,
    ) -> MergeResult:
        grouped = self.group_candidates(
            channels,
            source_priorities=(
                source_priorities
            ),
            health_scores=health_scores,
        )

        selected_channels: list[
            Channel
        ] = []

        decisions: list[
            MergeDecision
        ] = []

        for group in grouped.groups:
            selected_channels.append(
                group.preferred_channel
            )

            if not group.is_duplicate:
                continue

            selected = (
                group.preferred_candidate
            )

            discarded = (
                group.alternative_candidates
            )

            decisions.append(
                MergeDecision(
                    selected=selected,
                    discarded=discarded,
                    reason=(
                        self._selection_reason(
                            selected,
                            discarded[0],
                        )
                    ),
                )
            )

        selected_channels.sort(
            key=self._output_sort_key
        )

        stats = MergeStats(
            input_channels=(
                grouped.stats.input_channels
            ),
            output_channels=len(
                selected_channels
            ),
            duplicate_groups=(
                grouped.stats
                .duplicate_groups
            ),
            duplicates_removed=(
                grouped.stats
                .alternative_candidates
            ),
            url_collisions=(
                grouped.stats
                .url_collisions
            ),
            tvg_id_collisions=(
                grouped.stats
                .tvg_id_collisions
            ),
            name_collisions=(
                grouped.stats
                .name_collisions
            ),
        )

        return MergeResult(
            channels=tuple(
                selected_channels
            ),
            decisions=tuple(
                decisions
            ),
            stats=stats,
        )

    @staticmethod
    def _validated_channels(
        channels: Iterable[Channel],
    ) -> list[Channel]:
        channel_list = list(channels)

        for channel in channel_list:
            if not isinstance(
                channel,
                Channel,
            ):
                raise TypeError(
                    "channels must contain "
                    "only Channel instances"
                )

        return channel_list

    def _build_clusters(
        self,
        channels: list[Channel],
    ) -> tuple[
        tuple[tuple[int, ...], ...],
        dict[str, int],
    ]:
        count = len(channels)

        parents = list(
            range(count)
        )

        ranks = [0] * count

        key_owners: dict[
            tuple[str, str],
            int,
        ] = {}

        collisions = {
            "url": 0,
            "tvg_id": 0,
            "name": 0,
        }

        for index, channel in enumerate(
            channels
        ):
            for key_type, key_value in (
                self._identity_keys(channel)
            ):
                identity = (
                    key_type,
                    key_value,
                )

                owner = key_owners.get(
                    identity
                )

                if owner is None:
                    key_owners[
                        identity
                    ] = index
                    continue

                collisions[
                    key_type
                ] += 1

                self._union(
                    parents,
                    ranks,
                    owner,
                    index,
                )

        clusters: dict[
            int,
            list[int],
        ] = defaultdict(list)

        for index in range(count):
            root = self._find(
                parents,
                index,
            )

            clusters[root].append(
                index
            )

        ordered_clusters = tuple(
            tuple(indices)
            for _, indices in sorted(
                clusters.items(),
                key=lambda item: min(
                    item[1]
                ),
            )
        )

        return (
            ordered_clusters,
            collisions,
        )

    def _evaluate(
        self,
        channel: Channel,
        index: int,
        source_priorities: Mapping[
            str,
            int,
        ],
        health_scores: Mapping[
            str,
            float,
        ],
    ) -> CandidateScore:
        source_key = self._normalize_text(
            channel.source_id
        )

        priority = source_priorities.get(
            source_key,
            self.DEFAULT_SOURCE_PRIORITY,
        )

        normalized_url = (
            self._normalize_url(
                channel.stream_url
            )
        )

        health_score = health_scores.get(
            normalized_url,
            0.0,
        )

        return CandidateScore(
            index=index,
            name=channel.name,
            stream_url=channel.stream_url,
            source_id=channel.source_id,
            health_score=health_score,
            source_priority=priority,
            quality_score=(
                self._quality_score(
                    channel
                )
            ),
            metadata_score=(
                self._metadata_score(
                    channel
                )
            ),
            transport_score=(
                self._transport_score(
                    channel.stream_url
                )
            ),
        )

    def _identity_keys(
        self,
        channel: Channel,
    ) -> tuple[
        tuple[str, str],
        ...,
    ]:
        keys: list[
            tuple[str, str]
        ] = []

        url_key = self._normalize_url(
            channel.stream_url
        )

        if url_key:
            keys.append(
                (
                    "url",
                    url_key,
                )
            )

        tvg_id_key = (
            self._normalize_text(
                channel.tvg_id
            )
        )

        if tvg_id_key:
            keys.append(
                (
                    "tvg_id",
                    tvg_id_key,
                )
            )

        name_key = self._normalize_name(
            channel.name
        )

        if (
            name_key
            and name_key
            not in GENERIC_NAMES
        ):
            keys.append(
                (
                    "name",
                    name_key,
                )
            )

        return tuple(keys)

    def _cluster_identity_keys(
        self,
        channels: tuple[
            Channel,
            ...,
        ],
    ) -> tuple[str, ...]:
        unique_keys = {
            f"{key_type}:{key_value}"
            for channel in channels
            for key_type, key_value
            in self._identity_keys(
                channel
            )
        }

        return tuple(
            sorted(
                unique_keys,
                key=self._identity_key_sort,
            )
        )

    @staticmethod
    def _identity_key_sort(
        identity: str,
    ) -> tuple[int, str]:
        key_type, _, value = (
            identity.partition(":")
        )

        return (
            IDENTITY_TYPE_ORDER.get(
                key_type,
                99,
            ),
            value,
        )

    @staticmethod
    def _group_id(
        identity_keys: tuple[
            str,
            ...,
        ],
        preferred: CandidateScore,
    ) -> str:
        if identity_keys:
            return identity_keys[0]

        return (
            "index:"
            f"{preferred.index}"
        )

    @classmethod
    def _candidate_group_sort_key(
        cls,
        group: CandidateGroup,
    ) -> tuple[str, str, str]:
        return cls._output_sort_key(
            group.preferred_channel
        )

    @staticmethod
    def _quality_score(
        channel: Channel,
    ) -> int:
        combined = " ".join(
            (
                channel.name,
                channel.tvg_name,
                channel.group,
                channel.stream_url,
            )
        ).casefold()

        if re.search(
            r"\b(?:4k|uhd|2160p?)\b",
            combined,
        ):
            return 400

        if re.search(
            r"\b(?:fhd|full\s*hd|1080p|1080i)\b",
            combined,
        ):
            return 300

        if re.search(
            r"\b(?:hd|720p)\b",
            combined,
        ):
            return 200

        if re.search(
            r"\b(?:sd|576p|480p)\b",
            combined,
        ):
            return 100

        return 0

    @staticmethod
    def _metadata_score(
        channel: Channel,
    ) -> int:
        score = 0

        if channel.tvg_id.strip():
            score += 30

        if channel.tvg_name.strip():
            score += 20

        if channel.logo.strip():
            score += 20

        if channel.group.strip():
            score += 15

        attributes = channel.attributes

        if isinstance(
            attributes,
            dict,
        ):
            score += min(
                10,
                sum(
                    1
                    for value
                    in attributes.values()
                    if str(value).strip()
                ),
            )

        directives = (
            channel.extra_directives
        )

        if isinstance(
            directives,
            list,
        ):
            score += min(
                5,
                len(directives),
            )

        return score

    @staticmethod
    def _transport_score(
        stream_url: str,
    ) -> int:
        normalized = stream_url.strip()
        parts = urlsplit(normalized)

        score = 0

        if (
            parts.scheme.casefold()
            == "https"
        ):
            score += 20

        elif (
            parts.scheme.casefold()
            == "http"
        ):
            score += 10

        if (
            parts.path
            .casefold()
            .endswith(".m3u8")
        ):
            score += 5

        return score

    @staticmethod
    def _selection_reason(
        selected: CandidateScore,
        runner_up: CandidateScore,
    ) -> str:
        if (
            selected.health_score
            != runner_up.health_score
        ):
            return "higher_health_score"

        if (
            selected.source_priority
            != runner_up.source_priority
        ):
            return "better_source_priority"

        if (
            selected.quality_score
            != runner_up.quality_score
        ):
            return "higher_video_quality"

        if (
            selected.metadata_score
            != runner_up.metadata_score
        ):
            return "richer_metadata"

        if (
            selected.transport_score
            != runner_up.transport_score
        ):
            return "better_transport"

        return "earlier_insertion_order"

    @classmethod
    def _normalize_priorities(
        cls,
        priorities: (
            Mapping[str, int] | None
        ),
    ) -> dict[str, int]:
        if priorities is None:
            return {}

        normalized: dict[
            str,
            int,
        ] = {}

        for source_id, priority in (
            priorities.items()
        ):
            if (
                isinstance(
                    priority,
                    bool,
                )
                or not isinstance(
                    priority,
                    int,
                )
            ):
                continue

            normalized[
                cls._normalize_text(
                    str(source_id)
                )
            ] = priority

        return normalized

    @classmethod
    def _normalize_health_scores(
        cls,
        scores: (
            Mapping[str, float] | None
        ),
    ) -> dict[str, float]:
        if scores is None:
            return {}

        normalized: dict[
            str,
            float,
        ] = {}

        for stream_url, value in (
            scores.items()
        ):
            try:
                numeric_value = float(
                    value
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if not math.isfinite(
                numeric_value
            ):
                continue

            normalized[
                cls._normalize_url(
                    str(stream_url)
                )
            ] = numeric_value

        return normalized

    @staticmethod
    def _find(
        parents: list[int],
        index: int,
    ) -> int:
        while (
            parents[index]
            != index
        ):
            parents[index] = (
                parents[
                    parents[index]
                ]
            )

            index = parents[index]

        return index

    @classmethod
    def _union(
        cls,
        parents: list[int],
        ranks: list[int],
        first: int,
        second: int,
    ) -> None:
        first_root = cls._find(
            parents,
            first,
        )

        second_root = cls._find(
            parents,
            second,
        )

        if (
            first_root
            == second_root
        ):
            return

        if (
            ranks[first_root]
            < ranks[second_root]
        ):
            parents[first_root] = (
                second_root
            )

        elif (
            ranks[first_root]
            > ranks[second_root]
        ):
            parents[second_root] = (
                first_root
            )

        else:
            parents[second_root] = (
                first_root
            )

            ranks[first_root] += 1

    @classmethod
    def _normalize_url(
        cls,
        url: str,
    ) -> str:
        normalized = str(
            url
        ).strip()

        if (
            len(normalized) >= 2
            and normalized[0]
            == normalized[-1]
            and normalized[0]
            in {'"', "'"}
        ):
            normalized = (
                normalized[1:-1]
                .strip()
            )

        try:
            parts = urlsplit(
                normalized
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

        if (
            port is not None
            and not (
                parts.scheme.casefold()
                == "http"
                and port == 80
            )
            and not (
                parts.scheme.casefold()
                == "https"
                and port == 443
            )
        ):
            hostname = (
                f"{hostname}:{port}"
            )

        return urlunsplit(
            (
                parts.scheme.casefold(),
                hostname,
                parts.path,
                parts.query,
                "",
            )
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        normalized = (
            unicodedata.normalize(
                "NFKC",
                str(value),
            )
        )

        return " ".join(
            normalized.split()
        ).casefold()

    @classmethod
    def _normalize_name(
        cls,
        name: str,
    ) -> str:
        normalized = (
            unicodedata.normalize(
                "NFKD",
                str(name),
            )
        )

        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(
                character
            )
        ).casefold()

        normalized = (
            QUALITY_PATTERN.sub(
                " ",
                normalized,
            )
        )

        return (
            NON_ALPHANUMERIC_PATTERN.sub(
                "",
                normalized,
            )
        )

    @staticmethod
    def _output_sort_key(
        channel: Channel,
    ) -> tuple[str, str, str]:
        return (
            channel.group.casefold(),
            channel.name.casefold(),
            channel.stream_url,
        )
