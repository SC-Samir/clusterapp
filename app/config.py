from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DEFAULT_EMBEDDING_MODEL = str(APP_DIR / "models" / "all-MiniLM-L6-v2")


class Settings(BaseSettings):
    app_name: str = "LecPac RSS Demo"
    database_url: str = Field("sqlite:///./local.db", alias="DATABASE_URL")
    db_pool_size: int = Field(20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(20, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(1800, alias="DB_POOL_RECYCLE")
    db_connect_timeout: int = Field(5, alias="DB_CONNECT_TIMEOUT")
    db_use_null_pool: bool = Field(False, alias="DB_USE_NULL_POOL")
    vector_dim: int = Field(384, alias="VECTOR_DIM")
    rss_feeds: str = Field(
        "https://hnrss.org/frontpage,https://www.reddit.com/r/programming/.rss,https://techcrunch.com/feed/,https://www.theverge.com/rss/index.xml,https://feeds.arstechnica.com/arstechnica/index,https://www.infoq.com/feed/",
        alias="RSS_FEEDS",
    )
    ingest_interval_minutes: int = Field(30, alias="INGEST_INTERVAL_MINUTES")
    embedding_model: str = Field(DEFAULT_EMBEDDING_MODEL, alias="EMBEDDING_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    def model_post_init(self, __context) -> None:
        candidate = Path(self.embedding_model)
        if candidate.exists():
            self.embedding_model = str(candidate.resolve())
            return

        if not candidate.is_absolute():
            project_relative = PROJECT_ROOT / candidate
            if project_relative.exists():
                self.embedding_model = str(project_relative.resolve())

    @property
    def parsed_feeds(self) -> list[str]:
        return [f.strip() for f in self.rss_feeds.split(",") if f.strip()]

    @property
    def sync_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        return url

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
