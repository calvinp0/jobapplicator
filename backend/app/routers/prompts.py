"""Prompt harness editor API (task 098).

Read/update/delete the local prompt overrides used by the resume
tailoring and revision workers. The router never accepts a free-form
filename or path — every endpoint is keyed by the registered prompt id
(see ``app.prompt_harness.PROMPT_REGISTRY``), so a caller cannot read
or write arbitrary files.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..prompt_harness import (
    PromptHarnessError,
    UnknownPromptError,
    build_detail,
    build_summary,
    delete_override,
    get_prompt_definition,
    list_prompts,
    save_override,
    validate_prompt_content,
)


router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptSummaryRead(BaseModel):
    id: str
    label: str
    description: str
    default_path: str
    has_override: bool
    effective_source: str
    updated_at: str | None


class PromptDetailRead(BaseModel):
    id: str
    label: str
    description: str
    default_path: str
    has_override: bool
    effective_source: str
    default_content: str
    override_content: str | None
    effective_content: str
    effective_hash: str
    updated_at: str | None


class PromptOverrideUpdate(BaseModel):
    content: str = Field(..., min_length=1)


class PromptValidationRead(BaseModel):
    valid: bool
    warnings: list[str]


def _lookup_or_404(prompt_id: str):
    try:
        return get_prompt_definition(prompt_id)
    except UnknownPromptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[PromptSummaryRead])
def list_prompt_harnesses() -> list[PromptSummaryRead]:
    summaries: list[PromptSummaryRead] = []
    for definition in list_prompts():
        summary = build_summary(definition)
        summaries.append(
            PromptSummaryRead(
                id=summary.id,
                label=summary.label,
                description=summary.description,
                default_path=summary.default_path,
                has_override=summary.has_override,
                effective_source=summary.effective_source,
                updated_at=summary.updated_at,
            )
        )
    return summaries


@router.get("/{prompt_id}", response_model=PromptDetailRead)
def get_prompt_harness(prompt_id: str) -> PromptDetailRead:
    definition = _lookup_or_404(prompt_id)
    try:
        detail = build_detail(definition)
    except PromptHarnessError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PromptDetailRead(
        id=detail.id,
        label=detail.label,
        description=detail.description,
        default_path=detail.default_path,
        has_override=detail.has_override,
        effective_source=detail.effective_source,
        default_content=detail.default_content,
        override_content=detail.override_content,
        effective_content=detail.effective_content,
        effective_hash=detail.effective_hash,
        updated_at=detail.updated_at,
    )


@router.put("/{prompt_id}/override", response_model=PromptDetailRead)
def save_prompt_override(
    prompt_id: str, payload: PromptOverrideUpdate
) -> PromptDetailRead:
    definition = _lookup_or_404(prompt_id)
    try:
        save_override(definition, payload.content)
    except PromptHarnessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_prompt_harness(prompt_id)


@router.delete("/{prompt_id}/override", response_model=PromptDetailRead)
def delete_prompt_override(prompt_id: str) -> PromptDetailRead:
    definition = _lookup_or_404(prompt_id)
    try:
        delete_override(definition)
    except PromptHarnessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_prompt_harness(prompt_id)


@router.post(
    "/{prompt_id}/validate",
    response_model=PromptValidationRead,
    status_code=status.HTTP_200_OK,
)
def validate_prompt(prompt_id: str) -> PromptValidationRead:
    """Validate the *effective* prompt body for ``prompt_id``.

    Validation runs against whichever content the worker would use —
    the override if one exists, otherwise the default. Warnings are
    informational; this endpoint does not reject prompts that are
    missing required elements.
    """
    definition = _lookup_or_404(prompt_id)
    try:
        detail = build_detail(definition)
    except PromptHarnessError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    result = validate_prompt_content(definition.id, detail.effective_content)
    return PromptValidationRead(valid=result.valid, warnings=result.warnings)
