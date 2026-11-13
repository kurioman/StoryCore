"""Unique (story_id, request_id) for player turns so retries/double submits can never create a second turn

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older databases may already contain duplicate request ids (e.g. from an earlier client bug). Keep every message,
    # but release the request id on all but the earliest occurrence so the unique index can be created.
    op.execute("""
        UPDATE messages SET request_id = NULL
        WHERE request_id IS NOT NULL AND id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY story_id, request_id ORDER BY created_at, id) AS rn
                FROM messages WHERE request_id IS NOT NULL
            ) WHERE rn = 1
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_story_request ON messages(story_id, request_id) "
               "WHERE request_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_messages_story_request")
