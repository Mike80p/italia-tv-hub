from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from threading import RLock
import unicodedata

from src.models.channel import Channel


def _normalize_text(value: str | None) -> str:
    """
    Normalizza i valori usati negli indici.

    - converte Unicode in formato NFKC;
    - elimina spazi iniziali e finali;
    - compatta gli spazi multipli;
    - rende il confronto case-insensitive.
    """
    if value is None:
        return ""

    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.split()).casefold()


def _normalize_url(value: str | None) -> str:
    """
    Normalizza l'URL senza modificarne maiuscole e minuscole.

    Il path di un URL può essere case-sensitive, quindi vengono rimossi
    solamente gli spazi iniziali e finali.
    """
    if value is None:
        return ""

    return str(value).strip()


@dataclass(frozen=True, slots=True)
class RegistryBatchResult:
    """
    Risultato di un inserimento multiplo.
    """

    inserted: int = 0
    replaced: int = 0
    skipped: int = 0

    @property
    def changed(self) -> int:
        return self.inserted + self.replaced


@dataclass(frozen=True, slots=True)
class RegistryStats:
    """
    Statistiche sintetiche del registro.
    """

    channels: int
    sources: int
    groups: int
    tvg_ids: int


class ChannelRegistry:
    """
    Registro centrale thread-safe dei canali.

    Regole:

    - l'URL è la chiave univoca primaria;
    - due canali con lo stesso URL non vengono duplicati;
    - canali con lo stesso nome ma URL differenti sono ammessi;
    - nome, sorgente, gruppo e tvg-id sono indici secondari;
    - l'ordine di inserimento viene preservato;
    - le operazioni sulla struttura sono protette da lock.
    """

    def __init__(
        self,
        channels: Iterable[Channel] | None = None,
    ) -> None:
        self._lock = RLock()

        self._channels: dict[str, Channel] = {}
        self._order: list[str] = []

        self._name_index: dict[str, set[str]] = {}
        self._source_index: dict[str, set[str]] = {}
        self._group_index: dict[str, set[str]] = {}
        self._tvg_id_index: dict[str, set[str]] = {}

        if channels is not None:
            self.add_many(channels)

    def __len__(self) -> int:
        with self._lock:
            return len(self._channels)

    def __bool__(self) -> bool:
        return len(self) > 0

    def __iter__(self) -> Iterator[Channel]:
        return iter(self.snapshot())

    def __contains__(self, channel_or_url: object) -> bool:
        if isinstance(channel_or_url, Channel):
            return self.contains_url(channel_or_url.stream_url)

        if isinstance(channel_or_url, str):
            return self.contains_url(channel_or_url)

        return False

    @staticmethod
    def _validate_channel(channel: Channel) -> str:
        if not isinstance(channel, Channel):
            raise TypeError(
                "channel must be an instance of Channel"
            )

        if not str(channel.name).strip():
            raise ValueError(
                "channel.name cannot be empty"
            )

        normalized_url = _normalize_url(channel.stream_url)

        if not normalized_url:
            raise ValueError(
                "channel.stream_url cannot be empty"
            )

        return normalized_url

    @staticmethod
    def _index_add(
        index: dict[str, set[str]],
        key: str,
        url: str,
    ) -> None:
        if not key:
            return

        index.setdefault(key, set()).add(url)

    @staticmethod
    def _index_remove(
        index: dict[str, set[str]],
        key: str,
        url: str,
    ) -> None:
        if not key:
            return

        urls = index.get(key)

        if not urls:
            return

        urls.discard(url)

        if not urls:
            index.pop(key, None)

    def _add_to_indexes(
        self,
        channel: Channel,
        url: str,
    ) -> None:
        self._index_add(
            self._name_index,
            _normalize_text(channel.name),
            url,
        )

        self._index_add(
            self._source_index,
            _normalize_text(channel.source_id),
            url,
        )

        self._index_add(
            self._group_index,
            _normalize_text(channel.group),
            url,
        )

        self._index_add(
            self._tvg_id_index,
            _normalize_text(channel.tvg_id),
            url,
        )

    def _remove_from_indexes(
        self,
        channel: Channel,
        url: str,
    ) -> None:
        self._index_remove(
            self._name_index,
            _normalize_text(channel.name),
            url,
        )

        self._index_remove(
            self._source_index,
            _normalize_text(channel.source_id),
            url,
        )

        self._index_remove(
            self._group_index,
            _normalize_text(channel.group),
            url,
        )

        self._index_remove(
            self._tvg_id_index,
            _normalize_text(channel.tvg_id),
            url,
        )

    def _channels_for_urls(
        self,
        urls: set[str] | None,
    ) -> tuple[Channel, ...]:
        if not urls:
            return ()

        return tuple(
            self._channels[url]
            for url in self._order
            if url in urls and url in self._channels
        )

    def add(
        self,
        channel: Channel,
        *,
        replace: bool = False,
    ) -> bool:
        """
        Inserisce un canale.

        Restituisce True se il registro viene modificato.

        Se l'URL esiste già:

        - con replace=False il canale viene ignorato;
        - con replace=True il canale precedente viene sostituito.
        """
        url = self._validate_channel(channel)

        with self._lock:
            current = self._channels.get(url)

            if current is not None:
                if not replace:
                    return False

                self._remove_from_indexes(current, url)

                self._channels[url] = channel

                self._add_to_indexes(channel, url)

                return True

            self._channels[url] = channel
            self._order.append(url)

            self._add_to_indexes(channel, url)

            return True

    def upsert(self, channel: Channel) -> bool:
        """
        Inserisce il canale oppure sostituisce quello con lo stesso URL.
        """
        return self.add(
            channel,
            replace=True,
        )

    def add_many(
        self,
        channels: Iterable[Channel],
        *,
        replace: bool = False,
    ) -> RegistryBatchResult:
        """
        Inserisce più canali e restituisce il riepilogo dell'operazione.
        """
        inserted = 0
        replaced = 0
        skipped = 0

        for channel in channels:
            url = self._validate_channel(channel)

            with self._lock:
                already_present = url in self._channels

                changed = self.add(
                    channel,
                    replace=replace,
                )

            if not changed:
                skipped += 1
            elif already_present:
                replaced += 1
            else:
                inserted += 1

        return RegistryBatchResult(
            inserted=inserted,
            replaced=replaced,
            skipped=skipped,
        )

    def contains_url(self, url: str) -> bool:
        key = _normalize_url(url)

        if not key:
            return False

        with self._lock:
            return key in self._channels

    def get_by_url(self, url: str) -> Channel | None:
        key = _normalize_url(url)

        if not key:
            return None

        with self._lock:
            return self._channels.get(key)

    def find_by_name(
        self,
        name: str,
    ) -> tuple[Channel, ...]:
        key = _normalize_text(name)

        with self._lock:
            return self._channels_for_urls(
                self._name_index.get(key)
            )

    def find_by_source(
        self,
        source_id: str,
    ) -> tuple[Channel, ...]:
        key = _normalize_text(source_id)

        with self._lock:
            return self._channels_for_urls(
                self._source_index.get(key)
            )

    def find_by_group(
        self,
        group: str,
    ) -> tuple[Channel, ...]:
        key = _normalize_text(group)

        with self._lock:
            return self._channels_for_urls(
                self._group_index.get(key)
            )

    def find_by_tvg_id(
        self,
        tvg_id: str,
    ) -> tuple[Channel, ...]:
        key = _normalize_text(tvg_id)

        with self._lock:
            return self._channels_for_urls(
                self._tvg_id_index.get(key)
            )

    def search(
        self,
        query: str,
    ) -> tuple[Channel, ...]:
        """
        Ricerca parziale nei campi:

        - name;
        - tvg_name;
        - group;
        - tvg_id;
        - source_id.
        """
        needle = _normalize_text(query)

        if not needle:
            return self.snapshot()

        with self._lock:
            result: list[Channel] = []

            for url in self._order:
                channel = self._channels.get(url)

                if channel is None:
                    continue

                haystack = " ".join(
                    (
                        _normalize_text(channel.name),
                        _normalize_text(channel.tvg_name),
                        _normalize_text(channel.group),
                        _normalize_text(channel.tvg_id),
                        _normalize_text(channel.source_id),
                    )
                )

                if needle in haystack:
                    result.append(channel)

            return tuple(result)

    def remove_by_url(
        self,
        url: str,
    ) -> Channel | None:
        key = _normalize_url(url)

        if not key:
            return None

        with self._lock:
            channel = self._channels.pop(key, None)

            if channel is None:
                return None

            self._remove_from_indexes(channel, key)

            try:
                self._order.remove(key)
            except ValueError:
                pass

            return channel

    def remove(self, channel: Channel) -> bool:
        """
        Rimuove un canale utilizzando il suo URL.
        """
        url = self._validate_channel(channel)

        return self.remove_by_url(url) is not None

    def remove_source(
        self,
        source_id: str,
    ) -> tuple[Channel, ...]:
        """
        Rimuove tutti i canali appartenenti a una sorgente.
        """
        key = _normalize_text(source_id)

        if not key:
            return ()

        with self._lock:
            urls = set(
                self._source_index.get(key, set())
            )

            removed = self._channels_for_urls(urls)

            for channel in removed:
                self.remove_by_url(channel.stream_url)

            return removed

    def replace(
        self,
        old_url: str,
        channel: Channel,
    ) -> bool:
        """
        Sostituisce un canale, anche quando cambia URL.

        La posizione originale viene mantenuta.

        Restituisce False se old_url non esiste.

        Solleva ValueError se il nuovo URL appartiene già a un altro
        canale presente nel registro.
        """
        old_key = _normalize_url(old_url)
        new_key = self._validate_channel(channel)

        if not old_key:
            return False

        with self._lock:
            current = self._channels.get(old_key)

            if current is None:
                return False

            if (
                new_key != old_key
                and new_key in self._channels
            ):
                raise ValueError(
                    f"channel URL already registered: {new_key}"
                )

            position = self._order.index(old_key)

            self._remove_from_indexes(
                current,
                old_key,
            )

            self._channels.pop(
                old_key,
                None,
            )

            self._channels[new_key] = channel
            self._order[position] = new_key

            self._add_to_indexes(
                channel,
                new_key,
            )

            return True

    def snapshot(self) -> tuple[Channel, ...]:
        """
        Restituisce uno snapshot ordinato e strutturalmente immutabile.
        """
        with self._lock:
            return tuple(
                self._channels[url]
                for url in self._order
                if url in self._channels
            )

    def stats(self) -> RegistryStats:
        with self._lock:
            return RegistryStats(
                channels=len(self._channels),
                sources=len(self._source_index),
                groups=len(self._group_index),
                tvg_ids=len(self._tvg_id_index),
            )

    def clear(self) -> None:
        """
        Svuota completamente il registro e tutti gli indici.
        """
        with self._lock:
            self._channels.clear()
            self._order.clear()

            self._name_index.clear()
            self._source_index.clear()
            self._group_index.clear()
            self._tvg_id_index.clear()