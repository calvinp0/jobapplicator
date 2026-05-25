"""User-editable application settings (ADR-009 / task 066).

Today this exposes only the default-LLM-provider setting. The endpoint
shape bundles the current default with the registry listing so the
Settings page can render the dropdown without a second round trip.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..llm_providers import list_providers
from ..schemas import LLMProviderRead
from ..settings import (
    UnknownLLMProviderError,
    get_default_llm_provider,
    set_default_llm_provider,
)


router = APIRouter(prefix="/settings", tags=["settings"])


class DefaultLLMProviderRead(BaseModel):
    default_provider: str
    available: list[LLMProviderRead]


class DefaultLLMProviderUpdate(BaseModel):
    default_provider: str


def _available_providers() -> list[LLMProviderRead]:
    return [
        LLMProviderRead(
            id=p.id,
            display_name=p.display_name,
            default_binary=p.default_binary,
            binary_env_var=p.binary_env_var,
        )
        for p in list_providers()
    ]


@router.get("/llm-provider", response_model=DefaultLLMProviderRead)
def read_default_llm_provider() -> DefaultLLMProviderRead:
    return DefaultLLMProviderRead(
        default_provider=get_default_llm_provider(),
        available=_available_providers(),
    )


@router.put("/llm-provider", response_model=DefaultLLMProviderRead)
def update_default_llm_provider(
    payload: DefaultLLMProviderUpdate,
) -> DefaultLLMProviderRead:
    try:
        set_default_llm_provider(payload.default_provider)
    except UnknownLLMProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DefaultLLMProviderRead(
        default_provider=get_default_llm_provider(),
        available=_available_providers(),
    )
