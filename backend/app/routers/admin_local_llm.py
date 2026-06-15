"""Admin diagnostics endpoints for local LLM requests."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..local_llm_diagnostics import diagnostics_store


router = APIRouter(prefix="/admin/local-llm", tags=["admin-local-llm"])


@router.get("/diagnostics")
def get_local_llm_diagnostics() -> dict[str, Any]:
    """Return the current in-memory local LLM diagnostic snapshot."""
    return diagnostics_store.snapshot()

