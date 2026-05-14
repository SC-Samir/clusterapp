# LecPac RSS Demo (FastAPI + pgvector)

Demo application for LecPac presentation:
- Ingest curated RSS feeds
- Store articles + vectors in PostgreSQL/pgvector
- Add comments per article
- Recommend similar articles
- Preprocess article content (HTML cleanup + sentence chunking) before embeddings

## Run locally

1. Install dependencies:
   ```bash
   uv sync
   ```
2. Configure env:
   ```bash
   cp .env.example .env
   # edit DATABASE_URL
   ```
3. Run DB migration:
   ```bash
   uv run alembic upgrade head
   ```
4. Run app:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

## Local quick test with Docker Compose (Postgres + pgvector)

1. Start database:
   ```bash
   docker compose up -d db
   ```
2. Use docker env:
   ```bash
   cp .env.docker .env
   ```
3. Run migrations:
   ```bash
   uv run alembic upgrade head
   ```
4. Start app:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

Shortcut script:
```bash
./scripts_local_docker_test.sh
```

## API routes

- `GET /articles` (optional query: `source`)
- `GET /articles/{id}`
- `POST /articles/{id}/comments`
- `GET /articles/{id}/recommendations`
- `POST /articles/{id}/reindex`
- `POST /ingest/run`

## UI routes

- `GET /` (optional query: `source`; homepage includes source filter control)
- `GET /articles/{id}/view`
- `POST /articles/{id}/comment-form`

## Default RSS feeds

By default, `RSS_FEEDS` includes:
- `https://hnrss.org/frontpage`
- `https://www.reddit.com/r/programming/.rss`
- `https://techcrunch.com/feed/`
- `https://www.theverge.com/rss/index.xml`
- `https://feeds.arstechnica.com/arstechnica/index`
- `https://www.infoq.com/feed/`

## Kubernetes (Outscale-compatible)

1. Build/push image.
2. Apply manifests:
   ```bash
   kubectl apply -f app/k8s/configmap.yaml
   kubectl apply -f app/k8s/secret.example.yaml # replace with real secret file
   kubectl apply -f app/k8s/deployment.yaml
   kubectl apply -f app/k8s/service.yaml
   kubectl apply -f app/k8s/ingress.yaml
   kubectl apply -f app/k8s/cronjob.yaml
   ```

Use Scalingo DB URL in `DATABASE_URL` secret value.

## Helm deployment (recommended)

1. Edit chart values:
   - `helm/lecpac-rss/values.yaml`
   - Set image repository/tag, ingress host, and `secrets.DATABASE_URL`.
2. Install/upgrade:
   ```bash
   helm upgrade --install lecpac-rss ./helm/lecpac-rss
   ```
3. Verify:
   ```bash
   kubectl get pods,svc,ingress
   ```
