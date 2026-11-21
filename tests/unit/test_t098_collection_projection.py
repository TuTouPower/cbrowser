"""t098: the bounded collection page carries each row's runtime
projection, resolved with a fixed number of queries.

AC-001: rows deliver config + runtime projection in the page itself;
a row without a runtime record carries an explicit ``runtime=None``
(the unknown case), never a synthesized state.
AC-004: the runtime reads behind one page stay constant as the total
profile count grows (one batch read for the page's ids).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import event

from cbrowser.adapters.database.models import ProfileRuntimeModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService


@pytest_asyncio.fixture
async def repo(db_context):
    _engine, session_maker = db_context
    return ProfileRepository(session_maker)


@pytest_asyncio.fixture
async def service(repo):
    return ProfileService(repo)


async def _make_profile(repo, name):
    return await repo.create_profile(ProfileConfig(name=name))


async def _set_observed(repo, profile_id, observed):
    async with repo._session_maker() as session:
        row = await session.get(ProfileRuntimeModel, profile_id)
        row.observed_state = observed
        await session.commit()


def _count_selects(engine):
    statements: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _listener)
    return statements, _listener


@pytest.mark.asyncio
async def test_page_rows_carry_runtime_projection(repo, service):
    p_run = await _make_profile(repo, "env-run")
    await repo.bind_runtime_instance(p_run.id, "inst-1", config_version=1)
    await _set_observed(repo, p_run.id, "running")
    p_idle = await _make_profile(repo, "env-idle")

    page = await service.list_profiles_page(page=1, page_size=50)
    by_id = {item.id: item for item in page.items}
    run_rt = by_id[p_run.id].runtime
    assert run_rt is not None
    assert run_rt.observed_state == "running"
    assert run_rt.desired_state in ("running", "stopped")
    assert run_rt.runtime_instance_id == "inst-1"
    assert run_rt.config_version == 1
    # The monotonic fence travels with the projection.
    assert run_rt.state_revision >= 1

    idle_rt = by_id[p_idle.id].runtime
    assert idle_rt is not None
    assert idle_rt.observed_state == "stopped"


@pytest.mark.asyncio
async def test_page_row_without_runtime_row_is_explicit_none(repo, service):
    p = await _make_profile(repo, "env-orphan")
    async with repo._session_maker() as session:
        row = await session.get(ProfileRuntimeModel, p.id)
        await session.delete(row)
        await session.commit()

    page = await service.list_profiles_page(page=1, page_size=50)
    by_id = {item.id: item for item in page.items}
    # No runtime fact is held: the projection is absent, not filled
    # with a guessed "stopped".
    assert by_id[p.id].runtime is None


@pytest.mark.asyncio
async def test_state_revision_increases_with_runtime_writes(repo, service):
    p = await _make_profile(repo, "env-rev")
    page = await service.list_profiles_page(page=1, page_size=50)
    first = page.items[0].runtime
    assert first is not None
    await _set_observed(repo, p.id, "starting")
    page = await service.list_profiles_page(page=1, page_size=50)
    second = page.items[0].runtime
    assert second is not None
    assert second.state_revision > first.state_revision


@pytest.mark.asyncio
async def test_page_query_count_fixed_as_total_grows(repo, service, db_context):
    """AC-004: with the page size fixed, the number of SELECTs behind
    one collection page must not grow when the profile total grows.
    Scale points follow the repo's established 20/100/1000 ladder
    (t098 test review f005) and the total count is asserted exactly:
    a constant-query implementation has no scale-dependent slack."""
    engine, _maker = db_context

    async def measure() -> tuple[int, int, int]:
        statements, listener = _count_selects(engine)
        try:
            page = await service.list_profiles_page(page=1, page_size=5)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        assert len(page.items) == 5
        runtime_selects = sum(1 for s in statements if "profile_runtimes" in s)
        return page.total, len(statements), runtime_selects

    for i in range(20):
        await _make_profile(repo, f"env-a-{i:02d}")
    total20, selects20, runtime20 = await measure()
    assert total20 == 20

    for i in range(80):
        await _make_profile(repo, f"env-b-{i:02d}")
    total100, selects100, runtime100 = await measure()
    assert total100 == 100

    for i in range(900):
        await _make_profile(repo, f"env-c-{i:03d}")
    total1000, selects1000, runtime1000 = await measure()
    assert total1000 == 1000

    assert runtime20 == runtime100 == runtime1000, (
        f"runtime SELECTs grew with total profiles: "
        f"{runtime20} -> {runtime100} -> {runtime1000}"
    )
    assert selects20 == selects100 == selects1000, (
        f"page SELECTs grew with total profiles: "
        f"{selects20} -> {selects100} -> {selects1000}"
    )


@pytest.mark.asyncio
async def test_list_runtimes_by_ids_single_batch(repo):
    ids = []
    for i in range(5):
        p = await _make_profile(repo, f"env-batch-{i}")
        ids.append(p.id)
    runtimes = await repo.list_runtimes_by_ids(ids)
    assert set(runtimes) == set(ids)
    assert await repo.list_runtimes_by_ids([]) == {}
    subset = await repo.list_runtimes_by_ids(ids[:2])
    assert set(subset) == set(ids[:2])
