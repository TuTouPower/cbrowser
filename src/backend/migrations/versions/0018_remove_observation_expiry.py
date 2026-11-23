"""0018: retire the proxy observation TTL (t105).

An egress observation is a point-in-time snapshot: its latency, egress IP
and geography belong together and stay valid until a newer observation
supersedes them or the endpoint / credentials change.  ``expires_at`` was
an API-generated product convention (86400 seconds), not probe data, and
made successful results disappear from the UI after 24h while failed rows
never expired.  Drop the column and the time dimension entirely.

Downgrade is unsupported: cbrowser migrations only move forward.
"""

from __future__ import annotations

from alembic import op

revision: str = "b2c3d4e5f601"
down_revision: str | None = "e10400170001"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def upgrade() -> None:
    with op.batch_alter_table("proxy_egress_observations", recreate="always") as batch_op:
        batch_op.drop_column("expires_at")


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
