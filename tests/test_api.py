from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Article, Comment


class DummyQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args, **kwargs):
        for expr in args:
            left = getattr(expr, "left", None)
            right = getattr(expr, "right", None)
            if getattr(left, "key", None) == "source":
                source_value = getattr(right, "value", None)
                self.items = [item for item in self.items if item.source == source_value]
        return self

    def one_or_none(self):
        return self.items[0] if self.items else None

    def options(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def offset(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.items


class DummyDB:
    def __init__(self, article=None, articles=None):
        self.article = article
        self.articles = articles or ([article] if article else [])
        self.saved_comment = None

    def query(self, model):
        if model is Article:
            return DummyQuery(self.articles)
        if model is Comment:
            return DummyQuery([])
        if str(model) == "Article.source":
            sources = sorted({item.source for item in self.articles})
            return DummyQuery([(source,) for source in sources])
        return DummyQuery([])

    def add(self, item):
        self.saved_comment = item

    def commit(self):
        pass

    def refresh(self, item):
        item.id = 1
        item.created_at = datetime.now(timezone.utc)


def test_post_comment():
    article = Article(
        id=1,
        source="feed",
        rss_guid="g",
        title="title",
        url="https://example.com",
        content="body",
        published_at=datetime.now(timezone.utc),
        embedding=[0.1] * 384,
    )

    db = DummyDB(article=article)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.post("/articles/1/comments", json={"author_name": "Sam", "body": "Nice"})

    assert response.status_code == 200
    assert response.json()["body"] == "Nice"
    assert db.saved_comment is not None

    app.dependency_overrides.clear()


def test_list_articles_without_source_filter():
    articles = [
        Article(
            id=1,
            source="Feed A",
            rss_guid="g1",
            title="title1",
            url="https://example.com/1",
            content="body1",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
        Article(
            id=2,
            source="Feed B",
            rss_guid="g2",
            title="title2",
            url="https://example.com/2",
            content="body2",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
    ]
    db = DummyDB(articles=articles)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/articles")

    assert response.status_code == 200
    assert len(response.json()) == 2
    app.dependency_overrides.clear()


def test_list_articles_with_source_filter():
    articles = [
        Article(
            id=1,
            source="Feed A",
            rss_guid="g1",
            title="title1",
            url="https://example.com/1",
            content="body1",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
        Article(
            id=2,
            source="Feed B",
            rss_guid="g2",
            title="title2",
            url="https://example.com/2",
            content="body2",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
    ]
    db = DummyDB(articles=articles)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/articles", params={"source": "Feed A"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["source"] == "Feed A"
    app.dependency_overrides.clear()


def test_home_with_source_filter():
    articles = [
        Article(
            id=1,
            source="Feed A",
            rss_guid="g1",
            title="title1",
            url="https://example.com/1",
            content="body1",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
        Article(
            id=2,
            source="Feed B",
            rss_guid="g2",
            title="title2",
            url="https://example.com/2",
            content="body2",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
    ]
    db = DummyDB(articles=articles)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/", params={"source": "Feed A"})

    assert response.status_code == 200
    assert "Feed A" in response.text
    assert "Feed B" in response.text
    app.dependency_overrides.clear()


def test_home_without_source_filter():
    articles = [
        Article(
            id=1,
            source="Feed A",
            rss_guid="g1",
            title="title1",
            url="https://example.com/1",
            content="body1",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
        Article(
            id=2,
            source="Feed B",
            rss_guid="g2",
            title="title2",
            url="https://example.com/2",
            content="body2",
            published_at=datetime.now(timezone.utc),
            embedding=[0.1] * 384,
        ),
    ]
    db = DummyDB(articles=articles)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "title1" in response.text
    assert "title2" in response.text
    app.dependency_overrides.clear()
