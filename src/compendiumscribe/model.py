from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Topic:
    name: str
    content: str = ""
    keywords: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)

    def outline(self, indent: int = 0) -> str:
        return " " * indent + f"- {self.name}"


@dataclass
class Domain:
    name: str
    summary: str = ""
    topics: list[Topic] = field(default_factory=list)
    subdomains: list[Domain] = field(default_factory=list)

    def outline(self, indent: int = 0) -> str:
        result = " " * indent + f"- {self.name}\n"
        for topic in self.topics:
            result += topic.outline(indent + 2) + "\n"
        for subdomain in self.subdomains:
            result += subdomain.outline(indent + 2) + "\n"
        return result.rstrip()  # Remove trailing newline
