"""Read-only listing of the LLM provider registry (ADR-009).

The frontend uses this endpoint to render a provider selector without
duplicating the registry on the client. The route is anonymous to match
the rest of the local-first backend; the registry contents are not
secrets.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..llm_providers import list_providers
from ..schemas import LLMProviderRead


router = APIRouter(prefix="/llm-providers", tags=["llm-providers"])


@router.get("", response_model=list[LLMProviderRead])
def list_llm_providers() -> list[LLMProviderRead]:
    return [
        LLMProviderRead(
            id=p.id,
            display_name=p.display_name,
            default_binary=p.default_binary,
            binary_env_var=p.binary_env_var,
        )
        for p in list_providers()
    ]
