from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload
from typing import Optional

from app.config import get_settings
from app.database import get_db
from app.models import Article, Comment
from app.schemas import ArticleDetail, ArticleListItem, CommentCreate, CommentOut, IngestRunOut, RecommendationOut
from app.services.embeddings import EmbeddingService
from app.services.content_processing import strip_html
from app.services.ingestion import ingest_feeds
from app.services.recommendations import recommend_similar_articles

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["clean_text"] = strip_html
_embedder = None


def get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder


@router.get("/articles", response_model=list[ArticleListItem])
def list_articles(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Article)
    if source:
        query = query.filter(Article.source == source)

    return query.order_by(Article.published_at.desc()).offset(offset).limit(limit).all()


@router.get("/articles/{article_id}", response_model=ArticleDetail)
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = (
        db.query(Article)
        .options(selectinload(Article.comments))
        .filter(Article.id == article_id)
        .one_or_none()
    )
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("/articles/{article_id}/comments", response_model=CommentOut)
def post_comment(article_id: int, payload: CommentCreate, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    comment = Comment(
        article_id=article_id,
        author_name=payload.author_name,
        body=payload.body.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/articles/{article_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(article_id: int, k: int = Query(default=5, ge=1, le=20), db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

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


@router.post("/ingest/run", response_model=IngestRunOut)
def run_ingestion(db: Session = Depends(get_db)):
    result = ingest_feeds(db, settings.parsed_feeds, get_embedder())
    return IngestRunOut(**result.__dict__)


@router.get("/")
def home(request: Request, source: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    sources = [row[0] for row in db.query(Article.source).distinct().order_by(Article.source.asc()).all()]
    query = db.query(Article)
    if source:
        query = query.filter(Article.source == source)
    articles = query.order_by(Article.published_at.desc()).limit(50).all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"articles": articles, "sources": sources, "selected_source": source},
    )


@router.get("/articles/{article_id}/view")
def article_view(request: Request, article_id: int, db: Session = Depends(get_db)):
    article = (
        db.query(Article)
        .options(selectinload(Article.comments))
        .filter(Article.id == article_id)
        .one_or_none()
    )
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    recommendations = recommend_similar_articles(db, article, limit=5)
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

    article = db.query(Article).filter(Article.id == article_id).one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    comment = Comment(article_id=article_id, author_name=author_name or None, body=body.strip())
    db.add(comment)
    db.commit()
    return RedirectResponse(url=f"/articles/{article_id}/view", status_code=303)
