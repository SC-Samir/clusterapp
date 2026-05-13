from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.database import SessionLocal
from app.services.embeddings import EmbeddingService
from app.services.ingestion import ingest_feeds

settings = get_settings()
scheduler = BackgroundScheduler()
from typing import Optional

embedder: Optional[EmbeddingService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    def scheduled_ingest() -> None:
        global embedder
        if embedder is None:
            embedder = EmbeddingService()
        db = SessionLocal()
        try:
            ingest_feeds(db, settings.parsed_feeds, embedder)
        finally:
            db.close()

    scheduler.add_job(
        scheduled_ingest,
        trigger="interval",
        minutes=settings.ingest_interval_minutes,
        id="rss_ingestion",
        replace_existing=True,
    )
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)
