from app.config import Settings


def test_rss_feeds_parsing_with_big_pack_bundle():
    settings = Settings(
        RSS_FEEDS=(
            "https://hnrss.org/frontpage,"
            "https://www.reddit.com/r/programming/.rss,"
            "https://techcrunch.com/feed/,"
            "https://www.theverge.com/rss/index.xml,"
            "https://feeds.arstechnica.com/arstechnica/index,"
            "https://www.infoq.com/feed/"
        )
    )

    assert "https://hnrss.org/frontpage" in settings.parsed_feeds
    assert "https://www.reddit.com/r/programming/.rss" in settings.parsed_feeds
    assert "https://techcrunch.com/feed/" in settings.parsed_feeds
    assert "https://www.theverge.com/rss/index.xml" in settings.parsed_feeds
    assert "https://feeds.arstechnica.com/arstechnica/index" in settings.parsed_feeds
    assert "https://www.infoq.com/feed/" in settings.parsed_feeds
