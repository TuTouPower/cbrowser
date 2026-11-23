"""t106: config pending is one domain-derived fact carried by every read model."""

from __future__ import annotations

import pytest

from cbrowser.api.v1.runtime_views import (
    make_runtime_event_data,
    make_runtime_response,
)
from cbrowser.domain.models import (
    ProfileRuntime,
    ProfileRuntimeProjection,
    config_pending,
)


def runtime(observed: str = "running", config_version: int = 1) -> ProfileRuntime:
    return ProfileRuntime(
        profile_id="p1",
        display_number=1,
        observed_state=observed,  # type: ignore[arg-type]
        config_version=config_version,
        updated_at="2026-11-23T00:00:00Z",
    )


@pytest.mark.parametrize(
    ("observed", "runtime_version", "current_version", "expected"),
    [
        ("running", 1, 2, True),
        ("starting", 1, 2, True),
        ("stopping", 1, 2, True),
        ("error", 1, 2, True),
        ("stopped", 1, 2, False),
        ("running", 2, 2, False),
        ("running", 3, 2, False),
    ],
)
def test_config_pending_truth_table(
    observed: str, runtime_version: int, current_version: int, expected: bool
) -> None:
    assert config_pending(current_version, runtime(observed, runtime_version)) is expected


def test_no_runtime_never_pending() -> None:
    assert config_pending(2, None) is False


def test_projection_carries_the_same_fact() -> None:
    projection = ProfileRuntimeProjection.from_runtime(
        runtime("running", 1), current_config_version=2
    )
    assert projection.config_pending is True


@pytest.mark.asyncio
async def test_runtime_response_carries_the_same_fact() -> None:
    response = await make_runtime_response(
        runtime("running", 1), current_config_version=2
    )
    assert response.config_pending is True


@pytest.mark.parametrize(
    ("observed", "runtime_version", "current_version", "expected"),
    [
        ("running", 1, 2, True),
        ("running", 2, 2, False),
        ("stopped", 1, 2, False),
    ],
)
def test_sse_event_factory_derives_config_pending(
    observed: str, runtime_version: int, current_version: int, expected: bool
) -> None:
    event = make_runtime_event_data(
        runtime(observed, runtime_version), current_version
    )
    assert event.config_pending is expected


import pytest_asyncio

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


@pytest.mark.asyncio
async def test_collection_row_flips_pending_after_config_bump(repo, service) -> None:
    profile = await repo.create_profile(ProfileConfig(name="env-run"))
    await repo.bind_runtime_instance(profile.id, "inst-1", config_version=1)
    async with repo._session_maker() as session:
        row = await session.get(ProfileRuntimeModel, profile.id)
        row.observed_state = "running"
        await session.commit()

    before = await service.list_profiles_page(page=1, page_size=50)
    before_row = next(item for item in before.items if item.id == profile.id)
    assert before_row.runtime is not None
    assert before_row.runtime.config_pending is False

    await repo.update_profile(profile.id, {"timezone": "Asia/Tokyo"})

    after = await service.list_profiles_page(page=1, page_size=50)
    after_row = next(item for item in after.items if item.id == profile.id)
    assert after_row.runtime is not None
    assert after_row.runtime.config_pending is True
