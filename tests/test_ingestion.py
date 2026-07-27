import os
from datetime import datetime, timezone

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.core.models import Article
from app.ingestion.ingestion import ingest_feeds


class FakeEmbedder:
    def embed(self, text: str):
        return [0.1] * 384

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 384 for _ in texts]


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def __iter__(self):
        return iter(self._items)


class FakeExecResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return FakeScalarResult(self._items)


class FakeDB:
    def __init__(self, existing_articles=None):
        self.items = []
        self.existing_articles = existing_articles or []
        self.commits = 0
        self.execute_calls = 0

    async def execute(self, stmt):
        self.execute_calls += 1
        return FakeExecResult(self.existing_articles)

    def add_all(self, items):
        self.items.extend(items)

    async def commit(self):
        self.commits += 1


def build_existing_article() -> Article:
    return Article(
        id=1,
        source="Feed A",
        rss_guid="guid-1",
        title="Hello",
        url="https://example.com/a",
        content="World",
        content_preview="World",
        published_at=datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
        embedding=[0.1] * 384,
    )


@pytest.mark.anyio
async def test_ingest_basic(monkeypatch):
    fake_feed = {
        "feed": {"title": "Feed A"},
        "entries": [
            {
                "id": "guid-1",
                "link": "https://example.com/a",
                "title": "Hello",
                "summary": "World",
                "published": "Tue, 05 May 2026 10:00:00 GMT",
            }
        ],
        "bozo": False,
    }

    monkeypatch.setattr("app.ingestion.ingestion.feedparser.parse", lambda _: fake_feed)

    db = FakeDB()
    result = await ingest_feeds(db, ["https://example.com/rss"], FakeEmbedder())

    assert result.ingested == 1
    assert result.updated == 0
    assert result.skipped == 0
    assert result.failed_feeds == []
    assert len(db.items) == 1
    assert db.commits == 1
    assert db.execute_calls == 1


@pytest.mark.anyio
async def test_ingest_updates_existing_when_changed(monkeypatch):
    fake_feed = {
        "feed": {"title": "Feed B"},
        "entries": [
            {
                "id": "guid-1",
                "link": "https://example.com/a",
                "title": "Hello updated",
                "summary": "World updated",
                "published": "Tue, 06 May 2026 10:00:00 GMT",
            }
        ],
        "bozo": False,
    }

    monkeypatch.setattr("app.ingestion.ingestion.feedparser.parse", lambda _: fake_feed)

    existing = build_existing_article()
    db = FakeDB(existing_articles=[existing])
    result = await ingest_feeds(db, ["https://example.com/rss"], FakeEmbedder())

    assert result.ingested == 0
    assert result.updated == 1
    assert db.commits == 1
    assert existing.source == "Feed B"
    assert existing.title == "Hello updated"


@pytest.mark.anyio
async def test_ingest_skips_write_when_existing_unchanged(monkeypatch):
    fake_feed = {
        "feed": {"title": "Feed A"},
        "entries": [
            {
                "id": "guid-1",
                "link": "https://example.com/a",
                "title": "Hello",
                "summary": "World",
                "published": "Tue, 05 May 2026 10:00:00 GMT",
            }
        ],
        "bozo": False,
    }

    monkeypatch.setattr("app.ingestion.ingestion.feedparser.parse", lambda _: fake_feed)

    existing = build_existing_article()
    db = FakeDB(existing_articles=[existing])
    result = await ingest_feeds(db, ["https://example.com/rss"], FakeEmbedder())

    assert result.ingested == 0
    assert result.updated == 0
    assert db.commits == 0
    assert db.execute_calls == 1
