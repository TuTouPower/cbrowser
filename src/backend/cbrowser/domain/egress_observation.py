"""Egress observation: the value object and its validity rules (t052).

Pure domain logic only (t062): this module performs no HTTP, no file
I/O and no environment lookups. The probe implementation that produces
observations (echo fetch + local GeoIP), its echo endpoint set and its
error types live in ``cbrowser.shared.egress``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

OBSERVATION_PERSPECTIVE = "browser"


@dataclass(frozen=True)
class EgressObservation:
    """One egress observation.  ``country_code`` is only meaningful while
    :func:`observation_is_current` holds for the proxy's present endpoint
    fingerprint and credential revision."""

    proxy_id: str
    endpoint_fingerprint: str
    credential_revision: int
    perspective: str = OBSERVATION_PERSPECTIVE
    egress_ip: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    city: str | None = None
    latency_ms: int | None = None
    source: str = "supervisor_probe"
    status: str = "ok"  # pending | ok | failed
    error_code: str | None = None
    observed_at: datetime.datetime | None = None


def observation_is_current(
    obs: EgressObservation,
    endpoint_fingerprint: str,
    credential_revision: int,
) -> bool:
    """An observation is current while it belongs to the proxy's present
    endpoint identity.  An ``ok`` row additionally needs an egress IP and
    country.  Observations are point-in-time snapshots with no expiry: a
    result stays current until a newer observation supersedes it or the
    endpoint / credentials change (t105)."""
    if obs.endpoint_fingerprint != endpoint_fingerprint:
        return False
    if obs.credential_revision != credential_revision:
        return False
    if obs.status == "ok" and (not obs.egress_ip or not obs.country_code):
        return False
    return True
