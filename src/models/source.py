from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


SOURCE_ID_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
)

SUPPORTED_SCHEMES = {
    "",
    "file",
    "http",
    "https",
}

SUPPORTED_SOURCE_KINDS = {
    "playlist",
    "api",
    "catalog",
    "repository",
    "generated",
}

SUPPORTED_DISCOVERY_MODES = {
    "static",
    "country",
    "language",
    "tags",
    "search",
    "api",
}


@dataclass(
    slots=True,
    frozen=True,
)
class Source:
    """
    Sorgente di canali o di candidati stream.

    I primi cinque campi mantengono la firma storica del progetto:

        Source(id, name, url, enabled=True, priority=100)

    I campi successivi preparano il Source Discovery Engine senza
    rompere i vecchi file JSON o i test esistenti.
    """

    id: str
    name: str
    url: str
    enabled: bool = True
    priority: int = 100

    # Metadati Discovery, tutti opzionali e retrocompatibili.
    kind: str = "playlist"
    country: str = ""
    language: str = ""
    tags: tuple[str, ...] = ()
    discovery_enabled: bool = False
    discovery_mode: str = "static"
    trust_score: int = 50
    refresh_hours: int = 24
    origin: str = ""

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "id",
            str(self.id).strip(),
        )

        object.__setattr__(
            self,
            "name",
            str(self.name).strip(),
        )

        object.__setattr__(
            self,
            "url",
            str(self.url).strip(),
        )

        object.__setattr__(
            self,
            "kind",
            self._normalize_token(
                self.kind,
                default="playlist",
            ),
        )

        object.__setattr__(
            self,
            "country",
            self._normalize_country(
                self.country
            ),
        )

        object.__setattr__(
            self,
            "language",
            self._normalize_language(
                self.language
            ),
        )

        object.__setattr__(
            self,
            "tags",
            self._normalize_tags(
                self.tags
            ),
        )

        object.__setattr__(
            self,
            "discovery_mode",
            self._normalize_token(
                self.discovery_mode,
                default="static",
            ),
        )

        object.__setattr__(
            self,
            "origin",
            str(self.origin).strip(),
        )

    def validate(
        self,
    ) -> None:
        """
        Valida la sorgente.

        Il metodo continua a sollevare ValueError come la versione
        precedente, così SourceRegistry e loader rimangono compatibili.
        """

        if not self.id:
            raise ValueError(
                "Sorgente incompleta: "
                "ID sorgente mancante"
            )

        if not SOURCE_ID_PATTERN.fullmatch(
            self.id
        ):
            raise ValueError(
                "ID sorgente non valido"
            )

        if not self.name:
            raise ValueError(
                "Sorgente incompleta: "
                "nome sorgente mancante"
            )

        if not self.url:
            raise ValueError(
                "Sorgente incompleta: "
                "URL sorgente mancante"
            )

        parsed = urlparse(
            self.url
        )

        scheme = (
            parsed.scheme.casefold()
        )

        if scheme not in SUPPORTED_SCHEMES:
            raise ValueError(
                "Schema non supportato"
            )

        if (
            scheme in {"http", "https"}
            and not parsed.netloc
        ):
            raise ValueError(
                "URL remoto non valido"
            )

        if (
            isinstance(self.enabled, bool)
            is False
        ):
            raise ValueError(
                "enabled deve essere booleano"
            )

        if (
            isinstance(self.priority, bool)
            or not isinstance(
                self.priority,
                int,
            )
        ):
            raise ValueError(
                "priority deve essere intero"
            )

        if self.kind not in (
            SUPPORTED_SOURCE_KINDS
        ):
            raise ValueError(
                "Tipo sorgente non supportato"
            )

        if (
            self.discovery_mode
            not in SUPPORTED_DISCOVERY_MODES
        ):
            raise ValueError(
                "Modalità discovery non supportata"
            )

        if (
            isinstance(
                self.discovery_enabled,
                bool,
            )
            is False
        ):
            raise ValueError(
                "discovery_enabled deve "
                "essere booleano"
            )

        if (
            isinstance(self.trust_score, bool)
            or not isinstance(
                self.trust_score,
                int,
            )
            or not 0
            <= self.trust_score
            <= 100
        ):
            raise ValueError(
                "trust_score deve essere "
                "compreso tra 0 e 100"
            )

        if (
            isinstance(
                self.refresh_hours,
                bool,
            )
            or not isinstance(
                self.refresh_hours,
                int,
            )
            or self.refresh_hours <= 0
        ):
            raise ValueError(
                "refresh_hours deve essere "
                "maggiore di zero"
            )

        if (
            self.discovery_enabled
            and self.discovery_mode
            == "static"
        ):
            raise ValueError(
                "Una sorgente discovery non può "
                "usare discovery_mode static"
            )

    def is_remote(
        self,
    ) -> bool:
        return (
            urlparse(self.url)
            .scheme.casefold()
            in {
                "http",
                "https",
            }
        )

    def is_local(
        self,
    ) -> bool:
        return not self.is_remote()

    def is_discovery_source(
        self,
    ) -> bool:
        return (
            self.discovery_enabled
            or self.kind
            in {
                "api",
                "catalog",
                "repository",
                "generated",
            }
        )

    def is_github_source(
        self,
    ) -> bool:
        hostname = (
            urlparse(self.url)
            .hostname
            or ""
        ).casefold()

        return hostname in {
            "github.com",
            "api.github.com",
            "raw.githubusercontent.com",
        }

    def local_path(
        self,
        root: Path,
    ) -> Path:
        parsed = urlparse(
            self.url
        )

        scheme = (
            parsed.scheme.casefold()
        )

        if scheme in {
            "http",
            "https",
        }:
            raise ValueError(
                "Una sorgente remota non ha "
                "un percorso locale"
            )

        if scheme == "file":
            raw_path = unquote(
                parsed.path
            )

            if (
                parsed.netloc
                and parsed.netloc
                not in {
                    "",
                    "localhost",
                }
            ):
                raw_path = (
                    f"//{parsed.netloc}"
                    f"{raw_path}"
                )

            path = Path(
                raw_path
            )

            # file:///C:/... su Windows viene letto come /C:/...
            if (
                len(raw_path) >= 3
                and raw_path[0] == "/"
                and raw_path[2] == ":"
            ):
                path = Path(
                    raw_path[1:]
                )

            return path

        path = Path(
            self.url
        )

        if path.is_absolute():
            return path.resolve()

        return (
            root
            / path
        ).resolve()

    def matches(
        self,
        *,
        country: str = "",
        language: str = "",
        tags: tuple[str, ...]
        | list[str]
        | set[str]
        | None = None,
    ) -> bool:
        """
        Verifica se la sorgente è pertinente a una richiesta Discovery.

        I filtri vuoti non restringono il risultato. Per i tag basta
        almeno una corrispondenza.
        """

        normalized_country = (
            self._normalize_country(
                country
            )
        )

        if (
            normalized_country
            and self.country
            and normalized_country
            != self.country
        ):
            return False

        normalized_language = (
            self._normalize_language(
                language
            )
        )

        if (
            normalized_language
            and self.language
            and normalized_language
            != self.language
        ):
            return False

        requested_tags = (
            self._normalize_tags(
                tags or ()
            )
        )

        if (
            requested_tags
            and self.tags
            and not set(
                requested_tags
            ).intersection(
                self.tags
            )
        ):
            return False

        return True

    def to_dict(
        self,
    ) -> dict[str, object]:
        payload = asdict(
            self
        )

        payload["tags"] = list(
            self.tags
        )

        return payload

    @staticmethod
    def _normalize_token(
        value: object,
        *,
        default: str,
    ) -> str:
        normalized = (
            str(value)
            .strip()
            .casefold()
            .replace("-", "_")
            .replace(" ", "_")
        )

        return (
            normalized
            or default
        )

    @staticmethod
    def _normalize_country(
        value: object,
    ) -> str:
        normalized = (
            str(value)
            .strip()
            .upper()
        )

        aliases = {
            "ITALIA": "IT",
            "ITALY": "IT",
            "ITA": "IT",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    @staticmethod
    def _normalize_language(
        value: object,
    ) -> str:
        normalized = (
            str(value)
            .strip()
            .casefold()
        )

        aliases = {
            "italian": "it",
            "italiano": "it",
            "ita": "it",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    @staticmethod
    def _normalize_tags(
        values: object,
    ) -> tuple[str, ...]:
        if values is None:
            return ()

        if isinstance(
            values,
            str,
        ):
            candidates = re.split(
                r"[,;|]",
                values,
            )

        else:
            try:
                candidates = list(
                    values
                )
            except TypeError:
                candidates = [
                    values
                ]

        normalized: list[
            str
        ] = []

        seen: set[
            str
        ] = set()

        for value in candidates:
            tag = (
                str(value)
                .strip()
                .casefold()
                .replace("-", "_")
                .replace(" ", "_")
            )

            if (
                not tag
                or tag in seen
            ):
                continue

            seen.add(
                tag
            )

            normalized.append(
                tag
            )

        return tuple(
            normalized
        )
