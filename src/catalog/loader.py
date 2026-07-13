import json
from pathlib import Path
from src.models.source import Source
def load_sources(directory:Path):
    out=[]; ids=set()
    for path in sorted(directory.glob('*.json')):
        data=json.loads(path.read_text(encoding='utf-8'))
        for item in data.get('sources',[]):
            s=Source(str(item.get('id','')),str(item.get('name','')),str(item.get('url','')),bool(item.get('enabled',True)),int(item.get('priority',100)))
            s.validate()
            if s.id in ids: raise ValueError(f'ID duplicato: {s.id}')
            ids.add(s.id)
            if s.enabled: out.append(s)
    return sorted(out,key=lambda x:(x.priority,x.id))
