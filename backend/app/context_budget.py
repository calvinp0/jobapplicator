"""Lightweight context-window safeguards for local LLM calls."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


BudgetAction = Literal["pass", "compress", "fallback", "abort", "fail"]


@dataclass(frozen=True)
class ContextBudget:
    context_window_tokens: int
    reserved_output_tokens: int
    max_input_tokens: int


@dataclass(frozen=True)
class ContextBudgetCheck:
    estimated_input_tokens: int
    context_window_tokens: int
    reserved_output_tokens: int
    max_input_tokens: int
    over_budget: bool
    overflow_tokens: int
    action: BudgetAction

    def as_dict(self) -> dict[str, int | bool | str]:
        return {
            "estimated_input_tokens": self.estimated_input_tokens,
            "context_window_tokens": self.context_window_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "max_input_tokens": self.max_input_tokens,
            "over_budget": self.over_budget,
            "overflow_tokens": self.overflow_tokens,
            "action": self.action,
        }


def estimate_tokens(text: str) -> int:
    """Conservatively estimate prompt tokens without a tokenizer dependency."""
    if not text:
        return 0
    char_estimate = math.ceil(len(text) / 4)
    word_estimate = math.ceil(len(text.split()) * 1.3)
    return max(char_estimate, word_estimate)


def build_context_budget(
    context_window_tokens: int,
    reserved_output_tokens: int,
    max_input_tokens: int | None,
) -> ContextBudget:
    """Build and validate a local-model input budget."""
    try:
        context_window = int(context_window_tokens)
        reserved_output = int(reserved_output_tokens)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "context_window_tokens and reserved_output_tokens must be integers"
        ) from exc

    if context_window <= 0:
        raise ValueError("context_window_tokens must be positive")
    if reserved_output <= 0:
        raise ValueError("reserved_output_tokens must be positive")
    computed_max = context_window - reserved_output
    if computed_max <= 0:
        raise ValueError(
            "reserved_output_tokens must be smaller than context_window_tokens"
        )

    if max_input_tokens is None:
        max_input = computed_max
    else:
        try:
            max_input = int(max_input_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_input_tokens must be an integer") from exc
        if max_input <= 0:
            raise ValueError("max_input_tokens must be positive")
        if max_input > computed_max:
            raise ValueError(
                "max_input_tokens cannot exceed context_window_tokens minus "
                "reserved_output_tokens"
            )

    return ContextBudget(
        context_window_tokens=context_window,
        reserved_output_tokens=reserved_output,
        max_input_tokens=max_input,
    )


def check_context_budget(
    prompt: str,
    budget: ContextBudget,
    *,
    action: BudgetAction | None = None,
) -> ContextBudgetCheck:
    estimated = estimate_tokens(prompt)
    overflow = max(0, estimated - budget.max_input_tokens)
    over = overflow > 0
    return ContextBudgetCheck(
        estimated_input_tokens=estimated,
        context_window_tokens=budget.context_window_tokens,
        reserved_output_tokens=budget.reserved_output_tokens,
        max_input_tokens=budget.max_input_tokens,
        over_budget=over,
        overflow_tokens=overflow,
        action=action or ("compress" if over else "pass"),
    )
