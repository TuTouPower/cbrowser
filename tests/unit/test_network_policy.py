"""Unit tests for NetworkPolicySpec, iptables generation, and startup gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cbrowser.supervisor.network_policy import (
    NetworkPolicySpec,
    render_ip6tables_rules,
    render_iptables_rules,
)
from cbrowser.supervisor.startup_gate import wait_for_marker
from pydantic import ValidationError


def test_network_policy_spec_validation() -> None:
    # Valid browser spec
    b_spec = NetworkPolicySpec(
        role="browser",
        allowed_tcp=[("1.1.1.1", 443)],
        allowed_udp=[],
    )
    assert b_spec.role == "browser"
    assert b_spec.allowed_tcp == [("1.1.1.1", 443)]

    # t097: the stream role no longer exists — Stream isolation is a
    # property of the media topology, not an installed policy. The old
    # stream shape (role and its udp_mux_port field) is rejected.
    with pytest.raises(ValidationError):
        NetworkPolicySpec(role="stream")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        NetworkPolicySpec(role="browser", udp_mux_port=30000)  # type: ignore[call-arg]

    # Invalid IP or port fails
    with pytest.raises(ValidationError):
        NetworkPolicySpec(role="browser", allowed_tcp=[("not-an-ip", 80)])

    with pytest.raises(ValidationError):
        NetworkPolicySpec(role="browser", allowed_tcp=[("1.1.1.1", 70000)])

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        NetworkPolicySpec(role="browser", extra_field="bad")  # type: ignore[call-arg]


def test_render_iptables_rules_browser() -> None:
    spec = NetworkPolicySpec(
        role="browser",
        allowed_tcp=[("192.168.1.100", 8080)],
        allowed_udp=[],
    )
    rules = render_iptables_rules(spec)
    assert ":INPUT DROP" in rules
    assert ":OUTPUT DROP" in rules
    assert "-A INPUT -i lo -j ACCEPT" in rules
    assert "-A OUTPUT -p tcp -d 192.168.1.100 --dport 8080 -j ACCEPT" in rules
    assert "-A OUTPUT -d 10.0.0.0/8 -j DROP" in rules
    assert "-A OUTPUT -d 172.16.0.0/12 -j DROP" in rules
    assert "-A OUTPUT -d 192.168.0.0/16 -j DROP" in rules
    assert "-A OUTPUT -d 100.64.0.0/10 -j DROP" in rules
    assert "-A OUTPUT -j ACCEPT" in rules
    assert "COMMIT" in rules


def test_startup_gate_logic(tmp_path: Path) -> None:
    gate_dir = tmp_path / "gate"
    gate_dir.mkdir()

    # Non-existent marker times out
    assert not wait_for_marker(
        gate_dir=gate_dir,
        expected_instance_id="inst-1",
        expected_role="browser",
        timeout=0.2,
        poll_interval=0.05,
    )

    # Wrong instance ID fails
    marker = gate_dir / "ready.json"
    marker.write_text(
        json.dumps({"instance_id": "inst-2", "role": "browser", "status": "ready"})
    )
    assert not wait_for_marker(
        gate_dir=gate_dir,
        expected_instance_id="inst-1",
        expected_role="browser",
        timeout=0.2,
        poll_interval=0.05,
    )

    # Wrong role fails
    marker.write_text(
        json.dumps({"instance_id": "inst-1", "role": "stream", "status": "ready"})
    )
    assert not wait_for_marker(
        gate_dir=gate_dir,
        expected_instance_id="inst-1",
        expected_role="browser",
        timeout=0.2,
        poll_interval=0.05,
    )

    # Status not ready fails
    marker.write_text(
        json.dumps({"instance_id": "inst-1", "role": "browser", "status": "error"})
    )
    assert not wait_for_marker(
        gate_dir=gate_dir,
        expected_instance_id="inst-1",
        expected_role="browser",
        timeout=0.2,
        poll_interval=0.05,
    )

    # Matching ready marker succeeds
    marker.write_text(
        json.dumps({"instance_id": "inst-1", "role": "browser", "status": "ready"})
    )
    assert wait_for_marker(
        gate_dir=gate_dir,
        expected_instance_id="inst-1",
        expected_role="browser",
        timeout=0.2,
        poll_interval=0.05,
    )


def _output_rules(rendered: str) -> list[str]:
    return [
        line.strip()
        for line in rendered.splitlines()
        if line.strip().startswith("-A OUTPUT")
    ]


def _unconditional_output_accepts(rendered: str) -> list[str]:
    return [
        line.strip()
        for line in rendered.splitlines()
        if line.strip() == "-A OUTPUT -j ACCEPT"
    ]


def test_browser_output_terminal_both_families() -> None:
    # t097: only the Browser renders a policy. Direct mode ends in an
    # unconditional ACCEPT; proxy-enforced mode fails closed with DROP
    # and no unconditional accepts, in both address families.
    direct = NetworkPolicySpec(role="browser")
    enforced = NetworkPolicySpec(role="browser", proxy_enforced=True)
    for render in (render_iptables_rules, render_ip6tables_rules):
        assert _output_rules(render(direct))[-1] == "-A OUTPUT -j ACCEPT"
        assert _output_rules(render(enforced))[-1] == "-A OUTPUT -j DROP"
        assert _unconditional_output_accepts(render(enforced)) == []


def test_browser_keeps_public_egress() -> None:
    spec = NetworkPolicySpec(role="browser")
    rules = render_iptables_rules(spec)
    assert "-A OUTPUT -j ACCEPT" in rules


def test_allow_lan_media_field_is_rejected() -> None:
    # t054: the deleted field must not silently survive as an ignored
    # extra — NetworkPolicySpec forbids extras, so passing it fails.
    with pytest.raises(ValidationError):
        NetworkPolicySpec(
            role="browser", allow_lan_media=True  # type: ignore[call-arg]
        )
