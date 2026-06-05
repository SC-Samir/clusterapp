from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, load_only, selectinload
from typing import Optional

from app.config import get_settings
from app.database import get_db
from app.models import Article, Comment
from app.schemas import (
    ArticleDetail,
    ArticleListItem,
    CommentCreate,
    CommentOut,
    IngestRunOut,
    RecommendationOut,
    ReindexArticleOut,
)
from app.services.embeddings import EmbeddingService
from app.services.cache import TTLCache
from app.services.content_processing import build_embedding_text, strip_html
from app.services.ingestion import ingest_feeds
from app.services.recommendations import recommend_similar_articles

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


def get_article_or_404(
    db: Session,
    article_id: int,
    *,
    with_comments: bool = False,
    with_embedding: bool = False,
) -> Article:
    base_load = ARTICLE_RECOMMENDATION_SUBJECT_LOAD if with_embedding else ARTICLE_DETAIL_LOAD
    options = [base_load]
    if with_comments:
        options.append(selectinload(Article.comments).options(COMMENT_LOAD))
    article = db.get(Article, article_id, options=options)

    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


def load_article_detail_payload(db: Session, article_id: int) -> ArticleDetail:
    article = get_article_or_404(db, article_id, with_comments=True)
    return ArticleDetail.model_validate(article)


def load_recommendation_payload(db: Session, article_id: int, k: int) -> list[RecommendationOut]:
    article = get_article_or_404(db, article_id, with_embedding=True)
    recs = recommend_similar_articles(db, article, limit=k)
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


def create_comment_or_404(
    db: Session,
    *,
    article_id: int,
    author_name: Optional[str],
    body: str,
) -> CommentOut:
    cleaned_body = body.strip()

    if hasattr(db, "execute"):
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
            row = db.execute(stmt).one()
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.get(Article, article_id) is None:
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

    comment = Comment(article_id=article_id, author_name=author_name, body=cleaned_body)
    db.add(comment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(Article, article_id) is None:
            raise HTTPException(status_code=404, detail="Article not found")
        raise
    db.refresh(comment)
    invalidate_article_cache(article_id)
    return CommentOut.model_validate(comment)


@router.get("/articles", response_model=list[ArticleListItem])
def list_articles(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    def load() -> list[ArticleListItem]:
        query = db.query(Article).options(ARTICLE_LIST_LOAD)
        if source:
            query = query.filter(Article.source == source)
        articles = query.order_by(Article.published_at.desc()).offset(offset).limit(limit).all()
        return [ArticleListItem.model_validate(article) for article in articles]

    cache_key = f"articles:list:{source or '*'}:{limit}:{offset}"
    return read_cache.get_or_set(cache_key, load)


@router.get("/articles/{article_id}", response_model=ArticleDetail)
def get_article(article_id: int, db: Session = Depends(get_db)):
    return read_cache.get_or_set(
        f"articles:detail:{article_id}",
        lambda: load_article_detail_payload(db, article_id),
    )


@router.post("/articles/{article_id}/comments", response_model=CommentOut)
def post_comment(article_id: int, payload: CommentCreate, db: Session = Depends(get_db)):
    return create_comment_or_404(
        db,
        article_id=article_id,
        author_name=payload.author_name,
        body=payload.body,
    )


@router.get("/articles/{article_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(article_id: int, k: int = Query(default=5, ge=1, le=20), db: Session = Depends(get_db)):
    return read_cache.get_or_set(
        f"articles:recommendations:{article_id}:{k}",
        lambda: load_recommendation_payload(db, article_id, k),
    )


@router.post("/ingest/run", response_model=IngestRunOut)
def run_ingestion(db: Session = Depends(get_db)):
    result = ingest_feeds(db, settings.parsed_feeds, get_embedder())
    invalidate_article_cache(invalidate_sources=True)
    return IngestRunOut(**result.__dict__)


@router.post("/articles/{article_id}/reindex", response_model=ReindexArticleOut)
def reindex_article(article_id: int, db: Session = Depends(get_db)):
    article = get_article_or_404(db, article_id)
    article.embedding = get_embedder().embed(build_embedding_text(article.title, article.content))
    db.commit()
    invalidate_article_cache(article_id)
    return ReindexArticleOut(article_id=article.id, reindexed=True)


@router.get("/")
def home(request: Request, source: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    def load_sources():
        return db.execute(select(Article.source).distinct().order_by(Article.source.asc())).scalars().all()

    def load():
        query = db.query(Article).options(ARTICLE_LIST_LOAD)
        if source:
            query = query.filter(Article.source == source)
        articles = query.order_by(Article.published_at.desc()).limit(50).all()
        return articles

    sources = source_cache.get_or_set("article_sources", load_sources)
    articles = read_cache.get_or_set(f"home:{source or '*'}", load)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"articles": articles, "sources": sources, "selected_source": source},
    )


@router.get("/articles/{article_id}/view")
def article_view(request: Request, article_id: int, db: Session = Depends(get_db)):
    article = read_cache.get_or_set(
        f"articles:detail:{article_id}",
        lambda: load_article_detail_payload(db, article_id),
    )
    recommendations = read_cache.get_or_set(
        f"articles:recommendations:{article_id}:5",
        lambda: load_recommendation_payload(db, article_id, 5),
    )
    return templates.TemplateResponse(
        request,
        "article.html",
        {"article": article, "recommendations": recommendations},
    )


@router.post("/articles/{article_id}/comment-form")
def post_comment_form(
    article_id: int,
    author_name: str = Form(default=""),
    body: str = Form(...),
    db: Session = Depends(get_db),
):
    if not body.strip():
        return RedirectResponse(url=f"/articles/{article_id}/view", status_code=303)

    create_comment_or_404(
        db,
        article_id=article_id,
        author_name=author_name or None,
        body=body,
    )
    return RedirectResponse(url=f"/articles/{article_id}/view", status_code=303)
