from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

def main():
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    playlist_path = output_dir / "playlist.m3u"
    playlist_path.write_text("#EXTM3U\n", encoding="utf-8")

    report = {
        "project": "Italia TV Hub",
        "repository": "italia-tv-hub",
        "version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "foundation_ready",
        "enabled_sources": 0,
        "channels": 0
    }

    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print("Italia TV Hub: foundation pronta.")

if __name__ == "__main__":
    main()
