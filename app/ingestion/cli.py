import argparse
import asyncio
import sys
from typing import Optional

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.models import Article
from app.core.services.embeddings import EmbeddingService
from app.ingestion.ingestion import ingest_feeds
from app.ingestion.reindex import reindex_article


async def run_ingest() -> None:
    settings = get_settings()
    embedder = EmbeddingService()
    async with AsyncSessionLocal() as db:
        result = await ingest_feeds(db, settings.parsed_feeds, embedder)
    print(
        f"ingested={result.ingested} updated={result.updated} "
        f"skipped={result.skipped} failed_feeds={result.failed_feeds}"
    )
    if result.failed_feeds:
        sys.exit(1)


async def run_reindex(article_id: int) -> None:
    embedder = EmbeddingService()
    async with AsyncSessionLocal() as db:
        article = await db.get(Article, article_id)
        if article is None:
            print(f"Article {article_id} not found", file=sys.stderr)
            sys.exit(2)
        await reindex_article(db, article, embedder)
    print(f"reindexed article_id={article_id}")


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="app.ingestion.cli", description="LecPac RSS ingestion runner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("ingest", help="Run feed ingestion once")

    reindex_parser = sub.add_parser("reindex", help="Reindex a single article by id")
    reindex_parser.add_argument("article_id", type=int)

    args = parser.parse_args(argv)

    if args.command == "reindex":
        asyncio.run(run_reindex(args.article_id))
    else:
        # default to ingest (including when no subcommand given)
        asyncio.run(run_ingest())


if __name__ == "__main__":
    main()
