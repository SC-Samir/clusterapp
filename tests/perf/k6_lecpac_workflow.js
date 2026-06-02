import http from 'k6/http';
import { check, fail } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || '').replace(/\/$/, '');

if (!BASE_URL) {
  fail('BASE_URL is required, e.g. BASE_URL=https://lecpac.example.com');
}

const LIST_LIMIT = Number(__ENV.LIST_LIMIT || 200);
const RANDOM_SEED = Number(__ENV.RANDOM_SEED || Date.now());
const REQUEST_TIMEOUT = __ENV.REQUEST_TIMEOUT || '30s';
const NO_CONNECTION_REUSE = (__ENV.NO_CONNECTION_REUSE || 'false').toLowerCase() === 'true';
const SCENARIOS = (__ENV.SCENARIOS || 'read,comment,reindex,ingest')
  .split(',')
  .map((item) => item.trim().toLowerCase())
  .filter(Boolean);

const SMOKE_VUS = Number(__ENV.SMOKE_VUS || 2);
const SMOKE_DURATION = __ENV.SMOKE_DURATION || '45s';

const READ_RAMP_PRE_VUS = Number(__ENV.READ_RAMP_PRE_VUS || 5);
const READ_RAMP_PRE_DURATION = __ENV.READ_RAMP_PRE_DURATION || '2m';
const READ_RAMP_VUS = Number(__ENV.READ_RAMP_VUS || 20);
const READ_RAMP_DURATION = __ENV.READ_RAMP_DURATION || '8m';
const READ_RAMP_POST_DURATION = __ENV.READ_RAMP_POST_DURATION || '1m';

const COMMENT_RAMP_PRE_VUS = Number(__ENV.COMMENT_RAMP_PRE_VUS || 2);
const COMMENT_RAMP_PRE_DURATION = __ENV.COMMENT_RAMP_PRE_DURATION || '2m';
const COMMENT_RAMP_VUS = Number(__ENV.COMMENT_RAMP_VUS || 8);
const COMMENT_RAMP_DURATION = __ENV.COMMENT_RAMP_DURATION || '8m';
const COMMENT_RAMP_POST_DURATION = __ENV.COMMENT_RAMP_POST_DURATION || '1m';

const REINDEX_RAMP_PRE_VUS = Number(__ENV.REINDEX_RAMP_PRE_VUS || 1);
const REINDEX_RAMP_PRE_DURATION = __ENV.REINDEX_RAMP_PRE_DURATION || '2m';
const REINDEX_RAMP_VUS = Number(__ENV.REINDEX_RAMP_VUS || 4);
const REINDEX_RAMP_DURATION = __ENV.REINDEX_RAMP_DURATION || '8m';
const REINDEX_RAMP_POST_DURATION = __ENV.REINDEX_RAMP_POST_DURATION || '1m';

const INGEST_SMOKE_RATE = Number(__ENV.INGEST_SMOKE_RATE || 3);
const INGEST_RAMP_RATE = Number(__ENV.INGEST_RAMP_RATE || 12);
const INGEST_RAMP_DURATION = __ENV.INGEST_RAMP_DURATION || '11m';
const INGEST_PREALLOCATED_VUS = Number(__ENV.INGEST_PREALLOCATED_VUS || 2);
const INGEST_MAX_VUS = Number(__ENV.INGEST_MAX_VUS || 4);

const READ_P95_MS = Number(__ENV.READ_P95_MS || 1200);
const COMMENT_P95_MS = Number(__ENV.COMMENT_P95_MS || 1600);
const REINDEX_P95_MS = Number(__ENV.REINDEX_P95_MS || 3500);
const INGEST_P95_MS = Number(__ENV.INGEST_P95_MS || 8000);

const ERROR_RATE_MAX = Number(__ENV.ERROR_RATE_MAX || 0.05);

export const readLatency = new Trend('read_latency', true);
export const commentLatency = new Trend('comment_latency', true);
export const reindexLatency = new Trend('reindex_latency', true);
export const ingestLatency = new Trend('ingest_latency', true);
export const errorRate = new Rate('error_rate');

const ALL_OPERATIONS = ['read', 'comment', 'reindex', 'ingest'];
const SELECTED_OPERATIONS = SCENARIOS.includes('all') ? ALL_OPERATIONS : SCENARIOS;
const INVALID_OPERATIONS = SELECTED_OPERATIONS.filter((name) => !ALL_OPERATIONS.includes(name));

if (INVALID_OPERATIONS.length > 0) {
  fail(`Invalid SCENARIOS value(s): ${INVALID_OPERATIONS.join(', ')}. Use any of: ${ALL_OPERATIONS.join(', ')}, all`);
}

if (SELECTED_OPERATIONS.length === 0) {
  fail(`SCENARIOS must select at least one operation: ${ALL_OPERATIONS.join(', ')}`);
}

const NEEDS_ARTICLE_IDS = SELECTED_OPERATIONS.some((name) => name !== 'ingest');

function buildScenarios() {
  const scenarios = {};

  if (SELECTED_OPERATIONS.includes('read')) {
    scenarios.read_articles_smoke = {
      executor: 'constant-vus',
      vus: SMOKE_VUS,
      duration: SMOKE_DURATION,
      exec: 'readArticles',
      tags: { operation: 'read', phase: 'smoke' },
    };
    scenarios.read_articles_ramp = {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: READ_RAMP_PRE_DURATION, target: READ_RAMP_PRE_VUS },
        { duration: READ_RAMP_DURATION, target: READ_RAMP_VUS },
        { duration: READ_RAMP_POST_DURATION, target: 0 },
      ],
      gracefulRampDown: '30s',
      startTime: SMOKE_DURATION,
      exec: 'readArticles',
      tags: { operation: 'read', phase: 'ramp' },
    };
  }

  if (SELECTED_OPERATIONS.includes('comment')) {
    scenarios.post_comments_smoke = {
      executor: 'constant-vus',
      vus: SMOKE_VUS,
      duration: SMOKE_DURATION,
      exec: 'postComments',
      tags: { operation: 'comment', phase: 'smoke' },
    };
    scenarios.post_comments_ramp = {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: COMMENT_RAMP_PRE_DURATION, target: COMMENT_RAMP_PRE_VUS },
        { duration: COMMENT_RAMP_DURATION, target: COMMENT_RAMP_VUS },
        { duration: COMMENT_RAMP_POST_DURATION, target: 0 },
      ],
      gracefulRampDown: '30s',
      startTime: SMOKE_DURATION,
      exec: 'postComments',
      tags: { operation: 'comment', phase: 'ramp' },
    };
  }

  if (SELECTED_OPERATIONS.includes('reindex')) {
    scenarios.reindex_articles_smoke = {
      executor: 'constant-vus',
      vus: 1,
      duration: SMOKE_DURATION,
      exec: 'reindexArticles',
      tags: { operation: 'reindex', phase: 'smoke' },
    };
    scenarios.reindex_articles_ramp = {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: REINDEX_RAMP_PRE_DURATION, target: REINDEX_RAMP_PRE_VUS },
        { duration: REINDEX_RAMP_DURATION, target: REINDEX_RAMP_VUS },
        { duration: REINDEX_RAMP_POST_DURATION, target: 0 },
      ],
      gracefulRampDown: '30s',
      startTime: SMOKE_DURATION,
      exec: 'reindexArticles',
      tags: { operation: 'reindex', phase: 'ramp' },
    };
  }

  if (SELECTED_OPERATIONS.includes('ingest')) {
    scenarios.run_ingest_smoke = {
      executor: 'constant-arrival-rate',
      rate: INGEST_SMOKE_RATE,
      timeUnit: '1m',
      duration: SMOKE_DURATION,
      preAllocatedVUs: INGEST_PREALLOCATED_VUS,
      maxVUs: INGEST_MAX_VUS,
      exec: 'runIngest',
      tags: { operation: 'ingest', phase: 'smoke' },
    };
    scenarios.run_ingest_ramp = {
      executor: 'constant-arrival-rate',
      rate: INGEST_RAMP_RATE,
      timeUnit: '1m',
      duration: INGEST_RAMP_DURATION,
      preAllocatedVUs: INGEST_PREALLOCATED_VUS,
      maxVUs: INGEST_MAX_VUS,
      startTime: SMOKE_DURATION,
      exec: 'runIngest',
      tags: { operation: 'ingest', phase: 'ramp' },
    };
  }

  return scenarios;
}

function buildThresholds() {
  const thresholds = {
    error_rate: [`rate<${ERROR_RATE_MAX}`],
  };

  if (SELECTED_OPERATIONS.includes('read')) {
    thresholds.read_latency = [`p(95)<${READ_P95_MS}`];
  }
  if (SELECTED_OPERATIONS.includes('comment')) {
    thresholds.comment_latency = [`p(95)<${COMMENT_P95_MS}`];
  }
  if (SELECTED_OPERATIONS.includes('reindex')) {
    thresholds.reindex_latency = [`p(95)<${REINDEX_P95_MS}`];
  }
  if (SELECTED_OPERATIONS.includes('ingest')) {
    thresholds.ingest_latency = [`p(95)<${INGEST_P95_MS}`];
  }

  return thresholds;
}

export const options = {
  noConnectionReuse: NO_CONNECTION_REUSE,
  scenarios: buildScenarios(),
  thresholds: buildThresholds(),
};

function makeRng(seed) {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

const rng = makeRng(RANDOM_SEED);

function randomItem(items) {
  const idx = Math.floor(rng() * items.length);
  return items[idx];
}

function addError(success) {
  errorRate.add(success ? 0 : 1);
}

function commonHeaders() {
  return {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
}

function requestParams(tags) {
  return {
    headers: commonHeaders(),
    tags,
    timeout: REQUEST_TIMEOUT,
  };
}

function pickArticleId(data) {
  return randomItem(data.articleIds);
}

function commentPayload() {
  const author = `k6-user-${Math.floor(rng() * 1_000_000)}`;
  const body = `k6-load-test-comment-${Math.floor(rng() * 1_000_000_000)}`;
  return JSON.stringify({ author_name: author.slice(0, 120), body });
}

export function setup() {
  if (!NEEDS_ARTICLE_IDS) {
    return { articleIds: [] };
  }

  const listUrl = `${BASE_URL}/articles?limit=${LIST_LIMIT}`;
  const res = http.get(listUrl, requestParams({ operation: 'setup_list' }));

  const ok = check(res, {
    'setup list status is 200': (r) => r.status === 200,
    'setup list payload is array': (r) => {
      try {
        return Array.isArray(r.json());
      } catch (_err) {
        return false;
      }
    },
  });

  if (!ok) {
    fail(`setup failed: unable to fetch /articles from ${listUrl}`);
  }

  const payload = res.json();
  const articleIds = payload
    .map((item) => item && item.id)
    .filter((id) => Number.isInteger(id) && id > 0);

  if (articleIds.length === 0) {
    fail('setup failed: no articles found. Run POST /ingest/run first or seed test data.');
  }

  return { articleIds };
}

export function readArticles(data) {
  const articleId = pickArticleId(data);
  const res = http.get(`${BASE_URL}/articles/${articleId}`, requestParams({ operation: 'read' }));

  readLatency.add(res.timings.duration);

  const ok = check(res, {
    'read status is 200': (r) => r.status === 200,
    'read returns expected article id': (r) => {
      try {
        return r.json('id') === articleId;
      } catch (_err) {
        return false;
      }
    },
  });

  addError(ok);
}

export function postComments(data) {
  const articleId = pickArticleId(data);
  const res = http.post(
    `${BASE_URL}/articles/${articleId}/comments`,
    commentPayload(),
    requestParams({ operation: 'comment' }),
  );

  commentLatency.add(res.timings.duration);

  const ok = check(res, {
    'comment status is 200': (r) => r.status === 200,
    'comment returns id': (r) => {
      try {
        return Number.isInteger(r.json('id'));
      } catch (_err) {
        return false;
      }
    },
    'comment returns matching article_id': (r) => {
      try {
        return r.json('article_id') === articleId;
      } catch (_err) {
        return false;
      }
    },
  });

  addError(ok);
}

export function reindexArticles(data) {
  const articleId = pickArticleId(data);
  const res = http.post(`${BASE_URL}/articles/${articleId}/reindex`, null, requestParams({ operation: 'reindex' }));

  reindexLatency.add(res.timings.duration);

  const ok = check(res, {
    'reindex status is 200': (r) => r.status === 200,
    'reindex confirms article id': (r) => {
      try {
        return r.json('article_id') === articleId;
      } catch (_err) {
        return false;
      }
    },
    'reindex confirms true': (r) => {
      try {
        return r.json('reindexed') === true;
      } catch (_err) {
        return false;
      }
    },
  });

  addError(ok);
}

export function runIngest() {
  const res = http.post(`${BASE_URL}/ingest/run`, null, requestParams({ operation: 'ingest' }));

  ingestLatency.add(res.timings.duration);

  const ok = check(res, {
    'ingest status is 200': (r) => r.status === 200,
    'ingest returns counters': (r) => {
      try {
        const json = r.json();
        return (
          Number.isInteger(json.ingested) &&
          Number.isInteger(json.updated) &&
          Number.isInteger(json.skipped) &&
          Array.isArray(json.failed_feeds)
        );
      } catch (_err) {
        return false;
      }
    },
  });

  addError(ok);
}
