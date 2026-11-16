"""Portrait folders belong to a world (asset_roots.world_id).

Before v0.5 every portrait was looked up by character id across all worlds, so two lore packs with a character of the
same id (Lily in Hero's Chronicle and in Lumencia Academy) could show each other's pictures. The pack's image folder now
records its world; the next start fills it in and rescans (bundled.py). Folders added by hand stay shared (NULL).

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "world_id" not in {c["name"] for c in insp.get_columns("asset_roots")}:
        with op.batch_alter_table("asset_roots") as b:
            b.add_column(sa.Column("world_id", sa.String(36), nullable=True))
            b.create_index("ix_asset_roots_world_id", ["world_id"])


def downgrade() -> None:
    with op.batch_alter_table("asset_roots") as b:
        b.drop_index("ix_asset_roots_world_id")
        b.drop_column("world_id")
