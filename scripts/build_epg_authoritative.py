from __future__ import annotations
import argparse, gzip, json, re, shutil
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

DOCTYPE_RE = re.compile(rb"<!DOCTYPE\s+[^>\[]*(?:\[(?:[^\]]|\](?!>))*\]\s*)?>", re.I|re.S)
ENTITY_RE = re.compile(rb"<!ENTITY\b", re.I)
TS_RE = re.compile(r"^(\d{14})")

def parse_dt(v):
    m=TS_RE.match((v or "").strip())
    if not m: return None
    try: return datetime.strptime(m.group(1),"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError: return None

def download(url, timeout=30):
    req=urllib.request.Request(url,headers={"User-Agent":"Italia-TV-Hub-EPG/1.0"})
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        return resp.read()

def sanitize(data, url=""):
    if data.startswith(b"\x1f\x8b") or url.lower().endswith(".gz"):
        data=gzip.decompress(data)
    if ENTITY_RE.search(data[:262144]):
        raise ValueError("ENTITY declarations forbidden")
    data,_=DOCTYPE_RE.subn(b"",data,count=1)
    if b"<!doctype" in data[:262144].lower():
        raise ValueError("unsupported DOCTYPE")
    return data

def load_doc(data, url):
    root=ET.fromstring(sanitize(data,url))
    if root.tag.rsplit("}",1)[-1]!="tv": raise ValueError("not XMLTV")
    return root

def fresh_programme(p, now, past_hours=6, future_days=10):
    start=parse_dt(p.attrib.get("start","")); stop=parse_dt(p.attrib.get("stop","")); point=stop or start
    if not point: return False
    return now-timedelta(hours=past_hours) <= point <= now+timedelta(days=future_days)

def merge(roots, now=None):
    now=now or datetime.now(timezone.utc)
    channels={}; programmes={}
    for priority, source_id, root in roots:
        for c in root.findall("channel"):
            cid=(c.attrib.get("id") or "").strip()
            if cid and cid.casefold() not in channels:
                channels[cid.casefold()]=(priority,source_id,c)
        for p in root.findall("programme"):
            if not fresh_programme(p,now): continue
            cid=(p.attrib.get("channel") or "").strip(); title=(p.findtext("title") or "").strip().casefold()
            key=(cid.casefold(),p.attrib.get("start",""),p.attrib.get("stop",""),title)
            old=programmes.get(key)
            if old is None or priority < old[0]: programmes[key]=(priority,source_id,p)
    used={k[0] for k in programmes}
    out=ET.Element("tv",{"generator-info-name":"Italia TV Hub Authoritative EPG"})
    for key,(pri,sid,c) in sorted(channels.items()):
        if key in used: out.append(c)
    for key,(pri,sid,p) in sorted(programmes.items(), key=lambda x:(x[0][0],x[0][1],x[0][3])): out.append(p)
    return ET.ElementTree(out), len(used), len(programmes)

def build(config_path, candidate_path, report_path, now=None):
    cfg=json.loads(Path(config_path).read_text(encoding="utf-8")); roots=[]; reports=[]
    for s in sorted(cfg["sources"],key=lambda x:x["priority"]):
        try:
            data=download(s["url"],cfg.get("timeout_seconds",30)); root=load_doc(data,s["url"])
            roots.append((int(s["priority"]),s["id"],root)); reports.append({"id":s["id"],"status":"ok","channels":len(root.findall("channel")),"programmes":len(root.findall("programme"))})
        except Exception as e: reports.append({"id":s["id"],"status":"error","error":str(e)})
    tree, channel_count, programme_count=merge(roots,now=now)
    candidate_path=Path(candidate_path); candidate_path.parent.mkdir(parents=True,exist_ok=True); tree.write(candidate_path,encoding="utf-8",xml_declaration=True)
    payload={"sources":reports,"output_channels":channel_count,"output_programmes":programme_count}; Path(report_path).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if programme_count == 0: raise RuntimeError("candidate EPG contains zero current programmes")
    return payload

def publish(candidate, live, last_good):
    candidate=Path(candidate); live=Path(live); last_good=Path(last_good); root=ET.parse(candidate).getroot()
    if not root.findall("programme"): raise RuntimeError("refusing empty EPG")
    live.parent.mkdir(parents=True,exist_ok=True)
    if live.exists() and live.stat().st_size:
        last_good.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(live,last_good)
    tmp=live.with_suffix(live.suffix+".tmp"); shutil.copy2(candidate,tmp); tmp.replace(live)

def main():
    a=argparse.ArgumentParser(); a.add_argument("--config",default="config/epg_authoritative_sources.json"); a.add_argument("--candidate",default="output/epg.candidate.xml"); a.add_argument("--live",default="output/epg.xml"); a.add_argument("--last-good",default="output/epg.last_good.xml"); a.add_argument("--report",default="output/epg-authoritative-report.json"); args=a.parse_args(); build(args.config,args.candidate,args.report); publish(args.candidate,args.live,args.last_good)

if __name__=="__main__": main()
