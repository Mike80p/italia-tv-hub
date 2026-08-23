from pathlib import Path
import gzip
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import epg_refresh_publish as m


def check(name, value):
    if not value:
        raise AssertionError(name)


def xml(channel, title, start, stop):
    return f'<?xml version="1.0"?><tv><channel id="{channel}"><display-name>{channel}</display-name></channel><programme channel="{channel}" start="{start}" stop="{stop}"><title>{title}</title></programme></tv>'.encode()


def test_end_to_end():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        webroot = td / "web"
        webroot.mkdir()
        now = datetime(2026, 8, 23, 8, 0, tzinfo=timezone.utc)
        start = "20260823080000 +0000"
        stop = "20260823235900 +0000"
        (webroot / "a.xml.gz").write_bytes(gzip.compress(b'<!DOCTYPE tv SYSTEM "xmltv.dtd">' + xml("Rai1.it", "TG1", start, stop)))
        (webroot / "b.xml").write_bytes(xml("Canale5.it", "TG5", start, stop))

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        previous = os.getcwd()
        os.chdir(webroot)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            repo = td / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "EPG Test"], cwd=repo, check=True)
            (repo / "output").mkdir()
            (repo / "config").mkdir()
            (repo / "output" / "playlist.m3u").write_text('#EXTM3U\n#EXTINF:-1 tvg-id="Rai1.it@SD",Rai 1\nhttps://x\n#EXTINF:-1 tvg-id="Canale5.it",Canale 5\nhttps://y\n', encoding="utf-8")
            (repo / "output" / "epg.xml").write_text("", encoding="utf-8")
            settings = {"epg_sources": [f"http://127.0.0.1:{port}/a.xml.gz", f"http://127.0.0.1:{port}/b.xml"]}
            (repo / "config" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
            check("first publish", m.publish(repo, settings["epg_sources"], 5, True, now) == 0)
            text = (repo / "output" / "epg.xml").read_text(encoding="utf-8")
            check("alias channel", 'id="Rai1.it@SD"' in text)
            check("alias programme", 'channel="Rai1.it@SD"' in text)
            check("TG5", "TG5" in text)
            commits1 = int(subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=repo, text=True).strip())
            check("second publish", m.publish(repo, settings["epg_sources"], 5, True, now) == 0)
            commits2 = int(subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=repo, text=True).strip())
            check("idempotent", commits1 == commits2)
            try:
                m.sanitize_xmltv(b'<!DOCTYPE tv [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><tv></tv>', "x.xml")
            except ValueError:
                pass
            else:
                raise AssertionError("ENTITY must remain blocked")
        finally:
            server.shutdown()
            os.chdir(previous)
