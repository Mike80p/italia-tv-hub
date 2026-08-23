from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
import xml.etree.ElementTree as ET
from pathlib import Path

XMLTV_TS = re.compile(r"^(\d{14})")

@dataclass(frozen=True)
class Validation:
    valid: bool
    channel_count: int
    programme_count: int
    current_or_future_programmes: int
    latest_stop: str
    reason: str

def _parse_dt(value: str):
    m = XMLTV_TS.match((value or "").strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def validate_xmltv(text: str, *, now: datetime | None = None, max_stale_hours: int = 30) -> Validation:
    now = now or datetime.now(timezone.utc)
    if not text or not text.strip():
        return Validation(False,0,0,0,"","empty XMLTV")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return Validation(False,0,0,0,"",f"invalid XML: {exc}")
    if root.tag.rsplit("}",1)[-1].lower() != "tv":
        return Validation(False,0,0,0,"","root is not tv")
    channels = root.findall("channel")
    programmes = root.findall("programme")
    if not programmes:
        return Validation(False,len(channels),0,0,"","no programmes")
    stops=[]
    fresh=0
    stale_cutoff = now - timedelta(hours=max_stale_hours)
    for p in programmes:
        dt = _parse_dt(p.attrib.get("stop",""))
        if dt:
            stops.append(dt)
            if dt >= stale_cutoff:
                fresh += 1
    latest=max(stops) if stops else None
    if not latest:
        return Validation(False,len(channels),len(programmes),0,"","no parseable programme stop")
    if fresh == 0:
        return Validation(False,len(channels),len(programmes),0,latest.isoformat(),"all programmes stale")
    return Validation(True,len(channels),len(programmes),fresh,latest.isoformat(),"ok")

def atomic_publish(candidate: Path, live: Path, backup: Path, *, now: datetime | None = None) -> Validation:
    text = candidate.read_text(encoding="utf-8")
    result = validate_xmltv(text, now=now)
    if not result.valid:
        return result
    live.parent.mkdir(parents=True, exist_ok=True)
    if live.exists() and live.stat().st_size:
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(live.read_bytes())
    temp=live.with_suffix(live.suffix+".tmp")
    temp.write_text(text,encoding="utf-8",newline="\n")
    temp.replace(live)
    return result
