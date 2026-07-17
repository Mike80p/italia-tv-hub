from __future__ import annotations

import gzip
import io
import urllib.error
from email.message import Message
from typing import Any

import pytest

from src.epg.downloader import (
    EPGDownloadError,
    EPGDownloader,
)


class FakeResponse:
    def __init__(
        self,
        data: bytes,
        *,
        status: int = 200,
        final_url: str = (
            "https://example.test/epg.xml"
        ),
        content_type: str = (
            "application/xml"
        ),
        content_length: (
            int | None
        ) = None,
    ) -> None:
        self._stream = io.BytesIO(
            data
        )

        self.status = status
        self._final_url = (
            final_url
        )

        self.headers = Message()

        self.headers[
            "Content-Type"
        ] = content_type

        if content_length is not None:
            self.headers[
                "Content-Length"
            ] = str(
                content_length
            )

    def read(
        self,
        size: int = -1,
    ) -> bytes:
        return self._stream.read(
            size
        )

    def geturl(
        self,
    ) -> str:
        return self._final_url

    def __enter__(
        self,
    ) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc: Any,
        traceback: Any,
    ) -> None:
        return None


class FakeOpener:
    def __init__(
        self,
        outcomes: list[
            object
        ],
    ) -> None:
        self.outcomes = list(
            outcomes
        )

        self.calls = 0
        self.requests: list[
            object
        ] = []

    def urlopen(
        self,
        request: object,
        *,
        timeout: int,
    ) -> FakeResponse:
        self.calls += 1

        self.requests.append(
            request
        )

        if not self.outcomes:
            raise AssertionError(
                "Nessun outcome configurato"
            )

        outcome = (
            self.outcomes.pop(0)
        )

        if isinstance(
            outcome,
            BaseException,
        ):
            raise outcome

        assert isinstance(
            outcome,
            FakeResponse,
        )

        return outcome


def test_successful_xml_download() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b"<tv></tv>",
                content_length=9,
            )
        ]
    )

    result = EPGDownloader(
        opener=opener,
        sleep_function=lambda _: None,
    ).fetch(
        "https://example.test/epg.xml"
    )

    assert result.data == b"<tv></tv>"
    assert result.http_status == 200
    assert result.attempt_count == 1
    assert result.compressed is False
    assert result.bytes_downloaded == 9
    assert (
        result.attempts[0].status
        == "ok"
    )


def test_gzip_is_detected_by_magic_bytes() -> None:
    payload = gzip.compress(
        b"<tv></tv>"
    )

    opener = FakeOpener(
        [
            FakeResponse(
                payload,
                final_url=(
                    "https://example.test/"
                    "guide.bin"
                ),
                content_type=(
                    "application/octet-stream"
                ),
            )
        ]
    )

    result = EPGDownloader(
        opener=opener,
        sleep_function=lambda _: None,
    ).fetch(
        "https://example.test/guide.bin"
    )

    assert result.compressed is True


def test_gzip_is_detected_by_content_type() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b"compressed-placeholder",
                content_type=(
                    "application/gzip"
                ),
            )
        ]
    )

    result = EPGDownloader(
        opener=opener,
        sleep_function=lambda _: None,
    ).fetch(
        "https://example.test/guide"
    )

    assert result.compressed is True


def test_final_redirect_url_is_preserved() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b"<tv />",
                final_url=(
                    "https://cdn.example.test/"
                    "guide.xml"
                ),
            )
        ]
    )

    result = EPGDownloader(
        opener=opener,
        sleep_function=lambda _: None,
    ).fetch(
        "https://example.test/redirect"
    )

    assert result.final_url == (
        "https://cdn.example.test/"
        "guide.xml"
    )


def test_retryable_http_error_is_retried() -> None:
    http_error = (
        urllib.error.HTTPError(
            url=(
                "https://example.test/"
                "epg.xml"
            ),
            code=503,
            msg=(
                "Service Unavailable"
            ),
            hdrs=None,
            fp=None,
        )
    )

    opener = FakeOpener(
        [
            http_error,
            FakeResponse(
                b"<tv />"
            ),
        ]
    )

    delays: list[
        float
    ] = []

    result = EPGDownloader(
        retry_count=2,
        retry_backoff_seconds=0.25,
        opener=opener,
        sleep_function=delays.append,
    ).fetch(
        "https://example.test/epg.xml"
    )

    assert result.attempt_count == 2
    assert opener.calls == 2
    assert delays == [0.25]
    assert (
        result.attempts[0].retryable
        is True
    )


def test_non_retryable_http_error_stops_immediately() -> None:
    http_error = (
        urllib.error.HTTPError(
            url=(
                "https://example.test/"
                "missing.xml"
            ),
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
    )

    opener = FakeOpener(
        [
            http_error
        ]
    )

    with pytest.raises(
        EPGDownloadError
    ) as error_info:
        EPGDownloader(
            retry_count=3,
            opener=opener,
            sleep_function=lambda _: None,
        ).fetch(
            "https://example.test/missing.xml"
        )

    error = error_info.value

    assert error.status_code == 404
    assert error.retryable is False
    assert error.attempt_count == 1
    assert opener.calls == 1


def test_network_error_is_retried() -> None:
    opener = FakeOpener(
        [
            urllib.error.URLError(
                "temporary"
            ),
            FakeResponse(
                b"<tv />"
            ),
        ]
    )

    result = EPGDownloader(
        retry_count=1,
        opener=opener,
        sleep_function=lambda _: None,
    ).fetch(
        "https://example.test/epg.xml"
    )

    assert result.attempt_count == 2


def test_empty_response_is_rejected() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b""
            )
        ]
    )

    with pytest.raises(
        EPGDownloadError,
        match="vuota",
    ):
        EPGDownloader(
            opener=opener,
            sleep_function=lambda _: None,
        ).fetch(
            "https://example.test/epg.xml"
        )


def test_content_length_limit_is_enforced() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b"<tv />",
                content_length=1000,
            )
        ]
    )

    with pytest.raises(
        EPGDownloadError,
        match="Content-Length",
    ):
        EPGDownloader(
            max_download_bytes=100,
            opener=opener,
            sleep_function=lambda _: None,
        ).fetch(
            "https://example.test/epg.xml"
        )


def test_streamed_size_limit_is_enforced() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b"x" * 101
            )
        ]
    )

    with pytest.raises(
        EPGDownloadError,
        match="supera il limite",
    ):
        EPGDownloader(
            max_download_bytes=100,
            opener=opener,
            sleep_function=lambda _: None,
        ).fetch(
            "https://example.test/epg.xml"
        )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///tmp/epg.xml",
        "ftp://example.test/epg.xml",
        "not-a-url",
    ],
)
def test_invalid_urls_are_rejected(
    url: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="URL EPG",
    ):
        EPGDownloader().fetch(
            url
        )


def test_request_contains_user_agent_and_accept_headers() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                b"<tv />"
            )
        ]
    )

    EPGDownloader(
        user_agent="test-agent",
        opener=opener,
        sleep_function=lambda _: None,
    ).fetch(
        "https://example.test/epg.xml"
    )

    request = opener.requests[0]

    assert (
        request.get_header(
            "User-agent"
        )
        == "test-agent"
    )

    assert "application/xml" in (
        request.get_header(
            "Accept"
        )
    )


def test_invalid_constructor_values_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds",
    ):
        EPGDownloader(
            timeout_seconds=0
        )

    with pytest.raises(
        ValueError,
        match="retry_count",
    ):
        EPGDownloader(
            retry_count=-1
        )

    with pytest.raises(
        ValueError,
        match="max_download_bytes",
    ):
        EPGDownloader(
            max_download_bytes=0
        )
