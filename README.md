# Italia TV Hub

Motore automatico per aggregare, verificare e pubblicare canali TV italiani con playlist M3U, EPG XMLTV e guida TV web.

## Funzioni principali

- aggregazione e deduplicazione delle sorgenti;
- Health/Playback verification degli stream;
- selezione automatica delle alternative migliori;
- playlist ottimizzata per Samsung/Tizen;
- EPG XMLTV multi-sorgente;
- guida TV web per singolo canale con programma in onda e palinsesto giornaliero;
- aggiornamento automatico tramite GitHub Actions.

## EPG

Il motore combina più guide XMLTV italiane. Oltre alle guide GlobeTV, usa:

- EPGShare IT1 per i canali lineari italiani;
- Pluto TV Italia XMLTV per i canali FAST Pluto.

L'associazione privilegia `tvg-id` / XMLTV channel ID e usa normalizzazione e fallback controllati senza accettare match ambigui.

## Stato

La release pubblicata su `main` resta invariata finché le modifiche correnti non superano i gate di test e la verifica reale della nuova copertura EPG.
