import json
from pathlib import Path
from src.parser.m3u import M3UParser
from src.core.application import Application
ROOT=Path(__file__).resolve().parents[1]
def test_parser():
 c=M3UParser().parse((ROOT/'samples/sample.m3u').read_text(encoding='utf-8'),'sample'); assert len(c)==2; assert c[0].group=='RAI'
def test_application():
 assert Application(ROOT).run()==0; assert 'Rai 1 Demo' in (ROOT/'output/playlist.m3u').read_text(encoding='utf-8'); assert json.loads((ROOT/'output/report.json').read_text())['channels']==2
