import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Article
from app.core.services.content_processing import build_embedding_text, make_preview, strip_html
from app.core.services.embeddings import EmbeddingService


async def reindex_article(db: AsyncSession, article: Article, embedder: EmbeddingService) -> Article:
    """Recompute the embedding for a single article in place and commit.

    Also refreshes content_preview from the stored content so the preview stays
    consistent if content was edited directly in the DB.
    """
    # Stored content is already HTML-stripped by the ingestion pipeline, but we
    # re-strip defensively in case legacy rows contain markup.
    content_clean = strip_html(article.content)
    article.embedding = await asyncio.to_thread(
        embedder.embed,
        build_embedding_text(article.title, content_clean),
    )
    article.content_preview = make_preview(content_clean)
    await db.commit()
    return article