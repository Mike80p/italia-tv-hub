from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass(slots=True, frozen=True)
class Settings:
    output_file: str
    report_file: str
    health_file: str
    request_timeout_seconds: int
    retry_count: int
    user_agent: str
    health_enabled: bool
    health_timeout_seconds: int
    health_max_workers: int
    publish_only_online: bool

    # Controllo Pluto dedicato e playlist Samsung/Tizen.
    pluto_playback_enabled: bool = True
    pluto_minimum_score: float = 70.0
    pluto_timeout_seconds: int = 8
    pluto_max_workers: int = 16
    samsung_output_file: str = "output/playlist_samsung.m3u"
    pluto_report_file: str = "output/pluto-report.json"

    # Impostazioni EPG.
    #
    # I valori predefiniti mantengono compatibilità con i test e con
    # gli eventuali componenti che costruiscono Settings direttamente
    # usando soltanto i campi storici.
    epg_enabled: bool = False
    epg_file: str = "output/epg.xml"
    epg_report_file: str = "output/epg-report.json"
    epg_public_url: str = ""
    epg_timeout_seconds: int = 30
    epg_sources: tuple[str, ...] = ()

    @classmethod
    def load(
        cls,
        path: Path,
    ) -> "Settings":
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Il file settings deve contenere "
                "un oggetto JSON"
            )

        settings = cls(
            output_file=cls._read_text(
                data,
                "output_file",
                "output/playlist.m3u",
            ),
            report_file=cls._read_text(
                data,
                "report_file",
                "output/report.json",
            ),
            health_file=cls._read_text(
                data,
                "health_file",
                "output/health.json",
            ),
            request_timeout_seconds=int(
                data.get(
                    "request_timeout_seconds",
                    20,
                )
            ),
            retry_count=int(
                data.get(
                    "retry_count",
                    2,
                )
            ),
            user_agent=cls._read_text(
                data,
                "user_agent",
                "Italia-TV-Hub/0.4",
            ),
            health_enabled=cls._read_bool(
                data,
                "health_enabled",
                False,
            ),
            health_timeout_seconds=int(
                data.get(
                    "health_timeout_seconds",
                    10,
                )
            ),
            health_max_workers=int(
                data.get(
                    "health_max_workers",
                    12,
                )
            ),
            publish_only_online=cls._read_bool(
                data,
                "publish_only_online",
                False,
            ),
            pluto_playback_enabled=cls._read_bool(
                data,
                "pluto_playback_enabled",
                True,
            ),
            pluto_minimum_score=float(
                data.get("pluto_minimum_score", 70)
            ),
            pluto_timeout_seconds=int(
                data.get("pluto_timeout_seconds", 8)
            ),
            pluto_max_workers=int(
                data.get("pluto_max_workers", 16)
            ),
            samsung_output_file=cls._read_text(
                data,
                "samsung_output_file",
                "output/playlist_samsung.m3u",
            ),
            pluto_report_file=cls._read_text(
                data,
                "pluto_report_file",
                "output/pluto-report.json",
            ),
            epg_enabled=cls._read_bool(
                data,
                "epg_enabled",
                False,
            ),
            epg_file=cls._read_text(
                data,
                "epg_file",
                "output/epg.xml",
            ),
            epg_report_file=cls._read_text(
                data,
                "epg_report_file",
                "output/epg-report.json",
            ),
            epg_public_url=cls._read_text(
                data,
                "epg_public_url",
                "",
            ),
            epg_timeout_seconds=int(
                data.get(
                    "epg_timeout_seconds",
                    30,
                )
            ),
            epg_sources=cls._read_sources(
                data.get(
                    "epg_sources",
                    (),
                )
            ),
        )

        settings._validate()

        return settings

    def _validate(
        self,
    ) -> None:
        required_paths = {
            "output_file": self.output_file,
            "report_file": self.report_file,
            "health_file": self.health_file,
            "samsung_output_file": self.samsung_output_file,
            "pluto_report_file": self.pluto_report_file,
            "epg_file": self.epg_file,
            "epg_report_file": (
                self.epg_report_file
            ),
        }

        for field_name, value in (
            required_paths.items()
        ):
            if not value:
                raise ValueError(
                    f"{field_name} non può "
                    "essere vuoto"
                )

        if (
            self.request_timeout_seconds
            <= 0
        ):
            raise ValueError(
                "request_timeout_seconds deve "
                "essere maggiore di zero"
            )

        if self.retry_count < 0:
            raise ValueError(
                "retry_count non può essere "
                "negativo"
            )

        if (
            self.health_timeout_seconds
            <= 0
        ):
            raise ValueError(
                "health_timeout_seconds deve "
                "essere maggiore di zero"
            )

        if self.health_max_workers <= 0:
            raise ValueError(
                "health_max_workers deve "
                "essere maggiore di zero"
            )

        if not 0 <= self.pluto_minimum_score <= 100:
            raise ValueError(
                "pluto_minimum_score deve essere tra 0 e 100"
            )

        if self.pluto_timeout_seconds <= 0:
            raise ValueError(
                "pluto_timeout_seconds deve essere maggiore di zero"
            )

        if self.pluto_max_workers <= 0:
            raise ValueError(
                "pluto_max_workers deve essere maggiore di zero"
            )

        if self.epg_timeout_seconds <= 0:
            raise ValueError(
                "epg_timeout_seconds deve "
                "essere maggiore di zero"
            )

        if self.epg_enabled:
            if not self.epg_public_url:
                raise ValueError(
                    "epg_public_url è "
                    "obbligatorio quando "
                    "epg_enabled è true"
                )

            parsed_url = urlsplit(
                self.epg_public_url
            )

            if (
                parsed_url.scheme
                not in {
                    "http",
                    "https",
                }
                or not parsed_url.netloc
            ):
                raise ValueError(
                    "epg_public_url deve essere "
                    "un URL HTTP o HTTPS valido"
                )

    @staticmethod
    def _read_text(
        data: dict[str, Any],
        key: str,
        default: str,
    ) -> str:
        value = data.get(
            key,
            default,
        )

        if value is None:
            return ""

        return str(
            value
        ).strip()

    @staticmethod
    def _read_bool(
        data: dict[str, Any],
        key: str,
        default: bool,
    ) -> bool:
        value = data.get(
            key,
            default,
        )

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            int,
        ):
            if value in {
                0,
                1,
            }:
                return bool(
                    value
                )

        if isinstance(
            value,
            str,
        ):
            normalized = (
                value
                .strip()
                .casefold()
            )

            if normalized in {
                "true",
                "1",
                "yes",
                "on",
                "si",
                "sì",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "off",
            }:
                return False

        raise ValueError(
            f"{key} deve essere booleano"
        )

    @staticmethod
    def _read_sources(
        value: Any,
    ) -> tuple[str, ...]:
        if value is None:
            return ()

        if isinstance(
            value,
            str,
        ):
            raw_sources = [
                value
            ]

        elif isinstance(
            value,
            (
                list,
                tuple,
            ),
        ):
            raw_sources = list(
                value
            )

        else:
            raise ValueError(
                "epg_sources deve essere "
                "una lista di stringhe"
            )

        sources: list[
            str
        ] = []

        seen: set[
            str
        ] = set()

        for raw_source in raw_sources:
            source = str(
                raw_source
            ).strip()

            if not source:
                continue

            if source in seen:
                continue

            seen.add(
                source
            )

            sources.append(
                source
            )

        return tuple(
            sources
        )
