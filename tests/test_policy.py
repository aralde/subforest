import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from subforest.policy import Policy, TurnState

EXAMPLE = Path(__file__).parents[1] / "examples" / "policies" / "read-before-semantic-search.yaml"


def test_require_before_counts_calls() -> None:
    policy = Policy.from_dict(
        {"rules": [{"type": "require_before", "tool": "x", "requires": "read", "min_calls": 2}]}
    )
    assert policy.check("x", ["read"]) is not None
    assert policy.check("x", ["read", "search", "read"]) is None
    assert policy.check("other", []) is None


def test_max_calls() -> None:
    policy = Policy.from_dict({"rules": [{"type": "max_calls", "tool": "search", "limit": 2}]})
    assert policy.check("search", ["search"]) is None
    assert "limited to 2" in (policy.check("search", ["search", "read", "search"]) or "")


def test_max_calls_zero_disables_tool() -> None:
    policy = Policy.from_dict({"rules": [{"type": "max_calls", "tool": "search", "limit": 0}]})
    assert policy.check("search", []) is not None


def test_cooldown_counts_calls_since_last_use() -> None:
    policy = Policy.from_dict({"rules": [{"type": "cooldown", "tool": "search", "calls": 2}]})
    assert policy.check("search", []) is None
    assert policy.check("search", ["search", "read"]) is not None
    assert policy.check("search", ["search", "read", "expand"]) is None
    assert policy.check("search", ["search", "read", "expand", "search"]) is not None


def test_custom_message_and_first_violation_wins() -> None:
    policy = Policy.from_dict(
        {
            "rules": [
                {"type": "max_calls", "tool": "search", "limit": 0, "message": "no searching"},
                {"type": "cooldown", "tool": "search", "calls": 1},
            ]
        }
    )
    assert policy.check("search", []) == "no searching"


@pytest.mark.parametrize(
    "rule",
    [
        {"type": "unknown", "tool": "x"},
        {"type": "max_calls", "tool": "x", "limit": -1},
        {"type": "cooldown", "tool": "x", "calls": 0},
        {"type": "require_before", "tool": "x"},
        {"type": "max_calls", "tool": "x", "limit": 1, "extra": True},
    ],
)
def test_invalid_rules_rejected(rule: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Policy.from_dict({"rules": [rule]})


def test_turn_state_records_blocked_separately() -> None:
    state = TurnState(
        Policy.from_dict({"rules": [{"type": "require_before", "tool": "x", "requires": "read"}]})
    )
    assert state.attempt("x") is not None
    assert state.attempt("read") is None
    assert state.attempt("x") is None
    assert state.calls == ["read", "x"] and state.blocked == ["x"]
    state.new_turn()
    assert state.calls == [] and state.blocked == []


def test_load_yaml_example() -> None:
    policy = Policy.load(EXAMPLE)
    assert [r.type for r in policy.rules] == ["require_before", "cooldown", "max_calls"]
    assert "read at least one node" in (policy.check("semantic_search", []) or "")


def test_load_json_and_reject_non_mapping(tmp_path: Path) -> None:
    good = tmp_path / "p.json"
    good.write_text(json.dumps({"rules": [{"type": "max_calls", "tool": "search", "limit": 1}]}))
    assert len(Policy.load(good).rules) == 1
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a list\n")
    with pytest.raises(ValueError):
        Policy.load(bad)
