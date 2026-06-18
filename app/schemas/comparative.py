"""Schemas for comparative genomics endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HomologHit(BaseModel):
    """Homolog hit."""

    query_gene: str
    target_gene: str
    description: str | None = None
    species: str
    gene_name: str | None = None
    qcovs: float | None = None
    length: int | None = None
    identity: float | None = None
    positive: float | None = None
    evalue: float | None = None
    score: float | None = None


class SyntenyRecord(BaseModel):
    """Synteny lookup row."""

    chromosome: str
    start_mb: float
    end_mb: float
    strand: str
    gene: str
    chinese_spring: str | None = None
    durum_wheat: str | None = None
    wild_emmer: str | None = None
    triticum_urartu: str | None = None
    aegilops_tauschii: str | None = None


class IDMapping(BaseModel):
    """Gene ID mapping."""

    query_gene: str
    reference_gene: str
    code: str
    length: str
