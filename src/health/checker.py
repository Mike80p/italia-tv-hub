from __future__ import annotations

import concurrent.futures
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Iterable

from src.models.channel import Channel


@dataclass(slots=True)
class HealthResult:
    name: str
    stream_url: str
    source_id: str
    status: str
    http_status: int | None
    response_ms: int | None
    content_type: str
    final_url: str
    error: str

    # Campi Quality Engine.
    # I valori predefiniti mantengono compatibile il vecchio
    # costruttore di HealthResult.
    health_score: int = 0
    classification_reason: str = ""
    bytes_read: int = 0
    redirected: bool = False
    error_type: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HealthStats:
    input_channels: int
    checked: int
    online: int
    reachable: int
    offline: int
    redirects: int
    errors: int
    average_score: float
    average_response_ms: float
    min_score: int
    max_score: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HealthBatchResult:
    results: tuple[HealthResult, ...]
    stats: HealthStats

    def to_dict(self) -> dict[str, object]:
        return {
            "stats": self.stats.to_dict(),
            "results": [
                result.to_dict()
                for result in self.results
            ],
        }


class StreamHealthChecker:
    MEDIA_CONTENT_TYPES = (
        "mpegurl",
        "video/",
        "audio/",
        "octet-stream",
        "mp2t",
    )

    def __init__(
        self,
        timeout_seconds: int = 10,
        max_workers: int = 12,
        user_agent: str = "Italia-TV-Hub/0.9",
        read_bytes: int = 2048,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds deve essere "
                "maggiore di zero"
            )

        if max_workers <= 0:
            raise ValueError(
                "max_workers deve essere "
                "maggiore di zero"
            )

        if read_bytes <= 0:
            raise ValueError(
                "read_bytes deve essere "
                "maggiore di zero"
            )

        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self.user_agent = user_agent
        self.read_bytes = read_bytes

    def check_many(
        self,
        channels: Iterable[Channel],
    ) -> list[HealthResult]:
        """
        Interfaccia compatibile con il checker precedente.

        Restituisce la sola lista dei risultati, mantenendo
        l'ordine dei canali ricevuti.
        """

        detailed = self.check_many_detailed(
            channels
        )

        return list(detailed.results)

    def check_many_detailed(
        self,
        channels: Iterable[Channel],
    ) -> HealthBatchResult:
        """
        Controlla più canali in parallelo e produce anche
        statistiche aggregate del batch.
        """

        channel_list = list(channels)

        if not channel_list:
            return HealthBatchResult(
                results=(),
                stats=self._empty_stats(),
            )

        ordered_results: list[
            HealthResult | None
        ] = [
            None
            for _ in channel_list
        ]

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            futures = {
                executor.submit(
                    self.check,
                    channel,
                ): index
                for index, channel
                in enumerate(channel_list)
            }

            for future in (
                concurrent.futures.as_completed(
                    futures
                )
            ):
                index = futures[future]
                ordered_results[index] = (
                    future.result()
                )

        results = tuple(
            result
            for result in ordered_results
            if result is not None
        )

        return HealthBatchResult(
            results=results,
            stats=self._build_stats(
                input_channels=len(
                    channel_list
                ),
                results=results,
            ),
        )

    def check(
        self,
        channel: Channel,
    ) -> HealthResult:
        started = time.perf_counter()

        request = urllib.request.Request(
            channel.stream_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": (
                    "application/vnd.apple.mpegurl,"
                    "application/x-mpegURL,"
                    "video/*,"
                    "audio/*,"
                    "application/octet-stream,"
                    "*/*"
                ),
                "Range": (
                    f"bytes=0-{self.read_bytes - 1}"
                ),
                "Cache-Control": "no-cache",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                data = response.read(
                    self.read_bytes
                )

                response_ms = self._elapsed_ms(
                    started
                )

                http_status = response.getcode()

                content_type = (
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                    or ""
                )

                final_url = (
                    response.geturl()
                    or channel.stream_url
                )

                (
                    status,
                    classification_reason,
                    base_score,
                ) = self._assess_response(
                    http_status=http_status,
                    content_type=content_type,
                    data=data,
                )

                redirected = (
                    final_url
                    != channel.stream_url
                )

                health_score = (
                    self._calculate_score(
                        status=status,
                        base_score=base_score,
                        response_ms=response_ms,
                        redirected=redirected,
                    )
                )

                return HealthResult(
                    name=channel.name,
                    stream_url=(
                        channel.stream_url
                    ),
                    source_id=channel.source_id,
                    status=status,
                    http_status=http_status,
                    response_ms=response_ms,
                    content_type=content_type,
                    final_url=final_url,
                    error="",
                    health_score=health_score,
                    classification_reason=(
                        classification_reason
                    ),
                    bytes_read=len(data),
                    redirected=redirected,
                    error_type="",
                )

        except urllib.error.HTTPError as exc:
            return self._error_result(
                channel=channel,
                started=started,
                http_status=exc.code,
                error=(
                    "HTTPError "
                    f"{exc.code}: {exc.reason}"
                ),
                error_type="HTTPError",
                classification_reason=(
                    "http_error"
                ),
                final_url=(
                    exc.geturl()
                    if hasattr(
                        exc,
                        "geturl",
                    )
                    else channel.stream_url
                ),
            )

        except urllib.error.URLError as exc:
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error=(
                    f"URLError: {exc.reason}"
                ),
                error_type="URLError",
                classification_reason=(
                    "network_error"
                ),
            )

        except (
            TimeoutError,
            socket.timeout,
        ):
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error="Timeout",
                error_type="TimeoutError",
                classification_reason="timeout",
            )

        except Exception as exc:
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                error_type=type(exc).__name__,
                classification_reason=(
                    "unexpected_error"
                ),
            )

    @classmethod
    def _assess_response(
        cls,
        http_status: int | None,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str, int]:
        if (
            http_status is None
            or not 200 <= http_status < 400
        ):
            return (
                "offline",
                "invalid_http_status",
                0,
            )

        lowered_type = (
            content_type.casefold()
        )

        text = data.decode(
            "utf-8",
            errors="ignore",
        )

        if "#EXTM3U" in text.upper():
            return (
                "online",
                "hls_signature",
                100,
            )

        if any(
            value in lowered_type
            for value in (
                cls.MEDIA_CONTENT_TYPES
            )
        ):
            return (
                "online",
                "media_content_type",
                90,
            )

        if data:
            return (
                "reachable",
                "payload_reachable",
                50,
            )

        return (
            "offline",
            "empty_payload",
            0,
        )

    @classmethod
    def _classify_response(
        cls,
        http_status: int,
        content_type: str,
        data: bytes,
    ) -> str:
        """
        Metodo mantenuto per compatibilità con il vecchio
        Health Engine e con i relativi test.
        """

        status, _, _ = cls._assess_response(
            http_status=http_status,
            content_type=content_type,
            data=data,
        )

        return status

    @staticmethod
    def _calculate_score(
        status: str,
        base_score: int,
        response_ms: int | None,
        redirected: bool,
    ) -> int:
        if (
            status == "offline"
            or base_score <= 0
        ):
            return 0

        latency_penalty = 0

        if response_ms is not None:
            if response_ms > 5000:
                latency_penalty = 25
            elif response_ms > 2500:
                latency_penalty = 18
            elif response_ms > 1500:
                latency_penalty = 12
            elif response_ms > 750:
                latency_penalty = 7
            elif response_ms > 250:
                latency_penalty = 3

        redirect_penalty = (
            2
            if redirected
            else 0
        )

        score = (
            base_score
            - latency_penalty
            - redirect_penalty
        )

        return max(
            1,
            min(
                100,
                score,
            ),
        )

    @staticmethod
    def _error_result(
        channel: Channel,
        started: float,
        http_status: int | None,
        error: str,
        error_type: str = "",
        classification_reason: str = (
            "request_error"
        ),
        final_url: str | None = None,
    ) -> HealthResult:
        response_ms = (
            StreamHealthChecker._elapsed_ms(
                started
            )
        )

        resolved_final_url = (
            final_url
            or channel.stream_url
        )

        return HealthResult(
            name=channel.name,
            stream_url=channel.stream_url,
            source_id=channel.source_id,
            status="offline",
            http_status=http_status,
            response_ms=response_ms,
            content_type="",
            final_url=resolved_final_url,
            error=error,
            health_score=0,
            classification_reason=(
                classification_reason
            ),
            bytes_read=0,
            redirected=(
                resolved_final_url
                != channel.stream_url
            ),
            error_type=error_type,
        )

    @staticmethod
    def _build_stats(
        input_channels: int,
        results: tuple[
            HealthResult,
            ...,
        ],
    ) -> HealthStats:
        if not results:
            return HealthStats(
                input_channels=(
                    input_channels
                ),
                checked=0,
                online=0,
                reachable=0,
                offline=0,
                redirects=0,
                errors=0,
                average_score=0.0,
                average_response_ms=0.0,
                min_score=0,
                max_score=0,
            )

        scores = [
            result.health_score
            for result in results
        ]

        response_times = [
            result.response_ms
            for result in results
            if result.response_ms is not None
        ]

        average_response_ms = (
            sum(response_times)
            / len(response_times)
            if response_times
            else 0.0
        )

        return HealthStats(
            input_channels=input_channels,
            checked=len(results),
            online=sum(
                1
                for result in results
                if result.status == "online"
            ),
            reachable=sum(
                1
                for result in results
                if result.status
                == "reachable"
            ),
            offline=sum(
                1
                for result in results
                if result.status == "offline"
            ),
            redirects=sum(
                1
                for result in results
                if result.redirected
            ),
            errors=sum(
                1
                for result in results
                if bool(result.error)
                or bool(result.error_type)
            ),
            average_score=(
                sum(scores)
                / len(scores)
            ),
            average_response_ms=(
                average_response_ms
            ),
            min_score=min(scores),
            max_score=max(scores),
        )

    @staticmethod
    def _empty_stats() -> HealthStats:
        return HealthStats(
            input_channels=0,
            checked=0,
            online=0,
            reachable=0,
            offline=0,
            redirects=0,
            errors=0,
            average_score=0.0,
            average_response_ms=0.0,
            min_score=0,
            max_score=0,
        )

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> int:
        return int(
            (
                time.perf_counter()
                - started
            )
            * 1000
        )
