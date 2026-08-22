from __future__ import annotations
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

@dataclass(frozen=True)
class Programme:
    channel_id: str
    start: str
    stop: str
    title: str
    description: str = ""
    category: str = ""
    icon: str = ""
    source_id: str = ""
    source_priority: int = 100

def programme_key(p: Programme):
    return (p.channel_id, p.start, p.stop, p.title.casefold().strip())

class EpgUnifier:
    def merge(self, programmes: list[Programme]) -> list[Programme]:
        best = {}
        for p in programmes:
            key = programme_key(p)
            current = best.get(key)
            if current is None or p.source_priority < current.source_priority:
                best[key] = p
        return sorted(best.values(), key=lambda p: (p.channel_id, p.start, p.stop, p.title.casefold()))

    @staticmethod
    def write_json(path: Path, channels: list[dict], programmes: list[Programme]):
        payload = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "channels": channels,
            "programmes": [asdict(p) for p in programmes],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def write_xmltv(path: Path, channels: list[dict], programmes: list[Programme]):
        tv = ET.Element("tv", {"generator-info-name":"Italia TV Hub EPG V2"})
        for c in channels:
            node = ET.SubElement(tv, "channel", {"id": c["channel_id"]})
            ET.SubElement(node, "display-name", {"lang":"it"}).text = c["name"]
            if c.get("logo"):
                ET.SubElement(node, "icon", {"src": c["logo"]})
        for p in programmes:
            node = ET.SubElement(tv, "programme", {"channel":p.channel_id, "start":p.start, "stop":p.stop})
            ET.SubElement(node, "title", {"lang":"it"}).text = p.title
            if p.description:
                ET.SubElement(node, "desc", {"lang":"it"}).text = p.description
            if p.category:
                ET.SubElement(node, "category", {"lang":"it"}).text = p.category
            if p.icon:
                ET.SubElement(node, "icon", {"src":p.icon})
        ET.ElementTree(tv).write(path, encoding="utf-8", xml_declaration=True)
