"""Add the built-in "Cinematic" narration preset to a stored list of presets.

The list of narration presets is stored in the app settings as soon as the player edits it once, and a stored list
replaces the built-in one. A preset added to the code (v0.6: "Cinematic", the OOC.AI-like style) would then never show
up: it is appended to the stored list here, once. Without a stored list the built-in one already holds it.

Revision ID: 0011
Revises: 0010
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from story.services.settings_service import NARRATION_PRESETS  # importable here, as in env.py

    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT value_json FROM app_settings WHERE key = 'narration_presets'")).fetchone()
    if row is None:
        return
    stored = row[0]
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except ValueError:
            return
    if not isinstance(stored, list):
        return
    ids = {p.get("id") for p in stored if isinstance(p, dict)}
    added = [p for p in NARRATION_PRESETS if p["id"] == "cinematic" and p["id"] not in ids]
    if added:
        bind.execute(sa.text("UPDATE app_settings SET value_json = :v WHERE key = 'narration_presets'"),
                     {"v": json.dumps(stored + added, ensure_ascii=False)})


def downgrade() -> None:
    pass  # a preset left in the list is harmless
