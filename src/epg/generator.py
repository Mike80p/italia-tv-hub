from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from src.epg.matcher import (
    EPGChannel,
    EPGChannelMatcher,
    EPGMatch,
    EPGMatchBatchResult,
)
from src.epg.xmltv import (
    XMLTVDocument,
    XMLTVProgramme,
)
from src.models.channel import Channel


@dataclass(
    frozen=True,
    slots=True,
)
class EPGGenerationStats:
    input_documents: int
    input_epg_channels: int
    input_programmes: int
    merged_epg_channels: int
    merged_programmes: int
    playlist_channels: int
    matched_playlist_channels: int
    unmatched_playlist_channels: int
    ambiguous_playlist_channels: int
    output_channels: int
    output_programmes: int
    programme_duplicates_removed: int
    channels_without_programmes: int
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
class EPGGenerationResult:
    xml_text: str
    match_result: EPGMatchBatchResult
    output_channels: tuple[
        EPGChannel,
        ...,
    ]
    output_programmes: tuple[
        XMLTVProgramme,
        ...,
    ]
    stats: EPGGenerationStats
    source_documents: tuple[
        dict[str, object],
        ...,
    ]

    def to_report_dict(
        self,
    ) -> dict[str, object]:
        return {
            "stats": (
                self.stats.to_dict()
            ),
            "matching": (
                self.match_result.to_dict()
            ),
            "source_documents": list(
                self.source_documents
            ),
            "output_channel_ids": [
                channel.channel_id
                for channel
                in self.output_channels
            ],
        }


class EPGGenerator:
    """
    Unisce guide XMLTV e genera un file filtrato per la playlist.

    Il generatore:

    - unisce canali provenienti da più documenti XMLTV;
    - deduplica i programmi;
    - abbina i canali della playlist tramite EPGChannelMatcher;
    - conserva solo canali e programmi realmente utili;
    - produce XMLTV deterministico;
    - può applicare ai Channel il tvg-id trovato dal matcher.
    """

    def __init__(
        self,
        *,
        matcher: (
            EPGChannelMatcher | None
        ) = None,
        generator_name: str = (
            "Italia TV Hub"
        ),
    ) -> None:
        self.matcher = (
            matcher
            if matcher is not None
            else EPGChannelMatcher()
        )

        self.generator_name = (
            str(generator_name).strip()
            or "Italia TV Hub"
        )

    def generate(
        self,
        playlist_channels: Iterable[
            Channel
        ],
        documents: Iterable[
            XMLTVDocument
        ],
    ) -> EPGGenerationResult:
        playlist = tuple(
            playlist_channels
        )

        source_documents = tuple(
            documents
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
                document,
                XMLTVDocument,
            )
            for document
            in source_documents
        ):
            raise TypeError(
                "documents contiene elementi "
                "non XMLTVDocument"
            )

        (
            merged_channels,
            merged_programmes,
            programme_duplicates_removed,
        ) = self._merge_documents(
            source_documents
        )

        match_result = (
            self.matcher.match_channels(
                playlist,
                merged_channels,
            )
        )

        matched_ids = {
            match.epg_channel
            .channel_id
            .casefold()
            for match
            in match_result.matches
        }

        output_channels = tuple(
            channel
            for channel
            in merged_channels
            if channel.channel_id.casefold()
            in matched_ids
        )

        canonical_ids = {
            channel.channel_id
            .casefold(): channel.channel_id
            for channel
            in output_channels
        }

        output_programmes = tuple(
            sorted(
                (
                    self._with_channel_id(
                        programme,
                        canonical_ids[
                            programme
                            .channel_id
                            .casefold()
                        ],
                    )
                    for programme
                    in merged_programmes
                    if programme
                    .channel_id
                    .casefold()
                    in matched_ids
                ),
                key=lambda item: (
                    item.channel_id
                    .casefold(),
                    item.start,
                    item.stop,
                    item.title.casefold(),
                ),
            )
        )

        programme_channel_ids = {
            programme.channel_id
            .casefold()
            for programme
            in output_programmes
        }

        channels_without_programmes = sum(
            1
            for channel
            in output_channels
            if channel.channel_id
            .casefold()
            not in programme_channel_ids
        )

        xml_text = self._render_xml(
            output_channels,
            output_programmes,
        )

        source_summaries = tuple(
            {
                "source_url": (
                    document.source_url
                ),
                "stats": (
                    document.stats.to_dict()
                ),
                "issues_reported": len(
                    document.issues
                ),
            }
            for document
            in source_documents
        )

        stats = EPGGenerationStats(
            input_documents=len(
                source_documents
            ),
            input_epg_channels=sum(
                len(
                    document.channels
                )
                for document
                in source_documents
            ),
            input_programmes=sum(
                len(
                    document.programmes
                )
                for document
                in source_documents
            ),
            merged_epg_channels=len(
                merged_channels
            ),
            merged_programmes=len(
                merged_programmes
            ),
            playlist_channels=len(
                playlist
            ),
            matched_playlist_channels=(
                match_result.stats.matched
            ),
            unmatched_playlist_channels=(
                match_result.stats.unmatched
            ),
            ambiguous_playlist_channels=(
                match_result.stats.ambiguous
            ),
            output_channels=len(
                output_channels
            ),
            output_programmes=len(
                output_programmes
            ),
            programme_duplicates_removed=(
                programme_duplicates_removed
            ),
            channels_without_programmes=(
                channels_without_programmes
            ),
            coverage_percent=(
                match_result
                .stats
                .coverage_percent
            ),
        )

        return EPGGenerationResult(
            xml_text=xml_text,
            match_result=match_result,
            output_channels=(
                output_channels
            ),
            output_programmes=(
                output_programmes
            ),
            stats=stats,
            source_documents=(
                source_summaries
            ),
        )

    def write(
        self,
        epg_path: Path,
        report_path: Path,
        result: EPGGenerationResult,
    ) -> None:
        if not isinstance(
            result,
            EPGGenerationResult,
        ):
            raise TypeError(
                "result deve essere "
                "EPGGenerationResult"
            )

        epg_path = Path(
            epg_path
        )

        report_path = Path(
            report_path
        )

        epg_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        report_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        epg_path.write_text(
            result.xml_text,
            encoding="utf-8",
        )

        report_path.write_text(
            json.dumps(
                result.to_report_dict(),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def apply_matches(
        result: EPGGenerationResult,
    ) -> int:
        """
        Applica ai Channel della playlist il tvg-id trovato.

        Aggiorna anche tvg-name e logo soltanto quando mancanti.
        Restituisce il numero di canali modificati.
        """

        if not isinstance(
            result,
            EPGGenerationResult,
        ):
            raise TypeError(
                "result deve essere "
                "EPGGenerationResult"
            )

        updated = 0

        for match in (
            result.match_result.matches
        ):
            channel = (
                match.playlist_channel
            )

            epg_channel = (
                match.epg_channel
            )

            changed = False

            if (
                channel.tvg_id
                != epg_channel.channel_id
            ):
                channel.tvg_id = (
                    epg_channel.channel_id
                )

                changed = True

            if (
                not channel.tvg_name
                and epg_channel
                .display_names
            ):
                channel.tvg_name = (
                    epg_channel
                    .display_names[0]
                )

                changed = True

            if (
                not channel.logo
                and epg_channel.icon_url
            ):
                channel.logo = (
                    epg_channel.icon_url
                )

                changed = True

            if changed:
                updated += 1

        return updated

    @classmethod
    def _merge_documents(
        cls,
        documents: tuple[
            XMLTVDocument,
            ...,
        ],
    ) -> tuple[
        tuple[
            EPGChannel,
            ...,
        ],
        tuple[
            XMLTVProgramme,
            ...,
        ],
        int,
    ]:
        channels_by_id: dict[
            str,
            EPGChannel,
        ] = {}

        for document in documents:
            for channel in (
                document.channels
            ):
                key = (
                    channel.channel_id
                    .casefold()
                )

                existing = (
                    channels_by_id.get(
                        key
                    )
                )

                if existing is None:
                    channels_by_id[
                        key
                    ] = channel

                    continue

                display_names = tuple(
                    dict.fromkeys(
                        (
                            *existing
                            .display_names,
                            *channel
                            .display_names,
                        )
                    )
                )

                channels_by_id[
                    key
                ] = EPGChannel(
                    channel_id=(
                        existing.channel_id
                    ),
                    display_names=(
                        display_names
                    ),
                    icon_url=(
                        existing.icon_url
                        or channel.icon_url
                    ),
                    source_url=(
                        existing.source_url
                        or channel.source_url
                    ),
                )

        canonical_ids = {
            key: channel.channel_id
            for key, channel
            in channels_by_id.items()
        }

        programmes_by_key: dict[
            tuple[
                str,
                str,
                str,
                str,
            ],
            XMLTVProgramme,
        ] = {}

        duplicate_count = 0

        for document in documents:
            for programme in (
                document.programmes
            ):
                channel_key = (
                    programme.channel_id
                    .casefold()
                )

                canonical_id = (
                    canonical_ids.get(
                        channel_key,
                        programme.channel_id,
                    )
                )

                normalized_programme = (
                    cls._with_channel_id(
                        programme,
                        canonical_id,
                    )
                )

                identity_key = (
                    normalized_programme
                    .identity_key()
                )

                existing = (
                    programmes_by_key.get(
                        identity_key
                    )
                )

                if existing is not None:
                    duplicate_count += 1

                    programmes_by_key[
                        identity_key
                    ] = (
                        cls._prefer_programme(
                            existing,
                            normalized_programme,
                        )
                    )

                    continue

                programmes_by_key[
                    identity_key
                ] = normalized_programme

        merged_channels = tuple(
            sorted(
                channels_by_id.values(),
                key=lambda item: (
                    item.channel_id
                    .casefold()
                ),
            )
        )

        merged_programmes = tuple(
            sorted(
                programmes_by_key.values(),
                key=lambda item: (
                    item.channel_id
                    .casefold(),
                    item.start,
                    item.stop,
                    item.title.casefold(),
                ),
            )
        )

        return (
            merged_channels,
            merged_programmes,
            duplicate_count,
        )

    @staticmethod
    def _prefer_programme(
        first: XMLTVProgramme,
        second: XMLTVProgramme,
    ) -> XMLTVProgramme:
        first_score = (
            int(
                bool(
                    first.description
                )
            )
            + int(
                bool(
                    first.subtitle
                )
            )
            + len(
                first.categories
            )
            + int(
                bool(
                    first.icon_url
                )
            )
            + int(
                bool(
                    first.episode_num
                )
            )
        )

        second_score = (
            int(
                bool(
                    second.description
                )
            )
            + int(
                bool(
                    second.subtitle
                )
            )
            + len(
                second.categories
            )
            + int(
                bool(
                    second.icon_url
                )
            )
            + int(
                bool(
                    second.episode_num
                )
            )
        )

        return (
            second
            if second_score > first_score
            else first
        )

    @staticmethod
    def _with_channel_id(
        programme: XMLTVProgramme,
        channel_id: str,
    ) -> XMLTVProgramme:
        if (
            programme.channel_id
            == channel_id
        ):
            return programme

        return XMLTVProgramme(
            channel_id=channel_id,
            start=programme.start,
            stop=programme.stop,
            title=programme.title,
            subtitle=(
                programme.subtitle
            ),
            description=(
                programme.description
            ),
            categories=(
                programme.categories
            ),
            icon_url=(
                programme.icon_url
            ),
            episode_num=(
                programme.episode_num
            ),
            source_url=(
                programme.source_url
            ),
        )

    def _render_xml(
        self,
        channels: tuple[
            EPGChannel,
            ...,
        ],
        programmes: tuple[
            XMLTVProgramme,
            ...,
        ],
    ) -> str:
        root = ET.Element(
            "tv",
            {
                "generator-info-name": (
                    self.generator_name
                )
            },
        )

        for channel in channels:
            channel_element = (
                ET.SubElement(
                    root,
                    "channel",
                    {
                        "id": (
                            channel.channel_id
                        )
                    },
                )
            )

            for display_name in (
                channel.display_names
            ):
                element = ET.SubElement(
                    channel_element,
                    "display-name",
                )

                element.text = (
                    display_name
                )

            if channel.icon_url:
                ET.SubElement(
                    channel_element,
                    "icon",
                    {
                        "src": (
                            channel.icon_url
                        )
                    },
                )

        for programme in programmes:
            attributes = {
                "channel": (
                    programme.channel_id
                ),
                "start": (
                    programme.start
                ),
            }

            if programme.stop:
                attributes[
                    "stop"
                ] = programme.stop

            programme_element = (
                ET.SubElement(
                    root,
                    "programme",
                    attributes,
                )
            )

            title = ET.SubElement(
                programme_element,
                "title",
            )

            title.text = (
                programme.title
            )

            if programme.subtitle:
                subtitle = ET.SubElement(
                    programme_element,
                    "sub-title",
                )

                subtitle.text = (
                    programme.subtitle
                )

            if programme.description:
                description = (
                    ET.SubElement(
                        programme_element,
                        "desc",
                    )
                )

                description.text = (
                    programme.description
                )

            for category_name in (
                programme.categories
            ):
                category = ET.SubElement(
                    programme_element,
                    "category",
                )

                category.text = (
                    category_name
                )

            if programme.icon_url:
                ET.SubElement(
                    programme_element,
                    "icon",
                    {
                        "src": (
                            programme.icon_url
                        )
                    },
                )

            if programme.episode_num:
                episode = ET.SubElement(
                    programme_element,
                    "episode-num",
                )

                episode.text = (
                    programme.episode_num
                )

        ET.indent(
            root,
            space="  ",
        )

        xml_body = ET.tostring(
            root,
            encoding="unicode",
            short_empty_elements=True,
        )

        return (
            '<?xml version="1.0" '
            'encoding="UTF-8"?>\n'
            + xml_body
            + "\n"
        )
