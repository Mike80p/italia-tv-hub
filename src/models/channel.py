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
    attributes: dict[str,str] = field(default_factory=dict)
    extra_directives: list[str] = field(default_factory=list)
    def __post_init__(self):
        self.name=self.name.strip(); self.stream_url=self.stream_url.strip()
        if not self.name: raise ValueError("Nome canale vuoto")
        if not self.stream_url: raise ValueError("URL flusso vuoto")
