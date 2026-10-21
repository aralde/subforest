"""Declarative tool-order rules evaluated against the calls made in the current turn."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Rule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    message: str | None = None


class RequireBefore(_Rule):
    """`tool` may run only after `requires` ran at least `min_calls` times this turn."""

    type: Literal["require_before"] = "require_before"
    requires: str
    min_calls: int = Field(default=1, ge=1)

    def violation(self, calls: list[str]) -> str | None:
        done = calls.count(self.requires)
        if done >= self.min_calls:
            return None
        return self.message or (
            f"Blocked: call `{self.requires}` at least {self.min_calls} time(s) before `{self.tool}` "
            f"this turn ({done} so far). Use `{self.requires}` on a node from your last results first."
        )


class MaxCalls(_Rule):
    """`tool` may run at most `limit` times per turn."""

    type: Literal["max_calls"] = "max_calls"
    limit: int = Field(ge=0)

    def violation(self, calls: list[str]) -> str | None:
        if calls.count(self.tool) < self.limit:
            return None
        return self.message or (
            f"Blocked: `{self.tool}` is limited to {self.limit} call(s) per turn. "
            "Work with the nodes you already have (expand / read) or answer."
        )


class Cooldown(_Rule):
    """After `tool` runs, at least `calls` other tool calls must happen before it runs again."""

    type: Literal["cooldown"] = "cooldown"
    calls: int = Field(ge=1)

    def violation(self, calls: list[str]) -> str | None:
        if self.tool not in calls:
            return None
        since = len(calls) - 1 - max(i for i, name in enumerate(calls) if name == self.tool)
        if since >= self.calls:
            return None
        return self.message or (
            f"Blocked: `{self.tool}` needs {self.calls} other call(s) since its last use ({since} so far). "
            "Inspect the current results (expand / read) before searching again."
        )


Rule = Annotated[RequireBefore | MaxCalls | Cooldown, Field(discriminator="type")]


class Policy(BaseModel):
    """A list of tool-order rules.

    Example:
        >>> policy = Policy.from_dict({"rules": [
        ...     {"type": "require_before", "tool": "semantic_search", "requires": "read"}]})
        >>> policy.check("semantic_search", []) is not None, policy.check("semantic_search", ["read"])
        (True, None)
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: list[Rule] = Field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Policy:
        """Validate a policy from plain data (as loaded from JSON or YAML).

        Example:
            >>> len(Policy.from_dict({"rules": [{"type": "max_calls", "tool": "search", "limit": 3}]}).rules)
            1
        """
        return cls.model_validate(dict(data))

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        """Load a policy from a `.json`, `.yaml` or `.yml` file (YAML needs the `subforest[yaml]` extra).

        Example:
            >>> Policy.load("missing.json")
            Traceback (most recent call last):
            ...
            FileNotFoundError: ...
        """
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise ImportError("YAML policies need PyYAML: pip install 'subforest[yaml]'") from exc
            data = yaml.safe_load(raw) or {}
        else:
            data = json.loads(raw)
        if not isinstance(data, Mapping):
            raise ValueError(f"{path}: a policy must be a mapping with a `rules` list")
        return cls.from_dict(data)

    def check(self, tool: str, calls: list[str]) -> str | None:
        """Return the first violation message for calling `tool` after `calls` this turn, or `None`.

        Example:
            >>> Policy.from_dict({"rules": [{"type": "cooldown", "tool": "search", "calls": 1}]}).check(
            ...     "search", ["search"])
            'Blocked: `search` needs 1 other call(s) since its last use (0 so far). ...'
        """
        for rule in self.rules:
            if rule.tool == tool and (message := rule.violation(calls)):
                return message
        return None


class TurnState:
    """Calls executed in the current turn, checked against a policy before each new call.

    Blocked calls are recorded separately and do not count as calls.

    Example:
        >>> limit_one = {"rules": [{"type": "max_calls", "tool": "search", "limit": 1}]}
        >>> state = TurnState(Policy.from_dict(limit_one))
        >>> state.attempt("search") is None, state.attempt("search") is not None
        (True, True)
        >>> state.calls, state.blocked
        (['search'], ['search'])
    """

    def __init__(self, policy: Policy | None = None) -> None:
        self.policy = policy or Policy()
        self.calls: list[str] = []
        self.blocked: list[str] = []

    def attempt(self, tool: str) -> str | None:
        """Check `tool` against the policy; record it as executed if allowed, else return the message."""
        message = self.policy.check(tool, self.calls)
        (self.blocked if message else self.calls).append(tool)
        return message

    def new_turn(self) -> None:
        """Forget this turn's calls.

        Example:
            >>> state = TurnState()
            >>> _ = state.attempt("read"); state.new_turn(); state.calls
            []
        """
        self.calls.clear()
        self.blocked.clear()
