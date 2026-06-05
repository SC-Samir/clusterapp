"""add query indexes

Revision ID: 20260605_01
Revises: 20260505_01
Create Date: 2026-06-05
"""

from alembic import op


revision = "20260605_01"
down_revision = "20260505_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_articles_source_published_at",
        "articles",
        ["source", "published_at"],
    )
    op.create_index("ix_comments_article_id", "comments", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_comments_article_id", table_name="comments")
    op.drop_index("ix_articles_source_published_at", table_name="articles")
