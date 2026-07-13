# Italia TV Hub

Versione **v0.2.0 — Core Engine**.

Funzioni: catalogo sorgenti JSON, download HTTP/locale, parser M3U, modello Channel, exporter M3U, report JSON e test automatici.

## Avvio
```bash
python -m src.main
```

## Test
```bash
python -m pip install -r requirements.txt
pytest -q
```

Playlist finale prevista:
```text
https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u
```

Le sorgenti Internet reali sono disabilitate in questa release; il motore viene collaudato con una playlist locale.
