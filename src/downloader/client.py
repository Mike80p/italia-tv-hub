import time, urllib.request
from pathlib import Path
from src.models.source import Source
class DownloadError(RuntimeError): pass
class PlaylistDownloader:
    def __init__(self,project_root:Path,timeout:int,retries:int,user_agent:str): self.root=project_root; self.timeout=timeout; self.retries=retries; self.user_agent=user_agent
    def fetch(self,source:Source):
        if not source.is_remote():
            try:return source.local_path(self.root).read_text(encoding='utf-8-sig')
            except OSError as e: raise DownloadError(str(e)) from e
        last=None
        for n in range(self.retries+1):
            try:
                req=urllib.request.Request(source.url,headers={'User-Agent':self.user_agent})
                with urllib.request.urlopen(req,timeout=self.timeout) as r:return r.read().decode('utf-8-sig',errors='replace')
            except Exception as e:
                last=e
                if n<self.retries: time.sleep(min(n+1,3))
        raise DownloadError(f'Download fallito: {source.id}') from last
