from src.stream_v2.stream_resolver import (
    ProbeResult,
    StreamCandidate,
    StreamResolver,
    is_expired,
    looks_dynamic,
)
from src.stream_v2.hourly_health import HealthObservation, summarize


def test_dynamic_and_expiry_detection():
    assert looks_dynamic("https://x/live.m3u8?token=a")
    assert is_expired("https://x/live.m3u8?exp=1000", now_ts=2000)


def test_refresh_before_playback():
    probes = {
        "https://stable/relink?fresh=1": ProbeResult(
            "x", True, 92, "ok", 200
        )
    }

    def probe(url):
        return probes.get(url, ProbeResult(url, False, 0, "fail", 403))

    def refresh(candidate):
        return candidate.stable_endpoint + "?fresh=1"

    result = StreamResolver(probe, refresh).resolve(
        [
            StreamCandidate(
                "https://cdn/a.m3u8?exp=1000",
                "rai",
                1,
                "https://stable/relink",
            )
        ],
        now_ts=2000,
    )
    assert result.refreshed
    assert result.source_id == "rai"


def test_fallback_alternative():
    probes = {
        "https://alt/live.m3u8": ProbeResult(
            "x", True, 85, "ok", 200
        )
    }

    def probe(url):
        return probes.get(url, ProbeResult(url, False, 0, "fail", 403))

    result = StreamResolver(probe, lambda _candidate: None).resolve(
        [
            StreamCandidate("https://bad/live.m3u8", "a", 1),
            StreamCandidate("https://alt/live.m3u8", "b", 2),
        ]
    )
    assert result.source_id == "b"
    assert result.fallback_used


def test_hourly_health_separates_time_windows():
    report = summarize(
        [
            HealthObservation("rai1", "a", 17, True, 90),
            HealthObservation("rai1", "a", 23, False, 0),
        ]
    )
    rows = {row["hour"]: row for row in report["rows"]}
    assert rows[17]["ok_rate"] == 1.0
    assert rows[23]["ok_rate"] == 0.0
