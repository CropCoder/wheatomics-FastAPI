"""Schemas for task-like bioinformatics workflows."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SyntenyFigureRequest(BaseModel):
    """Request body for jcvi synteny rendering."""

    style: str = "line"
    dpi: int = 300
    format: str = "pdf"
    font: str = "Arial"
    diverge: str = "RdYlBu"
    scalebar: bool = False
    shadestyle: str = "curve"
    figsize: str = "12,8"
    block: list[str]
    layout: list[str]
    bed: list[str] | None = None
    use_default_bed: bool = True


class PrimerDesignRequest(BaseModel):
    """Request body for legacy SNP primer workflow."""

    querydb: str
    ploidy: str
    price: str
    caps: bool = True
    kasp: bool = True
    tm: str
    size: str
    pick: str
    markers: list[str] = Field(default_factory=list)


class TaskArtifact(BaseModel):
    """Output artifact reference."""

    file_name: str
    path: str
