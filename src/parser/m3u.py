from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from threading import RLock

from src.models.channel import Channel


ATTRIBUTE_PATTERN = re.compile(
    r"""
    (?P<key>[A-Za-z0-9_-]+)
    \s*=\s*
    (?:
        "(?P<double>(?:\\.|[^"])*)"
        |
        '(?P<single>(?:\\.|[^'])*)'
        |
        (?P<bare>[^\s,]+)
    )
    """,
    re.VERBOSE,
)

CONTROL_CHARACTER_PATTERN = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"
)

WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ParseIssue:
    line_number: int
    code: str
    message: str
    raw_line: str
    source_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "code": self.code,
            "message": self.message,
            "raw_line": self.raw_line,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class ParseStats:
    lines_total: int
    non_empty_lines: int
    extinf_records: int
    channels_created: int
    skipped_records: int
    malformed_extinf: int
    missing_name: int
    missing_url: int
    invalid_channel: int
    orphan_lines: int
    abandoned_records: int
    directives_collected: int

    def to_dict(self) -> dict[str, int]:
        return {
            "lines_total": self.lines_total,
            "non_empty_lines": self.non_empty_lines,
            "extinf_records": self.extinf_records,
            "channels_created": self.channels_created,
            "skipped_records": self.skipped_records,
            "malformed_extinf": self.malformed_extinf,
            "missing_name": self.missing_name,
            "missing_url": self.missing_url,
            "invalid_channel": self.invalid_channel,
            "orphan_lines": self.orphan_lines,
            "abandoned_records": self.abandoned_records,
            "directives_collected": self.directives_collected,
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    source_id: str
    channels: tuple[Channel, ...]
    issues: tuple[ParseIssue, ...]
    stats: ParseStats

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "stats": self.stats.to_dict(),
            "issues": [
                issue.to_dict()
                for issue in self.issues
            ],
        }


@dataclass(slots=True)
class _PendingRecord:
    info_line: str
    line_number: int
    directives: list[str]


class M3UParser:
    """
    Parser M3U normalizzato con diagnostica.

    Compatibilità:

    - parse() continua a restituire list[Channel];
    - parse_detailed() restituisce canali, statistiche e problemi;
    - last_result conserva il risultato dell'ultima elaborazione.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._last_result: ParseResult | None = None

    @property
    def last_result(self) -> ParseResult | None:
        with self._lock:
            return self._last_result

    def parse(
        self,
        text: str,
        source_id: str,
    ) -> list[Channel]:
        """
        Metodo compatibile con l'Application esistente.
        """

        result = self.parse_detailed(
            text,
            source_id,
        )

        return list(result.channels)

    def parse_detailed(
        self,
        text: str,
        source_id: str,
    ) -> ParseResult:
        if not isinstance(text, str):
            raise TypeError(
                "text must be a string"
            )

        if not isinstance(source_id, str):
            raise TypeError(
                "source_id must be a string"
            )

        normalized_source_id = self._normalize_text(
            source_id
        )

        normalized_text = (
            text
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        lines = normalized_text.split("\n")

        channels: list[Channel] = []
        issues: list[ParseIssue] = []

        pending: _PendingRecord | None = None

        non_empty_lines = 0
        extinf_records = 0
        malformed_extinf = 0
        missing_name = 0
        missing_url = 0
        invalid_channel = 0
        orphan_lines = 0
        abandoned_records = 0
        directives_collected = 0

        for line_number, raw_line in enumerate(
            lines,
            start=1,
        ):
            line = self._normalize_line(
                raw_line
            )

            if not line:
                continue

            non_empty_lines += 1

            upper_line = line.upper()

            if upper_line.startswith("#EXTM3U"):
                continue

            if upper_line.startswith("#EXTINF:"):
                extinf_records += 1

                if pending is not None:
                    abandoned_records += 1

                    issues.append(
                        ParseIssue(
                            line_number=(
                                pending.line_number
                            ),
                            code=(
                                "abandoned_record"
                            ),
                            message=(
                                "Record EXTINF sostituito "
                                "prima della presenza "
                                "dell'URL"
                            ),
                            raw_line=(
                                pending.info_line
                            ),
                            source_id=(
                                normalized_source_id
                            ),
                        )
                    )

                pending = _PendingRecord(
                    info_line=line,
                    line_number=line_number,
                    directives=[],
                )

                continue

            if pending is not None:
                if line.startswith("#"):
                    directive = (
                        self._normalize_directive(
                            line
                        )
                    )

                    if directive:
                        pending.directives.append(
                            directive
                        )

                        directives_collected += 1

                    continue

                channel, issue_code, message = (
                    self._create_channel(
                        info_line=(
                            pending.info_line
                        ),
                        stream_url=line,
                        source_id=(
                            normalized_source_id
                        ),
                        directives=(
                            pending.directives
                        ),
                    )
                )

                if channel is not None:
                    channels.append(channel)

                else:
                    if (
                        issue_code
                        == "malformed_extinf"
                    ):
                        malformed_extinf += 1

                    elif (
                        issue_code
                        == "missing_name"
                    ):
                        missing_name += 1

                    elif (
                        issue_code
                        == "missing_url"
                    ):
                        missing_url += 1

                    else:
                        invalid_channel += 1

                    issues.append(
                        ParseIssue(
                            line_number=(
                                pending.line_number
                            ),
                            code=(
                                issue_code
                                or "invalid_channel"
                            ),
                            message=(
                                message
                                or "Canale non valido"
                            ),
                            raw_line=(
                                pending.info_line
                            ),
                            source_id=(
                                normalized_source_id
                            ),
                        )
                    )

                pending = None
                continue

            if not line.startswith("#"):
                orphan_lines += 1

                issues.append(
                    ParseIssue(
                        line_number=line_number,
                        code="orphan_line",
                        message=(
                            "URL o contenuto senza "
                            "record EXTINF associato"
                        ),
                        raw_line=line,
                        source_id=(
                            normalized_source_id
                        ),
                    )
                )

        if pending is not None:
            missing_url += 1

            issues.append(
                ParseIssue(
                    line_number=(
                        pending.line_number
                    ),
                    code="missing_url",
                    message=(
                        "Record EXTINF senza URL "
                        "dello stream"
                    ),
                    raw_line=(
                        pending.info_line
                    ),
                    source_id=(
                        normalized_source_id
                    ),
                )
            )

        skipped_records = (
            malformed_extinf
            + missing_name
            + missing_url
            + invalid_channel
            + abandoned_records
        )

        stats = ParseStats(
            lines_total=len(lines),
            non_empty_lines=non_empty_lines,
            extinf_records=extinf_records,
            channels_created=len(channels),
            skipped_records=skipped_records,
            malformed_extinf=malformed_extinf,
            missing_name=missing_name,
            missing_url=missing_url,
            invalid_channel=invalid_channel,
            orphan_lines=orphan_lines,
            abandoned_records=abandoned_records,
            directives_collected=(
                directives_collected
            ),
        )

        result = ParseResult(
            source_id=normalized_source_id,
            channels=tuple(channels),
            issues=tuple(issues),
            stats=stats,
        )

        with self._lock:
            self._last_result = result

        return result

    def _create_channel(
        self,
        info_line: str,
        stream_url: str,
        source_id: str,
        directives: list[str],
    ) -> tuple[
        Channel | None,
        str | None,
        str | None,
    ]:
        payload = info_line[
            len("#EXTINF:"):
        ]

        split_result = (
            self._split_metadata_and_name(
                payload
            )
        )

        if split_result is None:
            return (
                None,
                "malformed_extinf",
                "Record EXTINF privo della "
                "virgola che separa metadati "
                "e nome",
            )

        metadata, raw_name = split_result

        attributes = (
            self._parse_attributes(
                metadata
            )
        )

        normalized_url = self._normalize_url(
            stream_url
        )

        if not normalized_url:
            return (
                None,
                "missing_url",
                "URL dello stream vuoto",
            )

        name = self._normalize_text(
            raw_name
        )

        tvg_name = self._normalize_text(
            attributes.get(
                "tvg-name",
                "",
            )
        )

        if not name:
            name = tvg_name

        if not name:
            return (
                None,
                "missing_name",
                "Nome canale e tvg-name vuoti",
            )

        group = self._normalize_text(
            attributes.get(
                "group-title",
                "",
            )
        )

        if not group:
            group = (
                self._group_from_directives(
                    directives
                )
            )

        tvg_id = self._normalize_text(
            attributes.get(
                "tvg-id",
                "",
            )
        )

        logo = self._normalize_url(
            attributes.get(
                "tvg-logo",
                "",
            )
        )

        normalized_attributes = dict(
            attributes
        )

        self._set_attribute(
            normalized_attributes,
            "tvg-id",
            tvg_id,
        )

        self._set_attribute(
            normalized_attributes,
            "tvg-name",
            tvg_name,
        )

        self._set_attribute(
            normalized_attributes,
            "group-title",
            group,
        )

        self._set_attribute(
            normalized_attributes,
            "tvg-logo",
            logo,
        )

        normalized_directives = [
            directive
            for directive in (
                self._normalize_directive(
                    value
                )
                for value in directives
            )
            if directive
        ]

        try:
            channel = Channel(
                name=name,
                stream_url=normalized_url,
                group=group,
                tvg_id=tvg_id,
                tvg_name=tvg_name,
                logo=logo,
                source_id=source_id,
                attributes=(
                    normalized_attributes
                ),
                extra_directives=(
                    normalized_directives
                ),
            )

        except (TypeError, ValueError) as exc:
            return (
                None,
                "invalid_channel",
                str(exc),
            )

        return channel, None, None

    @staticmethod
    def _split_metadata_and_name(
        payload: str,
    ) -> tuple[str, str] | None:
        """
        Trova la prima virgola non racchiusa
        tra virgolette.

        Permette attributi come:

        group-title="News, Italia"
        """

        quote: str | None = None
        escaped = False

        for index, character in enumerate(
            payload
        ):
            if escaped:
                escaped = False
                continue

            if character == "\\":
                escaped = True
                continue

            if quote is not None:
                if character == quote:
                    quote = None

                continue

            if character in {'"', "'"}:
                quote = character
                continue

            if character == ",":
                return (
                    payload[:index],
                    payload[index + 1:],
                )

        return None

    def _parse_attributes(
        self,
        metadata: str,
    ) -> dict[str, str]:
        attributes: dict[str, str] = {}

        for match in ATTRIBUTE_PATTERN.finditer(
            metadata
        ):
            key = match.group(
                "key"
            ).strip().casefold()

            raw_value = (
                match.group("double")
                if match.group("double")
                is not None
                else match.group("single")
                if match.group("single")
                is not None
                else match.group("bare")
                or ""
            )

            value = self._unescape_attribute(
                raw_value
            )

            attributes[key] = (
                self._normalize_text(
                    value
                )
            )

        return attributes

    @staticmethod
    def _unescape_attribute(
        value: str,
    ) -> str:
        return (
            value
            .replace(r"\"", '"')
            .replace(r"\'", "'")
            .replace(r"\\", "\\")
        )

    def _group_from_directives(
        self,
        directives: list[str],
    ) -> str:
        for directive in directives:
            if directive.upper().startswith(
                "#EXTGRP:"
            ):
                return self._normalize_text(
                    directive.split(
                        ":",
                        1,
                    )[1]
                )

        return ""

    @staticmethod
    def _set_attribute(
        attributes: dict[str, str],
        key: str,
        value: str,
    ) -> None:
        if value:
            attributes[key] = value

        elif key in attributes:
            attributes[key] = ""

    @staticmethod
    def _normalize_text(
        value: str | None,
    ) -> str:
        if value is None:
            return ""

        normalized = unicodedata.normalize(
            "NFKC",
            str(value),
        )

        normalized = (
            CONTROL_CHARACTER_PATTERN.sub(
                "",
                normalized,
            )
        )

        return WHITESPACE_PATTERN.sub(
            " ",
            normalized,
        ).strip()

    @staticmethod
    def _normalize_url(
        value: str | None,
    ) -> str:
        if value is None:
            return ""

        normalized = unicodedata.normalize(
            "NFKC",
            str(value),
        )

        normalized = (
            CONTROL_CHARACTER_PATTERN.sub(
                "",
                normalized,
            )
        ).strip()

        if (
            len(normalized) >= 2
            and normalized[0]
            == normalized[-1]
            and normalized[0]
            in {'"', "'"}
        ):
            normalized = (
                normalized[1:-1].strip()
            )

        if normalized.startswith("#"):
            return ""

        return normalized

    @staticmethod
    def _normalize_line(
        value: str,
    ) -> str:
        normalized = unicodedata.normalize(
            "NFKC",
            value,
        )

        normalized = (
            CONTROL_CHARACTER_PATTERN.sub(
                "",
                normalized,
            )
        )

        return normalized.strip()

    @staticmethod
    def _normalize_directive(
        value: str,
    ) -> str:
        normalized = unicodedata.normalize(
            "NFKC",
            value,
        )

        normalized = (
            CONTROL_CHARACTER_PATTERN.sub(
                "",
                normalized,
            )
        )

        return normalized.strip()