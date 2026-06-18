"""Schemas for literature endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LiteraturePaper(BaseModel):
    """Literature record."""

    pmid: str
    title: str
    journal: str | None = None
    pub_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    link: str | None = None
    tags: list[str] = Field(default_factory=list)


class LiteratureTagCount(BaseModel):
    """Popular tag stats."""

    tag_name: str
    count: int
