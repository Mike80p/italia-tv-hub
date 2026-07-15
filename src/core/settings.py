from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def load(cls, path: Path) -> "Settings":
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        settings = cls(
            output_file=str(
                data.get(
                    "output_file",
                    "output/playlist.m3u",
                )
            ),
            report_file=str(
                data.get(
                    "report_file",
                    "output/report.json",
                )
            ),
            health_file=str(
                data.get(
                    "health_file",
                    "output/health.json",
                )
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
            user_agent=str(
                data.get(
                    "user_agent",
                    "Italia-TV-Hub/0.4",
                )
            ),
            health_enabled=bool(
                data.get(
                    "health_enabled",
                    False,
                )
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
            publish_only_online=bool(
                data.get(
                    "publish_only_online",
                    False,
                )
            ),
        )

        if settings.request_timeout_seconds <= 0:
            raise ValueError(
                "request_timeout_seconds deve essere maggiore di zero"
            )

        if settings.retry_count < 0:
            raise ValueError(
                "retry_count non può essere negativo"
            )

        if settings.health_timeout_seconds <= 0:
            raise ValueError(
                "health_timeout_seconds deve essere maggiore di zero"
            )

        if settings.health_max_workers <= 0:
            raise ValueError(
                "health_max_workers deve essere maggiore di zero"
            )

        return settings