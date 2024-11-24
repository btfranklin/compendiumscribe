from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Concept:
    name: str
    keywords: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    content: str = ""


@dataclass
class Topic:
    name: str
    topic_summary: str = ""
    concepts: list[Concept] = field(default_factory=list)


@dataclass
class Domain:
    name: str
    summary: str = ""
    topics: list[Topic] = field(default_factory=list)
