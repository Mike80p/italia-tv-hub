from pathlib import Path
import json

from src.epg_v2.identity_registry import ChannelIdentityRegistry
from src.epg_v2.m3u import parse_m3u
from src.epg_v2.epg_unifier import Programme, EpgUnifier

ROOT = Path(__file__).resolve().parents[1]
seed = json.loads((ROOT / "config" / "channel_registry_seed_v2.json").read_text(encoding="utf-8"))
registry = ChannelIdentityRegistry(seed)


def test_rai_variants_converge():
    ids = {
        registry.resolve(name="Rai 1 (720p)").channel_id,
        registry.resolve(name="Rai 1 G").channel_id,
        registry.resolve(tvg_id="Rai1.it@SD").channel_id,
        registry.resolve(tvg_id="Rai1.it").channel_id,
    }
    assert ids == {"it.rai.rai1"}


def test_regional_variants_stay_distinct():
    assert registry.resolve(name="Rai 3 TGR Puglia").channel_id != registry.resolve(name="Rai 3 TGR Lazio").channel_id


def test_m3u_duplicates_keep_alternative_streams():
    sample = '''#EXTM3U
#EXTINF:-1 tvg-id="Rai1.it@SD" tvg-name="Rai 1" group-title="RAI",Rai 1 (720p)
https://example.test/rai1-a.m3u8
#EXTINF:-1 tvg-id="Rai1.it" tvg-name="Rai 1" group-title="RAI",Rai 1 G
https://example.test/rai1-b.m3u8
'''
    built = registry.build_registry(parse_m3u(sample))
    assert len(built["channels"]) == 1
    assert len(built["channels"][0]["streams"]) == 2


def test_higher_priority_epg_wins_collision():
    u = EpgUnifier()
    low = Programme("it.rai.rai1", "20260822180000 +0200", "20260822190000 +0200", "TG1", source_id="low", source_priority=50)
    high = Programme("it.rai.rai1", "20260822180000 +0200", "20260822190000 +0200", "TG1", description="Edizione serale", source_id="high", source_priority=10)
    merged = u.merge([low, high])
    assert len(merged) == 1
    assert merged[0].source_id == "high"
