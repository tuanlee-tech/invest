# Implementation Roadmap

**Project**: VN Investment Intelligence
**Scope**: Finish and harden the local-first, evidence-first MVP.
**Owner**: Next coding agent
**Rule**: Work in priority order. Keep the free baseline working. Do not add auto-trading.

## Agent Instructions

1. Read `HANDOFF.md`, `plans/architecture-proposal.md`, and the current Git diff before editing.
2. Do not revert existing user or agent changes.
3. Prefer the smallest change that satisfies the acceptance criteria.
4. Update this file by checking completed items and recording blockers.
5. Run the relevant tests after each phase and the full verification checklist before stopping.
6. If external data is unavailable, preserve the raw failure and do not silently create fake investment data.

## Current Baseline

- FastAPI + SQLite + SQLAlchemy application runs locally.
- Docker files and Alembic initial migration exist.
- Six fund configurations are present, but several holdings are seeded/manual.
- Live vnstock price endpoint exists.
- Corporate-action adjustment module exists and needs broader verification.
- Retry decorators exist and are applied to market-data functions.
- OpenCode LLM client has Ollama fallback routing, but Ollama is not installed/tested locally.
- Lifecycle test currently passes: `5 passed, 0 failed`.
- `HANDOFF.md` contains stale statements about corporate actions and Ollama; update it after implementation work.

## Phase 0: Establish A Reliable Baseline

**Priority**: P0

- [ ] Add `GET /health` with database, market-data, and LLM-provider status.
- [ ] Verify a clean database can be created with Alembic, then seeded without errors.
- [ ] Define which records are live, seeded, or fallback/manual data.
- [ ] Reconcile stale claims in `HANDOFF.md` and this roadmap.
- [ ] Confirm the documented local and Docker startup paths.

**Acceptance criteria**

```bash
alembic upgrade head
python -m tests.test_lifecycle
curl http://localhost:8000/health
```

The health response must identify dependency failures instead of returning a misleading healthy status.

## Phase 1: Data Quality And Provenance

**Priority**: P0

### Fund ingestion

- [ ] Complete or explicitly mark parsers for VCBF-BCF, SSI-SCA, DCDS, and PYN Elite.
- [ ] Persist source URL, retrieval timestamp, file hash, reporting period, and effective date for every holdings snapshot.
- [ ] Preserve old snapshots; never overwrite point-in-time data.
- [ ] Record parser failures with source and error details.

### Holdings normalization

- [ ] Normalize ticker, percentage, currency, units, and snapshot date.
- [ ] Detect duplicate holdings in one snapshot.
- [ ] Validate allocation totals and report cash/other assets separately.

### Market data

- [ ] Cache short-lived price responses to protect vnstock rate limits.
- [ ] Retry only transient failures such as timeout, connection failure, and HTTP 5xx.
- [ ] Return explicit provider/data errors for invalid symbols or malformed responses.

### Corporate actions

- [ ] Add verified split, dividend, and rights-issue data sources or a clearly documented manual data format.
- [ ] Add tests for each adjustment type.
- [ ] Verify historical returns, drawdown, and P&L before and after adjustments.

**Acceptance criteria**

- Every imported snapshot has provenance.
- Parser failures are visible in logs/job results.
- Historical calculations do not silently mix adjusted and unadjusted prices.

## Phase 2: Investment Intelligence Correctness

**Priority**: P1

### Causal graph

- [ ] Implement and verify `event -> sector -> ticker -> fund holding -> proposal` links.
- [ ] Store classification (`FACT`, `INFERENCE`, `FORECAST`), mechanism, direction, confidence, source event, and timestamp.
- [ ] Add tests for positive, negative, and irrelevant event links.

### Opportunity engine

- [ ] Use normalized fundamentals in scoring.
- [ ] Prevent duplicate proposals across repeated scans.
- [ ] Create a new version only when an event, holding, fundamental, or thesis materially changes.
- [ ] Preserve `changed_from_previous` and all evidence references.

### Portfolio re-evaluation

- [ ] Evaluate structured invalidation conditions automatically.
- [ ] Persist thesis health as `HEALTHY`, `AT_RISK`, or `INVALIDATED`.
- [ ] Preserve every ADD/HOLD/REDUCE/EXIT decision as history.
- [ ] Keep all trading execution manual and out of scope.

### Track record

- [ ] Run evaluation on seeded proposals using point-in-time market data.
- [ ] Calculate return by horizon, target/stop outcomes, invalidation outcome, win rate, and confidence calibration.
- [ ] Slice results by ticker, fund, action, model, and prompt version.

**Acceptance criteria**

- Every proposal can be traced to events, fund snapshots, and fundamentals.
- Re-running a scan does not create duplicate proposals.
- Track-record results are reproducible from stored point-in-time data.

## Phase 3: LLM And Scheduler Reliability

**Priority**: P1

### LLM provider boundary

- [ ] Keep OpenCode/free models as the default path.
- [ ] Verify Ollama detection, model availability, timeout, and fallback behavior when installed.
- [ ] Log provider, model, latency, and failure reason without logging secrets.
- [ ] If all providers fail, persist the event and mark the proposal job `LLM_FAILED`; never invent a proposal.

### Structured output

- [ ] Validate every LLM response with Pydantic before database insertion.
- [ ] Reject invalid action, confidence, price ranges, position size, and missing invalidation conditions.
- [ ] Store raw model output only for debugging/audit, not as trusted UI data.

### Scheduler

- [ ] Add job execution ID, start/end time, status, error, and record counts.
- [ ] Prevent overlapping executions of the same job.
- [ ] Ensure one failed job does not stop the scheduler.

**Acceptance criteria**

- LLM failure does not lose ingested events.
- Invalid model output cannot enter the proposal tables.
- Job history makes failures diagnosable without reading process output.

## Phase 4: Local Production Hardening

**Priority**: P1

### Database and backup

- [ ] Add migration tests from an empty database.
- [ ] Add SQLite backup and restore commands.
- [ ] Verify backups after restart and restore into a clean database.

### API and security

- [ ] Validate all write endpoints.
- [ ] Limit request sizes and avoid secrets in logs.
- [ ] Restrict CORS to configured origins.
- [ ] Add basic authentication before exposing the app beyond localhost.

### Logging and observability

- [ ] Replace remaining `print()` calls with contextual logging.
- [ ] Include job, ticker, provider, and request identifiers where useful.
- [ ] Track request failures, ingestion failures, LLM latency, and provider latency.

### Docker

- [ ] Run the container as a non-root user.
- [ ] Add a Compose healthcheck.
- [ ] Persist database and logs through volumes.
- [ ] Verify restart does not lose data.

## Phase 5: Test And Release

**Priority**: P1

- [ ] Add unit tests for retry, corporate actions, scoring, proposal validation, and price normalization.
- [ ] Add integration tests for ingestion -> event -> causal graph -> proposal.
- [ ] Add integration tests for position -> re-evaluation -> evaluation.
- [ ] Add failure tests for vnstock timeout, malformed PDF, RSS failure, LLM timeout, invalid JSON, and database lock.
- [ ] Run the Docker smoke test.

## Final Verification Checklist

```bash
alembic upgrade head
python -m tests.test_lifecycle
docker compose build
docker compose up -d
curl http://localhost:8000/health
curl http://localhost:8000/api/prices?tickers=HPG,MWG
curl -X POST http://localhost:8000/api/jobs/ingestion
curl -X POST http://localhost:8000/api/jobs/opportunity-scan
curl -X POST http://localhost:8000/api/jobs/portfolio-reeval
curl -X POST http://localhost:8000/api/jobs/evaluation
```

Before declaring completion, verify all six UI routes, database backup/restore, logs, and migration-from-empty-database behavior.

## Explicitly Out Of Scope

- Automatic order placement or live trading.
- Mandatory paid LLM providers.
- Public internet exposure without authentication.
- Mobile application.
- Large-scale multi-user deployment before the single-user pipeline is reliable.
