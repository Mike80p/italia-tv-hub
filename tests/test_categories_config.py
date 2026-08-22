from __future__ import annotations

import json
from pathlib import Path

from src.exporter.m3u import M3UExporter


def test_category_registry_matches_exporter_order() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "config/categories.json").read_text(
            encoding="utf-8"
        )
    )

    configured = payload["order"]
    exporter = [
        name
        for name, _ in sorted(
            M3UExporter.CATEGORY_ORDER.items(),
            key=lambda item: item[1],
        )
    ]

    assert configured == exporter


def test_category_registry_has_no_duplicates() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "config/categories.json").read_text(
            encoding="utf-8"
        )
    )

    configured = payload["order"]
    assert len(configured) == len(set(configured))
