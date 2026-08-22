from __future__ import annotations
import re
ATTR = re.compile(r'([\w-]+)="([^"]*)"')

def parse_m3u(text: str) -> list[dict]:
    lines = text.replace("\r","").split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        attrs = dict(ATTR.findall(line))
        name = line.rsplit(",",1)[-1].strip() if "," in line else attrs.get("tvg-name","Canale")
        j, url = i + 1, ""
        while j < len(lines):
            candidate = lines[j].strip()
            if candidate and not candidate.startswith("#"):
                url = candidate
                break
            j += 1
        out.append({
            "name": name,
            "tvg_id": attrs.get("tvg-id",""),
            "tvg_name": attrs.get("tvg-name",""),
            "logo": attrs.get("tvg-logo",""),
            "group": attrs.get("group-title",""),
            "url": url,
        })
        i = max(i+1, j+1)
    return out
