import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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


@dataclass
class NormalizedEntry:
    guid: str
    link: str
    title: str
    content_clean: str
    published_at: datetime


UPSERT_CHUNK_SIZE = 100


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


def _normalize_feed_entries(entries: list[feedparser.FeedParserDict], result: IngestResult) -> list[NormalizedEntry]:
    normalized: list[NormalizedEntry] = []
    for entry in entries:
        guid = entry.get("id") or entry.get("guid") or entry.get("link")
        link = entry.get("link")
        title = entry.get("title", "Untitled")
        content = _entry_content(entry)
        content_clean = strip_html(content)
        if not guid or not link:
            result.skipped += 1
            continue

        normalized.append(
            NormalizedEntry(
                guid=guid,
                link=link,
                title=title,
                content_clean=content_clean or "No content",
                published_at=_entry_published(entry),
            )
        )
    return normalized


async def _embed_entry(embedder, entry: NormalizedEntry) -> list[float]:
    return await asyncio.to_thread(
        embedder.embed,
        build_embedding_text(entry.title, entry.content_clean),
    )


async def _load_existing_articles(db: AsyncSession, entries: list[NormalizedEntry]) -> dict[str, Article]:
    if not entries:
        return {}

    guids = [entry.guid for entry in entries]
    links = [entry.link for entry in entries]
    result = await db.execute(
        select(Article).where(or_(Article.rss_guid.in_(guids), Article.url.in_(links)))
    )

    existing: dict[str, Article] = {}
    for article in result.scalars():
        existing[f"guid:{article.rss_guid}"] = article
        existing[f"url:{article.url}"] = article
    return existing


async def ingest_feeds(db: AsyncSession, feed_urls: list[str], embedder) -> IngestResult:
    result = IngestResult()

    for feed_url in feed_urls:
        try:
            parsed = await asyncio.to_thread(feedparser.parse, feed_url)
        except Exception:
            result.failed_feeds.append(feed_url)
            continue

        if parsed.get("bozo"):
            # Still attempt to process valid entries even if parser raised warnings.
            pass

        feed_meta = parsed.get("feed", {})
        source = feed_meta.get("title", feed_url)
        normalized_entries = _normalize_feed_entries(parsed.get("entries", []), result)

        for start in range(0, len(normalized_entries), UPSERT_CHUNK_SIZE):
            chunk = normalized_entries[start : start + UPSERT_CHUNK_SIZE]
            existing_by_key = await _load_existing_articles(db, chunk)
            new_articles: list[Article] = []
            chunk_updated = 0

            for entry in chunk:
                vector = await _embed_entry(embedder, entry)
                existing = existing_by_key.get(f"guid:{entry.guid}") or existing_by_key.get(f"url:{entry.link}")

                if existing is None:
                    new_articles.append(
                        Article(
                            source=source,
                            rss_guid=entry.guid,
                            title=entry.title,
                            url=entry.link,
                            content=entry.content_clean,
                            published_at=entry.published_at,
                            embedding=vector,
                        )
                    )
                    result.ingested += 1
                    continue

                changed = False
                if existing.source != source:
                    existing.source = source
                    changed = True
                if existing.title != entry.title:
                    existing.title = entry.title
                    changed = True
                if existing.url != entry.link:
                    existing.url = entry.link
                    changed = True
                if existing.content != entry.content_clean:
                    existing.content = entry.content_clean
                    changed = True
                if existing.published_at != entry.published_at:
                    existing.published_at = entry.published_at
                    changed = True
                if existing.embedding != vector:
                    existing.embedding = vector
                    changed = True

                if changed:
                    result.updated += 1
                    chunk_updated += 1

            if new_articles:
                db.add_all(new_articles)
            if new_articles or chunk_updated:
                await db.commit()

    return result
