"""The chart keeps call load off the system-under-test SIP ports."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CHART = Path(__file__).resolve().parents[2] / "sim-platform" / "chart" / "templates"
_POLICY = (_CHART / "networkpolicy.yaml").read_text(encoding="utf-8")


def test_call_load_egress_names_only_the_scscf() -> None:
    """The load generator's policy allows SIP toward the simulated S-CSCF."""
    section = _POLICY.split("name: call-load-egress", 1)[1].split("name: sut-sip-ingress", 1)[0]
    assert "app.kubernetes.io/component: call-load" in section
    assert "app.kubernetes.io/component: scscf" in section
    assert "app.kubernetes.io/component: sut" not in section
    assert "ssbc-north" not in section
    assert "ssbc-south" not in section


def test_sut_ingress_allows_only_the_north_s_sbc() -> None:
    """The system under test accepts SIP from the simulated S-SBC, not from call load."""
    section = _POLICY.split("sut-sip-ingress", 1)[1]
    assert "app.kubernetes.io/component: sut" in section
    assert "app.kubernetes.io/component: ssbc-north" in section
    assert "app.kubernetes.io/component: ssbc-south" in section
    assert "call-load" not in section
