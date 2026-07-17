from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any


SleepFunction = Callable[[float], None]


@dataclass(
    frozen=True,
    slots=True,
)
class EPGDownloadAttempt:
    attempt_number: int
    status: str
    elapsed_ms: int
    bytes_read: int
    http_status: int | None
    final_url: str
    content_type: str
    retryable: bool
    error: str = ""

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
class EPGDownloadResult:
    source_url: str
    final_url: str
    data: bytes
    content_type: str
    compressed: bool
    attempt_count: int
    total_elapsed_ms: int
    bytes_downloaded: int
    http_status: int
    attempts: tuple[
        EPGDownloadAttempt,
        ...,
    ]

    def to_dict(
        self,
        *,
        include_data: bool = False,
    ) -> dict[str, object]:
        payload: dict[
            str,
            object,
        ] = {
            "source_url": self.source_url,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "compressed": self.compressed,
            "attempt_count": (
                self.attempt_count
            ),
            "total_elapsed_ms": (
                self.total_elapsed_ms
            ),
            "bytes_downloaded": (
                self.bytes_downloaded
            ),
            "http_status": (
                self.http_status
            ),
            "attempts": [
                attempt.to_dict()
                for attempt
                in self.attempts
            ],
        }

        if include_data:
            payload["data"] = self.data

        return payload


class EPGDownloadError(
    RuntimeError
):
    def __init__(
        self,
        message: str,
        *,
        source_url: str,
        attempts: tuple[
            EPGDownloadAttempt,
            ...,
        ] = (),
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message
        )

        self.source_url = (
            source_url
        )

        self.attempts = attempts
        self.status_code = (
            status_code
        )

        self.retryable = (
            retryable
        )

    @property
    def attempt_count(
        self,
    ) -> int:
        return len(
            self.attempts
        )


class EPGDownloader:
    """
    Scarica guide XMLTV pubbliche.

    Caratteristiche:

    - timeout configurabile;
    - retry per errori temporanei;
    - redirect gestiti da urllib;
    - limite massimo sui byte scaricati;
    - diagnostica per ogni tentativo;
    - nessuna decompressione: i dati GZIP vengono passati al parser.
    """

    RETRYABLE_HTTP_STATUS = {
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    }

    GZIP_CONTENT_TYPES = {
        "application/gzip",
        "application/x-gzip",
        "application/gzip-compressed",
    }

    GZIP_MAGIC = b"\x1f\x8b"

    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        retry_count: int = 2,
        user_agent: str = (
            "Italia-TV-Hub/EPG"
        ),
        max_download_bytes: int = (
            50 * 1024 * 1024
        ),
        retry_backoff_seconds: float = 0.5,
        opener: Any | None = None,
        sleep_function: (
            SleepFunction | None
        ) = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds deve essere "
                "maggiore di zero"
            )

        if retry_count < 0:
            raise ValueError(
                "retry_count non può essere "
                "negativo"
            )

        if max_download_bytes <= 0:
            raise ValueError(
                "max_download_bytes deve essere "
                "maggiore di zero"
            )

        if retry_backoff_seconds < 0:
            raise ValueError(
                "retry_backoff_seconds non può "
                "essere negativo"
            )

        self.timeout_seconds = int(
            timeout_seconds
        )

        self.retry_count = int(
            retry_count
        )

        self.user_agent = (
            str(user_agent).strip()
            or "Italia-TV-Hub/EPG"
        )

        self.max_download_bytes = int(
            max_download_bytes
        )

        self.retry_backoff_seconds = float(
            retry_backoff_seconds
        )

        self.opener = (
            opener
            if opener is not None
            else urllib.request
        )

        self.sleep_function = (
            sleep_function
            if sleep_function is not None
            else time.sleep
        )

    def fetch(
        self,
        source_url: str,
    ) -> EPGDownloadResult:
        normalized_url = (
            self._validate_url(
                source_url
            )
        )

        attempts: list[
            EPGDownloadAttempt
        ] = []

        max_attempts = (
            self.retry_count + 1
        )

        last_status_code: (
            int | None
        ) = None

        last_retryable = False
        last_message = (
            "Download EPG non riuscito"
        )

        for attempt_number in range(
            1,
            max_attempts + 1,
        ):
            started = (
                time.monotonic()
            )

            try:
                result = (
                    self._fetch_once(
                        normalized_url,
                        attempt_number=(
                            attempt_number
                        ),
                    )
                )

                elapsed_ms = max(
                    0,
                    int(
                        (
                            time.monotonic()
                            - started
                        )
                        * 1000
                    ),
                )

                success_attempt = (
                    EPGDownloadAttempt(
                        attempt_number=(
                            attempt_number
                        ),
                        status="ok",
                        elapsed_ms=(
                            elapsed_ms
                        ),
                        bytes_read=(
                            len(result["data"])
                        ),
                        http_status=(
                            result[
                                "http_status"
                            ]
                        ),
                        final_url=(
                            result[
                                "final_url"
                            ]
                        ),
                        content_type=(
                            result[
                                "content_type"
                            ]
                        ),
                        retryable=False,
                    )
                )

                attempts.append(
                    success_attempt
                )

                return EPGDownloadResult(
                    source_url=(
                        normalized_url
                    ),
                    final_url=(
                        result["final_url"]
                    ),
                    data=result["data"],
                    content_type=(
                        result["content_type"]
                    ),
                    compressed=(
                        self._is_compressed(
                            data=result["data"],
                            final_url=(
                                result[
                                    "final_url"
                                ]
                            ),
                            content_type=(
                                result[
                                    "content_type"
                                ]
                            ),
                        )
                    ),
                    attempt_count=len(
                        attempts
                    ),
                    total_elapsed_ms=sum(
                        attempt.elapsed_ms
                        for attempt
                        in attempts
                    ),
                    bytes_downloaded=len(
                        result["data"]
                    ),
                    http_status=(
                        result["http_status"]
                    ),
                    attempts=tuple(
                        attempts
                    ),
                )

            except EPGDownloadError as exc:
                elapsed_ms = max(
                    0,
                    int(
                        (
                            time.monotonic()
                            - started
                        )
                        * 1000
                    ),
                )

                last_status_code = (
                    exc.status_code
                )

                last_retryable = (
                    exc.retryable
                )

                last_message = str(
                    exc
                )

                attempts.append(
                    EPGDownloadAttempt(
                        attempt_number=(
                            attempt_number
                        ),
                        status="error",
                        elapsed_ms=(
                            elapsed_ms
                        ),
                        bytes_read=0,
                        http_status=(
                            exc.status_code
                        ),
                        final_url=(
                            normalized_url
                        ),
                        content_type="",
                        retryable=(
                            exc.retryable
                        ),
                        error=str(
                            exc
                        ),
                    )
                )

                should_retry = (
                    exc.retryable
                    and attempt_number
                    < max_attempts
                )

                if not should_retry:
                    break

                delay = (
                    self.retry_backoff_seconds
                    * attempt_number
                )

                if delay > 0:
                    self.sleep_function(
                        delay
                    )

        raise EPGDownloadError(
            last_message,
            source_url=(
                normalized_url
            ),
            attempts=tuple(
                attempts
            ),
            status_code=(
                last_status_code
            ),
            retryable=(
                last_retryable
            ),
        )

    def _fetch_once(
        self,
        source_url: str,
        *,
        attempt_number: int,
    ) -> dict[str, Any]:
        request = (
            urllib.request.Request(
                source_url,
                headers={
                    "User-Agent": (
                        self.user_agent
                    ),
                    "Accept": (
                        "application/xml,"
                        "text/xml,"
                        "application/gzip,"
                        "application/x-gzip,"
                        "application/octet-stream,"
                        "*/*"
                    ),
                    "Accept-Encoding": (
                        "identity"
                    ),
                    "Cache-Control": (
                        "no-cache"
                    ),
                },
                method="GET",
            )
        )

        try:
            response_context = (
                self.opener.urlopen(
                    request,
                    timeout=(
                        self.timeout_seconds
                    ),
                )
            )

            with response_context as response:
                http_status = int(
                    getattr(
                        response,
                        "status",
                        200,
                    )
                    or 200
                )

                final_url = str(
                    response.geturl()
                    if hasattr(
                        response,
                        "geturl",
                    )
                    else source_url
                ).strip()

                self._validate_url(
                    final_url
                )

                content_type = (
                    self._content_type(
                        response
                    )
                )

                content_length = (
                    self._content_length(
                        response
                    )
                )

                if (
                    content_length
                    is not None
                    and content_length
                    > self.max_download_bytes
                ):
                    raise EPGDownloadError(
                        "Guida EPG troppo grande "
                        "secondo Content-Length: "
                        f"{content_length} byte",
                        source_url=source_url,
                        status_code=(
                            http_status
                        ),
                        retryable=False,
                    )

                data = (
                    self._read_limited(
                        response
                    )
                )

                if not data:
                    raise EPGDownloadError(
                        "Guida EPG vuota",
                        source_url=source_url,
                        status_code=(
                            http_status
                        ),
                        retryable=False,
                    )

                return {
                    "data": data,
                    "final_url": (
                        final_url
                    ),
                    "content_type": (
                        content_type
                    ),
                    "http_status": (
                        http_status
                    ),
                    "attempt_number": (
                        attempt_number
                    ),
                }

        except urllib.error.HTTPError as exc:
            retryable = (
                int(exc.code)
                in self.RETRYABLE_HTTP_STATUS
            )

            message = (
                "Errore HTTP EPG "
                f"{exc.code}"
            )

            reason = str(
                getattr(
                    exc,
                    "reason",
                    "",
                )
            ).strip()

            if reason:
                message += (
                    f": {reason}"
                )

            raise EPGDownloadError(
                message,
                source_url=source_url,
                status_code=int(
                    exc.code
                ),
                retryable=retryable,
            ) from exc

        except urllib.error.URLError as exc:
            reason = str(
                getattr(
                    exc,
                    "reason",
                    exc,
                )
            ).strip()

            raise EPGDownloadError(
                "Errore rete EPG: "
                f"{reason}",
                source_url=source_url,
                retryable=True,
            ) from exc

        except TimeoutError as exc:
            raise EPGDownloadError(
                "Timeout download EPG",
                source_url=source_url,
                retryable=True,
            ) from exc

        except OSError as exc:
            raise EPGDownloadError(
                "Errore I/O download EPG: "
                f"{exc}",
                source_url=source_url,
                retryable=True,
            ) from exc

    def _read_limited(
        self,
        response: Any,
    ) -> bytes:
        chunks: list[
            bytes
        ] = []

        total = 0

        while True:
            remaining = (
                self.max_download_bytes
                - total
            )

            chunk = response.read(
                min(
                    1024 * 1024,
                    remaining + 1,
                )
            )

            if not chunk:
                break

            if not isinstance(
                chunk,
                (
                    bytes,
                    bytearray,
                ),
            ):
                raise EPGDownloadError(
                    "La risposta EPG non "
                    "contiene bytes",
                    source_url="",
                    retryable=False,
                )

            data = bytes(
                chunk
            )

            total += len(
                data
            )

            if (
                total
                > self.max_download_bytes
            ):
                raise EPGDownloadError(
                    "Guida EPG supera il limite "
                    f"di {self.max_download_bytes} "
                    "byte",
                    source_url="",
                    retryable=False,
                )

            chunks.append(
                data
            )

        return b"".join(
            chunks
        )

    @staticmethod
    def _content_type(
        response: Any,
    ) -> str:
        headers = getattr(
            response,
            "headers",
            None,
        )

        if headers is None:
            return ""

        if hasattr(
            headers,
            "get_content_type",
        ):
            try:
                return str(
                    headers.get_content_type()
                ).strip().casefold()
            except (
                AttributeError,
                TypeError,
            ):
                pass

        value = str(
            headers.get(
                "Content-Type",
                "",
            )
        ).strip()

        return value.split(
            ";",
            1,
        )[0].strip().casefold()

    @staticmethod
    def _content_length(
        response: Any,
    ) -> int | None:
        headers = getattr(
            response,
            "headers",
            None,
        )

        if headers is None:
            return None

        raw_value = headers.get(
            "Content-Length"
        )

        if raw_value is None:
            return None

        try:
            value = int(
                raw_value
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        return (
            value
            if value >= 0
            else None
        )

    @classmethod
    def _is_compressed(
        cls,
        *,
        data: bytes,
        final_url: str,
        content_type: str,
    ) -> bool:
        return (
            data.startswith(
                cls.GZIP_MAGIC
            )
            or content_type
            in cls.GZIP_CONTENT_TYPES
            or urllib.parse.urlsplit(
                final_url
            ).path.casefold().endswith(
                ".gz"
            )
        )

    @staticmethod
    def _validate_url(
        value: str,
    ) -> str:
        normalized = str(
            value
        ).strip()

        if not normalized:
            raise ValueError(
                "URL EPG vuoto"
            )

        try:
            parsed = (
                urllib.parse.urlsplit(
                    normalized
                )
            )
        except ValueError as exc:
            raise ValueError(
                "URL EPG non valido"
            ) from exc

        if (
            parsed.scheme.casefold()
            not in {
                "http",
                "https",
            }
            or not parsed.netloc
        ):
            raise ValueError(
                "URL EPG deve usare HTTP "
                "o HTTPS"
            )

        return normalized
