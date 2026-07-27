import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.core.database import get_async_db
from app.api.main import app
from app.core.models import Article


class FakeEmbedder:
    def embed(self, text: str):
        return [0.42, 0.24]


class DummyScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class DummyExecResult:
    def __init__(self, *, items=None, row=None):
        self._items = items or []
        self._row = row

    def scalars(self):
        return DummyScalarResult(self._items)

    def one(self):
        return self._row

    def all(self):
        return self._items


class DummyDB:
    def __init__(self, article=None, articles=None):
        self.article = article
        self.articles = articles or ([article] if article else [])
        self.saved_comment = None

    async def execute(self, stmt):
        if isinstance(stmt, Insert):
            params = stmt.compile().params
            self.saved_comment = SimpleNamespace(
                id=1,
                article_id=params["article_id"],
                author_name=params["author_name"],
                body=params["body"],
                created_at=datetime.now(timezone.utc),
            )
            return DummyExecResult(row=self.saved_comment)

        items = list(self.articles)
        for expr in getattr(stmt, "_where_criteria", ()):
            left = getattr(expr, "left", None)
            right = getattr(expr, "right", None)
            if getattr(left, "key", None) == "source":
                source_value = getattr(right, "value", None)
                items = [item for item in items if item.source == source_value]

        selected_columns = getattr(stmt, "selected_columns", None)
        if selected_columns is not None:
            keys = [getattr(column, "key", None) for column in selected_columns]
            if keys == ["source"]:
                sources = sorted({item.source for item in self.articles})
                return DummyExecResult(items=sources)

        return DummyExecResult(items=items)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, item):
        item.id = 1
        item.created_at = datetime.now(timezone.utc)

    async def get(self, model, item_id, options=None):
        for article in self.articles:
            if article.id == item_id:
                return article
        return None


def build_article(article_id: int, source: str, suffix: str) -> Article:
    return Article(
        id=article_id,
        source=source,
        rss_guid=f"g{suffix}",
        title=f"title{suffix}",
        url=f"https://example.com/{suffix}",
        content=f"body{suffix}",
        content_preview=f"body{suffix}",
        published_at=datetime.now(timezone.utc),
        embedding=[0.1] * 384,
    )


@pytest.fixture(autouse=True)
def clear_app_state():
    from app.api import routes as routes_module

    routes_module.read_cache._items.clear()
    routes_module.source_cache._items.clear()
    app.dependency_overrides.clear()
    yield
    routes_module.read_cache._items.clear()
    routes_module.source_cache._items.clear()
    app.dependency_overrides.clear()


def override_db(db):
    async def _override():
        yield db

    app.dependency_overrides[get_async_db] = _override


def test_post_comment():
    db = DummyDB(article=build_article(1, "feed", "1"))
    override_db(db)
    client = TestClient(app)

    response = client.post("/articles/1/comments", json={"author_name": "Sam", "body": "Nice"})

    assert response.status_code == 200
    assert response.json()["body"] == "Nice"
    assert db.saved_comment is not None


def test_list_articles_without_source_filter():
    db = DummyDB(articles=[build_article(1, "Feed A", "1"), build_article(2, "Feed B", "2")])
    override_db(db)
    client = TestClient(app)

    response = client.get("/articles")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_articles_with_source_filter():
    db = DummyDB(articles=[build_article(1, "Feed A", "1"), build_article(2, "Feed B", "2")])
    override_db(db)
    client = TestClient(app)

    response = client.get("/articles", params={"source": "Feed A"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["source"] == "Feed A"


def test_home_with_source_filter():
    db = DummyDB(articles=[build_article(1, "Feed A", "1"), build_article(2, "Feed B", "2")])
    override_db(db)
    client = TestClient(app)

    response = client.get("/", params={"source": "Feed A"})

    assert response.status_code == 200
    assert "Feed A" in response.text
    assert "Feed B" in response.text


def test_home_without_source_filter():
    db = DummyDB(articles=[build_article(1, "Feed A", "1"), build_article(2, "Feed B", "2")])
    override_db(db)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "title1" in response.text
    assert "title2" in response.text


def test_reindex_article():
    article = build_article(1, "Feed A", "1")
    db = DummyDB(article=article)
    override_db(db)
    from app.api import routes as routes_module

    previous_embedder = routes_module._embedder
    routes_module._embedder = FakeEmbedder()
    client = TestClient(app)

    response = client.post("/articles/1/reindex")

    assert response.status_code == 200
    assert response.json() == {"article_id": 1, "reindexed": True}
    assert article.embedding == [0.42, 0.24]

    routes_module._embedder = previous_embedder


def test_reindex_article_not_found():
    db = DummyDB(articles=[])
    override_db(db)
    client = TestClient(app)

    response = client.post("/articles/999/reindex")

    assert response.status_code == 404
    assert response.json()["detail"] == "Article not found"
