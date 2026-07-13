from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

@dataclass(slots=True,frozen=True)
class Source:
    id:str; name:str; url:str; enabled:bool=True; priority:int=100
    def validate(self):
        if not self.id or not self.name or not self.url: raise ValueError("Sorgente incompleta")
        if urlparse(self.url).scheme not in {"","file","http","https"}: raise ValueError("Schema non supportato")
    def is_remote(self): return urlparse(self.url).scheme in {"http","https"}
    def local_path(self,root:Path): return (root/self.url).resolve() if not self.url.startswith('file://') else Path(self.url[7:])
