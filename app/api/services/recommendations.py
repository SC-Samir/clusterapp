from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.models import Article


async def recommend_similar_articles(
    db: AsyncSession, article: Article, limit: int = 5
) -> list[tuple[Article, float]]:
    distance_expr = Article.embedding.cosine_distance(article.embedding)
    stmt = (
        select(Article, distance_expr.label("distance"))
        .options(
            load_only(
                Article.id,
                Article.source,
                Article.title,
                Article.url,
                Article.published_at,
            )
        )
        .where(Article.id != article.id)
        .order_by(distance_expr.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(row[0], max(0.0, 1.0 - float(row[1]))) for row in rows]
