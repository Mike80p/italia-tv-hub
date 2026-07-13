import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_required_files_exist():
    required = [
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "config/sources.json",
        "config/settings.json",
        "src/main.py",
        "docs/index.html",
    ]
    for relative in required:
        assert (ROOT / relative).exists(), relative

def test_sources_config_is_valid():
    data = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
    assert isinstance(data.get("sources"), list)
