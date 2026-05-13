from datetime import datetime, timezone

from app.services.recommendations import recommend_similar_articles


class FakeArticle:
    def __init__(self, article_id, distance):
        self.id = article_id
        self.source = "x"
        self.title = "t"
        self.url = "u"
        self.published_at = datetime.now(timezone.utc)
        self.embedding = [0.1]
        self._distance = distance


class FakeDistance:
    def label(self, _):
        return self

    def asc(self):
        return self


class FakeEmbedding:
    def cosine_distance(self, _):
        return FakeDistance()


class FakeArticleModel:
    embedding = FakeEmbedding()
    id = 0


class FakeExecResult:
    def all(self):
        return [
            (FakeArticle(2, 0.1), 0.1),
            (FakeArticle(3, 0.2), 0.2),
        ]


class FakeDB:
    def execute(self, stmt):
        return FakeExecResult()


class FakeSelect:
    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self


def test_recommendation_similarity_scores(monkeypatch):
    monkeypatch.setattr("app.services.recommendations.Article", FakeArticleModel)
    monkeypatch.setattr("app.services.recommendations.select", lambda *args, **kwargs: FakeSelect())
    base = FakeArticle(1, 0.0)
    db = FakeDB()

    recs = recommend_similar_articles(db, base, limit=2)
    assert len(recs) == 2
    assert recs[0][1] == 0.9
    assert recs[1][1] == 0.8
