"""t026 AC-005: live netfilter state is compared, not assumed.

The renderer that installs policy and the verifier that convergence
trusts must agree on normalized rules; any drift — including a missing
terminal DROP — reads as non-conforming.
"""

import pytest
import cbrowser.supervisor.network_policy as np_module
from cbrowser.supervisor.network_policy import (
    NetworkPolicySpec,
    parse_filter_rules,
    render_ip6tables_rules,
    render_iptables_rules,
    rendered_filter_rules,
    verify_policy,
)

# t097: the policy model is Browser-only (Stream isolation is the
# media topology). Two distinct Browser specs stand in for the old
# stream/browser pair in the verify-machinery cases below.
ENFORCED_BROWSER_SPEC = NetworkPolicySpec(
    role="browser",
    allowed_tcp=[("10.251.7.254", 8443)],
    proxy_enforced=True,
)
BROWSER_SPEC = NetworkPolicySpec(
    role="browser",
    allowed_tcp=[("10.251.7.20", 1080)],
)


def test_render_parse_round_trip_both_families():
    for spec, render in (
        (ENFORCED_BROWSER_SPEC, render_iptables_rules),
        (ENFORCED_BROWSER_SPEC, render_ip6tables_rules),
        (BROWSER_SPEC, render_iptables_rules),
    ):
        policies, rules = parse_filter_rules(render(spec))
        assert policies["OUTPUT"] == "DROP"
        assert rules  # non-empty ruleset
    assert rendered_filter_rules(ENFORCED_BROWSER_SPEC)["ipv4"] == parse_filter_rules(
        render_iptables_rules(ENFORCED_BROWSER_SPEC)
    )


def test_counters_do_not_affect_parsed_equality():
    rendered = render_iptables_rules(ENFORCED_BROWSER_SPEC)
    with_counters = rendered.replace("[0:0]", "[123:4567]")
    assert parse_filter_rules(with_counters) == parse_filter_rules(rendered)


def test_verify_policy_compares_live_dump(monkeypatch):
    expected = rendered_filter_rules(ENFORCED_BROWSER_SPEC)
    monkeypatch.setattr(
        np_module, "current_filter_rules", lambda family: expected[family]
    )
    assert verify_policy(ENFORCED_BROWSER_SPEC) is True

    drifted = dict(expected)
    policies, rules = expected["ipv4"]
    drifted["ipv4"] = (policies, {**rules, "OUTPUT": rules["OUTPUT"][:-1]})
    monkeypatch.setattr(
        np_module, "current_filter_rules", lambda family: drifted[family]
    )
    assert verify_policy(ENFORCED_BROWSER_SPEC) is False


@pytest.mark.parametrize("drift", ["moved", "duplicated"])
def test_verify_policy_rejects_changed_output_chain(monkeypatch, drift):
    rendered = render_iptables_rules(BROWSER_SPEC)
    accept = "-A OUTPUT -j ACCEPT\n"
    assert accept in rendered
    changed = rendered if drift == "duplicated" else rendered.replace(accept, "")
    changed = changed.replace("-A OUTPUT -d 0.0.0.0/8 -j DROP\n", accept + "-A OUTPUT -d 0.0.0.0/8 -j DROP\n")
    live = {"ipv4": changed, "ipv6": render_ip6tables_rules(BROWSER_SPEC)}
    monkeypatch.setattr(np_module, "current_filter_rules", lambda family: parse_filter_rules(live[family]))
    assert not verify_policy(BROWSER_SPEC)


def test_distinct_browser_specs_are_not_interchangeable(monkeypatch):
    expected = rendered_filter_rules(ENFORCED_BROWSER_SPEC)
    monkeypatch.setattr(
        np_module, "current_filter_rules", lambda family: expected[family]
    )
    assert verify_policy(BROWSER_SPEC) is False


def test_install_fail_closed_raises_when_restore_fails(monkeypatch):
    # code f010: the explicit fail-closed entry point is strict — a
    # restore that exits nonzero must surface, never report success
    # (the Supervisor records the Browser as sealed on this result).
    import subprocess as _sp

    def _failing_run(*args, **kwargs):
        return _sp.CompletedProcess(args, 1, stdout=b"", stderr=b"denied")

    monkeypatch.setattr(np_module.subprocess, "run", _failing_run)
    with pytest.raises(np_module.NetworkPolicyError):
        np_module.install_fail_closed()


def test_install_fail_closed_succeeds_when_restores_pass(monkeypatch):
    import subprocess as _sp

    def _ok_run(*args, **kwargs):
        return _sp.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(np_module.subprocess, "run", _ok_run)
    np_module.install_fail_closed()  # must not raise


def test_install_fail_closed_raises_on_single_family_failure(monkeypatch):
    # test f010: a failure in only the second family must still raise —
    # an all-or-nothing stub cannot see a swallowed per-family error.
    import subprocess as _sp

    def _run(args, **kwargs):
        if "ip6tables" in args[0]:
            return _sp.CompletedProcess(args, 1, stdout=b"", stderr=b"denied")
        return _sp.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(np_module.subprocess, "run", _run)
    with pytest.raises(np_module.NetworkPolicyError):
        np_module.install_fail_closed()


def test_canonicalized_dump_matches_rendered_browser_spec():
    """A canonicalized sample derived from the current browser renderer checks
    that implicit protocol modules, /32 hosts, clause order and conntrack state
    order differ textually while the ruleset is identical. The sample is
    constructed from renderer output, not captured from a live kernel;
    verification must not report drift for an unchanged policy (t032 AC-007)."""
    spec = NetworkPolicySpec(
        role="browser",
        allowed_tcp=[("10.253.0.254", 18080)],
        proxy_enforced=True,
    )
    live = """# Canonicalized sample derived from the current browser rendering
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT DROP [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A OUTPUT -o lo -j ACCEPT
-A OUTPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A OUTPUT -d 10.253.0.254/32 -p tcp -m tcp --dport 18080 -j ACCEPT
-A OUTPUT -d 0.0.0.0/8 -j DROP
-A OUTPUT -d 192.0.0.0/24 -j DROP
-A OUTPUT -d 192.0.2.0/24 -j DROP
-A OUTPUT -d 192.88.99.0/24 -j DROP
-A OUTPUT -d 198.51.100.0/24 -j DROP
-A OUTPUT -d 203.0.113.0/24 -j DROP
-A OUTPUT -d 10.0.0.0/8 -j DROP
-A OUTPUT -d 172.16.0.0/12 -j DROP
-A OUTPUT -d 192.168.0.0/16 -j DROP
-A OUTPUT -d 100.64.0.0/10 -j DROP
-A OUTPUT -d 127.0.0.0/8 -j DROP
-A OUTPUT -d 169.254.0.0/16 -j DROP
-A OUTPUT -d 198.18.0.0/15 -j DROP
-A OUTPUT -d 224.0.0.0/4 -j DROP
-A OUTPUT -d 240.0.0.0/4 -j DROP
-A OUTPUT -j DROP
COMMIT
"""
    assert parse_filter_rules(live) == rendered_filter_rules(spec)["ipv4"]
