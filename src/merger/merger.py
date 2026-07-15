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
            "duplicate_groups": self.duplicate_groups,
            "duplicates_removed": (
                self.duplicates_removed
            ),
            "url_collisions": self.url_collisions,
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
    Deduplicazione qualitativa dei canali.

    I canali vengono considerati duplicati quando condividono almeno
    una delle seguenti identità:

    - URL normalizzato;
    - tvg-id normalizzato;
    - nome normalizzato senza indicatori HD/SD/4K.

    Il canale migliore non è necessariamente il primo incontrato.
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

        priorities = self._normalize_priorities(
            source_priorities
        )

        normalized_health = (
            self._normalize_health_scores(
                health_scores
            )
        )

        count = len(channel_list)

        if count == 0:
            return MergeResult(
                channels=(),
                decisions=(),
                stats=MergeStats(
                    input_channels=0,
                    output_channels=0,
                    duplicate_groups=0,
                    duplicates_removed=0,
                    url_collisions=0,
                    tvg_id_collisions=0,
                    name_collisions=0,
                ),
            )

        parents = list(range(count))
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
            channel_list
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
                    key_owners[identity] = index
                    continue

                collisions[key_type] += 1

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

            clusters[root].append(index)

        selected_channels: list[Channel] = []
        decisions: list[MergeDecision] = []

        for indices in clusters.values():
            evaluations = [
                self._evaluate(
                    channel_list[index],
                    index,
                    priorities,
                    normalized_health,
                )
                for index in indices
            ]

            selected_score = max(
                evaluations,
                key=lambda candidate: (
                    candidate.rank
                ),
            )

            selected_channel = (
                channel_list[
                    selected_score.index
                ]
            )

            selected_channels.append(
                selected_channel
            )

            if len(evaluations) > 1:
                discarded = tuple(
                    candidate
                    for candidate in sorted(
                        evaluations,
                        key=lambda item: (
                            item.rank
                        ),
                        reverse=True,
                    )
                    if candidate.index
                    != selected_score.index
                )

                decisions.append(
                    MergeDecision(
                        selected=selected_score,
                        discarded=discarded,
                        reason=(
                            self._selection_reason(
                                selected_score,
                                discarded[0],
                            )
                        ),
                    )
                )

        selected_channels.sort(
            key=self._output_sort_key
        )

        duplicates_removed = (
            count - len(selected_channels)
        )

        stats = MergeStats(
            input_channels=count,
            output_channels=len(
                selected_channels
            ),
            duplicate_groups=len(
                decisions
            ),
            duplicates_removed=(
                duplicates_removed
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
        )

        return MergeResult(
            channels=tuple(
                selected_channels
            ),
            decisions=tuple(decisions),
            stats=stats,
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

        if parts.scheme.casefold() == "https":
            score += 20

        elif parts.scheme.casefold() == "http":
            score += 10

        if parts.path.casefold().endswith(
            ".m3u8"
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
                isinstance(priority, bool)
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
        while parents[index] != index:
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

        if first_root == second_root:
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
        normalized = str(url).strip()

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
        normalized = unicodedata.normalize(
            "NFKC",
            str(value),
        )

        return " ".join(
            normalized.split()
        ).casefold()

    @classmethod
    def _normalize_name(
        cls,
        name: str,
    ) -> str:
        normalized = unicodedata.normalize(
            "NFKD",
            str(name),
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