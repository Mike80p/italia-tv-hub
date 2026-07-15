from __future__ import annotations

import io
import urllib.error
from dataclasses import asdict

import pytest

import src.health.checker as health_module
from src.health.checker import (
    HealthBatchResult,
    HealthResult,
    HealthStats,
    StreamHealthChecker,
)
from src.models.channel import Channel


def make_channel(
    name: str,
    stream_url: str,
    source_id: str = "source-a",
) -> Channel:
    return Channel(
        name,
        stream_url,
        "Generali",
        "",
        "",
        "",
        source_id,
        {},
        [],
    )


def make_result(
    channel: Channel,
    *,
    status: str,
    health_score: int,
    response_ms: int | None,
    classification_reason: str,
    http_status: int | None = 200,
    error: str = "",
    error_type: str = "",
    redirected: bool = False,
) -> HealthResult:
    return HealthResult(
        name=channel.name,
        stream_url=channel.stream_url,
        source_id=channel.source_id,
        status=status,
        http_status=http_status,
        response_ms=response_ms,
        content_type="application/vnd.apple.mpegurl",
        final_url=channel.stream_url,
        error=error,
        health_score=health_score,
        classification_reason=classification_reason,
        bytes_read=32,
        redirected=redirected,
        error_type=error_type,
    )


class FakeResponse:
    def __init__(
        self,
        *,
        data: bytes,
        status: int = 200,
        content_type: str = "",
        final_url: str = "https://stream.test/live",
    ) -> None:
        self._data = data
        self._status = status
        self._final_url = final_url
        self.headers = {
            "Content-Type": content_type,
        }

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._data

        return self._data[:size]

    def getcode(self) -> int:
        return self._status

    def geturl(self) -> str:
        return self._final_url


def test_checker_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        StreamHealthChecker(
            timeout_seconds=0,
        )

    with pytest.raises(ValueError):
        StreamHealthChecker(
            max_workers=0,
        )

    with pytest.raises(ValueError):
        StreamHealthChecker(
            read_bytes=0,
        )


def test_health_result_to_dict_contains_quality_diagnostics() -> None:
    channel = make_channel(
        "Rai 1",
        "https://stream.test/rai1",
    )

    result = make_result(
        channel,
        status="online",
        health_score=98,
        response_ms=120,
        classification_reason="hls_signature",
        redirected=True,
    )

    payload = result.to_dict()

    assert payload == asdict(result)
    assert payload["health_score"] == 98
    assert (
        payload["classification_reason"]
        == "hls_signature"
    )
    assert payload["bytes_read"] == 32
    assert payload["redirected"] is True
    assert payload["error_type"] == ""


def test_hls_signature_is_online_even_with_text_content_type(
    monkeypatch,
) -> None:
    channel = make_channel(
        "Rai 1",
        "https://origin.test/rai1",
    )

    response = FakeResponse(
        data=(
            b"#EXTM3U\n"
            b"#EXT-X-VERSION:3\n"
        ),
        status=200,
        content_type="text/plain; charset=utf-8",
        final_url="https://cdn.test/rai1/index.m3u8",
    )

    monkeypatch.setattr(
        health_module.urllib.request,
        "urlopen",
        lambda request, timeout: response,
    )

    result = StreamHealthChecker().check(
        channel
    )

    assert result.status == "online"
    assert result.http_status == 200
    assert result.health_score >= 90

    assert (
        result.classification_reason
        == "hls_signature"
    )

    assert result.bytes_read > 0
    assert result.redirected is True
    assert result.final_url == (
        "https://cdn.test/rai1/index.m3u8"
    )
    assert result.error == ""
    assert result.error_type == ""


@pytest.mark.parametrize(
    "content_type",
    [
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "video/mp2t",
        "video/mp4",
        "audio/aac",
        "application/octet-stream",
    ],
)
def test_media_content_types_are_online(
    monkeypatch,
    content_type: str,
) -> None:
    channel = make_channel(
        "Canale media",
        "https://stream.test/media",
    )

    response = FakeResponse(
        data=b"binary-media-payload",
        status=206,
        content_type=content_type,
        final_url=channel.stream_url,
    )

    monkeypatch.setattr(
        health_module.urllib.request,
        "urlopen",
        lambda request, timeout: response,
    )

    result = StreamHealthChecker().check(
        channel
    )

    assert result.status == "online"
    assert result.http_status == 206

    assert (
        result.classification_reason
        == "media_content_type"
    )

    assert result.health_score >= 80


def test_non_media_payload_is_reachable(
    monkeypatch,
) -> None:
    channel = make_channel(
        "Pagina HTML",
        "https://stream.test/html",
    )

    response = FakeResponse(
        data=b"<html>not a stream</html>",
        status=200,
        content_type="text/html",
        final_url=channel.stream_url,
    )

    monkeypatch.setattr(
        health_module.urllib.request,
        "urlopen",
        lambda request, timeout: response,
    )

    result = StreamHealthChecker().check(
        channel
    )

    assert result.status == "reachable"

    assert (
        result.classification_reason
        == "payload_reachable"
    )

    assert 1 <= result.health_score < 80


def test_empty_success_response_is_offline(
    monkeypatch,
) -> None:
    channel = make_channel(
        "Vuoto",
        "https://stream.test/empty",
    )

    response = FakeResponse(
        data=b"",
        status=200,
        content_type="text/plain",
        final_url=channel.stream_url,
    )

    monkeypatch.setattr(
        health_module.urllib.request,
        "urlopen",
        lambda request, timeout: response,
    )

    result = StreamHealthChecker().check(
        channel
    )

    assert result.status == "offline"
    assert result.health_score == 0

    assert (
        result.classification_reason
        == "empty_payload"
    )


def test_http_error_produces_offline_diagnostics(
    monkeypatch,
) -> None:
    channel = make_channel(
        "Errore HTTP",
        "https://stream.test/http-error",
    )

    def raise_http_error(
        request,
        timeout,
    ):
        raise urllib.error.HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(b""),
        )

    monkeypatch.setattr(
        health_module.urllib.request,
        "urlopen",
        raise_http_error,
    )

    result = StreamHealthChecker().check(
        channel
    )

    assert result.status == "offline"
    assert result.http_status == 503
    assert result.health_score == 0
    assert result.error_type == "HTTPError"

    assert (
        result.classification_reason
        == "http_error"
    )

    assert "503" in result.error
    assert result.response_ms is not None


def test_url_error_produces_offline_diagnostics(
    monkeypatch,
) -> None:
    channel = make_channel(
        "Errore rete",
        "https://stream.test/network-error",
    )

    def raise_url_error(
        request,
        timeout,
    ):
        raise urllib.error.URLError(
            "name resolution failed"
        )

    monkeypatch.setattr(
        health_module.urllib.request,
        "urlopen",
        raise_url_error,
    )

    result = StreamHealthChecker().check(
        channel
    )

    assert result.status == "offline"
    assert result.http_status is None
    assert result.health_score == 0
    assert result.error_type == "URLError"

    assert (
        result.classification_reason
        == "network_error"
    )

    assert "name resolution failed" in (
        result.error
    )


def test_check_many_preserves_input_order(
    monkeypatch,
) -> None:
    channels = [
        make_channel(
            "Uno",
            "https://stream.test/1",
        ),
        make_channel(
            "Due",
            "https://stream.test/2",
        ),
        make_channel(
            "Tre",
            "https://stream.test/3",
        ),
    ]

    checker = StreamHealthChecker(
        max_workers=3,
    )

    scores = {
        channels[0].stream_url: 91,
        channels[1].stream_url: 47,
        channels[2].stream_url: 0,
    }

    def fake_check(
        channel: Channel,
    ) -> HealthResult:
        score = scores[
            channel.stream_url
        ]

        status = (
            "online"
            if score >= 80
            else "reachable"
            if score > 0
            else "offline"
        )

        return make_result(
            channel,
            status=status,
            health_score=score,
            response_ms=100,
            classification_reason="test",
        )

    monkeypatch.setattr(
        checker,
        "check",
        fake_check,
    )

    results = checker.check_many(
        channels
    )

    assert [
        result.stream_url
        for result in results
    ] == [
        channel.stream_url
        for channel in channels
    ]


def test_check_many_detailed_builds_aggregate_stats(
    monkeypatch,
) -> None:
    channels = [
        make_channel(
            "Online",
            "https://stream.test/online",
        ),
        make_channel(
            "Reachable",
            "https://stream.test/reachable",
        ),
        make_channel(
            "Offline",
            "https://stream.test/offline",
        ),
    ]

    checker = StreamHealthChecker(
        max_workers=2,
    )

    results_by_url = {
        channels[0].stream_url: make_result(
            channels[0],
            status="online",
            health_score=96,
            response_ms=100,
            classification_reason="hls_signature",
            redirected=True,
        ),
        channels[1].stream_url: make_result(
            channels[1],
            status="reachable",
            health_score=45,
            response_ms=300,
            classification_reason="payload_reachable",
        ),
        channels[2].stream_url: make_result(
            channels[2],
            status="offline",
            health_score=0,
            response_ms=500,
            classification_reason="network_error",
            http_status=None,
            error="URLError: failed",
            error_type="URLError",
        ),
    }

    monkeypatch.setattr(
        checker,
        "check",
        lambda channel: results_by_url[
            channel.stream_url
        ],
    )

    detailed = (
        checker.check_many_detailed(
            channels
        )
    )

    assert isinstance(
        detailed,
        HealthBatchResult,
    )

    assert isinstance(
        detailed.stats,
        HealthStats,
    )

    assert len(detailed.results) == 3

    stats = detailed.stats

    assert stats.input_channels == 3
    assert stats.checked == 3
    assert stats.online == 1
    assert stats.reachable == 1
    assert stats.offline == 1
    assert stats.redirects == 1
    assert stats.errors == 1

    assert stats.average_score == pytest.approx(
        47.0
    )

    assert (
        stats.average_response_ms
        == pytest.approx(300.0)
    )

    assert stats.min_score == 0
    assert stats.max_score == 96

    payload = detailed.to_dict()

    assert payload["stats"] == (
        stats.to_dict()
    )

    assert len(payload["results"]) == 3


def test_check_many_remains_compatible_with_detailed_engine(
    monkeypatch,
) -> None:
    channel = make_channel(
        "Compatibile",
        "https://stream.test/compatible",
    )

    checker = StreamHealthChecker()

    expected = make_result(
        channel,
        status="online",
        health_score=90,
        response_ms=50,
        classification_reason="media_content_type",
    )

    monkeypatch.setattr(
        checker,
        "check_many_detailed",
        lambda channels: HealthBatchResult(
            results=(expected,),
            stats=HealthStats(
                input_channels=1,
                checked=1,
                online=1,
                reachable=0,
                offline=0,
                redirects=0,
                errors=0,
                average_score=90.0,
                average_response_ms=50.0,
                min_score=90,
                max_score=90,
            ),
        ),
    )

    assert checker.check_many(
        [channel]
    ) == [expected]


def test_empty_detailed_batch_has_zero_stats() -> None:
    checker = StreamHealthChecker()

    detailed = (
        checker.check_many_detailed([])
    )

    assert detailed.results == ()

    assert detailed.stats == HealthStats(
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
