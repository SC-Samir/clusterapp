from types import SimpleNamespace

from app.services.ingestion import ingest_feeds


class FakeEmbedder:
    def embed(self, text: str):
        return [0.1] * 384


class FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def one_or_none(self):
        return None


class FakeDB:
    def __init__(self):
        self.items = []
        self.commits = 0

    def query(self, model):
        return FakeQuery()

    def add(self, item):
        self.items.append(item)

    def commit(self):
        self.commits += 1


def test_ingest_basic(monkeypatch):
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

    monkeypatch.setattr("app.services.ingestion.feedparser.parse", lambda _: fake_feed)

    db = FakeDB()
    result = ingest_feeds(db, ["https://example.com/rss"], FakeEmbedder())

    assert result.ingested == 1
    assert result.updated == 0
    assert result.skipped == 0
    assert result.failed_feeds == []
    assert len(db.items) == 1
    assert db.commits == 1
