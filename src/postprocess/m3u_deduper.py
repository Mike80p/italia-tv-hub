from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
QUALITY_SUFFIX_RE = re.compile(r'@(sd|hd|fhd|uhd|4k)$', re.IGNORECASE)
QUALITY_NAME_RE = re.compile(
    r'\s*(?:\((?:\d{3,4}p|\d{3,4}i|sd|hd|fhd|uhd|4k)\)|'
    r'\b(?:sd|hd|fhd|uhd|4k|\d{3,4}p|\d{3,4}i)\b)\s*$',
    re.IGNORECASE,
)
NON_ALNUM_RE = re.compile(r'[^a-z0-9]+')


@dataclass
class Entry:
    lines: list[str]
    extinf: str


def _norm(value: str) -> str:
    return NON_ALNUM_RE.sub('', value.casefold())


def canonical_tvg_id(extinf: str) -> str:
    attrs = dict(ATTR_RE.findall(extinf))
    raw = attrs.get('tvg-id', '').strip()
    raw = QUALITY_SUFFIX_RE.sub('', raw)
    return _norm(raw)


def canonical_name(extinf: str) -> str:
    name = extinf.split(',', 1)[1].strip() if ',' in extinf else ''
    previous = None
    while previous != name:
        previous = name
        name = QUALITY_NAME_RE.sub('', name).strip()

    # Some source catalogs append a single "G" marker to display names.
    if name.endswith(' G') and len(name) > 2:
        name = name[:-2].rstrip()

    return _norm(name)


def split_m3u(text: str) -> tuple[list[str], list[Entry]]:
    lines = text.splitlines()
    preamble: list[str] = []
    entries: list[Entry] = []
    current: list[str] | None = None
    extinf = ''

    for line in lines:
        if line.startswith('#EXTINF:'):
            if current is not None:
                entries.append(Entry(current, extinf))
            current = [line]
            extinf = line
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)

    if current is not None:
        entries.append(Entry(current, extinf))

    return preamble, entries


def dedupe_m3u_text(text: str) -> tuple[str, int]:
    preamble, entries = split_m3u(text)
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    kept: list[Entry] = []
    removed = 0

    for entry in entries:
        tvg_id = canonical_tvg_id(entry.extinf)
        name = canonical_name(entry.extinf)
        duplicate = (
            (bool(tvg_id) and tvg_id in seen_ids)
            or (bool(name) and name in seen_names)
        )

        if duplicate:
            removed += 1
            continue

        kept.append(entry)
        if tvg_id:
            seen_ids.add(tvg_id)
        if name:
            seen_names.add(name)

    out_lines = preamble[:]
    for entry in kept:
        out_lines.extend(entry.lines)

    return '\n'.join(out_lines).rstrip() + '\n', removed


def dedupe_file(path: Path) -> int:
    original = path.read_text(encoding='utf-8')
    cleaned, removed = dedupe_m3u_text(original)
    path.write_text(cleaned, encoding='utf-8', newline='\n')
    return removed


def dedupe_outputs(root: Path) -> dict[str, int]:
    results: dict[str, int] = {}
    for relative in ('output/playlist.m3u', 'output/playlist_samsung.m3u'):
        path = root / relative
        if path.exists():
            results[relative] = dedupe_file(path)
    return results
