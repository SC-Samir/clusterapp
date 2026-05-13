from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LecPac RSS Demo"
    database_url: str = Field("sqlite:///./local.db", alias="DATABASE_URL")
    vector_dim: int = Field(384, alias="VECTOR_DIM")
    rss_feeds: str = Field(
        "https://hnrss.org/frontpage,https://www.reddit.com/r/programming/.rss,https://techcrunch.com/feed/,https://www.theverge.com/rss/index.xml,https://feeds.arstechnica.com/arstechnica/index,https://www.infoq.com/feed/",
        alias="RSS_FEEDS",
    )
    ingest_interval_minutes: int = Field(30, alias="INGEST_INTERVAL_MINUTES")
    embedding_model: str = Field("sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def parsed_feeds(self) -> list[str]:
        return [f.strip() for f in self.rss_feeds.split(",") if f.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
