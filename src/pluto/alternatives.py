from __future__ import annotations

import re
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Iterable

from src.models.channel import Channel


@dataclass(
    frozen=True,
    slots=True,
)
class PlutoAlternativeStats:
    input_channels: int
    direct_pluto_channels: int
    existing_resolver_channels: int
    generated_alternatives: int
    skipped_duplicate_urls: int
    missing_channel_id: int

    def to_dict(
        self,
    ) -> dict[str, int]:
        return asdict(
            self
        )


@dataclass(
    frozen=True,
    slots=True,
)
class PlutoAlternativeResult:
    channels: tuple[
        Channel,
        ...,
    ]

    generated_channels: tuple[
        Channel,
        ...,
    ]

    stats: PlutoAlternativeStats

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "stats": (
                self.stats.to_dict()
            ),
            "generated_channels": [
                {
                    "name": channel.name,
                    "stream_url": (
                        channel.stream_url
                    ),
                    "tvg_id": channel.tvg_id,
                    "source_id": (
                        channel.source_id
                    ),
                }
                for channel
                in self.generated_channels
            ],
        }


class PlutoAlternativeGenerator:
    """
    Genera una seconda URL candidata per i canali Pluto diretti.

    Il flusso originale con JWT non viene rimosso. Per ogni URL Pluto
    contenente l'ID del canale viene aggiunto:

        https://jmp2.uk/plu-<CHANNEL_ID>.m3u8

    Il ChannelMerger raggruppa originale e alternativa tramite tvg-id
    o nome; il Playback Verification Engine controlla entrambe e
    seleziona il candidato realmente riproducibile.

    La generazione è intenzionalmente conservativa:

    - soltanto host appartenenti a pluto.tv;
    - ID esadecimale di 24 caratteri;
    - nessun duplicato se la URL jmp2 è già presente;
    - metadati del canale preservati;
    - sorgente sintetica separata, con priorità configurabile
      dall'Application.
    """

    SOURCE_ID = "pluto_jmp2"
    SOURCE_PRIORITY = 105

    CHANNEL_ID_PATTERN = re.compile(
        (
            r"/(?:v\d+/)?"
            r"stitch/hls/channel/"
            r"([a-f0-9]{24})/"
        ),
        flags=re.IGNORECASE,
    )

    RAW_CHANNEL_ID_PATTERN = re.compile(
        r"^[a-f0-9]{24}$",
        flags=re.IGNORECASE,
    )

    JMP2_PATTERN = re.compile(
        (
            r"^https://jmp2\.uk/"
            r"plu-([a-f0-9]{24})"
            r"\.m3u8(?:[?#].*)?$"
        ),
        flags=re.IGNORECASE,
    )

    def expand(
        self,
        channels: Iterable[
            Channel
        ],
    ) -> PlutoAlternativeResult:
        channel_list = tuple(
            channels
        )

        if any(
            not isinstance(
                channel,
                Channel,
            )
            for channel in channel_list
        ):
            raise TypeError(
                "channels contiene elementi "
                "non Channel"
            )

        known_urls = {
            self._normalize_url(
                channel.stream_url
            )
            for channel in channel_list
        }

        output: list[
            Channel
        ] = list(
            channel_list
        )

        generated: list[
            Channel
        ] = []

        direct_pluto_channels = 0
        existing_resolver_channels = 0
        skipped_duplicate_urls = 0
        missing_channel_id = 0

        for channel in channel_list:
            if self.is_resolver_url(
                channel.stream_url
            ):
                existing_resolver_channels += 1
                continue

            if not self.is_direct_pluto_url(
                channel.stream_url
            ):
                continue

            direct_pluto_channels += 1

            channel_id = (
                self.extract_channel_id(
                    channel
                )
            )

            if not channel_id:
                missing_channel_id += 1
                continue

            alternative_url = (
                self.build_resolver_url(
                    channel_id
                )
            )

            normalized_alternative = (
                self._normalize_url(
                    alternative_url
                )
            )

            if (
                normalized_alternative
                in known_urls
            ):
                skipped_duplicate_urls += 1
                continue

            alternative = (
                self._clone_as_alternative(
                    channel,
                    alternative_url,
                    channel_id,
                )
            )

            known_urls.add(
                normalized_alternative
            )

            output.append(
                alternative
            )

            generated.append(
                alternative
            )

        return PlutoAlternativeResult(
            channels=tuple(
                output
            ),
            generated_channels=tuple(
                generated
            ),
            stats=PlutoAlternativeStats(
                input_channels=len(
                    channel_list
                ),
                direct_pluto_channels=(
                    direct_pluto_channels
                ),
                existing_resolver_channels=(
                    existing_resolver_channels
                ),
                generated_alternatives=len(
                    generated
                ),
                skipped_duplicate_urls=(
                    skipped_duplicate_urls
                ),
                missing_channel_id=(
                    missing_channel_id
                ),
            ),
        )

    @classmethod
    def extract_channel_id(
        cls,
        channel: Channel,
    ) -> str:
        request_url = str(
            channel.stream_url
        ).split(
            "|",
            1,
        )[0].strip()

        try:
            path = urllib.parse.urlsplit(
                request_url
            ).path
        except ValueError:
            path = ""

        match = cls.CHANNEL_ID_PATTERN.search(
            path
        )

        if match:
            return (
                match.group(1)
                .casefold()
            )

        tvg_id = str(
            channel.tvg_id
        ).strip()

        if cls.RAW_CHANNEL_ID_PATTERN.fullmatch(
            tvg_id
        ):
            return tvg_id.casefold()

        return ""

    @classmethod
    def is_direct_pluto_url(
        cls,
        value: str,
    ) -> bool:
        request_url = str(
            value
        ).split(
            "|",
            1,
        )[0].strip()

        try:
            parts = urllib.parse.urlsplit(
                request_url
            )
        except ValueError:
            return False

        hostname = (
            parts.hostname
            or ""
        ).casefold()

        if not (
            hostname == "pluto.tv"
            or hostname.endswith(
                ".pluto.tv"
            )
        ):
            return False

        return bool(
            cls.CHANNEL_ID_PATTERN.search(
                parts.path
            )
        ) or bool(
            cls.RAW_CHANNEL_ID_PATTERN.fullmatch(
                PathLikeName.from_path(
                    parts.path
                )
            )
        )

    @classmethod
    def is_resolver_url(
        cls,
        value: str,
    ) -> bool:
        return bool(
            cls.JMP2_PATTERN.fullmatch(
                str(value).strip()
            )
        )

    @staticmethod
    def build_resolver_url(
        channel_id: str,
    ) -> str:
        normalized = str(
            channel_id
        ).strip().casefold()

        if not (
            PlutoAlternativeGenerator
            .RAW_CHANNEL_ID_PATTERN
            .fullmatch(
                normalized
            )
        ):
            raise ValueError(
                "ID Pluto non valido"
            )

        return (
            "https://jmp2.uk/"
            f"plu-{normalized}.m3u8"
        )

    @classmethod
    def _clone_as_alternative(
        cls,
        channel: Channel,
        alternative_url: str,
        channel_id: str,
    ) -> Channel:
        attributes = dict(
            channel.attributes
        )

        attributes[
            "generated-alternative"
        ] = "jmp2"

        attributes[
            "pluto-channel-id"
        ] = channel_id

        attributes[
            "original-source-id"
        ] = channel.source_id

        return Channel(
            name=channel.name,
            stream_url=alternative_url,
            group=channel.group,
            tvg_id=channel.tvg_id,
            tvg_name=channel.tvg_name,
            logo=channel.logo,
            source_id=cls.SOURCE_ID,
            attributes=attributes,
            extra_directives=list(
                channel.extra_directives
            ),
        )

    @staticmethod
    def _normalize_url(
        value: str,
    ) -> str:
        raw = str(
            value
        ).strip()

        try:
            parts = urllib.parse.urlsplit(
                raw
            )
        except ValueError:
            return raw.casefold()

        hostname = (
            parts.hostname
            or ""
        ).casefold()

        scheme = (
            parts.scheme
            .casefold()
        )

        return urllib.parse.urlunsplit(
            (
                scheme,
                hostname,
                parts.path,
                parts.query,
                "",
            )
        )


class PathLikeName:
    """
    Helper minimo per leggere l'ultimo segmento di un percorso URL
    senza importare pathlib nel runtime del generatore.
    """

    @staticmethod
    def from_path(
        value: str,
    ) -> str:
        return (
            str(value)
            .rstrip("/")
            .rsplit(
                "/",
                1,
            )[-1]
            .split(
                ".",
                1,
            )[0]
            .strip()
        )
