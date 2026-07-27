import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Article
from app.core.services.content_processing import build_embedding_text
from app.core.services.embeddings import EmbeddingService


async def reindex_article(db: AsyncSession, article: Article, embedder: EmbeddingService) -> Article:
    """Recompute the embedding for a single article in place and commit."""
    article.embedding = await asyncio.to_thread(
        embedder.embed,
        build_embedding_text(article.title, article.content),
    )
    await db.commit()
    return article
