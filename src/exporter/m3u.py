from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable


class M3UExporter:
    """
    Esporta i canali in formato M3U e normalizza le categorie
    per renderle facilmente navigabili nelle app IPTV.

    La classificazione non modifica nome, URL o metadati del canale:
    aggiorna solamente il campo group-title dell'output.
    """

    ORDER = (
        "tvg-id",
        "tvg-name",
        "tvg-logo",
        "group-title",
    )

    CATEGORY_ORDER = {
        "RAI": 10,
        "MEDIASET": 20,
        "DISCOVERY": 30,
        "SKY": 40,
        "PLUTO TV": 50,
        "NEWS": 60,
        "SPORT": 70,
        "FILM": 80,
        "SERIE TV": 90,
        "DOCUMENTARI E LIFESTYLE": 100,
        "BAMBINI": 110,
        "MUSICA": 120,
        "REGIONALI E LOCALI": 130,
        "RADIO E VISUAL RADIO": 140,
        "RELIGIONE": 150,
        "INTRATTENIMENTO": 160,
        "ALTRO": 999,
    }

    MEDIASET_NAMES = (
        "canale 5",
        "italia 1",
        "rete 4",
        "20 mediaset",
        "mediaset 20",
        "iris",
        "la5",
        "cine34",
        "focus",
        "top crime",
        "mediaset extra",
        "tgcom24",
        "tgcom 24",
        "boing",
        "cartoonito",
        "italia 2",
        "mediaset italia 2",
    )

    DISCOVERY_NAMES = (
        "dmax",
        "nove",
        "real time",
        "giallo",
        "food network",
        "motor trend",
        "hgtv",
        "k2",
        "frisbee",
        "warner tv",
        "discovery channel",
        "discovery science",
        "animal planet",
        "eurosport",
    )

    SKY_NAMES = (
        "tv8",
        "cielo",
        "sky tg24",
        "sky arte",
        "sky uno",
        "sky sport",
        "sky cinema",
        "sky nature",
        "sky documentari",
    )

    GENERIC_GROUP_MAP = (
        (
            "NEWS",
            (
                "news",
                "notizie",
                "informazione",
                "information",
                "tg ",
                " tg",
                "telegiornale",
            ),
        ),
        (
            "SPORT",
            (
                "sport",
                "calcio",
                "football",
                "basket",
                "tennis",
                "motorsport",
                "racing",
            ),
        ),
        (
            "BAMBINI",
            (
                "kids",
                "children",
                "cartoon",
                "animation",
                "bambini",
                "ragazzi",
            ),
        ),
        (
            "FILM",
            (
                "movies",
                "movie",
                "cinema",
                "film",
            ),
        ),
        (
            "SERIE TV",
            (
                "series",
                "serie",
                "fiction",
                "soap",
                "telenovela",
            ),
        ),
        (
            "DOCUMENTARI E LIFESTYLE",
            (
                "documentary",
                "documentaries",
                "documentari",
                "science",
                "scienza",
                "nature",
                "natura",
                "travel",
                "viaggi",
                "cooking",
                "food",
                "lifestyle",
                "factual",
                "cultura",
                "education",
            ),
        ),
        (
            "MUSICA",
            (
                "music",
                "musica",
                "concert",
                "radio music",
            ),
        ),
        (
            "REGIONALI E LOCALI",
            (
                "regional",
                "regionale",
                "local",
                "locale",
                "tgr",
            ),
        ),
        (
            "RELIGIONE",
            (
                "religion",
                "religione",
                "religious",
                "catholic",
                "chiesa",
                "cristian",
            ),
        ),
        (
            "RADIO E VISUAL RADIO",
            (
                "radio",
                "visual radio",
            ),
        ),
        (
            "INTRATTENIMENTO",
            (
                "entertainment",
                "intrattenimento",
                "general",
                "generali",
                "varieta",
                "comedy",
                "reality",
            ),
        ),
    )

    def render(
        self,
        channels: Iterable[object],
    ) -> str:
        normalized_channels = sorted(
            list(channels),
            key=self._channel_sort_key,
        )

        lines = ["#EXTM3U"]

        for channel in normalized_channels:
            attributes = dict(
                getattr(
                    channel,
                    "attributes",
                    {},
                )
                or {}
            )

            tvg_id = self._safe_text(
                getattr(
                    channel,
                    "tvg_id",
                    "",
                )
            )
            tvg_name = self._safe_text(
                getattr(
                    channel,
                    "tvg_name",
                    "",
                )
            )
            logo = self._safe_text(
                getattr(
                    channel,
                    "logo",
                    "",
                )
            )

            category = self.category_for(
                channel
            )

            if tvg_id:
                attributes["tvg-id"] = tvg_id

            if tvg_name:
                attributes["tvg-name"] = (
                    tvg_name
                )

            if logo:
                attributes["tvg-logo"] = logo

            attributes[
                "group-title"
            ] = category

            keys = [
                key
                for key in self.ORDER
                if key in attributes
            ] + sorted(
                key
                for key in attributes
                if key not in self.ORDER
            )

            rendered_attributes = " ".join(
                (
                    f'{key}="'
                    f'{self._escape_attribute(attributes[key])}'
                    f'"'
                )
                for key in keys
            )

            name = self._safe_text(
                getattr(
                    channel,
                    "name",
                    "",
                )
            )

            lines.append(
                (
                    "#EXTINF:-1"
                    f'{(" " + rendered_attributes) if rendered_attributes else ""}'
                    f",{name}"
                )
            )

            extra_directives = getattr(
                channel,
                "extra_directives",
                (),
            ) or ()

            lines.extend(
                self._safe_text(directive)
                for directive in extra_directives
                if self._safe_text(directive)
            )

            stream_url = self._safe_text(
                getattr(
                    channel,
                    "stream_url",
                    "",
                )
            )

            lines.append(stream_url)

        return "\n".join(lines) + "\n"

    def write(
        self,
        path: Path,
        channels: Iterable[object],
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            self.render(channels),
            encoding="utf-8",
        )

    @classmethod
    def category_for(
        cls,
        channel: object,
    ) -> str:
        name = cls._normalize_text(
            getattr(
                channel,
                "name",
                "",
            )
        )

        source_id = cls._normalize_text(
            getattr(
                channel,
                "source_id",
                "",
            )
        )

        original_group = cls._normalize_text(
            getattr(
                channel,
                "group",
                "",
            )
        )

        if cls._is_rai(name):
            return "RAI"

        if cls._matches_name(
            name,
            cls.MEDIASET_NAMES,
        ):
            return "MEDIASET"

        if cls._matches_name(
            name,
            cls.DISCOVERY_NAMES,
        ):
            return "DISCOVERY"

        if cls._matches_name(
            name,
            cls.SKY_NAMES,
        ):
            return "SKY"

        if (
            source_id == "pluto it"
            or source_id.startswith(
                "pluto "
            )
            or name.startswith(
                "pluto tv"
            )
        ):
            return "PLUTO TV"

        searchable_text = (
            f" {name} {original_group} "
        )

        for category, keywords in (
            cls.GENERIC_GROUP_MAP
        ):
            if any(
                keyword in searchable_text
                for keyword in keywords
            ):
                return category

        return "ALTRO"

    @classmethod
    def _channel_sort_key(
        cls,
        channel: object,
    ) -> tuple[int, str, str]:
        category = cls.category_for(
            channel
        )

        normalized_name = (
            cls._normalize_text(
                getattr(
                    channel,
                    "name",
                    "",
                )
            )
        )

        stream_url = cls._safe_text(
            getattr(
                channel,
                "stream_url",
                "",
            )
        )

        return (
            cls.CATEGORY_ORDER.get(
                category,
                cls.CATEGORY_ORDER[
                    "ALTRO"
                ],
            ),
            normalized_name,
            stream_url,
        )

    @classmethod
    def _is_rai(
        cls,
        normalized_name: str,
    ) -> bool:
        return bool(
            re.match(
                r"^rai(?:\s|[0-9]|$)",
                normalized_name,
            )
        )

    @classmethod
    def _matches_name(
        cls,
        normalized_name: str,
        candidates: tuple[str, ...],
    ) -> bool:
        for candidate in candidates:
            if (
                normalized_name == candidate
                or normalized_name.startswith(
                    f"{candidate} "
                )
            ):
                return True

        return False

    @staticmethod
    def _normalize_text(
        value: object,
    ) -> str:
        text = unicodedata.normalize(
            "NFKD",
            str(value or ""),
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(
                character
            )
        )

        text = text.casefold()
        text = text.replace("&", " e ")

        text = re.sub(
            r"[\(\[].*?[\)\]]",
            " ",
            text,
        )

        text = re.sub(
            r"[^a-z0-9]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        quality_suffixes = (
            "4k",
            "uhd",
            "fhd",
            "full hd",
            "hd",
            "sd",
            "1080p",
            "720p",
            "576p",
            "480p",
        )

        changed = True

        while changed:
            changed = False

            for suffix in quality_suffixes:
                if text.endswith(
                    f" {suffix}"
                ):
                    text = text[
                        : -len(suffix)
                    ].strip()
                    changed = True
                    break

        return text

    @staticmethod
    def _safe_text(
        value: object,
    ) -> str:
        return str(
            value
            if value is not None
            else ""
        ).strip()

    @classmethod
    def _escape_attribute(
        cls,
        value: object,
    ) -> str:
        return cls._safe_text(
            value
        ).replace(
            '"',
            "'",
        )
