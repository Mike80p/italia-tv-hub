from dataclasses import dataclass
import re
from urllib.parse import urlsplit

PLUTO_ID = re.compile(r"/(?:v\d+/)?stitch/hls/channel/([a-f0-9]{24})/", re.I)
JMP2_PLUTO = re.compile(r"^https://jmp2\.uk/plu-([a-f0-9]{24})\.m3u8(?:[?#].*)?$", re.I)
SAMSUNG_JMP2 = re.compile(r"^https://jmp2\.uk/stvp-([A-Za-z0-9]+)(?:\.m3u8)?(?:[?#].*)?$", re.I)

@dataclass(frozen=True)
class AdapterResult:
    provider: str
    stable_endpoint: str
    refreshable: bool
    reason: str

def classify_provider(url: str, tvg_id: str = "", attributes: dict | None = None) -> AdapterResult:
    attributes = attributes or {}
    host = (urlsplit(url).hostname or "").casefold()

    if host.endswith("rai.it") or "relinkerservlet" in url.casefold():
        return AdapterResult(
            "rai",
            url,
            "relinkerservlet" in url.casefold(),
            "preserve Rai relinker",
        )

    match = JMP2_PLUTO.match(url)
    if match:
        return AdapterResult(
            "pluto",
            f"https://jmp2.uk/plu-{match.group(1).casefold()}.m3u8",
            True,
            "existing Pluto resolver",
        )

    if "pluto.tv" in host:
        match = PLUTO_ID.search(urlsplit(url).path)
        channel_id = (
            match.group(1).casefold()
            if match
            else (
                tvg_id.casefold()
                if re.fullmatch(r"[a-f0-9]{24}", tvg_id or "", re.I)
                else ""
            )
        )
        if channel_id:
            return AdapterResult(
                "pluto",
                f"https://jmp2.uk/plu-{channel_id}.m3u8",
                True,
                "derived Pluto resolver",
            )
        return AdapterResult("pluto", url, False, "missing Pluto id")

    match = SAMSUNG_JMP2.match(url)
    channel_id = (
        match.group(1) if match else ""
    ) or str(attributes.get("channel-id", "")).strip()
    if channel_id:
        return AdapterResult(
            "samsung",
            f"https://jmp2.uk/stvp-{channel_id}",
            True,
            "stable Samsung resolver",
        )

    return AdapterResult("generic", url, False, "generic probe/fallback")
