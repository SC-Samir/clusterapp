from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.core.config import get_settings
from app.core.database import get_async_db
from app.core.models import Article, Comment
from app.core.schemas import (
    ArticleDetail,
    ArticleListItem,
    CommentCreate,
    CommentOut,
    RecommendationOut,
    ReindexArticleOut,
)
from app.core.services.embeddings import EmbeddingService
from app.api.services.cache import TTLCache
from app.core.services.content_processing import strip_html
from app.api.services.recommendations import recommend_similar_articles
from app.ingestion.reindex import reindex_article

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["clean_text"] = strip_html
_embedder = None
read_cache = TTLCache(ttl_seconds=5.0)
source_cache = TTLCache(ttl_seconds=60.0)

ARTICLE_LIST_LOAD = load_only(
    Article.id,
    Article.source,
    Article.title,
    Article.url,
    Article.content,
    Article.published_at,
)
ARTICLE_DETAIL_LOAD = load_only(
    Article.id,
    Article.source,
    Article.rss_guid,
    Article.title,
    Article.url,
    Article.content,
    Article.published_at,
)
ARTICLE_RECOMMENDATION_SUBJECT_LOAD = load_only(
    Article.id,
    Article.source,
    Article.title,
    Article.url,
    Article.content,
    Article.published_at,
    Article.embedding,
)
COMMENT_LOAD = load_only(
    Comment.id,
    Comment.article_id,
    Comment.author_name,
    Comment.body,
    Comment.created_at,
)
RECOMMENDATION_ARTICLE_LOAD = load_only(
    Article.id,
    Article.source,
    Article.title,
    Article.url,
    Article.published_at,
)


def invalidate_article_cache(article_id: Optional[int] = None, *, invalidate_sources: bool = False) -> None:
    read_cache.invalidate_prefix("articles:list:")
    read_cache.invalidate_prefix("home:")
    if invalidate_sources:
        source_cache.clear()
    if article_id is not None:
        read_cache.invalidate_prefix(f"articles:detail:{article_id}")
        read_cache.invalidate_prefix(f"articles:recommendations:{article_id}:")
        read_cache.invalidate_prefix(f"articles:view:{article_id}")


def get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder


async def get_article_or_404(
    db: AsyncSession,
    article_id: int,
    *,
    with_comments: bool = False,
    with_embedding: bool = False,
) -> Article:
    base_load = ARTICLE_RECOMMENDATION_SUBJECT_LOAD if with_embedding else ARTICLE_DETAIL_LOAD
    options = [base_load]
    if with_comments:
        options.append(selectinload(Article.comments).options(COMMENT_LOAD))
    article = await db.get(Article, article_id, options=options)

    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


async def load_article_detail_payload(db: AsyncSession, article_id: int) -> ArticleDetail:
    article = await get_article_or_404(db, article_id, with_comments=True)
    return ArticleDetail.model_validate(article)


async def load_recommendation_payload(
    db: AsyncSession, article_id: int, k: int
) -> list[RecommendationOut]:
    article = await get_article_or_404(db, article_id, with_embedding=True)
    recs = await recommend_similar_articles(db, article, limit=k)
    return [
        RecommendationOut(
            id=item.id,
            source=item.source,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
            similarity=score,
        )
        for item, score in recs
    ]


async def create_comment_or_404(
    db: AsyncSession,
    *,
    article_id: int,
    author_name: Optional[str],
    body: str,
) -> CommentOut:
    cleaned_body = body.strip()
    stmt = (
        insert(Comment)
        .values(article_id=article_id, author_name=author_name, body=cleaned_body)
        .returning(
            Comment.id,
            Comment.article_id,
            Comment.author_name,
            Comment.body,
            Comment.created_at,
        )
    )
    try:
        row = (await db.execute(stmt)).one()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if await db.get(Article, article_id) is None:
            raise HTTPException(status_code=404, detail="Article not found")
        raise
    invalidate_article_cache(article_id)
    return CommentOut(
        id=row.id,
        article_id=row.article_id,
        author_name=row.author_name,
        body=row.body,
        created_at=row.created_at,
    )


@router.get("/articles", response_model=list[ArticleListItem])
async def list_articles(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
):
    async def load() -> list[ArticleListItem]:
        stmt = select(Article).options(ARTICLE_LIST_LOAD)
        if source:
            stmt = stmt.where(Article.source == source)
        stmt = stmt.order_by(Article.published_at.desc()).offset(offset).limit(limit)
        articles = (await db.execute(stmt)).scalars().all()
        return [ArticleListItem.model_validate(article) for article in articles]

    cache_key = f"articles:list:{source or '*'}:{limit}:{offset}"
    return await read_cache.get_or_set_async(cache_key, load)


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: int, db: AsyncSession = Depends(get_async_db)):
    return await read_cache.get_or_set_async(
        f"articles:detail:{article_id}",
        lambda: load_article_detail_payload(db, article_id),
    )


@router.post("/articles/{article_id}/comments", response_model=CommentOut)
async def post_comment(article_id: int, payload: CommentCreate, db: AsyncSession = Depends(get_async_db)):
    return await create_comment_or_404(
        db,
        article_id=article_id,
        author_name=payload.author_name,
        body=payload.body,
    )


@router.get("/articles/{article_id}/recommendations", response_model=list[RecommendationOut])
async def get_recommendations(
    article_id: int,
    k: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_async_db),
):
    return await read_cache.get_or_set_async(
        f"articles:recommendations:{article_id}:{k}",
        lambda: load_recommendation_payload(db, article_id, k),
    )


@router.post("/articles/{article_id}/reindex", response_model=ReindexArticleOut)
async def reindex_article_route(article_id: int, db: AsyncSession = Depends(get_async_db)):
    article = await get_article_or_404(db, article_id, with_embedding=True)
    await reindex_article(db, article, get_embedder())
    invalidate_article_cache(article_id)
    return ReindexArticleOut(article_id=article_id, reindexed=True)


@router.get("/")
async def home(
    request: Request, source: Optional[str] = Query(default=None), db: AsyncSession = Depends(get_async_db)
):
    async def load_sources():
        return (
            await db.execute(select(Article.source).distinct().order_by(Article.source.asc()))
        ).scalars().all()

    async def load():
        stmt = select(Article).options(ARTICLE_LIST_LOAD)
        if source:
            stmt = stmt.where(Article.source == source)
        stmt = stmt.order_by(Article.published_at.desc()).limit(50)
        return (await db.execute(stmt)).scalars().all()

    sources = await source_cache.get_or_set_async("article_sources", load_sources)
    articles = await read_cache.get_or_set_async(f"home:{source or '*'}", load)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"articles": articles, "sources": sources, "selected_source": source},
    )


@router.get("/articles/{article_id}/view")
async def article_view(request: Request, article_id: int, db: AsyncSession = Depends(get_async_db)):
    article = await read_cache.get_or_set_async(
        f"articles:detail:{article_id}",
        lambda: load_article_detail_payload(db, article_id),
    )
    recommendations = await read_cache.get_or_set_async(
        f"articles:recommendations:{article_id}:5",
        lambda: load_recommendation_payload(db, article_id, 5),
    )
    return templates.TemplateResponse(
        request,
        "article.html",
        {"article": article, "recommendations": recommendations},
    )


@router.post("/articles/{article_id}/comment-form")
async def post_comment_form(
    article_id: int,
    author_name: str = Form(default=""),
    body: str = Form(...),
    db: AsyncSession = Depends(get_async_db),
):
    if not body.strip():
        return RedirectResponse(url=f"/articles/{article_id}/view", status_code=303)

    await create_comment_or_404(
        db,
        article_id=article_id,
        author_name=author_name or None,
        body=body,
    )
    return RedirectResponse(url=f"/articles/{article_id}/view", status_code=303)
