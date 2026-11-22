"""0017: managed extension assets catalog + allow_extensions/extension_ids replacing extension_paths (t104).

Fail-before-write audit inspects every ``profiles`` row and every historical
``profile_config_versions`` snapshot (both flat and wrapped) before any DDL/DML
write. Any missing/ambiguous legacy asset or extension unable to preserve
``chrome.runtime.id`` continuity aborts the upgrade with zero writes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from cbrowser.adapters.database import extension_paths_migration

revision: str = "e10400170001"
down_revision: str | None = "a10300160001"
branch_labels: str | None = None
depends_on: str | None = None

_UNSUPPORTED_DOWNGRADE = (
    "Downgrade is not supported: cbrowser migrations only move forward. "
    "Roll back with a release rollback and a data-directory rebuild instead."
)


def _table_exists(conn: sa.Connection, name: str) -> bool:
    row = conn.execute(
        sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :name"),
        {"name": name},
    ).fetchone()
    return row is not None


def _table_columns(conn: sa.Connection, name: str) -> set[str]:
    rows = conn.execute(sa.text(f'PRAGMA table_info("{name}")')).fetchall()
    return {str(r[1]) for r in rows}


def _create_extension_assets_table(op_obj, conn: sa.Connection) -> None:
    if _table_exists(conn, "extension_assets"):
        return
    op_obj.create_table(
        "extension_assets",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("chromium_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("package_format", sa.String(16), nullable=False),
        sa.Column("identity_source", sa.String(32), nullable=False),
        sa.Column("manifest_key_sha256", sa.String(64), nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=False),
        sa.Column("icon_relpath", sa.String(512), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("integrity", sa.Text(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op_obj.create_index(
        "idx_extension_assets_chromium_id", "extension_assets", ["chromium_id"]
    )


def _alter_profiles_columns(op_obj, conn: sa.Connection) -> None:
    cols = _table_columns(conn, "profiles")
    needs_add_allow = "allow_extensions" not in cols
    needs_add_ids = "extension_ids" not in cols
    needs_drop_paths = "extension_paths" in cols
    if not (needs_add_allow or needs_add_ids or needs_drop_paths):
        return
    with op_obj.batch_alter_table("profiles", recreate="always") as batch_op:
        if needs_add_allow:
            batch_op.add_column(
                sa.Column(
                    "allow_extensions",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                )
            )
        if needs_add_ids:
            batch_op.add_column(
                sa.Column(
                    "extension_ids",
                    sa.Text(),
                    nullable=False,
                    server_default="[]",
                )
            )
        if needs_drop_paths:
            batch_op.drop_column("extension_paths")


def upgrade() -> None:
    conn = op.get_bind()
    inventory = extension_paths_migration.audit_extension_paths_database(conn)
    if inventory.blocking_errors:
        raise RuntimeError(
            "t104 managed extensions migration blocked; nothing was written. "
            "Resolve these entries and re-run:\n" + "\n".join(inventory.blocking_errors)
        )

    _create_extension_assets_table(op, conn)
    extension_paths_migration.seed_trusted_assets_table(conn, inventory.trusted_assets)
    _alter_profiles_columns(op, conn)
    extension_paths_migration.apply_extension_migration(conn, inventory)


def downgrade() -> None:
    raise RuntimeError(_UNSUPPORTED_DOWNGRADE)
