from app.context_budget import (
    build_context_budget,
    check_context_budget,
    estimate_tokens,
)


def test_token_estimator_is_conservative_and_deterministic():
    text = "Python machine learning " * 20
    assert estimate_tokens(text) == estimate_tokens(text)
    assert estimate_tokens(text) >= len(text.split())


def test_context_budget_calculation_reserves_output_tokens():
    budget = build_context_budget(8192, 1200, None)
    assert budget.max_input_tokens == 6992

    overridden = build_context_budget(8192, 1200, 6500)
    assert overridden.max_input_tokens == 6500


def test_budget_check_flags_over_budget_prompt():
    budget = build_context_budget(100, 20, 50)
    check = check_context_budget("x" * 1000, budget)
    assert check.over_budget is True
    assert check.overflow_tokens > 0
    assert check.action == "compress"


def test_budget_check_passes_in_budget_prompt():
    budget = build_context_budget(100, 20, 50)
    check = check_context_budget("short prompt", budget)
    assert check.over_budget is False
    assert check.overflow_tokens == 0
    assert check.action == "pass"
