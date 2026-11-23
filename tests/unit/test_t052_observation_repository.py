"""t052 / t105: repository-level egress observation currency.

An observation is a point-in-time snapshot with no expiry.  The single
current row per proxy is the newest one whose endpoint fingerprint and
credential revision still match the proxy.  Every status (ok / pending /
failed) obeys that same identity rule; only ``ok`` rows additionally need
an egress IP and country.  This file pins both the single-row path
(``_current_observation``) and the batched list path
(``_current_observations``), plus cross-restart reads of the same DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event

from cbrowser.adapters.database.models import ProxyEgressObservationModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.egress_observation import EgressObservation
from cbrowser.domain.proxy_endpoint import ProxyEndpoint

NOW = datetime.now(timezone.utc)


def _endpoint(host="proxy.example.com", port=8080):
    return ProxyEndpoint(scheme="http", host=host, port=port, username="user")


@pytest_asyncio.fixture
async def repo(db_context):
    _engine, session_maker = db_context
    return ProfileRepository(session_maker)


async def _make_proxy(repo, name, host="proxy.example.com", port=8080):
    return await repo.create_proxy(
        {
            "name": name,
            "scheme": "http",
            "host": host,
            "port": port,
            "username": "user",
            "password": "s3cret-pw",
        }
    )


def _observation(
    proxy,
    *,
    status="ok",
    observed_at=None,
    country_code="JP",
    egress_ip="203.0.113.7",
    endpoint_fingerprint=None,
    credential_revision=None,
):
    return EgressObservation(
        proxy_id=proxy.id,
        endpoint_fingerprint=endpoint_fingerprint
        or _endpoint(proxy.host, proxy.port).fingerprint,
        credential_revision=credential_revision
        if credential_revision is not None
        else proxy.credential_revision,
        status=status,
        egress_ip=egress_ip,
        country_code=country_code,
        observed_at=observed_at if observed_at is not None else NOW,
    )


@pytest.mark.asyncio
async def test_ok_observation_stays_current_across_any_time(repo, db_context):
    """t105 AC-002: a successful observation remains the current one
    regardless of how old its ``observed_at`` is."""
    proxy = await _make_proxy(repo, "px-old")
    await repo.record_egress_observation(
        proxy.id,
        _observation(proxy, observed_at=NOW - timedelta(days=4000)),
    )

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "ok"
    assert got.latency_ms is None
    assert got.country_code == "JP"
    assert got.egress_ip == "203.0.113.7"
    assert got.observed_at is not None


@pytest.mark.asyncio
async def test_current_observation_survives_new_repository_instance(
    repo, db_context
):
    """t105 AC-002: a fresh service/repository instance reading the same
    DB sees the same current observation (no in-memory clock or cache)."""
    proxy = await _make_proxy(repo, "px-restart")
    await repo.record_egress_observation(
        proxy.id, _observation(proxy, observed_at=NOW - timedelta(days=10))
    )

    _engine, session_maker = db_context
    restarted = ProfileRepository(session_maker)
    got = await restarted.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "ok"
    assert got.country_code == "JP"
    assert got.egress_ip == "203.0.113.7"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ok", "failed", "pending"])
@pytest.mark.parametrize("mismatch", ["endpoint", "credential"])
async def test_endpoint_or_credential_change_invalidates_every_status(
    repo, status, mismatch
):
    """t105 AC-003: the same identity rule hides all three statuses when
    the stored observation belongs to an old endpoint or credential set."""
    proxy = await _make_proxy(repo, f"px-{status}-{mismatch}-identity")
    override = (
        {"endpoint_fingerprint": "old-fingerprint"}
        if mismatch == "endpoint"
        else {"credential_revision": proxy.credential_revision + 1}
    )
    await repo.record_egress_observation(
        proxy.id,
        _observation(
            proxy,
            status=status,
            country_code=None if status != "ok" else "JP",
            egress_ip=None if status != "ok" else "203.0.113.7",
            **override,
        ),
    )

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "unknown"
    assert got.country_code is None
    assert got.egress_ip is None


@pytest.mark.asyncio
async def test_newest_pending_row_wins_over_old_ok(repo):
    """A newer pending row supersedes an older ok row; no time filter is
    involved in choosing the current snapshot."""
    proxy = await _make_proxy(repo, "px-reprobe")
    await repo.record_egress_observation(
        proxy.id,
        _observation(proxy, observed_at=NOW - timedelta(days=2)),
    )
    await repo.record_egress_observation(
        proxy.id,
        _observation(
            proxy,
            status="pending",
            observed_at=NOW,
            country_code=None,
            egress_ip=None,
        ),
    )

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "pending"
    assert got.country_code is None


@pytest.mark.asyncio
async def test_failed_row_is_surfaced_not_hidden(repo):
    proxy = await _make_proxy(repo, "px-failed")
    await repo.record_egress_observation(
        proxy.id,
        _observation(
            proxy,
            status="failed",
            country_code=None,
            egress_ip=None,
        ),
    )

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "failed"
    assert got.country_code is None


@pytest.mark.asyncio
async def test_list_proxies_batches_observation_lookup(repo, db_context):
    """code f005: listing N proxies must issue exactly one SELECT against
    proxy_egress_observations, not one per proxy row."""
    engine, _maker = db_context
    proxies = [
        await _make_proxy(repo, f"px-{i}", host=f"proxy{i}.example.com")
        for i in range(3)
    ]
    for i, proxy in enumerate(proxies):
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                observed_at=NOW - timedelta(days=i),
                country_code=["JP", "US", "DE"][i],
                egress_ip=f"203.0.113.{i + 1}",
            ),
        )

    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if "proxy_egress_observations" in statement:
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        listed = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    by_id = {p.id: p for p in listed}
    assert {by_id[p.id].country_code for p in proxies} == {"JP", "US", "DE"}
    assert all(by_id[p.id].observation_status == "ok" for p in proxies)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, selects


@pytest.mark.asyncio
async def test_list_proxies_fetches_only_latest_observation_row_per_proxy(
    repo, db_context
):
    """code f007: with several history rows per proxy, ``list_proxies``
    must return each proxy's latest row only, issue exactly one observation
    SELECT, and materialise one row per proxy — not the whole history."""
    engine, _maker = db_context
    proxies = [
        await _make_proxy(repo, f"px-hist-{i}", host=f"proxy{i}.example.com")
        for i in range(3)
    ]
    for i, proxy in enumerate(proxies):
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                observed_at=NOW - timedelta(seconds=7200),
                country_code=["JP", "US", "DE"][i],
                egress_ip=f"203.0.113.{i + 1}",
            ),
        )
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                observed_at=NOW - timedelta(seconds=3600),
                country_code=["FR", "GB", "NL"][i],
                egress_ip=f"198.51.100.{i + 1}",
            ),
        )
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                status="pending",
                observed_at=NOW,
                country_code=None,
                egress_ip=None,
            ),
        )

    statements: list[str] = []
    loaded_rows: list[object] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if "proxy_egress_observations" in statement:
            statements.append(statement)

    def _on_load(target, context):
        loaded_rows.append(target)

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    event.listen(ProxyEgressObservationModel, "load", _on_load)
    try:
        listed = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)
        event.remove(ProxyEgressObservationModel, "load", _on_load)

    by_id = {p.id: p for p in listed}
    assert len(listed) == 3
    for proxy in proxies:
        assert by_id[proxy.id].observation_status == "pending"
        assert by_id[proxy.id].country_code is None
        assert by_id[proxy.id].egress_ip is None
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, selects
    assert len(loaded_rows) == 3, len(loaded_rows)
