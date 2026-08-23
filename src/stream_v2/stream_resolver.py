from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl
from typing import Callable, Iterable

EXPIRY_KEYS={"exp","expires","expiry","expire","token_exp","e"}
DYNAMIC_HINTS=("token=","jwt=","session=","hdnea=","policy=","signature=","expires=","exp=")

@dataclass(frozen=True)
class StreamCandidate:
    url:str
    source_id:str
    priority:int=100
    stable_endpoint:str=""
    dynamic:bool|None=None

@dataclass(frozen=True)
class ProbeResult:
    url:str
    ok:bool
    score:float
    reason:str=""
    http_status:int|None=None

@dataclass(frozen=True)
class Resolution:
    selected_url:str
    source_id:str
    refreshed:bool
    fallback_used:bool
    attempts:tuple[dict,...]

def looks_dynamic(url:str)->bool:
    low=(url or "").casefold()
    if any(h in low for h in DYNAMIC_HINTS): return True
    return any(k.casefold() in EXPIRY_KEYS for k,_ in parse_qsl(urlsplit(url).query,keep_blank_values=True))

def unix_expiry(url:str)->int|None:
    q=dict(parse_qsl(urlsplit(url).query,keep_blank_values=True))
    for k,v in q.items():
        if k.casefold() in EXPIRY_KEYS and str(v).isdigit():
            ts=int(v); return ts//1000 if ts>10_000_000_000 else ts
    return None

def is_expired(url:str,*,now_ts:int|None=None,safety_seconds:int=120)->bool:
    exp=unix_expiry(url)
    if exp is None: return False
    if now_ts is None: now_ts=int(datetime.now(timezone.utc).timestamp())
    return exp <= now_ts+safety_seconds

class StreamResolver:
    def __init__(self,probe:Callable[[str],ProbeResult],refresh:Callable[[StreamCandidate],str|None],*,minimum_score:float=60.0):
        self.probe=probe; self.refresh=refresh; self.minimum_score=float(minimum_score)

    def resolve(self,candidates:Iterable[StreamCandidate],*,now_ts:int|None=None)->Resolution:
        ordered=sorted(candidates,key=lambda c:(c.priority,c.source_id,c.url))
        attempts=[]; refreshed_any=False
        for idx,c in enumerate(ordered):
            dynamic=looks_dynamic(c.url) if c.dynamic is None else c.dynamic
            url=c.url; refreshed=False
            if dynamic or is_expired(url,now_ts=now_ts):
                fresh=self.refresh(c)
                if fresh: url=fresh; refreshed=refreshed_any=True
            r=self.probe(url)
            attempts.append({"source_id":c.source_id,"url":url,"refreshed":refreshed,"ok":r.ok,"score":r.score,"reason":r.reason,"http_status":r.http_status})
            if r.ok and r.score>=self.minimum_score:
                return Resolution(url,c.source_id,refreshed_any,idx>0,tuple(attempts))
            if not refreshed:
                fresh=self.refresh(c)
                if fresh and fresh!=url:
                    refreshed_any=True; r2=self.probe(fresh)
                    attempts.append({"source_id":c.source_id,"url":fresh,"refreshed":True,"ok":r2.ok,"score":r2.score,"reason":r2.reason,"http_status":r2.http_status})
                    if r2.ok and r2.score>=self.minimum_score:
                        return Resolution(fresh,c.source_id,True,idx>0,tuple(attempts))
        return Resolution("","",refreshed_any,len(ordered)>1,tuple(attempts))
