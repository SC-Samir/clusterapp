import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Article
from app.core.services.content_processing import (
    build_embedding_text,
    make_preview,
    strip_html,
)


@dataclass
class IngestResult:
    ingested: int = 0
    updated: int = 0
    skipped: int = 0
    failed_feeds: list[str] = field(default_factory=list)


@dataclass
class NormalizedEntry:
    guid: str
    link: str
    title: str
    content_clean: str
    content_preview: str
    published_at: datetime


UPSERT_CHUNK_SIZE = 100
# Cap parallel feed parses to avoid unbounded thread spawn on large feed lists.
MAX_PARALLEL_FEEDS = 8


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

        preview = make_preview(content_clean)
        normalized.append(
            NormalizedEntry(
                guid=guid,
                link=link,
                title=title,
                content_clean=content_clean or "No content",
                content_preview=preview,
                published_at=_entry_published(entry),
            )
        )
    return normalized


@dataclass
class ParsedFeed:
    feed_url: str
    source: str
    entries: list[NormalizedEntry]
    failed: bool = False


async def _parse_one_feed(feed_url: str) -> ParsedFeed:
    """Parse a single feed in a worker thread; returns a ParsedFeed result."""
    try:
        parsed = await asyncio.to_thread(feedparser.parse, feed_url)
    except Exception:
        return ParsedFeed(feed_url=feed_url, source=feed_url, entries=[], failed=True)

    feed_meta = parsed.get("feed", {})
    source = feed_meta.get("title", feed_url)
    # _normalize_feed_entries mutates the shared IngestResult, but we normalize
    # here in the event loop thread (CPU-light) to keep parsing parallel while
    # avoiding a shared mutable counter across threads.
    dummy = IngestResult()
    entries = _normalize_feed_entries(parsed.get("entries", []), dummy)
    return ParsedFeed(
        feed_url=feed_url,
        source=source,
        entries=entries,
        failed=False,
    )


async def _embed_entries(
    embedder, entries: list[NormalizedEntry]
) -> list[list[float]]:
    """Embed a chunk of entries in a single batched forward pass off-thread."""
    if not entries:
        return []
    texts = [build_embedding_text(e.title, e.content_clean) for e in entries]
    return await asyncio.to_thread(embedder.embed_batch, texts)


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


def _entry_changed(existing: Article, entry: NormalizedEntry, source: str) -> bool:
    if existing.source != source:
        return True
    if existing.title != entry.title:
        return True
    if existing.url != entry.link:
        return True
    if existing.content != entry.content_clean:
        return True
    if existing.published_at != entry.published_at:
        return True
    if existing.content_preview != entry.content_preview:
        return True
    return False


async def ingest_feeds(db: AsyncSession, feed_urls: list[str], embedder) -> IngestResult:
    result = IngestResult()

    # Parse all feeds in parallel (bounded), each in its own thread.
    sem = asyncio.Semaphore(MAX_PARALLEL_FEEDS)

    async def _bounded_parse(feed_url: str) -> ParsedFeed:
        async with sem:
            return await _parse_one_feed(feed_url)

    parsed_feeds = await asyncio.gather(*[_bounded_parse(url) for url in feed_urls])

    for parsed in parsed_feeds:
        if parsed.failed:
            result.failed_feeds.append(parsed.feed_url)
            continue

        for start in range(0, len(parsed.entries), UPSERT_CHUNK_SIZE):
            chunk = parsed.entries[start : start + UPSERT_CHUNK_SIZE]
            existing_by_key = await _load_existing_articles(db, chunk)

            # Split chunk into new vs. existing entries. Only new entries (and
            # existing entries whose text fields changed) need an embedding.
            new_entries: list[NormalizedEntry] = []
            existing_pairs: list[tuple[Article, NormalizedEntry]] = []
            for entry in chunk:
                existing = existing_by_key.get(f"guid:{entry.guid}") or existing_by_key.get(f"url:{entry.link}")
                if existing is None:
                    new_entries.append(entry)
                elif _entry_changed(existing, entry, parsed.source):
                    existing_pairs.append((existing, entry))
                # else: unchanged -> skip entirely (no embedding, no write)

            # Batch-embed new entries in one forward pass.
            new_vectors = await _embed_entries(embedder, new_entries)

            new_articles: list[Article] = []
            for entry, vector in zip(new_entries, new_vectors):
                new_articles.append(
                    Article(
                        source=parsed.source,
                        rss_guid=entry.guid,
                        title=entry.title,
                        url=entry.link,
                        content=entry.content_clean,
                        content_preview=entry.content_preview,
                        published_at=entry.published_at,
                        embedding=vector,
                    )
                )
                result.ingested += 1

            # Batch-embed changed existing entries in one forward pass.
            changed_vectors = await _embed_entries(embedder, [e for _, e in existing_pairs])
            chunk_updated = 0
            for (existing, entry), vector in zip(existing_pairs, changed_vectors):
                existing.source = parsed.source
                existing.title = entry.title
                existing.url = entry.link
                existing.content = entry.content_clean
                existing.content_preview = entry.content_preview
                existing.published_at = entry.published_at
                existing.embedding = vector
                result.updated += 1
                chunk_updated += 1

            if new_articles:
                db.add_all(new_articles)
            if new_articles or chunk_updated:
                await db.commit()

    return result