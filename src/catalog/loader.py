from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.source import Source


def _as_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _build_source(
    item: dict[str, Any],
) -> Source:
    """
    Costruisce una Source da una definizione JSON.

    I campi Discovery sono tutti opzionali. In loro assenza vengono
    applicati i valori predefiniti del modello Source, mantenendo
    compatibili i vecchi file di configurazione.
    """

    return Source(
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
        kind=_as_text(
            item.get(
                "kind",
                "playlist",
            )
        )
        or "playlist",
        country=_as_text(
            item.get("country")
        ),
        language=_as_text(
            item.get("language")
        ),
        tags=item.get(
            "tags",
            (),
        ),
        discovery_enabled=item.get(
            "discovery_enabled",
            False,
        ),
        discovery_mode=_as_text(
            item.get(
                "discovery_mode",
                "static",
            )
        )
        or "static",
        trust_score=item.get(
            "trust_score",
            50,
        ),
        refresh_hours=item.get(
            "refresh_hours",
            24,
        ),
        origin=_as_text(
            item.get("origin")
        ),
    )


def load_sources(
    directory: Path,
) -> list[Source]:
    """
    Carica le definizioni delle sorgenti dai file JSON.

    Formato atteso:

        {
          "sources": [
            {
              "id": "...",
              "name": "...",
              "url": "..."
            }
          ]
        }

    I vecchi JSON con soli id, name, url, enabled e priority
    continuano a funzionare. I campi Source Discovery sono
    facoltativi.

    Il loader si occupa soltanto di:

    - leggere i file;
    - controllare la struttura JSON;
    - costruire gli oggetti Source.

    Validazione, deduplicazione, abilitazione e ordinamento vengono
    gestiti dal SourceRegistry.
    """

    sources: list[
        Source
    ] = []

    if not directory.exists():
        return sources

    if not directory.is_dir():
        raise ValueError(
            "Il percorso sorgenti non è "
            f"una cartella: {directory}"
        )

    for path in sorted(
        directory.glob(
            "*.json"
        )
    ):
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except UnicodeDecodeError as exc:
            raise ValueError(
                "Codifica non valida in "
                f"{path.name}: richiesto UTF-8"
            ) from exc

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON non valido in {path.name}: "
                f"riga {exc.lineno}, "
                f"colonna {exc.colno}"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Struttura non valida in "
                f"{path.name}: atteso oggetto JSON"
            )

        raw_sources = payload.get(
            "sources",
            [],
        )

        if not isinstance(
            raw_sources,
            list,
        ):
            raise ValueError(
                "Campo 'sources' non valido in "
                f"{path.name}: attesa lista"
            )

        for index, item in enumerate(
            raw_sources,
            start=1,
        ):
            if not isinstance(
                item,
                dict,
            ):
                raise ValueError(
                    "Sorgente non valida in "
                    f"{path.name}, elemento {index}: "
                    "atteso oggetto JSON"
                )

            sources.append(
                _build_source(
                    item
                )
            )

    return sources
