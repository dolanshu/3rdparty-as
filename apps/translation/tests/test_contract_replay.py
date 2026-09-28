"""Replay of the decision contract case set against the translation use case.

``testbed/contracts/decision/cases.json`` states, in data and not in Python,
"given this number and this configuration, this is the verdict". Every
implementation has to reproduce it: today the Python one, tomorrow the Go one
(ADR-0012). This module is the translation use case's replay of the cases that
apply to it — those whose ``applies_to`` carries ``translation`` or ``both``.

Only ``TRANSLATE`` is this use case's own answer; ``DECLINE``, ``NOT_FOUND`` and
``FORWARD`` are the kernel's and must come back untouched, which is what the
shared ``both`` cases assert. The rewriting itself is asserted by the
``translation`` cases, because the anti-fraud use case deliberately does not
rewrite and would answer differently (see the contract README).

The case set is data on disk, not a fixture invented here: a missing or empty
file fails the replay instead of silently replaying nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from as_platform.decision.decide import DecisionRequest
from as_platform.decision.rules import Action, Rule, RuleSet
from as_translation.decision import TranslationRule, decide_call

pytestmark = pytest.mark.contract

# The cases this use case must answer, and the ones it must share with every
# other implementation.
_THIS_USE_CASE: Final = "translation"
_SHARED: Final = "both"


def _repository_root() -> Path:
    """Return the workspace root, whichever directory the run started from.

    The root is the only ancestor that holds both the workspace manifest and
    the ``testbed/`` tree, so the walk stops there and nowhere else.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "testbed").is_dir():
            return candidate
    return here.parents[3]


_CASES_PATH: Final = _repository_root() / "testbed" / "contracts" / "decision" / "cases.json"


def _load_cases() -> list[dict[str, Any]]:
    """Read the contract case set, failing loudly when it is not there.

    Returns:
        Every case of the set, in file order.
    """
    if not _CASES_PATH.is_file():
        pytest.fail(f"the decision contract case set is missing: {_CASES_PATH}")

    cases: Any = json.loads(_CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        pytest.fail(f"the decision contract case set is empty: {_CASES_PATH}")
    return list(cases)


def _applies_to(case: dict[str, Any]) -> bool:
    """Tell whether one case is this use case's to answer."""
    return bool({_THIS_USE_CASE, _SHARED} & set(case["applies_to"]))


_CASES: Final = [case for case in _load_cases() if _applies_to(case)]


def _case_id(case: dict[str, Any]) -> str:
    """Name one parametrized case after its ``case_id``."""
    return str(case["case_id"])


def _rule_set(case: dict[str, Any]) -> RuleSet:
    """Build the kernel rule set one case declares."""
    return RuleSet(
        rules=tuple(
            Rule(
                rule_id=item["rule_id"],
                prefix=item["prefix"],
                action=Action(item["action"]),
            )
            for item in case.get("rules", ())
        )
    )


def _translations(case: dict[str, Any]) -> tuple[TranslationRule, ...]:
    """Build the translation rules one case declares."""
    return tuple(
        TranslationRule(
            rule_id=item["rule_id"],
            prefix=item["prefix"],
            strip_prefix=item["strip_prefix"],
            add_prefix=item["add_prefix"],
        )
        for item in case.get("translations", ())
    )


def _request(case: dict[str, Any]) -> DecisionRequest:
    """Build the request one case declares, with ``received_at`` as data."""
    return DecisionRequest(
        call_id=case["call_id"],
        calling_number=case["calling_number"],
        called_number=case["called_number"],
        received_at=float(case["received_at"]),
    )


@pytest.mark.contract
def test_the_contract_set_carries_cases_for_this_use_case() -> None:
    """A filter that matched nothing would make the replay below pass vacuously."""
    assert _CASES, f"the decision contract set carries no case for {_THIS_USE_CASE}"


@pytest.mark.contract
@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_contract_case(case: dict[str, Any]) -> None:
    """One contract case, replayed and compared field for field."""
    decision = decide_call(_request(case), _rule_set(case), _translations(case))
    expected = case["expected"]

    assert decision.action.value == expected["action"]
    assert decision.target == expected["target"]
    assert decision.reason_code == expected["reason_code"]
    assert decision.matched_rule_id == expected["matched_rule_id"]
