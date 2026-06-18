"""Schemas for sequence retrieval endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SequenceRecord(BaseModel):
    """Named sequence payload."""

    sequence_id: str
    fasta: str


class SequenceBundle(BaseModel):
    """Bundled sequences for a gene or interval."""

    gene_id: str | None = None
    genome_sequence: str | None = None
    gene_sequence: str | None = None
    protein_sequence: str | None = None
    additional_sequences: list[SequenceRecord] = Field(default_factory=list)
