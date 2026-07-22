from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from src.health.checker import HealthResult, StreamHealthChecker
from src.models.channel import Channel


@dataclass(frozen=True, slots=True)
class PlutoPlaybackResult:
    checked_channels: tuple[Channel, ...]
    health_results: tuple[HealthResult, ...]
    samsung_channels: tuple[Channel, ...]
    rejected_channels: tuple[Channel, ...]

    @property
    def checked(self) -> int:
        return len(self.health_results)

    @property
    def accepted(self) -> int:
        return len(self.samsung_channels)

    @property
    def rejected(self) -> int:
        return len(self.rejected_channels)


class PlutoPlaybackEngine:
    """Verifica soltanto i flussi Pluto e crea l'output Samsung/Tizen.

    Il controllo globale può restare disattivato: questo motore limita il
    lavoro ai canali Pluto, controlla manifest e primo segmento HLS tramite
    ``StreamHealthChecker`` e conserva soltanto i flussi con punteggio minimo.
    I canali non Pluto non vengono toccati.
    """

    PLUTO_HOST_MARKERS = (
        "pluto.tv",
        "plutotv.net",
        "jmp2.uk",
    )

    def __init__(
        self,
        checker: StreamHealthChecker,
        *,
        minimum_score: float = 70.0,
        accept_reachable: bool = True,
    ) -> None:
        if not 0 <= minimum_score <= 100:
            raise ValueError("minimum_score deve essere tra 0 e 100")

        self.checker = checker
        self.minimum_score = float(minimum_score)
        self.accept_reachable = bool(accept_reachable)

    @classmethod
    def is_pluto_channel(cls, channel: Channel) -> bool:
        source_id = channel.source_id.casefold()
        group = channel.group.casefold()
        name = channel.name.casefold()
        host = urlsplit(channel.stream_url).netloc.casefold()

        return (
            "pluto" in source_id
            or "pluto" in group
            or name.startswith("pluto ")
            or any(marker in host for marker in cls.PLUTO_HOST_MARKERS)
        )

    def verify(self, channels: Iterable[Channel]) -> PlutoPlaybackResult:
        unique: dict[str, Channel] = {}

        for channel in channels:
            if not self.is_pluto_channel(channel):
                continue
            unique.setdefault(channel.stream_url.strip(), channel)

        checked_channels = tuple(unique.values())
        if not checked_channels:
            return PlutoPlaybackResult((), (), (), ())

        health_results = tuple(self.checker.check_many(checked_channels))
        result_by_url = {
            result.stream_url.strip(): result
            for result in health_results
        }

        accepted: list[Channel] = []
        rejected: list[Channel] = []

        for channel in checked_channels:
            health = result_by_url.get(channel.stream_url.strip())
            if health is not None and self._is_accepted(health):
                accepted.append(channel)
            else:
                rejected.append(channel)

        return PlutoPlaybackResult(
            checked_channels=checked_channels,
            health_results=health_results,
            samsung_channels=tuple(accepted),
            rejected_channels=tuple(rejected),
        )

    def build_samsung_playlist_channels(
        self,
        all_channels: Iterable[Channel],
        result: PlutoPlaybackResult,
    ) -> list[Channel]:
        accepted_urls = {
            channel.stream_url.strip()
            for channel in result.samsung_channels
        }

        output: list[Channel] = []
        for channel in all_channels:
            if not self.is_pluto_channel(channel):
                output.append(channel)
            elif channel.stream_url.strip() in accepted_urls:
                output.append(channel)

        return output

    def write_report(self, path: Path, result: PlutoPlaybackResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        health_by_url = {
            item.stream_url.strip(): item
            for item in result.health_results
        }

        channels = []
        for channel in result.checked_channels:
            health = health_by_url.get(channel.stream_url.strip())
            channels.append(
                {
                    "name": channel.name,
                    "stream_url": channel.stream_url,
                    "source_id": channel.source_id,
                    "accepted_for_samsung": (
                        channel.stream_url.strip()
                        in {
                            item.stream_url.strip()
                            for item in result.samsung_channels
                        }
                    ),
                    "health": health.to_dict() if health is not None else None,
                }
            )

        payload = {
            "project": "Italia TV Hub",
            "engine": "Pluto Playback Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "minimum_score": self.minimum_score,
            "accept_reachable": self.accept_reachable,
            "checked": result.checked,
            "accepted": result.accepted,
            "rejected": result.rejected,
            "channels": channels,
        }

        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _is_accepted(self, result: HealthResult) -> bool:
        accepted_statuses = {"online"}
        if self.accept_reachable:
            accepted_statuses.add("reachable")

        return (
            result.status in accepted_statuses
            and float(result.health_score) >= self.minimum_score
        )
