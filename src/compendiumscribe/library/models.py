from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


LIBRARY_SCHEMA_VERSION = 1


class CatalogEntry(BaseModel):
    """Compact catalog entry used for library discovery."""

    id: str
    title: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    path: str
    markdown_path: str
    card_path: str
    created_at: datetime
    updated_at: datetime


class Catalog(BaseModel):
    """Root library catalog."""

    schema_version: int = LIBRARY_SCHEMA_VERSION
    updated_at: datetime
    entries: list[CatalogEntry] = Field(default_factory=list)


class CardSection(BaseModel):
    """Section-level preview metadata for progressive disclosure."""

    id: str
    title: str
    summary: str


class CompendiumCard(BaseModel):
    """Medium-depth metadata for a single library compendium."""

    schema_version: int = LIBRARY_SCHEMA_VERSION
    id: str
    title: str
    summary: str
    sections: list[CardSection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    section_count: int
    citation_count: int
    source_count: int
    path: str
    markdown_path: str
    created_at: datetime
    updated_at: datetime
