from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Channel:
    name: str
    stream_url: str
    group: str = ""
    tvg_id: str = ""
    tvg_name: str = ""
    logo: str = ""
    source_id: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    extra_directives: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.stream_url = self.stream_url.strip()
        self.group = self.group.strip()
        self.tvg_id = self.tvg_id.strip()
        self.tvg_name = self.tvg_name.strip()
        self.logo = self.logo.strip()
        self.source_id = self.source_id.strip()

        if not self.name:
            raise ValueError("Nome canale vuoto")

        if not self.stream_url:
            raise ValueError("URL flusso vuoto")

    def identity_key(self) -> tuple[str, str]:
        return self.name.casefold(), self.stream_url