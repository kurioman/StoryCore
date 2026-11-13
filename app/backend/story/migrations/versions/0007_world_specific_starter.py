"""Drop the old built-in "Enrollment" opening from the stored global starter list.

Until the multi-story refactor, the app's default openings included Lumencia's "Enrollment". A database that saved its
settings kept a copy of it in the global list, so it would be offered for every world. Lumencia now provides it from its
own pack. Only an unmodified copy of the old default is removed; an edited one, and every opening the player created, is
kept.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

OLD_ENROLLMENT = {"id": "enrollment", "name": "Enrollment",
                  "blueprint": "Begin at the start of the academy year. Place the protagonist at the academy's entrance, admissions hall or first orientation point. Establish the scale and atmosphere of the institution, hint at social tensions, and introduce one immediate decision. Do not decide the protagonist's dialogue, feelings or actions. End on a clear opening for player input."}


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT value_json FROM app_settings WHERE key = 'starter_presets'")).fetchone()
    if row is None or row[0] is None:
        return
    value = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    if not isinstance(value, list):
        return
    kept = [s for s in value if not (isinstance(s, dict) and s.get("id") == OLD_ENROLLMENT["id"]
                                     and s.get("blueprint") == OLD_ENROLLMENT["blueprint"])]
    if len(kept) != len(value):
        bind.execute(sa.text("UPDATE app_settings SET value_json = :v WHERE key = 'starter_presets'"),
                     {"v": json.dumps(kept)})


def downgrade() -> None:
    pass  # the removed entry was an unmodified default; nothing to restore
