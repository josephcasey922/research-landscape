from dataclasses import dataclass

@dataclass
class Author:
    author_id: str | None
    name: str
