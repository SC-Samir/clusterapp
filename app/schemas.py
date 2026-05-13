from datetime import datetime

from pydantic import BaseModel, Field
from pydantic import ConfigDict
from typing import Optional


class CommentCreate(BaseModel):
    author_name: Optional[str] = Field(default=None, max_length=120)
    body: str = Field(..., min_length=1)


class CommentOut(BaseModel):
    id: int
    article_id: int
    author_name: Optional[str]
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArticleListItem(BaseModel):
    id: int
    source: str
    title: str
    url: str
    content: str
    published_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArticleDetail(BaseModel):
    id: int
    source: str
    rss_guid: str
    title: str
    url: str
    content: str
    published_at: datetime
    comments: list[CommentOut]

    model_config = ConfigDict(from_attributes=True)


class RecommendationOut(BaseModel):
    id: int
    source: str
    title: str
    url: str
    published_at: datetime
    similarity: float


class IngestRunOut(BaseModel):
    ingested: int
    updated: int
    skipped: int
    failed_feeds: list[str]
