"""Task-like endpoints — now handled by primer_server router."""

from __future__ import annotations

from fastapi import APIRouter

# All primer endpoints moved to app/api/routers/primer_server.py
router = APIRouter(prefix="/tasks", tags=["SNP Marker Design"])
