from __future__ import annotations

import gzip
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from src.epg.matcher import EPGChannel


XMLTV_TIME_PATTERN = re.compile(
    r"^\d{8}(?:\d{2}){0,3}(?:\s*[+-]\d{4}|Z)?$"
)


class XMLTVParseError(
    ValueError
):
    """Errore durante la lettura o validazione di una guida XMLTV."""


@dataclass(
    frozen=True,
    slots=True,
)
class XMLTVProgramme:
    channel_id: str
    start: str
    stop: str
    title: str
    subtitle: str = ""
    description: str = ""
    categories: tuple[str, ...] = ()
    icon_url: str = ""
    episode_num: str = ""
    source_url: str = ""

    def __post_init__(
        self,
    ) -> None:
        channel_id = str(
            self.channel_id
        ).strip()

        start = str(
            self.start
        ).strip()

        stop = str(
            self.stop
        ).strip()

        title = str(
            self.title
        ).strip()

        if not channel_id:
            raise ValueError(
                "ID canale programma vuoto"
            )

        if not start:
            raise ValueError(
                "Ora di inizio programma vuota"
            )

        if not title:
            raise ValueError(
                "Titolo programma vuoto"
            )

        categories: list[
            str
        ] = []

        seen_categories: set[
            str
        ] = set()

        for value in self.categories:
            category = str(
                value
            ).strip()

            key = category.casefold()

            if (
                not category
                or key in seen_categories
            ):
                continue

            seen_categories.add(
                key
            )

            categories.append(
                category
            )

        object.__setattr__(
            self,
            "channel_id",
            channel_id,
        )

        object.__setattr__(
            self,
            "start",
            start,
        )

        object.__setattr__(
            self,
            "stop",
            stop,
        )

        object.__setattr__(
            self,
            "title",
            title,
        )

        object.__setattr__(
            self,
            "subtitle",
            str(
                self.subtitle
            ).strip(),
        )

        object.__setattr__(
            self,
            "description",
            str(
                self.description
            ).strip(),
        )

        object.__setattr__(
            self,
            "categories",
            tuple(
                categories
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
            "episode_num",
            str(
                self.episode_num
            ).strip(),
        )

        object.__setattr__(
            self,
            "source_url",
            str(
                self.source_url
            ).strip(),
        )

    def identity_key(
        self,
    ) -> tuple[
        str,
        str,
        str,
        str,
    ]:
        return (
            self.channel_id.casefold(),
            self.start,
            self.stop,
            self.title.casefold(),
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
class XMLTVIssue:
    kind: str
    message: str
    channel_id: str = ""
    item_index: int = 0

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
class XMLTVStats:
    compressed: bool
    input_bytes: int
    xml_bytes: int
    channels_found: int
    channels_created: int
    channel_duplicates: int
    programmes_found: int
    programmes_created: int
    programme_duplicates: int
    programmes_skipped: int
    issue_count: int

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
class XMLTVDocument:
    channels: tuple[
        EPGChannel,
        ...,
    ]
    programmes: tuple[
        XMLTVProgramme,
        ...,
    ]
    issues: tuple[
        XMLTVIssue,
        ...,
    ]
    stats: XMLTVStats
    source_url: str = ""

    def channel_ids(
        self,
    ) -> set[str]:
        return {
            channel.channel_id
            for channel in self.channels
        }

    def programmes_by_channel(
        self,
    ) -> dict[
        str,
        tuple[
            XMLTVProgramme,
            ...,
        ],
    ]:
        grouped: dict[
            str,
            list[
                XMLTVProgramme
            ],
        ] = {}

        for programme in self.programmes:
            grouped.setdefault(
                programme.channel_id,
                [],
            ).append(
                programme
            )

        return {
            channel_id: tuple(
                sorted(
                    items,
                    key=lambda item: (
                        item.start,
                        item.stop,
                        item.title.casefold(),
                    ),
                )
            )
            for channel_id, items
            in grouped.items()
        }

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "source_url": (
                self.source_url
            ),
            "stats": (
                self.stats.to_dict()
            ),
            "issues": [
                issue.to_dict()
                for issue
                in self.issues
            ],
            "channels": [
                channel.to_dict()
                for channel
                in self.channels
            ],
            "programmes": [
                programme.to_dict()
                for programme
                in self.programmes
            ],
        }


class XMLTVParser:
    """
    Parser sicuro e limitato per guide XMLTV.

    Supporta:

    - file XML non compressi;
    - file XML compressi GZIP;
    - deduplicazione dei canali;
    - deduplicazione dei programmi;
    - limiti di dimensione e quantità;
    - rifiuto di DTD ed entità esterne.

    Il parser non effettua richieste HTTP. I download saranno gestiti
    da un componente separato, così test e diagnostica restano chiari.
    """

    GZIP_MAGIC = b"\x1f\x8b"

    def __init__(
        self,
        *,
        max_input_bytes: int = (
            50 * 1024 * 1024
        ),
        max_xml_bytes: int = (
            250 * 1024 * 1024
        ),
        max_channels: int = 100_000,
        max_programmes: int = 500_000,
        issue_report_limit: int = 500,
    ) -> None:
        numeric_values = {
            "max_input_bytes": (
                max_input_bytes
            ),
            "max_xml_bytes": (
                max_xml_bytes
            ),
            "max_channels": (
                max_channels
            ),
            "max_programmes": (
                max_programmes
            ),
            "issue_report_limit": (
                issue_report_limit
            ),
        }

        for name, value in (
            numeric_values.items()
        ):
            if int(value) <= 0:
                raise ValueError(
                    f"{name} deve essere "
                    "maggiore di zero"
                )

        self.max_input_bytes = int(
            max_input_bytes
        )

        self.max_xml_bytes = int(
            max_xml_bytes
        )

        self.max_channels = int(
            max_channels
        )

        self.max_programmes = int(
            max_programmes
        )

        self.issue_report_limit = int(
            issue_report_limit
        )

    def parse_file(
        self,
        path: Path,
        *,
        source_url: str = "",
    ) -> XMLTVDocument:
        file_path = Path(
            path
        )

        try:
            size = (
                file_path.stat().st_size
            )
        except OSError as exc:
            raise XMLTVParseError(
                "Impossibile leggere il file "
                f"XMLTV: {exc}"
            ) from exc

        if size > self.max_input_bytes:
            raise XMLTVParseError(
                "File XMLTV troppo grande: "
                f"{size} byte"
            )

        try:
            data = file_path.read_bytes()
        except OSError as exc:
            raise XMLTVParseError(
                "Impossibile leggere il file "
                f"XMLTV: {exc}"
            ) from exc

        effective_source = (
            str(source_url).strip()
            or str(file_path)
        )

        return self.parse_bytes(
            data,
            source_url=(
                effective_source
            ),
            filename=file_path.name,
        )

    def parse_text(
        self,
        text: str,
        *,
        source_url: str = "",
    ) -> XMLTVDocument:
        if not isinstance(
            text,
            str,
        ):
            raise TypeError(
                "text deve essere una stringa"
            )

        return self.parse_bytes(
            text.encode(
                "utf-8"
            ),
            source_url=source_url,
        )

    def parse_bytes(
        self,
        data: bytes,
        *,
        source_url: str = "",
        filename: str = "",
    ) -> XMLTVDocument:
        if not isinstance(
            data,
            (
                bytes,
                bytearray,
            ),
        ):
            raise TypeError(
                "data deve essere bytes"
            )

        raw_data = bytes(
            data
        )

        input_bytes = len(
            raw_data
        )

        if input_bytes == 0:
            raise XMLTVParseError(
                "File XMLTV vuoto"
            )

        if (
            input_bytes
            > self.max_input_bytes
        ):
            raise XMLTVParseError(
                "Input XMLTV troppo grande: "
                f"{input_bytes} byte"
            )

        compressed = (
            raw_data.startswith(
                self.GZIP_MAGIC
            )
            or str(
                filename
            ).casefold().endswith(
                ".gz"
            )
        )

        xml_data = (
            self._decompress_gzip(
                raw_data
            )
            if compressed
            else raw_data
        )

        if len(
            xml_data
        ) > self.max_xml_bytes:
            raise XMLTVParseError(
                "XMLTV decompresso troppo "
                f"grande: {len(xml_data)} byte"
            )

        lowered_prefix = (
            xml_data[
                : min(
                    len(xml_data),
                    65_536,
                )
            ]
            .lower()
        )

        if (
            b"<!doctype"
            in lowered_prefix
            or b"<!entity"
            in lowered_prefix
        ):
            raise XMLTVParseError(
                "DTD ed entità XML non sono "
                "consentite"
            )

        try:
            root = ET.fromstring(
                xml_data
            )
        except ET.ParseError as exc:
            raise XMLTVParseError(
                "XMLTV non valido: "
                f"{exc}"
            ) from exc

        if self._local_name(
            root.tag
        ) != "tv":
            raise XMLTVParseError(
                "Elemento radice XMLTV "
                "non valido: atteso <tv>"
            )

        return self._parse_root(
            root,
            source_url=str(
                source_url
            ).strip(),
            compressed=compressed,
            input_bytes=input_bytes,
            xml_bytes=len(
                xml_data
            ),
        )

    def _parse_root(
        self,
        root: ET.Element,
        *,
        source_url: str,
        compressed: bool,
        input_bytes: int,
        xml_bytes: int,
    ) -> XMLTVDocument:
        channel_elements = [
            element
            for element in root
            if self._local_name(
                element.tag
            )
            == "channel"
        ]

        programme_elements = [
            element
            for element in root
            if self._local_name(
                element.tag
            )
            == "programme"
        ]

        if (
            len(channel_elements)
            > self.max_channels
        ):
            raise XMLTVParseError(
                "Numero di canali XMLTV "
                "superiore al limite: "
                f"{len(channel_elements)}"
            )

        if (
            len(programme_elements)
            > self.max_programmes
        ):
            raise XMLTVParseError(
                "Numero di programmi XMLTV "
                "superiore al limite: "
                f"{len(programme_elements)}"
            )

        issues: list[
            XMLTVIssue
        ] = []

        channels_by_key: dict[
            str,
            EPGChannel,
        ] = {}

        channel_duplicates = 0

        for index, element in enumerate(
            channel_elements,
            start=1,
        ):
            channel_id = str(
                element.attrib.get(
                    "id",
                    "",
                )
            ).strip()

            if not channel_id:
                self._append_issue(
                    issues,
                    XMLTVIssue(
                        kind=(
                            "channel_missing_id"
                        ),
                        message=(
                            "Canale XMLTV senza ID"
                        ),
                        item_index=index,
                    ),
                )
                continue

            display_names = (
                self._texts_by_tag(
                    element,
                    "display-name",
                )
            )

            icon_url = self._first_icon(
                element
            )

            channel = EPGChannel(
                channel_id=channel_id,
                display_names=(
                    display_names
                ),
                icon_url=icon_url,
                source_url=source_url,
            )

            key = (
                channel_id.casefold()
            )

            existing = (
                channels_by_key.get(
                    key
                )
            )

            if existing is None:
                channels_by_key[
                    key
                ] = channel
                continue

            channel_duplicates += 1

            merged_names = tuple(
                dict.fromkeys(
                    (
                        *existing
                        .display_names,
                        *channel
                        .display_names,
                    )
                )
            )

            channels_by_key[
                key
            ] = EPGChannel(
                channel_id=(
                    existing.channel_id
                ),
                display_names=(
                    merged_names
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

        programmes: list[
            XMLTVProgramme
        ] = []

        seen_programmes: set[
            tuple[
                str,
                str,
                str,
                str,
            ]
        ] = set()

        programme_duplicates = 0
        programmes_skipped = 0

        for index, element in enumerate(
            programme_elements,
            start=1,
        ):
            channel_id = str(
                element.attrib.get(
                    "channel",
                    "",
                )
            ).strip()

            start = str(
                element.attrib.get(
                    "start",
                    "",
                )
            ).strip()

            stop = str(
                element.attrib.get(
                    "stop",
                    "",
                )
            ).strip()

            title = self._preferred_text(
                element,
                "title",
            )

            invalid_reason = ""

            if not channel_id:
                invalid_reason = (
                    "programma senza channel"
                )
            elif not start:
                invalid_reason = (
                    "programma senza start"
                )
            elif not self._valid_time(
                start
            ):
                invalid_reason = (
                    "formato start non valido"
                )
            elif (
                stop
                and not self._valid_time(
                    stop
                )
            ):
                invalid_reason = (
                    "formato stop non valido"
                )
            elif not title:
                invalid_reason = (
                    "programma senza titolo"
                )

            if invalid_reason:
                programmes_skipped += 1

                self._append_issue(
                    issues,
                    XMLTVIssue(
                        kind=(
                            "programme_invalid"
                        ),
                        message=(
                            invalid_reason
                        ),
                        channel_id=(
                            channel_id
                        ),
                        item_index=index,
                    ),
                )
                continue

            programme = XMLTVProgramme(
                channel_id=channel_id,
                start=start,
                stop=stop,
                title=title,
                subtitle=(
                    self._preferred_text(
                        element,
                        "sub-title",
                    )
                ),
                description=(
                    self._preferred_text(
                        element,
                        "desc",
                    )
                ),
                categories=(
                    self._texts_by_tag(
                        element,
                        "category",
                    )
                ),
                icon_url=(
                    self._first_icon(
                        element
                    )
                ),
                episode_num=(
                    self._preferred_text(
                        element,
                        "episode-num",
                    )
                ),
                source_url=source_url,
            )

            identity_key = (
                programme.identity_key()
            )

            if (
                identity_key
                in seen_programmes
            ):
                programme_duplicates += 1
                continue

            seen_programmes.add(
                identity_key
            )

            programmes.append(
                programme
            )

        channels = tuple(
            sorted(
                channels_by_key.values(),
                key=lambda item: (
                    item.channel_id
                    .casefold()
                ),
            )
        )

        sorted_programmes = tuple(
            sorted(
                programmes,
                key=lambda item: (
                    item.channel_id
                    .casefold(),
                    item.start,
                    item.stop,
                    item.title.casefold(),
                ),
            )
        )

        stats = XMLTVStats(
            compressed=compressed,
            input_bytes=input_bytes,
            xml_bytes=xml_bytes,
            channels_found=len(
                channel_elements
            ),
            channels_created=len(
                channels
            ),
            channel_duplicates=(
                channel_duplicates
            ),
            programmes_found=len(
                programme_elements
            ),
            programmes_created=len(
                sorted_programmes
            ),
            programme_duplicates=(
                programme_duplicates
            ),
            programmes_skipped=(
                programmes_skipped
            ),
            issue_count=(
                programmes_skipped
                + sum(
                    1
                    for element
                    in channel_elements
                    if not str(
                        element.attrib.get(
                            "id",
                            "",
                        )
                    ).strip()
                )
            ),
        )

        return XMLTVDocument(
            channels=channels,
            programmes=(
                sorted_programmes
            ),
            issues=tuple(
                issues
            ),
            stats=stats,
            source_url=source_url,
        )

    def _decompress_gzip(
        self,
        data: bytes,
    ) -> bytes:
        output = io.BytesIO()

        try:
            with gzip.GzipFile(
                fileobj=io.BytesIO(
                    data
                ),
                mode="rb",
            ) as archive:
                while True:
                    remaining = (
                        self.max_xml_bytes
                        - output.tell()
                    )

                    chunk = archive.read(
                        min(
                            1024 * 1024,
                            remaining + 1,
                        )
                    )

                    if not chunk:
                        break

                    output.write(
                        chunk
                    )

                    if (
                        output.tell()
                        > self.max_xml_bytes
                    ):
                        raise XMLTVParseError(
                            "XMLTV GZIP supera il "
                            "limite decompresso"
                        )

        except (
            gzip.BadGzipFile,
            EOFError,
            OSError,
        ) as exc:
            raise XMLTVParseError(
                "Archivio XMLTV GZIP "
                f"non valido: {exc}"
            ) from exc

        return output.getvalue()

    def _append_issue(
        self,
        issues: list[
            XMLTVIssue
        ],
        issue: XMLTVIssue,
    ) -> None:
        if (
            len(issues)
            < self.issue_report_limit
        ):
            issues.append(
                issue
            )

    @classmethod
    def _preferred_text(
        cls,
        parent: ET.Element,
        tag_name: str,
    ) -> str:
        candidates: list[
            tuple[
                int,
                str,
            ]
        ] = []

        for child in parent:
            if (
                cls._local_name(
                    child.tag
                )
                != tag_name
            ):
                continue

            text = cls._element_text(
                child
            )

            if not text:
                continue

            language = str(
                child.attrib.get(
                    "lang",
                    "",
                )
            ).strip().casefold()

            priority = (
                0
                if language
                in {
                    "it",
                    "ita",
                    "it-it",
                }
                else 1
            )

            candidates.append(
                (
                    priority,
                    text,
                )
            )

        if not candidates:
            return ""

        candidates.sort(
            key=lambda item: (
                item[0],
            )
        )

        return candidates[0][1]

    @classmethod
    def _texts_by_tag(
        cls,
        parent: ET.Element,
        tag_name: str,
    ) -> tuple[str, ...]:
        values: list[
            str
        ] = []

        seen: set[
            str
        ] = set()

        for child in parent:
            if (
                cls._local_name(
                    child.tag
                )
                != tag_name
            ):
                continue

            text = cls._element_text(
                child
            )

            key = text.casefold()

            if (
                not text
                or key in seen
            ):
                continue

            seen.add(
                key
            )

            values.append(
                text
            )

        return tuple(
            values
        )

    @classmethod
    def _first_icon(
        cls,
        parent: ET.Element,
    ) -> str:
        for child in parent:
            if (
                cls._local_name(
                    child.tag
                )
                != "icon"
            ):
                continue

            source = str(
                child.attrib.get(
                    "src",
                    "",
                )
            ).strip()

            if source:
                return source

        return ""

    @staticmethod
    def _element_text(
        element: ET.Element,
    ) -> str:
        return " ".join(
            part.strip()
            for part in element.itertext()
            if part.strip()
        ).strip()

    @staticmethod
    def _local_name(
        tag: object,
    ) -> str:
        text = str(
            tag
        )

        if "}" in text:
            text = text.rsplit(
                "}",
                1,
            )[1]

        return text.casefold()

    @staticmethod
    def _valid_time(
        value: str,
    ) -> bool:
        return bool(
            XMLTV_TIME_PATTERN.fullmatch(
                str(value).strip()
            )
        )
