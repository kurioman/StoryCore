"""Automatic memory summaries (v0.5, phase 7): the table and its full-text index.

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TOKENIZER = "tokenize='unicode61 remove_diacritics 2'"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "memory_summaries" not in insp.get_table_names():
        op.create_table(
            "memory_summaries",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
            sa.Column("branch_id", sa.String(36), nullable=False),
            sa.Column("level", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("message_ids_json", sa.JSON(), nullable=False),
            sa.Column("start_message_id", sa.String(36), nullable=True),
            sa.Column("end_message_id", sa.String(36), nullable=True),
            sa.Column("start_seq", sa.Integer(), nullable=False),
            sa.Column("end_seq", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("source", sa.String(30), nullable=False),
            sa.Column("parent_id", sa.String(36), nullable=True),
            sa.Column("data_json", sa.JSON(), nullable=False),
            sa.Column("model_id", sa.String(200), nullable=True),
            sa.Column("created_at", sa.String(40), nullable=False),
            sa.Column("updated_at", sa.String(40), nullable=False),
        )
        op.create_index("ix_memory_summaries_story_id", "memory_summaries", ["story_id"])
        op.create_index("ix_memory_summaries_branch_id", "memory_summaries", ["branch_id"])
    # searchable like the other journal records (phase 7.2 brings old scenes back when they become relevant)
    op.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(id UNINDEXED, story_id UNINDEXED, content, {TOKENIZER})")
    op.execute("CREATE TRIGGER IF NOT EXISTS summaries_fts_ai AFTER INSERT ON memory_summaries BEGIN "
               "INSERT INTO summaries_fts(id, story_id, content) VALUES (new.id, new.story_id, new.content); END")
    op.execute("CREATE TRIGGER IF NOT EXISTS summaries_fts_ad AFTER DELETE ON memory_summaries BEGIN "
               "DELETE FROM summaries_fts WHERE id = old.id; END")
    op.execute("CREATE TRIGGER IF NOT EXISTS summaries_fts_au AFTER UPDATE ON memory_summaries BEGIN "
               "DELETE FROM summaries_fts WHERE id = old.id; "
               "INSERT INTO summaries_fts(id, story_id, content) VALUES (new.id, new.story_id, new.content); END")


def downgrade() -> None:
    for suffix in ("ai", "ad", "au"):
        op.execute(f"DROP TRIGGER IF EXISTS summaries_fts_{suffix}")
    op.execute("DROP TABLE IF EXISTS summaries_fts")
    op.drop_table("memory_summaries")
