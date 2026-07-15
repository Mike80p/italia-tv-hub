from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.source import Source


def _as_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def load_sources(
    directory: Path,
) -> list[Source]:
    """
    Carica le definizioni delle sorgenti dai file JSON.

    Il loader si occupa soltanto di:

    - leggere i file;
    - controllare la struttura JSON;
    - costruire gli oggetti Source.

    Validazione, deduplicazione, abilitazione e ordinamento
    vengono gestiti dal SourceRegistry.
    """

    sources: list[Source] = []

    if not directory.exists():
        return sources

    if not directory.is_dir():
        raise ValueError(
            f"Il percorso sorgenti non è una cartella: "
            f"{directory}"
        )

    for path in sorted(
        directory.glob("*.json")
    ):
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON non valido in {path.name}: "
                f"riga {exc.lineno}, "
                f"colonna {exc.colno}"
            ) from exc

        if not isinstance(payload, dict):
            raise ValueError(
                f"Struttura non valida in "
                f"{path.name}: atteso oggetto JSON"
            )

        raw_sources = payload.get(
            "sources",
            [],
        )

        if not isinstance(raw_sources, list):
            raise ValueError(
                f"Campo 'sources' non valido in "
                f"{path.name}: attesa lista"
            )

        for index, item in enumerate(
            raw_sources,
            start=1,
        ):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Sorgente non valida in "
                    f"{path.name}, elemento {index}: "
                    f"atteso oggetto JSON"
                )

            source = Source(
                id=_as_text(
                    item.get("id")
                ),
                name=_as_text(
                    item.get("name")
                ),
                url=_as_text(
                    item.get("url")
                ),
                enabled=item.get(
                    "enabled",
                    True,
                ),
                priority=item.get(
                    "priority",
                    100,
                ),
            )

            sources.append(source)

    return sources