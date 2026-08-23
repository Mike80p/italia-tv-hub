from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

DOCTYPE_RE = re.compile(rb'<!DOCTYPE\s+[^>\[]*(?:\[(?:[^\]]|\](?!>))*\]\s*)?>', re.I | re.S)
ENTITY_RE = re.compile(rb'<!ENTITY\b', re.I)
VARIANT_RE = re.compile(r'@(?:SD|HD|FHD|UHD|4K)$', re.I)
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

@dataclass(frozen=True)
class SourceResult:
    url: str
    ok: bool
    channels: int = 0
    programmes: int = 0
    error: str = ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ItaliaTVHub-EPG/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sanitize_xmltv(data: bytes, url: str) -> bytes:
    if data.startswith(b"\x1f\x8b") or urlparse(url).path.lower().endswith(".gz"):
        data = gzip.decompress(data)
    if ENTITY_RE.search(data[:262144]):
        raise ValueError("ENTITY declarations forbidden")
    data, _ = DOCTYPE_RE.subn(b"", data, count=1)
    if b"<!doctype" in data[:262144].lower():
        raise ValueError("unsupported/multiple DOCTYPE")
    root = ET.fromstring(data)
    if root.tag.rsplit("}", 1)[-1].lower() != "tv":
        raise ValueError("root is not <tv>")
    return data


def parse_xmltv(data: bytes) -> tuple[dict[str, ET.Element], list[ET.Element]]:
    root = ET.fromstring(data)
    channels: dict[str, ET.Element] = {}
    programmes: list[ET.Element] = []
    folded: set[str] = set()
    for child in root:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "channel":
            cid = (child.get("id") or "").strip()
            if cid and cid.casefold() not in folded:
                channels[cid] = child
                folded.add(cid.casefold())
        elif tag == "programme":
            if (child.get("channel") or "").strip():
                programmes.append(child)
    return channels, programmes


def parse_playlist_ids(text: str) -> set[str]:
    ids: set[str] = set()
    for line in text.replace("\r", "").split("\n"):
        if not line.startswith("#EXTINF:"):
            continue
        attrs = dict(ATTR_RE.findall(line))
        tvg_id = attrs.get("tvg-id", "").strip()
        if tvg_id:
            ids.add(tvg_id)
    return ids


def canonical_id(value: str) -> str:
    return VARIANT_RE.sub("", value.strip())


def clone_element(elem: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(elem, encoding="utf-8"))


def build_merged(source_docs: list[bytes], playlist_ids: set[str]) -> tuple[bytes, dict]:
    channels: dict[str, ET.Element] = {}
    programmes_by_key: dict[tuple[str, str, str, str], ET.Element] = {}
    for data in source_docs:
        src_channels, src_programmes = parse_xmltv(data)
        for cid, elem in src_channels.items():
            channels.setdefault(cid.casefold(), clone_element(elem))
        for p in src_programmes:
            cid = (p.get("channel") or "").strip()
            start = (p.get("start") or "").strip()
            stop = (p.get("stop") or "").strip()
            title_node = next((x for x in p if x.tag.rsplit("}", 1)[-1] == "title"), None)
            title = ((title_node.text if title_node is not None else "") or "").strip().casefold()
            programmes_by_key.setdefault((cid.casefold(), start, stop, title), clone_element(p))
    alias_map: dict[str, str] = {}
    known = {k: v for k, v in channels.items()}
    for pid in sorted(playlist_ids):
        pkey = pid.casefold()
        if pkey in known:
            continue
        canon = canonical_id(pid)
        ckey = canon.casefold()
        if ckey in known:
            alias_map[pid] = canon
            clone = clone_element(known[ckey])
            clone.set("id", pid)
            channels[pkey] = clone
    original_programmes = list(programmes_by_key.values())
    for pid, canon in alias_map.items():
        for p in original_programmes:
            if (p.get("channel") or "").casefold() != canon.casefold():
                continue
            cp = clone_element(p)
            cp.set("channel", pid)
            start = (cp.get("start") or "").strip()
            stop = (cp.get("stop") or "").strip()
            title_node = next((x for x in cp if x.tag.rsplit("}", 1)[-1] == "title"), None)
            title = ((title_node.text if title_node is not None else "") or "").strip().casefold()
            programmes_by_key.setdefault((pid.casefold(), start, stop, title), cp)
    tv = ET.Element("tv", {"generator-info-name": "Italia TV Hub Authoritative EPG"})
    for key in sorted(channels):
        tv.append(channels[key])
    for key in sorted(programmes_by_key):
        tv.append(programmes_by_key[key])
    xml = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
    return xml + b"\n", {"channels": len(channels), "programmes": len(programmes_by_key), "aliases_created": len(alias_map)}


def parse_xmltv_dt(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    match = re.match(r"^(\d{14})(?:\s*([+-]\d{4}|Z))?", value)
    if not match:
        return None
    base = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    tz = match.group(2)
    if tz == "Z" or tz is None:
        return base.replace(tzinfo=timezone.utc)
    sign = 1 if tz[0] == "+" else -1
    offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
    return base.replace(tzinfo=timezone(offset)).astimezone(timezone.utc)


def validate_output(xml: bytes, now: datetime, freshness_hours: int = 36) -> dict:
    root = ET.fromstring(xml)
    programmes = [x for x in root if x.tag.rsplit("}", 1)[-1] == "programme"]
    if not programmes:
        raise ValueError("EPG has zero programmes")
    latest = None
    for p in programmes:
        dt = parse_xmltv_dt(p.get("stop") or p.get("start") or "")
        if dt is not None and (latest is None or dt > latest):
            latest = dt
    if latest is None:
        raise ValueError("EPG has no parseable programme timestamps")
    if latest < now.astimezone(timezone.utc) - timedelta(hours=freshness_hours):
        raise ValueError(f"EPG is stale: latest programme ends {latest.isoformat()}")
    return {"programmes": len(programmes), "latest_programme_end": latest.isoformat()}


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=check)


def publish(repo: Path, sources: list[str], timeout: int, no_push: bool = False, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    playlist = (repo / "output" / "playlist.m3u").read_text(encoding="utf-8")
    playlist_ids = parse_playlist_ids(playlist)
    docs: list[bytes] = []
    source_results: list[SourceResult] = []
    for url in sources:
        try:
            clean = sanitize_xmltv(fetch_bytes(url, timeout=timeout), url)
            channels, programmes = parse_xmltv(clean)
            docs.append(clean)
            source_results.append(SourceResult(url, True, len(channels), len(programmes)))
        except Exception as exc:
            source_results.append(SourceResult(url, False, error=str(exc)))
    if not docs:
        raise RuntimeError("all EPG sources failed")
    xml, stats = build_merged(docs, playlist_ids)
    validation = validate_output(xml, now)
    stats.update(validation)
    stats["source_success"] = sum(1 for x in source_results if x.ok)
    stats["source_failed"] = sum(1 for x in source_results if not x.ok)
    stats["sources"] = [x.__dict__ for x in source_results]
    stats["sha256"] = sha256_bytes(xml)
    out = repo / "output" / "epg.xml"
    report = repo / "output" / "epg-authoritative-report.json"
    last_good = repo / "output" / "epg.last-good.xml"
    current = out.read_bytes() if out.exists() else b""
    if current == xml:
        print("NO_CHANGE")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=out.parent) as fh:
        fh.write(xml)
        tmp_name = fh.name
    if current:
        last_good.write_bytes(current)
    os.replace(tmp_name, out)
    report.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_git(repo, "add", "output/epg.xml", "output/epg-authoritative-report.json")
    if last_good.exists():
        run_git(repo, "add", "output/epg.last-good.xml")
    if run_git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("NO_STAGED_CHANGE")
        return 0
    run_git(repo, "commit", "-m", "chore(epg): refresh authoritative guide [skip ci]")
    if not no_push:
        run_git(repo, "push")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    settings = json.loads((repo / args.settings).read_text(encoding="utf-8"))
    sources = list(settings.get("epg_sources") or [])
    if not sources:
        raise SystemExit("No epg_sources configured")
    return publish(repo, sources, args.timeout, args.no_push)

if __name__ == "__main__":
    raise SystemExit(main())
