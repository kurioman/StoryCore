"""Scene analysis v2: character beats (speaking + silent reactions with text anchors), validated dialogue spans,
evidence-backed relationship changes and per-attempt diagnostics for each analysed reply

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

COLUMNS = ("beats_json", "dialogue_json", "relationships_json", "diagnostics_json")


def upgrade() -> None:
    # Additive and nullable: existing analyses keep working (no beats -> the story view simply shows no inline portraits).
    with op.batch_alter_table("turn_analyses") as b:
        for c in COLUMNS:
            b.add_column(sa.Column(c, sa.JSON(), nullable=True))
        b.add_column(sa.Column("schema_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("turn_analyses") as b:
        for c in (*COLUMNS, "schema_version"):
            b.drop_column(c)
