"""LLM provider registry for the `auto` tailoring flow (ADR-009).

Each entry describes a CLI worker that can satisfy the run-directory
contract: read inputs from ``input/`` and write the required files in
``output/``. The backend dispatches based on the run's persisted
``llm_provider`` field; the registry encapsulates the per-provider CLI
shape (binary name, env-var override, non-interactive argv builder).

Cross-provider invariants (ADR-002 worker boundary and ADR-004 evidence
constraints) are enforced at the contract layer, not here — this module
only knows how to launch each CLI in non-interactive mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional


# All initial providers deliver the prompt body on stdin: the worker pipes
# ``input/tailoring_prompt.md`` to the subprocess and closes the pipe. A
# future provider that needs a different delivery shape must declare it
# explicitly so the worker can dispatch on the value.
PROMPT_DELIVERY_STDIN = "stdin"

CLAUDE_CODE_PROVIDER_ID = "claude_code"
CODEX_PROVIDER_ID = "codex"
GEMINI_PROVIDER_ID = "gemini"

# Sentinel stamped into ``metadata.json`` for runs whose
# ``tailoring_method == word_handoff``. No backend CLI runs in that case,
# but the field is non-optional so the metadata stays self-describing.
WORD_HANDOFF_PROVIDER_ID = "claude_for_word"

DEFAULT_PROVIDER_ID = CLAUDE_CODE_PROVIDER_ID


@dataclass(frozen=True)
class LLMProvider:
    """One CLI worker entry in the provider registry.

    ``build_argv`` produces the non-interactive command line given the
    resolved binary path and the permission-mode string. The prompt body
    itself is delivered via ``prompt_delivery`` (stdin in this iteration);
    it is not baked into the argv so large prompts don't hit ARG_MAX and
    don't leak into the process listing.
    """

    id: str
    display_name: str
    default_binary: str
    binary_env_var: str
    build_argv: Callable[[str, str], list[str]]
    prompt_delivery: str = PROMPT_DELIVERY_STDIN


def _claude_code_argv(binary: str, permission_mode: str) -> list[str]:
    """Claude Code's documented non-interactive form.

    ``--print`` makes Claude read the prompt and exit instead of opening a
    REPL; ``--permission-mode`` controls how tool calls (Write/Edit) are
    auto-approved inside the run directory.
    """
    return [binary, "--print", "--permission-mode", permission_mode]


def _codex_argv(binary: str, permission_mode: str) -> list[str]:
    """Codex CLI's non-interactive form (``codex exec``).

    Codex's permission model is not directly equivalent to Claude's
    ``--permission-mode``; the worker still passes the value through the
    registry so per-provider shims can map it if/when needed.
    """
    return [binary, "exec"]


def _gemini_argv(binary: str, permission_mode: str) -> list[str]:
    """Gemini CLI's non-interactive form.

    ``--prompt-stdin`` is the documented switch for piping a prompt body
    via stdin and exiting without an interactive REPL.
    """
    return [binary, "--prompt-stdin"]


_PROVIDERS: dict[str, LLMProvider] = {
    CLAUDE_CODE_PROVIDER_ID: LLMProvider(
        id=CLAUDE_CODE_PROVIDER_ID,
        display_name="Claude Code",
        default_binary="claude",
        binary_env_var="JOBAPPLY_CLAUDE_BINARY",
        build_argv=_claude_code_argv,
    ),
    CODEX_PROVIDER_ID: LLMProvider(
        id=CODEX_PROVIDER_ID,
        display_name="Codex CLI",
        default_binary="codex",
        binary_env_var="JOBAPPLY_CODEX_BINARY",
        build_argv=_codex_argv,
    ),
    GEMINI_PROVIDER_ID: LLMProvider(
        id=GEMINI_PROVIDER_ID,
        display_name="Gemini CLI",
        default_binary="gemini",
        binary_env_var="JOBAPPLY_GEMINI_BINARY",
        build_argv=_gemini_argv,
    ),
}


def list_providers() -> list[LLMProvider]:
    """Return the registered providers in declaration order."""
    return list(_PROVIDERS.values())


def get_provider(provider_id: str) -> Optional[LLMProvider]:
    """Return the provider with the given id, or ``None``."""
    return _PROVIDERS.get(provider_id)


def is_known_provider(provider_id: str) -> bool:
    """True when ``provider_id`` corresponds to a registered provider.

    The word-handoff sentinel (``claude_for_word``) is intentionally
    excluded — it is a metadata-only label, not a runnable provider, and
    must never be selected through the run-creation API.
    """
    return provider_id in _PROVIDERS


def resolve_binary(provider: LLMProvider) -> str:
    """Return the binary path for ``provider``, honoring the env override."""
    return os.environ.get(provider.binary_env_var, provider.default_binary)


def resolve_default_provider_id() -> str:
    """Return the application-wide default provider id.

    Task 066 wires this to a persisted setting; for now it stubs to the
    project-wide default (``claude_code``) so the rest of the flow can be
    implemented without coupling.
    """
    return DEFAULT_PROVIDER_ID
