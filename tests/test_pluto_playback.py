from pathlib import Path

from src.health.checker import HealthResult
from src.models.channel import Channel
from src.pluto.playback import PlutoPlaybackEngine


class FakeChecker:
    def check_many(self, channels):
        results = []
        for channel in channels:
            ok = "good" in channel.stream_url
            results.append(
                HealthResult(
                    name=channel.name,
                    stream_url=channel.stream_url,
                    source_id=channel.source_id,
                    status="online" if ok else "offline",
                    http_status=200 if ok else 403,
                    response_ms=10,
                    content_type="application/vnd.apple.mpegurl" if ok else "",
                    final_url=channel.stream_url,
                    error="" if ok else "HTTP 403",
                    health_score=95 if ok else 0,
                    classification_reason="hls_signature" if ok else "http_error",
                    bytes_read=128 if ok else 0,
                    redirected=False,
                    error_type="" if ok else "HTTPError",
                )
            )
        return results


def test_verifies_only_pluto_and_builds_samsung_output(tmp_path: Path):
    rai = Channel("Rai 1", "https://example.test/rai.m3u8", source_id="rai")
    good = Channel("Pluto Good", "https://good.jmp2.uk/plu-good.m3u8", source_id="pluto")
    bad = Channel("Pluto Bad", "https://bad.jmp2.uk/plu-bad.m3u8", source_id="pluto")

    engine = PlutoPlaybackEngine(FakeChecker(), minimum_score=70)
    result = engine.verify([rai, good, bad])

    assert result.checked == 2
    assert result.accepted == 1
    assert result.rejected == 1

    samsung = engine.build_samsung_playlist_channels([rai, good, bad], result)
    assert [channel.name for channel in samsung] == ["Rai 1", "Pluto Good"]

    report = tmp_path / "pluto-report.json"
    engine.write_report(report, result)
    assert report.exists()
    assert '"accepted": 1' in report.read_text(encoding="utf-8")


def test_identifies_direct_pluto_hosts():
    channel = Channel(
        "Cinema",
        "https://service-stitcher.clusters.pluto.tv/path/master.m3u8",
        source_id="external",
    )
    assert PlutoPlaybackEngine.is_pluto_channel(channel)
