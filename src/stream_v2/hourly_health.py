from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict

@dataclass(frozen=True)
class HealthObservation:
    channel_id:str
    source_id:str
    hour:int
    ok:bool
    score:float

def summarize(observations:list[HealthObservation])->dict:
    buckets=defaultdict(list)
    for o in observations: buckets[(o.channel_id,o.source_id,o.hour)].append(o)
    rows=[]
    for (cid,sid,hour),items in sorted(buckets.items()):
        rows.append({"channel_id":cid,"source_id":sid,"hour":hour,"samples":len(items),
                     "ok_rate":round(sum(1 for x in items if x.ok)/len(items),4),
                     "average_score":round(sum(x.score for x in items)/len(items),2)})
    return {"rows":rows}
