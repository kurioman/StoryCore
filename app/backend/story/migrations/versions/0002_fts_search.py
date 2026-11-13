"""FTS5 search indexes for lore, local canon, journal events, facts and recaps

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TOKENIZER = "tokenize='unicode61 remove_diacritics 2'"

# fts table -> (base table, [(fts column, base expression)])
INDEXES = {
    "lore_fts": ("lore_chunks", [
        ("id", "id"), ("world_id", "world_id"), ("entity_id", "entity_id"), ("category", "category"),
        ("title", "title"), ("content", "content"),
    ], 4),
    "canon_fts": ("local_canon", [
        ("id", "id"), ("world_id", "world_id"), ("story_id", "story_id"),
        ("title", "title"), ("content", "content"), ("tags", "tags_json"),
    ], 3),
    "events_fts": ("story_events", [
        ("id", "id"), ("story_id", "story_id"),
        ("title", "title"), ("summary", "summary"), ("tags", "tags_json"),
    ], 2),
    "facts_fts": ("entity_facts", [
        ("id", "id"), ("story_id", "story_id"),
        ("subject", "coalesce(subject_label, subject_entity_id, '')"), ("content", "content"), ("tags", "tags_json"),
    ], 2),
    "recaps_fts": ("recaps", [
        ("id", "id"), ("story_id", "story_id"), ("content", "content"),
    ], 2),
}


def upgrade() -> None:
    for fts, (base, cols, n_unindexed) in INDEXES.items():
        col_defs = ", ".join(f"{c} UNINDEXED" if i < n_unindexed else c for i, (c, _) in enumerate(cols))
        op.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {fts} USING fts5({col_defs}, {TOKENIZER})")
        names = ", ".join(c for c, _ in cols)
        new_vals = ", ".join(_prefix(expr, "new") for _, expr in cols)
        op.execute(f"CREATE TRIGGER IF NOT EXISTS {fts}_ai AFTER INSERT ON {base} BEGIN "
                   f"INSERT INTO {fts}({names}) VALUES ({new_vals}); END")
        op.execute(f"CREATE TRIGGER IF NOT EXISTS {fts}_ad AFTER DELETE ON {base} BEGIN "
                   f"DELETE FROM {fts} WHERE id = old.id; END")
        op.execute(f"CREATE TRIGGER IF NOT EXISTS {fts}_au AFTER UPDATE ON {base} BEGIN "
                   f"DELETE FROM {fts} WHERE id = old.id; "
                   f"INSERT INTO {fts}({names}) VALUES ({new_vals}); END")
        # backfill rows that existed before this migration (previous-version databases)
        old_vals = ", ".join(_prefix(expr, base) for _, expr in cols)
        op.execute(f"INSERT INTO {fts}({names}) SELECT {old_vals} FROM {base}")


def _prefix(expr: str, alias: str) -> str:
    if expr.startswith("coalesce("):
        inner = expr[len("coalesce("):-1]
        parts = [p.strip() for p in inner.split(",")]
        return "coalesce(" + ", ".join(p if p.startswith("'") else f"{alias}.{p}" for p in parts) + ")"
    return f"{alias}.{expr}"


def downgrade() -> None:
    for fts, (base, _cols, _n) in INDEXES.items():
        for suffix in ("ai", "ad", "au"):
            op.execute(f"DROP TRIGGER IF EXISTS {fts}_{suffix}")
        op.execute(f"DROP TABLE IF EXISTS {fts}")
