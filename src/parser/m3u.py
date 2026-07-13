import re
from src.models.channel import Channel
ATTR=re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
class M3UParser:
    def parse(self,text:str,source_id:str):
        out=[]; info=None; extra=[]
        for raw in text.replace('\r','').split('\n'):
            line=raw.strip()
            if not line: continue
            if line.startswith('#EXTINF:'): info=line; extra=[]; continue
            if info and line.startswith('#'): extra.append(line); continue
            if info and not line.startswith('#'):
                if ',' in info:
                    meta,name=info.split(',',1); attrs=dict(ATTR.findall(meta)); name=name.strip()
                    if name and line:
                        out.append(Channel(name,line,attrs.get('group-title',''),attrs.get('tvg-id',''),attrs.get('tvg-name',''),attrs.get('tvg-logo',''),source_id,attrs,list(extra)))
                info=None; extra=[]
        return out
