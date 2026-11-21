"""t097: Browser-only Policy Agent, grouped naming, legacy convergence.

Drives the real ``DockerAdapter`` against the t082 in-memory Docker
double plus the in-process Policy Agent rig:

- a Browser start creates its Agent under the display-number name
  ``<prefix>-<NNNN>-policy-agent``, grouped with the Profile's
  sandboxes (compose project ``<prefix>-profiles``, service
  ``<NNNN>-policy-agent``, profile-number label);
- a Stream target can no longer be given a Policy Agent at all;
- the startup orphan sweep removes Stream Agents outright and
  replaces a legacy-shaped Browser Agent (pre-t097 hash-slot name,
  no grouping labels) with exactly one current-shape Agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cbrowser.supervisor.docker_adapter import DockerSandboxError
from tests.unit.policy_agent_test_support import PolicyAgentTestRig
from tests.unit.test_t082_adapter_policy_agents import (
    _FakeClient,
    _adapter,
    _make_rig,
    _start_browser,
)

pytestmark = pytest.mark.serial

PREFIX = "cbrowser-t005"


def _agent_creates(client: _FakeClient) -> list[tuple[str, dict]]:
    return [
        (image, kwargs)
        for image, kwargs in client.created
        if (kwargs.get("labels") or {}).get("com.cbrowser.role")
        == "network-policy-agent"
    ]


@pytest.mark.asyncio
async def test_browser_agent_carries_display_number_name_and_grouping(
    tmp_path: Path,
):
    adapter, client, rig, container = await _start_browser(tmp_path)

    creates = _agent_creates(client)
    assert len(creates) == 1
    _, kwargs = creates[0]
    assert kwargs["name"] == f"{PREFIX}-0001-policy-agent"
    labels = kwargs["labels"]
    assert labels["com.docker.compose.project"] == f"{PREFIX}-profiles"
    assert labels["com.docker.compose.service"] == "0001-policy-agent"
    assert labels["com.cbrowser.profile-number"] == "0001"
    assert labels["com.cbrowser.target-role"] == "browser"
    assert labels["com.cbrowser.profile-id"] == "p1"


def test_stream_target_cannot_be_given_a_policy_agent(tmp_path: Path):
    client = _FakeClient()
    adapter = _adapter(tmp_path, client)
    adapter.remember_profile_number("p1", 1)
    target = client.create(
        "img", {"name": "stream-target", "labels": {}}
    )
    with pytest.raises(DockerSandboxError):
        adapter.ensure_policy_agent(
            target,
            profile_id="p1",
            instance_id="inst_1",
            config_version=3,
            role="stream",
        )
    assert _agent_creates(client) == []


def _seed_agent(
    client: _FakeClient,
    *,
    name: str,
    labels: dict[str, str],
):
    return client.create("img", {"name": name, "labels": labels})


def _browser_target(client: _FakeClient):
    return client.create(
        "img",
        {
            "name": f"{PREFIX}-0001-browser",
            "labels": {
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.profile-id": "p1",
                "com.cbrowser.role": "browser",
                "com.cbrowser.config-version": "3",
                "com.cbrowser.prefix": PREFIX,
                "com.cbrowser.profile-number": "0001",
            },
            "environment": {"RUNTIME_INSTANCE_ID": "inst_1"},
        },
    )


def _legacy_agent_labels(target_id: str) -> dict[str, str]:
    # The pre-t097 label shape: full binding labels, but no profile
    # number and no compose grouping.
    return {
        "com.cbrowser.prefix": PREFIX,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "network-policy-agent",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.runtime-instance-id": "inst_1",
        "com.cbrowser.config-version": "3",
        "com.cbrowser.target-role": "browser",
        "com.cbrowser.target-container-id": target_id,
        "com.cbrowser.instance-id": "dep-test",
    }


def test_orphan_sweep_removes_stream_agents_and_replaces_legacy_browser_agent(
    tmp_path: Path,
):
    client = _FakeClient()
    adapter = _adapter(tmp_path, client)
    rig: PolicyAgentTestRig = _make_rig()
    rig.install_on(adapter)
    adapter.remember_profile_number("p1", 1)

    browser = _browser_target(client)
    stream = client.create(
        "img",
        {
            "name": f"{PREFIX}-0001-stream",
            "labels": {
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.profile-id": "p1",
                "com.cbrowser.role": "stream",
                "com.cbrowser.config-version": "3",
                "com.cbrowser.prefix": PREFIX,
                "com.cbrowser.profile-number": "0001",
            },
            "environment": {"CBROWSER_RUNTIME_INSTANCE_ID": "inst_1"},
        },
    )
    stream_agent_labels = _legacy_agent_labels(stream.id)
    stream_agent_labels["com.cbrowser.target-role"] = "stream"
    stream_agent = _seed_agent(
        client,
        name=f"{PREFIX}-policy-agent-deadbeefdeadbeef01",
        labels=stream_agent_labels,
    )
    legacy_slot = adapter._policy_agent_slot("p1", "inst_1", "browser")
    legacy_agent = _seed_agent(
        client,
        name=f"{PREFIX}-policy-agent-{legacy_slot}",
        labels=_legacy_agent_labels(browser.id),
    )

    adapter._cleanup_orphan_policy_agents()

    # The Stream Agent is abolished: removed even though its target
    # is alive and its binding labels are complete.
    assert stream_agent.removed is True
    # The legacy Browser Agent is replaced by exactly one Agent in
    # the current shape, bound to the same target.
    assert legacy_agent.removed is True
    survivors = [
        c
        for c in client.containers_by_name.values()
        if c.labels.get("com.cbrowser.role") == "network-policy-agent"
    ]
    assert len(survivors) == 1
    survivor = survivors[0]
    assert survivor.name == f"{PREFIX}-0001-policy-agent"
    assert survivor.labels["com.docker.compose.project"] == f"{PREFIX}-profiles"
    assert survivor.labels["com.docker.compose.service"] == "0001-policy-agent"
    assert survivor.labels["com.cbrowser.profile-number"] == "0001"
    assert survivor.labels["com.cbrowser.target-container-id"] == browser.id
