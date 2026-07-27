"""add content_preview and hnsw vector index

Revision ID: 20260727_01
Revises: 20260605_01
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260727_01"
down_revision = "20260605_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Store a short, pre-cleaned preview so list/home queries avoid loading
    # the full Text body and avoid re-running strip_html on every render.
    op.add_column(
        "articles",
        sa.Column("content_preview", sa.Text(), nullable=False, server_default=""),
    )

    # Backfill preview from existing content. We do a lightweight whitespace
    # collapse here (no HTML stripping) because content is already stored
    # cleaned by the ingestion pipeline. A second pass with the app's
    # strip_html can be run offline if legacy rows contain markup.
    op.execute(
        """
        UPDATE articles
        SET content_preview = left(
            btrim(
                regexp_replace(content, '\\s+', ' ', 'g')
            ),
            280
        )
        """
    )

    # HNSW index for approximate nearest-neighbour search on embeddings.
    # Falls back gracefully if the extension/operator class is unavailable.
    bind = op.get_bind()
    has_hnsw = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_am WHERE amname = 'hnsw' LIMIT 1"
        )
    ).scalar() is not None
    if has_hnsw:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_articles_embedding_hnsw "
            "ON articles USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    has_hnsw = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_am WHERE amname = 'hnsw' LIMIT 1"
        )
    ).scalar() is not None
    if has_hnsw:
        op.execute("DROP INDEX IF EXISTS ix_articles_embedding_hnsw")
    op.drop_column("articles", "content_preview")