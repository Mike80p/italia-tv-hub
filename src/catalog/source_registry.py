from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from threading import RLock
import unicodedata

from src.models.source import Source


def _normalize_id(value: str | None) -> str:
    if value is None:
        return ""

    normalized = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    return normalized.strip().casefold()


def _normalize_url(value: str | None) -> str:
    if value is None:
        return ""

    normalized = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    return normalized.strip()


@dataclass(frozen=True, slots=True)
class SourceRegistryError:
    source_id: str
    message: str


@dataclass(frozen=True, slots=True)
class SourceBatchResult:
    inserted: int = 0
    replaced: int = 0
    skipped: int = 0
    invalid: int = 0
    errors: tuple[SourceRegistryError, ...] = ()

    @property
    def changed(self) -> int:
        return self.inserted + self.replaced

    @property
    def processed(self) -> int:
        return (
            self.inserted
            + self.replaced
            + self.skipped
            + self.invalid
        )


@dataclass(frozen=True, slots=True)
class SourceRegistryStats:
    total: int
    enabled: int
    disabled: int
    remote: int
    local: int


class SourceRegistry:
    """
    Registro centrale thread-safe delle sorgenti.

    Regole:

    - source.id è la chiave primaria;
    - il confronto degli ID non distingue maiuscole/minuscole;
    - lo stesso URL non può appartenere a due sorgenti;
    - l'ordinamento predefinito usa priority crescente;
    - a parità di priorità mantiene l'ordine di inserimento;
    - ogni sorgente viene validata prima della registrazione.
    """

    def __init__(
        self,
        sources: Iterable[Source] | None = None,
    ) -> None:
        self._lock = RLock()

        self._sources: dict[str, Source] = {}
        self._order: list[str] = []
        self._url_index: dict[str, str] = {}

        if sources is not None:
            self.add_many(sources)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sources)

    def __bool__(self) -> bool:
        return len(self) > 0

    def __iter__(self) -> Iterator[Source]:
        return iter(self.snapshot())

    def __contains__(
        self,
        source_or_id: object,
    ) -> bool:
        if isinstance(source_or_id, Source):
            return self.contains_id(
                source_or_id.id
            )

        if isinstance(source_or_id, str):
            return self.contains_id(
                source_or_id
            )

        return False

    @staticmethod
    def _validate_source(
        source: Source,
    ) -> tuple[str, str]:
        if not isinstance(source, Source):
            raise TypeError(
                "source must be an instance of Source"
            )

        source.validate()

        if not isinstance(source.enabled, bool):
            raise TypeError(
                "source.enabled must be a boolean"
            )

        if (
            isinstance(source.priority, bool)
            or not isinstance(source.priority, int)
        ):
            raise TypeError(
                "source.priority must be an integer"
            )

        source_id = _normalize_id(source.id)
        source_url = _normalize_url(source.url)

        if not source_id:
            raise ValueError(
                "source.id cannot be empty"
            )

        if not source_url:
            raise ValueError(
                "source.url cannot be empty"
            )

        return source_id, source_url

    def add(
        self,
        source: Source,
        *,
        replace_existing: bool = False,
    ) -> bool:
        """
        Inserisce una sorgente.

        Restituisce True quando il registro viene modificato.

        Se l'ID esiste già:

        - replace_existing=False: la sorgente viene ignorata;
        - replace_existing=True: la sorgente viene aggiornata.

        Se l'URL appartiene a un'altra sorgente:

        - durante un nuovo inserimento viene ignorata;
        - durante una sostituzione viene sollevato ValueError.
        """

        source_id, source_url = (
            self._validate_source(source)
        )

        with self._lock:
            current = self._sources.get(source_id)

            url_owner = self._url_index.get(
                source_url
            )

            if current is not None:
                if not replace_existing:
                    return False

                if (
                    url_owner is not None
                    and url_owner != source_id
                ):
                    raise ValueError(
                        "source URL already registered: "
                        f"{source_url}"
                    )

                old_url = _normalize_url(
                    current.url
                )

                self._url_index.pop(
                    old_url,
                    None,
                )

                self._sources[source_id] = source
                self._url_index[source_url] = (
                    source_id
                )

                return True

            if url_owner is not None:
                return False

            self._sources[source_id] = source
            self._order.append(source_id)
            self._url_index[source_url] = source_id

            return True

    def upsert(self, source: Source) -> bool:
        """
        Inserisce oppure aggiorna una sorgente
        utilizzando source.id.
        """

        return self.add(
            source,
            replace_existing=True,
        )

    def add_many(
        self,
        sources: Iterable[Source],
        *,
        replace_existing: bool = False,
        strict: bool = True,
    ) -> SourceBatchResult:
        """
        Inserisce più sorgenti.

        strict=True:
            la prima sorgente non valida interrompe l'operazione.

        strict=False:
            le sorgenti non valide vengono ignorate e registrate
            nel risultato.
        """

        inserted = 0
        replaced_count = 0
        skipped = 0
        invalid = 0

        errors: list[SourceRegistryError] = []

        for source in sources:
            try:
                source_id, _ = (
                    self._validate_source(source)
                )

                with self._lock:
                    already_present = (
                        source_id in self._sources
                    )

                changed = self.add(
                    source,
                    replace_existing=(
                        replace_existing
                    ),
                )

                if not changed:
                    skipped += 1
                elif already_present:
                    replaced_count += 1
                else:
                    inserted += 1

            except (TypeError, ValueError) as exc:
                if strict:
                    raise

                invalid += 1

                raw_source_id = getattr(
                    source,
                    "id",
                    "<unknown>",
                )

                errors.append(
                    SourceRegistryError(
                        source_id=(
                            str(raw_source_id).strip()
                            or "<unknown>"
                        ),
                        message=str(exc),
                    )
                )

        return SourceBatchResult(
            inserted=inserted,
            replaced=replaced_count,
            skipped=skipped,
            invalid=invalid,
            errors=tuple(errors),
        )

    def contains_id(
        self,
        source_id: str,
    ) -> bool:
        key = _normalize_id(source_id)

        if not key:
            return False

        with self._lock:
            return key in self._sources

    def get(
        self,
        source_id: str,
    ) -> Source | None:
        key = _normalize_id(source_id)

        if not key:
            return None

        with self._lock:
            return self._sources.get(key)

    def get_by_url(
        self,
        url: str,
    ) -> Source | None:
        key = _normalize_url(url)

        if not key:
            return None

        with self._lock:
            source_id = self._url_index.get(key)

            if source_id is None:
                return None

            return self._sources.get(source_id)

    def snapshot(
        self,
        *,
        enabled_only: bool | None = None,
        sort_by_priority: bool = True,
    ) -> tuple[Source, ...]:
        """
        Restituisce uno snapshot immutabile.

        enabled_only:
            None  -> tutte le sorgenti;
            True  -> solo abilitate;
            False -> solo disabilitate.
        """

        with self._lock:
            sources = [
                self._sources[source_id]
                for source_id in self._order
                if source_id in self._sources
            ]

            if enabled_only is not None:
                sources = [
                    source
                    for source in sources
                    if source.enabled
                    is enabled_only
                ]

            if sort_by_priority:
                sources.sort(
                    key=lambda source: (
                        source.priority
                    )
                )

            return tuple(sources)

    def enabled_sources(
        self,
    ) -> tuple[Source, ...]:
        return self.snapshot(
            enabled_only=True,
        )

    def disabled_sources(
        self,
    ) -> tuple[Source, ...]:
        return self.snapshot(
            enabled_only=False,
        )

    def set_enabled(
        self,
        source_id: str,
        enabled: bool,
    ) -> Source | None:
        if not isinstance(enabled, bool):
            raise TypeError(
                "enabled must be a boolean"
            )

        key = _normalize_id(source_id)

        if not key:
            return None

        with self._lock:
            current = self._sources.get(key)

            if current is None:
                return None

            updated = replace(
                current,
                enabled=enabled,
            )

            self.add(
                updated,
                replace_existing=True,
            )

            return updated

    def set_priority(
        self,
        source_id: str,
        priority: int,
    ) -> Source | None:
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
        ):
            raise TypeError(
                "priority must be an integer"
            )

        key = _normalize_id(source_id)

        if not key:
            return None

        with self._lock:
            current = self._sources.get(key)

            if current is None:
                return None

            updated = replace(
                current,
                priority=priority,
            )

            self.add(
                updated,
                replace_existing=True,
            )

            return updated

    def remove(
        self,
        source_id: str,
    ) -> Source | None:
        key = _normalize_id(source_id)

        if not key:
            return None

        with self._lock:
            source = self._sources.pop(
                key,
                None,
            )

            if source is None:
                return None

            source_url = _normalize_url(
                source.url
            )

            self._url_index.pop(
                source_url,
                None,
            )

            try:
                self._order.remove(key)
            except ValueError:
                pass

            return source

    def stats(self) -> SourceRegistryStats:
        with self._lock:
            sources = tuple(
                self._sources.values()
            )

            enabled = sum(
                1
                for source in sources
                if source.enabled
            )

            remote = sum(
                1
                for source in sources
                if source.is_remote()
            )

            total = len(sources)

            return SourceRegistryStats(
                total=total,
                enabled=enabled,
                disabled=total - enabled,
                remote=remote,
                local=total - remote,
            )

    def clear(self) -> None:
        with self._lock:
            self._sources.clear()
            self._order.clear()
            self._url_index.clear()