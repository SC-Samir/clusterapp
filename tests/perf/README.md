# k6 Performance Test: API + DB + Kubernetes CPU

This suite load tests the full workflow:
- `POST /ingest/run`
- `GET /articles/{id}`
- `POST /articles/{id}/comments`
- `POST /articles/{id}/reindex`

It discovers article IDs dynamically in `setup()` by calling `GET /articles?limit=...`.

## Prerequisites

- `k6` installed locally.
- Target app reachable through Kubernetes ingress.
- Target has at least one article (`/articles` must not be empty).

## Required Environment Variable

- `BASE_URL`: ingress URL for your API (no trailing slash required).

Example:

```bash
export BASE_URL="https://lecpac-rss.example.com"
```

## Quick Smoke Run

Runs low traffic across all 4 operations to validate behavior and payload checks.

```bash
k6 run tests/perf/k6_lecpac_workflow.js
```

## Run Only Selected Operations

Run only ingest:

```bash
BASE_URL="https://lecpac-rss.example.com" \
SCENARIOS=ingest \
k6 run tests/perf/k6_lecpac_workflow.js
```

Run only article reads:

```bash
BASE_URL="https://lecpac-rss.example.com" \
SCENARIOS=read \
k6 run tests/perf/k6_lecpac_workflow.js
```

Run reads plus comments:

```bash
BASE_URL="https://lecpac-rss.example.com" \
SCENARIOS=read,comment \
k6 run tests/perf/k6_lecpac_workflow.js
```

Run only reindex:

```bash
BASE_URL="https://lecpac-rss.example.com" \
SCENARIOS=reindex \
k6 run tests/perf/k6_lecpac_workflow.js
```

## Tuned Ramp Run Example

This example increases read/comment/reindex load and keeps ingestion low-rate control traffic.

```bash
BASE_URL="https://lecpac-rss.example.com" \
SMOKE_DURATION="1m" \
READ_RAMP_PRE_DURATION="3m" READ_RAMP_DURATION="12m" READ_RAMP_POST_DURATION="2m" \
READ_RAMP_PRE_VUS=10 READ_RAMP_VUS=40 \
COMMENT_RAMP_PRE_DURATION="3m" COMMENT_RAMP_DURATION="12m" COMMENT_RAMP_POST_DURATION="2m" \
COMMENT_RAMP_PRE_VUS=4 COMMENT_RAMP_VUS=14 \
REINDEX_RAMP_PRE_DURATION="3m" REINDEX_RAMP_DURATION="12m" REINDEX_RAMP_POST_DURATION="2m" \
REINDEX_RAMP_PRE_VUS=2 REINDEX_RAMP_VUS=6 \
INGEST_RAMP_RATE=9 INGEST_RAMP_DURATION="17m" INGEST_MAX_VUS=3 \
k6 run tests/perf/k6_lecpac_workflow.js
```

## Available Tunables

Core:
- `BASE_URL` (required)
- `SCENARIOS` (default `read,comment,reindex,ingest`; available: `read`, `comment`, `reindex`, `ingest`, `all`)
- `LIST_LIMIT` (default `200`)
- `RANDOM_SEED` (default current time)
- `REQUEST_TIMEOUT` (default `30s`)
- `NO_CONNECTION_REUSE` (default `false`; set to `true` if ingress closes keep-alive connections under load)

Smoke:
- `SMOKE_VUS` (default `2`)
- `SMOKE_DURATION` (default `45s`)

Read ramp:
- `READ_RAMP_PRE_VUS` (default `5`)
- `READ_RAMP_VUS` (default `20`)
- `READ_RAMP_PRE_DURATION` (default `2m`)
- `READ_RAMP_DURATION` (default `8m`)
- `READ_RAMP_POST_DURATION` (default `1m`)

Comment ramp:
- `COMMENT_RAMP_PRE_VUS` (default `2`)
- `COMMENT_RAMP_VUS` (default `8`)
- `COMMENT_RAMP_PRE_DURATION` (default `2m`)
- `COMMENT_RAMP_DURATION` (default `8m`)
- `COMMENT_RAMP_POST_DURATION` (default `1m`)

Reindex ramp:
- `REINDEX_RAMP_PRE_VUS` (default `1`)
- `REINDEX_RAMP_VUS` (default `4`)
- `REINDEX_RAMP_PRE_DURATION` (default `2m`)
- `REINDEX_RAMP_DURATION` (default `8m`)
- `REINDEX_RAMP_POST_DURATION` (default `1m`)

Ingestion control traffic:
- `INGEST_SMOKE_RATE` (default `3` req/min)
- `INGEST_RAMP_RATE` (default `12` req/min)
- `INGEST_RAMP_DURATION` (default `11m`)
- `INGEST_PREALLOCATED_VUS` (default `2`)
- `INGEST_MAX_VUS` (default `4`)

Thresholds (p95 ms / error-rate):
- `READ_P95_MS` (default `1200`)
- `COMMENT_P95_MS` (default `1600`)
- `REINDEX_P95_MS` (default `3500`)
- `INGEST_P95_MS` (default `8000`)
- `ERROR_RATE_MAX` (default `0.05`)

## Metrics Produced

- `read_latency`
- `comment_latency`
- `reindex_latency`
- `ingest_latency`
- `error_rate`

Threshold checks fail the run when limits are exceeded.

## What To Observe During Ramp

Kubernetes CPU (replace namespace/selector as needed):

```bash
kubectl top pods -n <namespace> -l app=lecpac-rss
```

Database saturation indicators:
- active connections / pool pressure
- slow queries
- lock wait or timeout symptoms

## Notes

- Script fails fast if no articles are found during setup.
- `setup()` skips article discovery automatically when `SCENARIOS=ingest`.
- No auth header is included by default because current API routes are unauthenticated.
- Ingest arrival rates must be integers because k6 `constant-arrival-rate` does not accept fractional `rate` values.
- `unexpected EOF` usually means the app pod, ingress, or upstream connection was closed before the response completed; on this project that is especially likely during `reindex` and `ingest`, which both do embedding work.
