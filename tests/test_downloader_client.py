from __future__ import annotations

from email.message import Message
from pathlib import Path
import urllib.error

import pytest

from src.downloader.client import (
    DownloadError,
    PlaylistDownloader,
)
from src.models.source import Source


def make_source(
    source_id: str,
    url: str,
) -> Source:
    return Source(
        id=source_id,
        name=f"Source {source_id}",
        url=url,
    )


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        status: int = 200,
        url: str = (
            "https://final.test/list.m3u"
        ),
        content_type: str = (
            "application/x-mpegURL; "
            "charset=utf-8"
        ),
    ) -> None:
        self.payload = payload
        self.status = status
        self.url = url

        self.headers = Message()
        self.headers[
            "Content-Type"
        ] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(
        self,
        size: int = -1,
    ) -> bytes:
        if size < 0:
            return self.payload

        return self.payload[:size]

    def geturl(self) -> str:
        return self.url


def test_reads_local_playlist_and_records_diagnostics(
    tmp_path: Path,
) -> None:
    playlist = (
        tmp_path
        / "config/local.m3u"
    )

    playlist.parent.mkdir(
        parents=True
    )

    playlist.write_bytes(
        b"\xef\xbb\xbf"
        b"#EXTM3U\n"
        b"#EXTINF:-1,Rai 1\n"
        b"https://stream.test/rai1\n"
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=2,
        user_agent="Italia-TV-Hub",
    )

    source = make_source(
        "local",
        "config/local.m3u",
    )

    content = downloader.fetch(
        source
    )

    assert content.startswith(
        "#EXTM3U"
    )

    assert (
        downloader.last_result
        is not None
    )

    assert (
        downloader.last_result
        .is_remote
        is False
    )

    assert (
        downloader.last_result
        .attempt_count
        == 1
    )

    assert (
        downloader.last_result
        .bytes_downloaded
        > 0
    )

    assert downloader.last_error is None


def test_missing_local_playlist_raises_detailed_error(
    tmp_path: Path,
) -> None:
    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=2,
        user_agent="Italia-TV-Hub",
    )

    source = make_source(
        "missing",
        "config/missing.m3u",
    )

    with pytest.raises(
        DownloadError,
        match="missing",
    ) as exc_info:
        downloader.fetch(source)

    error = exc_info.value

    assert error.source_id == "missing"
    assert error.attempt_count == 1
    assert error.retryable is False
    assert downloader.last_error is error


def test_remote_success_returns_content_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    response = FakeResponse(
        b"#EXTM3U\n",
        status=200,
        url=(
            "https://cdn.test/final.m3u"
        ),
    )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: response,
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=2,
        user_agent="Italia-TV-Hub",
    )

    result = downloader.fetch_detailed(
        make_source(
            "remote",
            "https://example.test/list.m3u",
        )
    )

    assert result.content == "#EXTM3U\n"
    assert result.http_status == 200

    assert result.final_url == (
        "https://cdn.test/final.m3u"
    )

    assert result.content_type == (
        "application/x-mpegurl"
    )

    assert result.attempt_count == 1

    assert (
        result.attempts[0].status
        == "success"
    )


def test_transient_network_error_is_retried(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(
        *args,
        **kwargs,
    ):
        nonlocal calls

        calls += 1

        if calls == 1:
            raise urllib.error.URLError(
                "temporary failure"
            )

        return FakeResponse(
            b"#EXTM3U\n"
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=2,
        user_agent="Italia-TV-Hub",
        sleep_func=sleeps.append,
    )

    result = downloader.fetch_detailed(
        make_source(
            "remote",
            "https://example.test/list.m3u",
        )
    )

    assert calls == 2
    assert sleeps == [1.0]
    assert result.attempt_count == 2

    assert (
        result.attempts[0].status
        == "error"
    )

    assert (
        result.attempts[1].status
        == "success"
    )


def test_http_404_is_not_retried(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(
        *args,
        **kwargs,
    ):
        nonlocal calls

        calls += 1

        raise urllib.error.HTTPError(
            "https://example.test/"
            "missing.m3u",
            404,
            "Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=3,
        user_agent="Italia-TV-Hub",
        sleep_func=sleeps.append,
    )

    with pytest.raises(
        DownloadError
    ) as exc_info:
        downloader.fetch(
            make_source(
                "missing",
                "https://example.test/"
                "missing.m3u",
            )
        )

    assert calls == 1
    assert sleeps == []

    assert (
        exc_info.value.status_code
        == 404
    )

    assert (
        exc_info.value.attempt_count
        == 1
    )

    assert (
        exc_info.value.retryable
        is False
    )


def test_http_503_retries_until_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(
        *args,
        **kwargs,
    ):
        nonlocal calls

        calls += 1

        raise urllib.error.HTTPError(
            "https://example.test/"
            "list.m3u",
            503,
            "Service Unavailable",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=2,
        user_agent="Italia-TV-Hub",
        sleep_func=sleeps.append,
    )

    with pytest.raises(
        DownloadError
    ) as exc_info:
        downloader.fetch(
            make_source(
                "unavailable",
                "https://example.test/"
                "list.m3u",
            )
        )

    error = exc_info.value

    assert calls == 3
    assert sleeps == [1.0, 2.0]
    assert error.status_code == 503
    assert error.attempt_count == 3
    assert error.retryable is True


def test_retry_after_header_is_respected_and_capped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    headers = Message()
    headers["Retry-After"] = "10"

    def fake_urlopen(
        *args,
        **kwargs,
    ):
        nonlocal calls

        calls += 1

        if calls == 1:
            raise urllib.error.HTTPError(
                "https://example.test/"
                "list.m3u",
                429,
                "Too Many Requests",
                hdrs=headers,
                fp=None,
            )

        return FakeResponse(
            b"#EXTM3U\n"
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=1,
        user_agent="Italia-TV-Hub",
        max_backoff_seconds=3,
        sleep_func=sleeps.append,
    )

    result = downloader.fetch_detailed(
        make_source(
            "limited",
            "https://example.test/list.m3u",
        )
    )

    assert result.attempt_count == 2
    assert sleeps == [3.0]


def test_response_larger_than_limit_is_rejected_without_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0

    def fake_urlopen(
        *args,
        **kwargs,
    ):
        nonlocal calls

        calls += 1

        return FakeResponse(
            b"123456"
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=3,
        user_agent="Italia-TV-Hub",
        max_response_bytes=5,
        sleep_func=lambda _: None,
    )

    with pytest.raises(
        DownloadError,
        match="Risposta troppo grande",
    ) as exc_info:
        downloader.fetch(
            make_source(
                "large",
                "https://example.test/list.m3u",
            )
        )

    assert calls == 1

    assert (
        exc_info.value.attempt_count
        == 1
    )

    assert (
        exc_info.value.retryable
        is False
    )


def test_empty_remote_playlist_is_rejected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (
            FakeResponse(
                b" \n\t"
            )
        ),
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=2,
        user_agent="Italia-TV-Hub",
    )

    with pytest.raises(
        DownloadError,
        match="Playlist vuota",
    ):
        downloader.fetch(
            make_source(
                "empty",
                "https://example.test/"
                "empty.m3u",
            )
        )


def test_clear_history_resets_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (
            FakeResponse(
                b"#EXTM3U\n"
            )
        ),
    )

    downloader = PlaylistDownloader(
        tmp_path,
        timeout=5,
        retries=0,
        user_agent="Italia-TV-Hub",
    )

    downloader.fetch(
        make_source(
            "remote",
            "https://example.test/list.m3u",
        )
    )

    assert len(
        downloader.history
    ) == 1

    assert (
        downloader.last_result
        is not None
    )

    downloader.clear_history()

    assert downloader.history == ()
    assert downloader.last_result is None
    assert downloader.last_error is None


@pytest.mark.parametrize(
    "kwargs,error_type",
    [
        (
            {"timeout": 0},
            ValueError,
        ),
        (
            {"retries": -1},
            ValueError,
        ),
        (
            {"retries": 1.5},
            TypeError,
        ),
        (
            {"max_response_bytes": 0},
            ValueError,
        ),
    ],
)
def test_invalid_downloader_configuration_is_rejected(
    tmp_path: Path,
    kwargs: dict[str, object],
    error_type: type[Exception],
) -> None:
    parameters: dict[
        str,
        object,
    ] = {
        "project_root": tmp_path,
        "timeout": 5,
        "retries": 1,
        "user_agent": "Italia-TV-Hub",
    }

    parameters.update(
        kwargs
    )

    with pytest.raises(
        error_type
    ):
        PlaylistDownloader(
            **parameters
        )