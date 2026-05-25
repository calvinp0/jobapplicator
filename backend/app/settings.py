"""Application-wide settings store (ADR-009 / task 066).

The user-facing default LLM provider lives here. Task 065 introduced the
provider registry and a per-run override; this module persists the
fallback used when a run-creation request does not specify one.

Helpers manage their own short-lived session via :data:`SessionLocal` so
callers (the run-creation route and the settings router) do not have to
thread a ``Session`` through. The store is a simple key/value table
(:class:`~app.models.AppSetting`) — intentionally not a general-purpose
feature-flag system. Only the ``default_llm_provider`` key is read or
written today.
"""

from __future__ import annotations

from .db import SessionLocal
from .llm_providers import DEFAULT_PROVIDER_ID, is_known_provider, list_providers
from .models import AppSetting


DEFAULT_LLM_PROVIDER_KEY = "default_llm_provider"


class UnknownLLMProviderError(ValueError):
    """Raised when an unknown provider id is passed to the setter."""


def _known_provider_ids() -> list[str]:
    return [p.id for p in list_providers()]


def get_default_llm_provider() -> str:
    """Return the persisted default provider id.

    Falls back to :data:`DEFAULT_PROVIDER_ID` (``claude_code``) when no row
    exists yet, so a fresh database (and any caller that runs before the
    Settings page has been used) gets the documented default without any
    one-time seeding step.
    """
    with SessionLocal() as session:
        row = session.get(AppSetting, DEFAULT_LLM_PROVIDER_KEY)
        if row is None:
            return DEFAULT_PROVIDER_ID
        return row.value


def set_default_llm_provider(provider_id: str) -> str:
    """Persist ``provider_id`` as the default and return it.

    Validates against the provider registry from task 065. An unknown id
    raises :class:`UnknownLLMProviderError` *before* the row is touched,
    so a rejected update leaves the persisted value unchanged.
    """
    if not is_known_provider(provider_id):
        known = ", ".join(_known_provider_ids())
        raise UnknownLLMProviderError(
            f"unknown llm_provider: {provider_id!r}; known: {known}"
        )
    with SessionLocal() as session:
        row = session.get(AppSetting, DEFAULT_LLM_PROVIDER_KEY)
        if row is None:
            row = AppSetting(key=DEFAULT_LLM_PROVIDER_KEY, value=provider_id)
            session.add(row)
        else:
            row.value = provider_id
        session.commit()
    return provider_id
