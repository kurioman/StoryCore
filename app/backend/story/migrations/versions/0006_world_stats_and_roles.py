"""World stats template and roles table (added to the models during the multi-story refactor).

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "stats_template" not in {c["name"] for c in insp.get_columns("worlds")}:
        with op.batch_alter_table("worlds") as b:
            b.add_column(sa.Column("stats_template", sa.String(120), nullable=False, server_default="fantasy"))
    if "roles" not in insp.get_table_names():
        op.create_table(
            "roles",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("world_id", sa.String(36), nullable=True),
            sa.Column("role_id", sa.String(80), nullable=False),
            sa.Column("character_id", sa.String(200), nullable=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("aliases_json", sa.JSON(), nullable=False),
            sa.Column("mandatory", sa.Boolean(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("source", sa.String(100), nullable=True),
            sa.Column("created_at", sa.String(40), nullable=False),
            sa.Column("updated_at", sa.String(40), nullable=False),
        )
        op.create_index("ix_roles_world_id", "roles", ["world_id"])
        op.create_index("ix_roles_role_id", "roles", ["role_id"])
        op.create_index("ix_roles_character_id", "roles", ["character_id"])


def downgrade() -> None:
    op.drop_table("roles")
    with op.batch_alter_table("worlds") as b:
        b.drop_column("stats_template")
