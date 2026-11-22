"""0016: retire invalid profile options & generic launch_args, add mute_audio (t103).

Fail-before-write audit inspects every ``profiles`` row and every historical
``profile_config_versions`` snapshot (both flat and wrapped) before mutating
the schema or rows. Any unmapped/unsupported argument or corrupt snapshot blocks
the upgrade with zero database writes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from cbrowser.adapters.database import launch_args_migration

revision: str = "a10300160001"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def _drop_retired_profile_columns(op_obj) -> None:
    with op_obj.batch_alter_table("profiles", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mute_audio",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        for col_name in launch_args_migration.RETIRED_PROFILE_KEYS:
            batch_op.drop_column(col_name)


def upgrade() -> None:
    conn = op.get_bind()
    inventory = launch_args_migration.audit_launch_args_database(conn)
    if inventory.blocking_errors:
        raise RuntimeError(
            "t103 profile option retirement migration blocked; nothing was written. "
            "Resolve these entries and re-run:\n" + "\n".join(inventory.blocking_errors)
        )

    _drop_retired_profile_columns(op)
    launch_args_migration.apply_launch_args_profile_updates(conn, inventory)
    launch_args_migration.rewrite_profile_snapshots_for_launch_args(conn)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
