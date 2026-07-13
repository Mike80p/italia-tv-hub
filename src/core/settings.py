import json
from dataclasses import dataclass
from pathlib import Path
@dataclass(slots=True,frozen=True)
class Settings:
    output_file:str; report_file:str; request_timeout_seconds:int; retry_count:int; user_agent:str
    @classmethod
    def load(cls,path:Path):
        d=json.loads(path.read_text(encoding='utf-8'))
        return cls(d['output_file'],d['report_file'],int(d.get('request_timeout_seconds',20)),int(d.get('retry_count',2)),d.get('user_agent','Italia-TV-Hub/0.2'))
