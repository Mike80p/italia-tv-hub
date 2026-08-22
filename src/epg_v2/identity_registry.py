from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass
from typing import Iterable

QUALITY = re.compile(r"\b(?:4k|uhd|fhd|full\s*hd|hd|sd|1080p|1080i|720p|576p|480p)\b", re.I)
PAREN_QUALITY = re.compile(r"\(\s*(?:4k|uhd|fhd|full\s*hd|hd|sd|1080p|1080i|720p|576p|480p)\s*\)", re.I)
SOURCE_SUFFIX = re.compile(r"\s+[gG]\s*$")
TVG_VARIANT = re.compile(r"@(?:SD|HD|FHD|UHD|4K)$", re.I)

def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = TVG_VARIANT.sub("", value)
    value = PAREN_QUALITY.sub(" ", value)
    value = QUALITY.sub(" ", value)
    value = SOURCE_SUFFIX.sub("", value)
    value = value.replace(".", " ")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().casefold()
    return re.sub(r"\s+", " ", value)

@dataclass(frozen=True)
class Identity:
    channel_id: str
    canonical_name: str
    category: str
    matched_by: str

class ChannelIdentityRegistry:
    def __init__(self, seed: dict):
        self._aliases, self._entries = {}, {}
        for item in seed.get("channels", []):
            cid = item["channel_id"]
            self._entries[cid] = item
            for alias in set(item.get("aliases", []) + [item.get("name","")]):
                key = fold(alias)
                if key:
                    self._aliases[key] = cid

    def resolve(self, *, name: str="", tvg_id: str="", tvg_name: str="") -> Identity:
        for source in (tvg_id, tvg_name, name):
            key = fold(source)
            if key in self._aliases:
                item = self._entries[self._aliases[key]]
                return Identity(item["channel_id"], item["name"], item.get("category","ALTRO"), "seed_alias")
        best = fold(tvg_name) or fold(name) or fold(tvg_id)
        slug = re.sub(r"[^a-z0-9]+", ".", best).strip(".") or "unknown"
        return Identity(f"it.auto.{slug}", name or tvg_name or tvg_id or "Canale", "ALTRO", "derived")

    def build_registry(self, channels: Iterable[dict]) -> dict:
        merged = {}
        for channel in channels:
            ident = self.resolve(name=channel.get("name",""), tvg_id=channel.get("tvg_id",""), tvg_name=channel.get("tvg_name",""))
            entry = merged.setdefault(ident.channel_id, {"channel_id": ident.channel_id, "name": ident.canonical_name, "category": ident.category, "aliases": set(), "streams": []})
            for value in (channel.get("name",""), channel.get("tvg_id",""), channel.get("tvg_name","")):
                if value:
                    entry["aliases"].add(value)
            if channel.get("url"):
                entry["streams"].append(channel["url"])
        output = []
        for item in merged.values():
            item["aliases"] = sorted(item["aliases"])
            item["streams"] = list(dict.fromkeys(item["streams"]))
            output.append(item)
        return {"version": 1, "channels": sorted(output, key=lambda x: x["channel_id"])}
