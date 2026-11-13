"""Scene presentation / suggested actions per assistant message, per-story character discovery, proposal dedupe keys

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive only: existing stories get no analyses and an empty discovered roster (nothing is invented).
    op.create_table(
        "turn_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("speakers_json", sa.JSON(), nullable=False),
        sa.Column("active_speaker_id", sa.String(200)),
        sa.Column("suggestions_json", sa.JSON(), nullable=False),
        sa.Column("suggestions_error", sa.Text()),
        sa.Column("discoveries_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("provider_id", sa.String(36)),
        sa.Column("model_id", sa.String(200)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("message_id", name="uq_turn_analyses_message"),
    )
    op.create_index("ix_turn_analyses_story_id", "turn_analyses", ["story_id"])
    op.create_index("ix_turn_analyses_branch_id", "turn_analyses", ["branch_id"])
    op.create_table(
        "character_discoveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(200), nullable=False),
        sa.Column("character_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_message_id", sa.String(36)),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("capture_method", sa.String(40), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("story_id", "dedupe_key", name="uq_discovery_dedupe"),
    )
    for col in ("story_id", "branch_id", "character_id", "source_message_id"):
        op.create_index(f"ix_character_discoveries_{col}", "character_discoveries", [col])
    with op.batch_alter_table("state_proposals") as b:
        b.add_column(sa.Column("dedupe_key", sa.String(80)))
    op.create_index("ix_state_proposals_dedupe_key", "state_proposals", ["dedupe_key"])


def downgrade() -> None:
    op.drop_index("ix_state_proposals_dedupe_key", "state_proposals")
    with op.batch_alter_table("state_proposals") as b:
        b.drop_column("dedupe_key")
    op.drop_table("character_discoveries")
    op.drop_table("turn_analyses")
