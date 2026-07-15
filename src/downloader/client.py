from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable

from src.models.source import Source


_RETRYABLE_HTTP_STATUS = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}


@dataclass(frozen=True, slots=True)
class DownloadAttempt:
    number: int
    status: str
    elapsed_ms: int
    http_status: int | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "http_status": self.http_status,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True, slots=True)
class DownloadResult:
    source_id: str
    requested_url: str
    final_url: str
    content: str
    bytes_downloaded: int
    encoding: str
    content_type: str
    http_status: int | None
    attempts: tuple[DownloadAttempt, ...]
    total_elapsed_ms: int
    is_remote: bool

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "bytes_downloaded": self.bytes_downloaded,
            "encoding": self.encoding,
            "content_type": self.content_type,
            "http_status": self.http_status,
            "attempt_count": self.attempt_count,
            "total_elapsed_ms": self.total_elapsed_ms,
            "is_remote": self.is_remote,
            "attempts": [
                attempt.to_dict()
                for attempt in self.attempts
            ],
        }


class DownloadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        source_id: str = "",
        url: str = "",
        attempts: tuple[DownloadAttempt, ...] = (),
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)

        self.source_id = source_id
        self.url = url
        self.attempts = attempts
        self.status_code = status_code
        self.retryable = retryable

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "message": str(self),
            "status_code": self.status_code,
            "retryable": self.retryable,
            "attempt_count": self.attempt_count,
            "attempts": [
                attempt.to_dict()
                for attempt in self.attempts
            ],
        }


class _ResponseTooLarge(RuntimeError):
    pass


class _EmptyResponse(RuntimeError):
    pass


class PlaylistDownloader:
    def __init__(
        self,
        project_root: Path,
        timeout: int | float,
        retries: int,
        user_agent: str,
        *,
        backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 3.0,
        max_response_bytes: int | None = 50_000_000,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0:
            raise ValueError(
                "timeout must be greater than zero"
            )

        if (
            isinstance(retries, bool)
            or not isinstance(retries, int)
        ):
            raise TypeError(
                "retries must be an integer"
            )

        if retries < 0:
            raise ValueError(
                "retries cannot be negative"
            )

        if backoff_seconds < 0:
            raise ValueError(
                "backoff_seconds cannot be negative"
            )

        if max_backoff_seconds < 0:
            raise ValueError(
                "max_backoff_seconds cannot be negative"
            )

        if (
            max_response_bytes is not None
            and max_response_bytes <= 0
        ):
            raise ValueError(
                "max_response_bytes must be "
                "greater than zero"
            )

        self.root = Path(project_root)
        self.timeout = timeout
        self.retries = retries
        self.user_agent = str(
            user_agent
        ).strip()

        self.backoff_seconds = float(
            backoff_seconds
        )

        self.max_backoff_seconds = float(
            max_backoff_seconds
        )

        self.max_response_bytes = (
            max_response_bytes
        )

        self._sleep = sleep_func

        self._lock = RLock()

        self._last_result: (
            DownloadResult | None
        ) = None

        self._last_error: (
            DownloadError | None
        ) = None

        self._history: list[
            DownloadResult
        ] = []

    @property
    def last_result(
        self,
    ) -> DownloadResult | None:
        with self._lock:
            return self._last_result

    @property
    def last_error(
        self,
    ) -> DownloadError | None:
        with self._lock:
            return self._last_error

    @property
    def history(
        self,
    ) -> tuple[DownloadResult, ...]:
        with self._lock:
            return tuple(self._history)

    def clear_history(self) -> None:
        with self._lock:
            self._last_result = None
            self._last_error = None
            self._history.clear()

    def fetch(
        self,
        source: Source,
    ) -> str:
        """
        Mantiene la compatibilità con Application.

        Restituisce soltanto il contenuto testuale.
        """

        return self.fetch_detailed(
            source
        ).content

    def fetch_detailed(
        self,
        source: Source,
    ) -> DownloadResult:
        """
        Scarica una playlist restituendo anche
        diagnostica e tentativi.
        """

        if not isinstance(source, Source):
            raise TypeError(
                "source must be an instance of Source"
            )

        try:
            source.validate()

        except (TypeError, ValueError) as exc:
            error = DownloadError(
                f"Sorgente non valida: {exc}",
                source_id=str(source.id),
                url=str(source.url),
            )

            self._record_error(error)
            raise error from exc

        if source.is_remote():
            return self._fetch_remote(
                source
            )

        return self._fetch_local(
            source
        )

    def _fetch_local(
        self,
        source: Source,
    ) -> DownloadResult:
        started = time.perf_counter()

        path = source.local_path(
            self.root
        )

        try:
            payload = path.read_bytes()

            self._validate_payload_size(
                payload
            )

            content, encoding = (
                self._decode_payload(
                    payload,
                    None,
                )
            )

            self._validate_content(
                content
            )

        except Exception as exc:
            elapsed_ms = self._elapsed_ms(
                started
            )

            attempt = DownloadAttempt(
                number=1,
                status="error",
                elapsed_ms=elapsed_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

            error = DownloadError(
                "Lettura playlist locale "
                f"fallita per {source.id}: "
                f"{path}: {exc}",
                source_id=source.id,
                url=str(path),
                attempts=(attempt,),
                retryable=False,
            )

            self._record_error(error)
            raise error from exc

        elapsed_ms = self._elapsed_ms(
            started
        )

        attempt = DownloadAttempt(
            number=1,
            status="success",
            elapsed_ms=elapsed_ms,
        )

        result = DownloadResult(
            source_id=source.id,
            requested_url=source.url,
            final_url=str(path),
            content=content,
            bytes_downloaded=len(payload),
            encoding=encoding,
            content_type=(
                "application/vnd.apple.mpegurl"
            ),
            http_status=None,
            attempts=(attempt,),
            total_elapsed_ms=elapsed_ms,
            is_remote=False,
        )

        self._record_result(result)

        return result

    def _fetch_remote(
        self,
        source: Source,
    ) -> DownloadResult:
        attempts: list[
            DownloadAttempt
        ] = []

        total_started = (
            time.perf_counter()
        )

        last_exception: (
            Exception | None
        ) = None

        last_status: int | None = None
        last_retryable = False

        for number in range(
            1,
            self.retries + 2,
        ):
            started = time.perf_counter()

            try:
                request = urllib.request.Request(
                    source.url,
                    headers={
                        "User-Agent": (
                            self.user_agent
                        ),
                        "Accept": (
                            "application/"
                            "vnd.apple.mpegurl,"
                            "application/"
                            "x-mpegURL,"
                            "text/plain,*/*"
                        ),
                        "Accept-Encoding": (
                            "identity"
                        ),
                    },
                )

                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout,
                ) as response:
                    status = (
                        self._response_status(
                            response
                        )
                    )

                    last_status = status

                    payload = (
                        self._read_response(
                            response
                        )
                    )

                    headers = getattr(
                        response,
                        "headers",
                        None,
                    )

                    charset = (
                        self._header_charset(
                            headers
                        )
                    )

                    content_type = (
                        self._header_content_type(
                            headers
                        )
                    )

                    content, encoding = (
                        self._decode_payload(
                            payload,
                            charset,
                        )
                    )

                    self._validate_content(
                        content
                    )

                    elapsed_ms = (
                        self._elapsed_ms(
                            started
                        )
                    )

                    attempts.append(
                        DownloadAttempt(
                            number=number,
                            status="success",
                            elapsed_ms=(
                                elapsed_ms
                            ),
                            http_status=status,
                        )
                    )

                    final_url = (
                        self._response_url(
                            response,
                            source.url,
                        )
                    )

                    result = DownloadResult(
                        source_id=source.id,
                        requested_url=(
                            source.url
                        ),
                        final_url=final_url,
                        content=content,
                        bytes_downloaded=len(
                            payload
                        ),
                        encoding=encoding,
                        content_type=(
                            content_type
                        ),
                        http_status=status,
                        attempts=tuple(
                            attempts
                        ),
                        total_elapsed_ms=(
                            self._elapsed_ms(
                                total_started
                            )
                        ),
                        is_remote=True,
                    )

                    self._record_result(
                        result
                    )

                    return result

            except urllib.error.HTTPError as exc:
                last_exception = exc
                last_status = exc.code

                last_retryable = (
                    exc.code
                    in _RETRYABLE_HTTP_STATUS
                )

                attempts.append(
                    self._failed_attempt(
                        number,
                        started,
                        exc,
                        http_status=(
                            exc.code
                        ),
                    )
                )

                if (
                    not last_retryable
                    or number > self.retries
                ):
                    break

                self._wait_before_retry(
                    number,
                    getattr(
                        exc,
                        "headers",
                        None,
                    ),
                )

            except (
                urllib.error.URLError,
                TimeoutError,
                socket.timeout,
                ConnectionError,
                OSError,
            ) as exc:
                last_exception = exc
                last_retryable = True

                attempts.append(
                    self._failed_attempt(
                        number,
                        started,
                        exc,
                    )
                )

                if number > self.retries:
                    break

                self._wait_before_retry(
                    number,
                    None,
                )

            except Exception as exc:
                last_exception = exc
                last_retryable = False

                attempts.append(
                    self._failed_attempt(
                        number,
                        started,
                        exc,
                        http_status=(
                            last_status
                        ),
                    )
                )

                break

        reason = (
            str(last_exception)
            if last_exception is not None
            else "errore sconosciuto"
        )

        error = DownloadError(
            "Download fallito per "
            f"{source.id} dopo "
            f"{len(attempts)} tentativi: "
            f"{reason}",
            source_id=source.id,
            url=source.url,
            attempts=tuple(attempts),
            status_code=last_status,
            retryable=last_retryable,
        )

        self._record_error(error)

        raise error from last_exception

    def _read_response(
        self,
        response: object,
    ) -> bytes:
        if self.max_response_bytes is None:
            payload = response.read()  # type: ignore[attr-defined]

        else:
            payload = response.read(  # type: ignore[attr-defined]
                self.max_response_bytes + 1
            )

        if not isinstance(payload, bytes):
            raise TypeError(
                "La risposta HTTP non contiene bytes"
            )

        self._validate_payload_size(
            payload
        )

        return payload

    def _validate_payload_size(
        self,
        payload: bytes,
    ) -> None:
        if (
            self.max_response_bytes
            is not None
            and len(payload)
            > self.max_response_bytes
        ):
            raise _ResponseTooLarge(
                "Risposta troppo grande: "
                f"{len(payload)} bytes, "
                "limite "
                f"{self.max_response_bytes}"
            )

    @staticmethod
    def _validate_content(
        content: str,
    ) -> None:
        if not content.strip():
            raise _EmptyResponse(
                "Playlist vuota"
            )

    @staticmethod
    def _decode_payload(
        payload: bytes,
        charset: str | None,
    ) -> tuple[str, str]:
        if charset:
            try:
                return (
                    payload.decode(
                        charset,
                        errors="replace",
                    ),
                    charset,
                )

            except LookupError:
                pass

        return (
            payload.decode(
                "utf-8-sig",
                errors="replace",
            ),
            "utf-8-sig",
        )

    @staticmethod
    def _response_status(
        response: object,
    ) -> int | None:
        status = getattr(
            response,
            "status",
            None,
        )

        if status is not None:
            return int(status)

        getcode = getattr(
            response,
            "getcode",
            None,
        )

        if callable(getcode):
            code = getcode()

            if code is not None:
                return int(code)

        return None

    @staticmethod
    def _response_url(
        response: object,
        fallback: str,
    ) -> str:
        geturl = getattr(
            response,
            "geturl",
            None,
        )

        if callable(geturl):
            value = geturl()

            if value:
                return str(value)

        return fallback

    @staticmethod
    def _header_charset(
        headers: object | None,
    ) -> str | None:
        if headers is None:
            return None

        method = getattr(
            headers,
            "get_content_charset",
            None,
        )

        if callable(method):
            return method()

        return None

    @staticmethod
    def _header_content_type(
        headers: object | None,
    ) -> str:
        if headers is None:
            return ""

        method = getattr(
            headers,
            "get_content_type",
            None,
        )

        if callable(method):
            return str(method())

        getter = getattr(
            headers,
            "get",
            None,
        )

        if callable(getter):
            value = getter(
                "Content-Type",
                "",
            )

            return (
                str(value)
                .split(";", 1)[0]
                .strip()
            )

        return ""

    def _wait_before_retry(
        self,
        attempt_number: int,
        headers: object | None,
    ) -> None:
        delay = (
            self._retry_after_seconds(
                headers
            )
        )

        if delay is None:
            delay = (
                self.backoff_seconds
                * attempt_number
            )

        delay = min(
            delay,
            self.max_backoff_seconds,
        )

        if delay > 0:
            self._sleep(delay)

    @staticmethod
    def _retry_after_seconds(
        headers: object | None,
    ) -> float | None:
        if headers is None:
            return None

        getter = getattr(
            headers,
            "get",
            None,
        )

        if not callable(getter):
            return None

        raw_value = getter(
            "Retry-After"
        )

        if raw_value is None:
            return None

        try:
            value = float(
                str(raw_value).strip()
            )

        except ValueError:
            return None

        return max(
            0.0,
            value,
        )

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> int:
        return max(
            0,
            round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000
            ),
        )

    def _failed_attempt(
        self,
        number: int,
        started: float,
        exc: Exception,
        *,
        http_status: int | None = None,
    ) -> DownloadAttempt:
        return DownloadAttempt(
            number=number,
            status="error",
            elapsed_ms=self._elapsed_ms(
                started
            ),
            http_status=http_status,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    def _record_result(
        self,
        result: DownloadResult,
    ) -> None:
        with self._lock:
            self._last_result = result
            self._last_error = None
            self._history.append(result)

    def _record_error(
        self,
        error: DownloadError,
    ) -> None:
        with self._lock:
            self._last_result = None
            self._last_error = error