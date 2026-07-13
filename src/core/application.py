import json
from datetime import datetime,timezone
from pathlib import Path
from src.catalog.loader import load_sources
from src.core.settings import Settings
from src.downloader.client import PlaylistDownloader,DownloadError
from src.parser.m3u import M3UParser
from src.exporter.m3u import M3UExporter
class Application:
    def __init__(self,root:Path):
        self.root=root; self.settings=Settings.load(root/'config/settings.json')
        self.downloader=PlaylistDownloader(root,self.settings.request_timeout_seconds,self.settings.retry_count,self.settings.user_agent)
    def run(self):
        channels=[]; results=[]; parser=M3UParser()
        sources=load_sources(self.root/'config/sources')
        for s in sources:
            try:
                parsed=parser.parse(self.downloader.fetch(s),s.id); channels.extend(parsed); results.append({'id':s.id,'status':'ok','channels':len(parsed)})
            except DownloadError as e: results.append({'id':s.id,'status':'error','channels':0,'error':str(e)})
        M3UExporter().write(self.root/self.settings.output_file,channels)
        report={'project':'Italia TV Hub','version':'0.2.0','generated_at':datetime.now(timezone.utc).isoformat(),'sources_enabled':len(sources),'channels':len(channels),'sources':results}
        p=self.root/self.settings.report_file; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return 0
