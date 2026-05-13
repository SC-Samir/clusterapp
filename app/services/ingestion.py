from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Article
from app.services.content_processing import build_embedding_text, strip_html


@dataclass
class IngestResult:
    ingested: int = 0
    updated: int = 0
    skipped: int = 0
    failed_feeds: list[str] = None

    def __post_init__(self) -> None:
        if self.failed_feeds is None:
            self.failed_feeds = []


def _entry_published(entry: feedparser.FeedParserDict) -> datetime:
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(tz=timezone.utc)


def _entry_content(entry: feedparser.FeedParserDict) -> str:
    if entry.get("content") and len(entry["content"]) > 0:
        return entry["content"][0].get("value", "")
    return entry.get("summary", "")


def ingest_feeds(db: Session, feed_urls: list[str], embedder) -> IngestResult:
    result = IngestResult()

    for feed_url in feed_urls:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            result.failed_feeds.append(feed_url)
            continue

        if parsed.get("bozo"):
            # Still attempt to process valid entries even if parser raised warnings.
            pass

        feed_meta = parsed.get("feed", {})
        source = feed_meta.get("title", feed_url)

        for entry in parsed.get("entries", []):
            guid = entry.get("id") or entry.get("guid") or entry.get("link")
            link = entry.get("link")
            title = entry.get("title", "Untitled")
            content = _entry_content(entry)
            content_clean = strip_html(content)
            if not guid or not link:
                result.skipped += 1
                continue

            published_at = _entry_published(entry)

            existing = (
                db.query(Article)
                .filter(or_(Article.rss_guid == guid, Article.url == link))
                .one_or_none()
            )

            vector = embedder.embed(build_embedding_text(title, content))

            if existing is None:
                article = Article(
                    source=source,
                    rss_guid=guid,
                    title=title,
                    url=link,
                    content=content_clean or "No content",
                    published_at=published_at,
                    embedding=vector,
                )
                db.add(article)
                result.ingested += 1
            else:
                existing.source = source
                existing.title = title
                existing.url = link
                existing.content = content_clean or existing.content
                existing.published_at = published_at
                existing.embedding = vector
                result.updated += 1

        db.commit()

    return result
