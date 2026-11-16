"""Remove the generic openings (Free Mode, Character Preview and any custom ones) stored in the app settings.

From v0.5 a story's openings come only from its lore pack, chosen by the pack's author. The generic list was a
development aid; it is dropped from the database (the setting now defaults to an empty list).

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM app_settings WHERE key = 'starter_presets'"))


def downgrade() -> None:
    pass  # the old defaults come back from the code of older versions
