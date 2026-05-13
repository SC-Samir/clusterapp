from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article


def recommend_similar_articles(db: Session, article: Article, limit: int = 5) -> list[tuple[Article, float]]:
    distance_expr = Article.embedding.cosine_distance(article.embedding)
    stmt = (
        select(Article, distance_expr.label("distance"))
        .where(Article.id != article.id)
        .order_by(distance_expr.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [(row[0], max(0.0, 1.0 - float(row[1]))) for row in rows]
