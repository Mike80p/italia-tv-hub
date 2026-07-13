# Italia TV Hub

Aggregatore open source per playlist TV italiane gratuite e pubblicamente accessibili, con supporto a Pluto TV Italia, controlli automatici e dashboard GitHub Pages.

## Stato del progetto

Versione iniziale: **v0.1.0 — Sprint 0 Foundation**

## Obiettivi

- raccogliere sorgenti M3U pubbliche e gratuite;
- normalizzare e deduplicare i canali;
- verificare la raggiungibilità dei flussi;
- generare una playlist ordinata;
- pubblicare report e dashboard tramite GitHub Pages;
- mantenere invariato il link finale della playlist.

## Regole

Il progetto deve usare solo flussi pubblici e legittimamente accessibili.

Non deve:

- aggirare DRM;
- aggirare autenticazioni;
- bypassare geoblocchi;
- includere contenuti non autorizzati.

## Link previsti

Playlist:

```text
https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u
```

Dashboard:

```text
https://mike80p.github.io/italia-tv-hub/
```

## Struttura

```text
.github/workflows/   Automazioni GitHub
src/                 Motore Python
config/              Configurazioni
output/              Playlist e report generati
docs/                Dashboard GitHub Pages
tests/               Test automatici
```

## Roadmap

- v0.1 — Foundation
- v0.2 — Parser M3U
- v0.3 — Merge e deduplicazione
- v0.4 — Health check
- v0.5 — Dashboard dinamica
- v1.0 — Prima release stabile
