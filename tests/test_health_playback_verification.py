from __future__ import annotations

import io
import time
import urllib.error

import pytest

import src.health.checker as health_module
from src.health.checker import (
    StreamHealthChecker,
)
from src.models.channel import Channel


class FakeResponse:
    def __init__(
        self,
        *,
        data: bytes,
        status: int = 200,
        content_type: str = "",
        final_url: str,
    ) -> None:
        self.data = data
        self.status = status
        self.content_type = content_type
        self.final_url = final_url
        self.headers = {
            "Content-Type": content_type,
        }

    def __enter__(
        self,
    ) -> FakeResponse:
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        return False

    def read(
        self,
        size: int = -1,
    ) -> bytes:
        if size < 0:
            return self.data

        return self.data[:size]

    def getcode(
        self,
    ) -> int:
        return self.status

    def geturl(
        self,
    ) -> str:
        return self.final_url


def make_channel(
    name: str,
    url: str,
    *,
    attributes: (
        dict[str, str] | None
    ) = None,
) -> Channel:
    return Channel(
        name=name,
        stream_url=url,
        group="Test",
        source_id="test",
        attributes=(
            attributes
            or {}
        ),
    )


def install_responses(
    monkeypatch,
    responses: dict[
        str,
        FakeResponse | Exception,
    ],
) -> None:
    def fake_urlopen(
        request,
        timeout,
    ):
        result = responses[
            request.full_url
        ]

        if isinstance(
            result,
            Exception,
        ):
            raise result

        return result

    monkeypatch.setattr(
        health_module
        .urllib.request,
        "urlopen",
        fake_urlopen,
    )


def test_deep_media_playlist_checks_real_segment(
    monkeypatch,
) -> None:
    manifest_url = (
        "https://cdn.test/live/"
        "index.m3u8"
    )

    segment_url = (
        "https://cdn.test/live/"
        "segment-1.ts"
    )

    install_responses(
        monkeypatch,
        {
            manifest_url: FakeResponse(
                data=(
                    b"#EXTM3U\n"
                    b"#EXT-X-TARGETDURATION:6\n"
                    b"#EXTINF:6.0,\n"
                    b"segment-1.ts\n"
                ),
                content_type=(
                    "application/"
                    "vnd.apple.mpegurl"
                ),
                final_url=manifest_url,
            ),
            segment_url: FakeResponse(
                data=(
                    b"\x47"
                    + b"\x00" * 500
                ),
                content_type=(
                    "video/mp2t"
                ),
                final_url=segment_url,
            ),
        },
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
    ).check(
        make_channel(
            "Canale",
            manifest_url,
        )
    )

    assert result.status == "online"
    assert (
        result.classification_reason
        == "hls_segment_verified"
    )
    assert result.playback_verified is True
    assert result.hls_kind == "media"
    assert result.segment_url == segment_url
    assert result.segment_bytes_read > 0


def test_deep_master_checks_variant_and_segment(
    monkeypatch,
) -> None:
    master_url = (
        "https://cdn.test/master.m3u8"
    )

    variant_url = (
        "https://cdn.test/720p/"
        "index.m3u8"
    )

    segment_url = (
        "https://cdn.test/720p/"
        "chunk.m4s"
    )

    install_responses(
        monkeypatch,
        {
            master_url: FakeResponse(
                data=(
                    b"#EXTM3U\n"
                    b"#EXT-X-STREAM-INF:"
                    b"BANDWIDTH=2500000,"
                    b"RESOLUTION=1280x720,"
                    b'CODECS="avc1.64001f,'
                    b'mp4a.40.2"\n'
                    b"720p/index.m3u8\n"
                ),
                content_type=(
                    "application/"
                    "vnd.apple.mpegurl"
                ),
                final_url=master_url,
            ),
            variant_url: FakeResponse(
                data=(
                    b"#EXTM3U\n"
                    b"#EXT-X-TARGETDURATION:4\n"
                    b"#EXTINF:4.0,\n"
                    b"chunk.m4s\n"
                ),
                content_type=(
                    "application/"
                    "vnd.apple.mpegurl"
                ),
                final_url=variant_url,
            ),
            segment_url: FakeResponse(
                data=(
                    b"\x00\x00\x00\x18"
                    b"ftyp"
                    + b"\x00" * 500
                ),
                content_type=(
                    "video/mp4"
                ),
                final_url=segment_url,
            ),
        },
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
    ).check(
        make_channel(
            "Canale master",
            master_url,
        )
    )

    assert result.status == "online"
    assert result.playback_verified is True
    assert result.hls_kind == "master"
    assert result.variant_url == (
        variant_url
    )
    assert result.segment_url == (
        segment_url
    )
    assert result.resolution == (
        "1280x720"
    )
    assert result.bandwidth == 2_500_000
    assert "avc1" in result.codecs


def test_segment_http_failure_is_offline(
    monkeypatch,
) -> None:
    manifest_url = (
        "https://cdn.test/fail/"
        "index.m3u8"
    )

    segment_url = (
        "https://cdn.test/fail/"
        "segment.ts"
    )

    install_responses(
        monkeypatch,
        {
            manifest_url: FakeResponse(
                data=(
                    b"#EXTM3U\n"
                    b"#EXT-X-TARGETDURATION:5\n"
                    b"#EXTINF:5,\n"
                    b"segment.ts\n"
                ),
                content_type=(
                    "application/"
                    "vnd.apple.mpegurl"
                ),
                final_url=manifest_url,
            ),
            segment_url: (
                urllib.error.HTTPError(
                    segment_url,
                    403,
                    "Forbidden",
                    hdrs=None,
                    fp=io.BytesIO(b""),
                )
            ),
        },
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
    ).check(
        make_channel(
            "Segmento bloccato",
            manifest_url,
        )
    )

    assert result.status == "offline"
    assert result.health_score == 0
    assert (
        result.classification_reason
        == "hls_segment_http_error"
    )
    assert result.segment_http_status == 403
    assert result.playback_verified is False


def test_drm_playlist_is_rejected(
    monkeypatch,
) -> None:
    manifest_url = (
        "https://cdn.test/drm/"
        "index.m3u8"
    )

    install_responses(
        monkeypatch,
        {
            manifest_url: FakeResponse(
                data=(
                    b"#EXTM3U\n"
                    b"#EXT-X-KEY:"
                    b"METHOD=SAMPLE-AES,"
                    b'KEYFORMAT="com.widevine"\n'
                    b"#EXTINF:5,\n"
                    b"segment.ts\n"
                ),
                content_type=(
                    "application/"
                    "vnd.apple.mpegurl"
                ),
                final_url=manifest_url,
            ),
        },
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
    ).check(
        make_channel(
            "DRM",
            manifest_url,
        )
    )

    assert result.status == "offline"
    assert result.drm_detected is True
    assert (
        result.classification_reason
        == "hls_drm_detected"
    )


def test_html_page_is_offline_in_deep_mode(
    monkeypatch,
) -> None:
    url = (
        "https://stream.test/"
        "fake.m3u8"
    )

    install_responses(
        monkeypatch,
        {
            url: FakeResponse(
                data=(
                    b"<html>access denied"
                    b"</html>"
                ),
                content_type="text/html",
                final_url=url,
            ),
        },
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
    ).check(
        make_channel(
            "Pagina HTML",
            url,
        )
    )

    assert result.status == "offline"
    assert (
        result.classification_reason
        == "non_media_payload"
    )


def test_expired_url_token_is_rejected_without_request(
    monkeypatch,
) -> None:
    expired = int(
        time.time()
    ) - 3600

    url = (
        "https://stream.test/"
        f"live.m3u8?exp={expired}"
    )

    def should_not_open(
        request,
        timeout,
    ):
        raise AssertionError(
            "La rete non deve essere "
            "chiamata"
        )

    monkeypatch.setattr(
        health_module
        .urllib.request,
        "urlopen",
        should_not_open,
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
    ).check(
        make_channel(
            "Token scaduto",
            url,
        )
    )

    assert result.status == "offline"
    assert (
        result.classification_reason
        == "token_expired"
    )


def test_foreign_market_metadata_is_rejected(
    monkeypatch,
) -> None:
    url = (
        "https://stream.test/"
        "foreign.m3u8"
    )

    def should_not_open(
        request,
        timeout,
    ):
        raise AssertionError(
            "La rete non deve essere "
            "chiamata"
        )

    monkeypatch.setattr(
        health_module
        .urllib.request,
        "urlopen",
        should_not_open,
    )

    result = StreamHealthChecker(
        deep_hls_check=True,
        expected_country="IT",
    ).check(
        make_channel(
            "Canale USA",
            url,
            attributes={
                "tvg-country": "US",
            },
        )
    )

    assert result.status == "offline"
    assert (
        result.classification_reason
        == "country_mismatch"
    )
    assert result.country_check == (
        "mismatch"
    )


def test_legacy_mode_keeps_old_hls_signature_behaviour(
    monkeypatch,
) -> None:
    url = (
        "https://stream.test/"
        "legacy.m3u8"
    )

    install_responses(
        monkeypatch,
        {
            url: FakeResponse(
                data=(
                    b"#EXTM3U\n"
                    b"#EXT-X-VERSION:3\n"
                ),
                content_type=(
                    "text/plain"
                ),
                final_url=url,
            ),
        },
    )

    result = StreamHealthChecker(
        deep_hls_check=False,
    ).check(
        make_channel(
            "Legacy",
            url,
        )
    )

    assert result.status == "online"
    assert (
        result.classification_reason
        == "hls_signature"
    )
