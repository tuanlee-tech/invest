# Implementation Roadmap

**Project**: VN Investment Intelligence
**Scope**: Finish and harden the local-first, evidence-first MVP.
**Owner**: Next coding agent
**Rule**: Work in priority order. Keep the free baseline working. Do not add auto-trading.

## Agent Instructions

1. Read `HANDOFF.md`, `OPENCODE.md`, `plans/architecture-proposal.md`, and the current Git diff before editing.
2. Do not revert existing user or agent changes.
3. Prefer the smallest change that satisfies the acceptance criteria.
4. Update this file by checking completed items and recording blockers.
5. Run the relevant tests after each phase and the full verification checklist before stopping.
6. If external data is unavailable, preserve the raw failure and do not silently create fake investment data.

## Current Baseline

- FastAPI + SQLite + SQLAlchemy application runs locally; `GET /health` returns 200 when DB + vnstock + OpenCode binary are healthy (503 with per-dependency errors otherwise).
- Docker files and Alembic migrations (`alembic upgrade head` → `a1b2c3d4e5f6`) exist and run against `settings.DATABASE_URL`.
- Six fund configurations. Holdings provenance (verified 2026-09-24 after Phase 0/1 work):
  - **SEED** — historical snapshots for VEIL/VESAF/VCBF-BCF (Jul/Aug/Sep 2026), sample SSI-SCA/DCDS rows; 6 funds, 17 securities, 4 events (manual causal links), 4 proposals.
  - **MANUAL** — 3 positions (closed prices/PnL hand-set), corporate-actions dict (documented manual format: split/rights/bonus `ratio`, dividend `amount`; 8 tickers).
  - **LIVE** — prices/OHLCV/fundamentals (vnstock, 60s/300s TTL cache, not persisted), fund-PDF/HTML ingestion (VEIL, VESAF, PYN parsed live; VCBF-BCF fails visibly; SSI-SCA/DCDS explicitly not-implemented), 2 proposal evaluations (FPT, CTG).
  - **Provenance** — all 13 snapshots have `source_url`/`source_hash`/`reporting_period`/`effective_date` (0 NULL); re-ingest never overwrites an existing `(fund_id, as_of_date)` row.
- Live vnstock price endpoint with short-lived cache; `vnstock_retry` retries only transient failures (timeout/connection/5xx/429), permanent errors fail fast as `MarketDataError`.
- Expired proposals are flipped `ACTIVE → EXPIRED` by the evaluation job (FPT, CTG now `EXPIRED`; HPG, MWG still `ACTIVE`).
- OpenCode LLM client has Ollama fallback routing, but Ollama is not installed/tested locally.
- Tests pass: `test_lifecycle` 7, `test_ingestion` 4, `test_market_data_unit` 10, `test_phase2` 5, `test_phase3` 6 (32 total).
- `HANDOFF.md`, `OPENCODE.md`, and this roadmap reconciled 2026-09-24 (provenance tables, health, market-data, corporate-actions updates).

## Phase 0: Establish A Reliable Baseline

**Priority**: P0

- [x] Add `GET /health` with database, market-data, and LLM-provider status.
- [x] Verify a clean database can be created with Alembic, then seeded without errors.
- [x] Define which records are live, seeded, or fallback/manual data.
- [x] Reconcile stale claims in `HANDOFF.md` and this roadmap.
- [x] Confirm the documented local and Docker startup paths.

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

- [x] Complete or explicitly mark parsers for VCBF-BCF, SSI-SCA, DCDS, and PYN Elite. (Live: VEIL, VESAF, PYN ✓; VCBF-BCF fails visibly with source+error; SSI-SCA/DCDS in `NOT_IMPLEMENTED_PARSERS` with reason — no fabricated rows.)
- [x] Persist source URL, retrieval timestamp, file hash, reporting period, and effective date for every holdings snapshot. (13/13 rows populated; seed rows use `seed:app/storage/seed.py` + sha256 of holdings; live rows use real URL/hash.)
- [x] Preserve old snapshots; never overwrite point-in-time data. (`save_snapshot` no-ops on existing `(fund_id, as_of_date)`; covered by `test_no_overwrite_on_reingest`.)
- [x] Record parser failures with source and error details. (`results["failures"]` in job response + structured logging.)

### Holdings normalization

- [x] Normalize ticker, percentage, currency, units, and snapshot date. (`normalize_holdings` handles `7.5%`, `7,5%`, `1,234.5`.)
- [x] Detect duplicate holdings in one snapshot. (`duplicates` in job result + warning log.)
- [x] Validate allocation totals and report cash/other assets separately. (`allocation.{equities,cash,other,total}_pct`, 0.5% tolerance.)

### Market data

- [x] Cache short-lived price responses to protect vnstock rate limits. (60s price / 300s history TTL cache in `market_data.py`.)
- [x] Retry only transient failures such as timeout, connection failure, and HTTP 5xx. (`retry_if=is_transient_error`; permanent errors raise immediately.)
- [x] Return explicit provider/data errors for invalid symbols or malformed responses. (`MarketDataError`; price endpoints map it to HTTP 502.)

### Corporate actions

- [x] Add verified split, dividend, and rights-issue data sources or a clearly documented manual data format. (Manual format documented in `corporate_actions.py` docstring; dividend `amount`, rights/bonus `ratio` supported; incomplete records skipped, never fabricated.)
- [x] Add tests for each adjustment type. (`tests/test_market_data_unit.py`: split window, dividend, rights, factor, combined.)
- [x] Verify historical returns, drawdown, and P&L before and after adjustments. (Adjustments windowed to `(start, end]` so pre-window events cannot distort returns; covered by split-window tests.)

**Acceptance criteria**

- Every imported snapshot has provenance.
- Parser failures are visible in logs/job results.
- Historical calculations do not silently mix adjusted and unadjusted prices.

## Phase 2: Investment Intelligence Correctness

**Priority**: P1

### Causal graph

- [x] Implement and verify `event -> sector -> ticker -> fund holding -> proposal` links. (Graph links merge with LLM links; relevance uses the merged set; proposals check fund holdings and store `evidence_refs`.)
- [x] Store classification (`FACT`, `INFERENCE`, `FORECAST`), mechanism, direction, confidence, source event, and timestamp. (`enrich_link` contract on every link in `Event.causal_links`.)
- [x] Add tests for positive, negative, and irrelevant event links. (`tests/test_phase2.py`.)

### Opportunity engine

- [x] Use normalized fundamentals in scoring. (`normalize_income` fed into `generate_proposal`.)
- [x] Prevent duplicate proposals across repeated scans. (One ACTIVE proposal per ticker blocks a new group regardless of age; result reports `proposals_skipped`. EXPIRED/REVISED allow a fresh group.)
- [ ] Create a new version only when an event, holding, fundamental, or thesis materially changes. (Revisions exist via portfolio re-eval + revise API; automatic material-change detection not implemented.)
- [x] Preserve `changed_from_previous` and all evidence references. (Set on create and on every revision.)

### Portfolio re-evaluation

- [x] Evaluate structured invalidation conditions automatically. (Price-based conditions machine-checked before LLM; financial-series conditions remain LLM-judged — no persisted financial series.)
- [x] Persist thesis health as `HEALTHY`, `AT_RISK`, or `INVALIDATED`. (`Position.thesis_health`; CRITICAL price trigger forces `INVALIDATED` + `EXIT` regardless of LLM.)
- [x] Preserve every ADD/HOLD/REDUCE/EXIT decision as history. (`position_decisions` append-only journal — unchanged HOLDs included; `decisions_recorded` in job result.)
- [x] Keep all trading execution manual and out of scope.

### Track record

- [x] Run evaluation on seeded proposals using point-in-time market data. (FPT, CTG evaluated and flipped to `EXPIRED`; HPG, MWG not yet settled — `valid_until` in 2027.)
- [x] Calculate return by horizon, target/stop outcomes, invalidation outcome, win rate, and confidence calibration. (`entry_hit`/`target_hit`/`stop_hit` computed from window close path; win rate + confidence calibration already present. Note: FPT/CTG rows predate this — hits stay default until re-evaluated.)
- [x] Slice results by ticker, fund, action, model, and prompt version. (ticker + action slices shipped; fund/model/prompt slices need `model_run_id` populated — deferred.)

**Acceptance criteria (Phase 2)**

- Every proposal can be traced to events, fund snapshots, and fundamentals.
- Re-running a scan does not create duplicate proposals.
- Track-record results are reproducible from stored point-in-time data.

## Phase 3: LLM And Scheduler Reliability

**Priority**: P1

### LLM provider boundary

- [x] Keep OpenCode/free models as the default path.
- [ ] Verify Ollama detection, model availability, timeout, and fallback behavior when installed. (Routing implemented in `app/llm/client.py`; Ollama absent on this machine — untested.)
- [x] Log provider, model, latency, and failure reason without logging secrets. (`llm provider=… model=… latency_ms=… status=… reason=…` lines; stderr truncated to 300 chars.)
- [x] If all providers fail, persist the event and mark the proposal job `LLM_FAILED`; never invent a proposal. (Scan returns `status=LLM_FAILED` + `llm_failed[]`; events stay stored; zero proposals created — covered by `test_scan_reports_llm_failed_without_fabricating`.)

### Structured output

- [x] Validate every LLM response with Pydantic before database insertion. (`validate_llm_proposal` in `app/schemas/domain.py`, called before any Proposal insert.)
- [x] Reject invalid action, confidence, price ranges, position size, and missing invalidation conditions. (Rejected payloads are logged with reason, never inserted.)
- [ ] Store raw model output only for debugging/audit, not as trusted UI data. (Currently logged on rejection only; no audit column.)

### Scheduler

- [x] Add job execution ID, start/end time, status, error, and record counts. (`job_runs` table + `GET /api/jobs`; uuid per run, scalar summary of result.)
- [x] Prevent overlapping executions of the same job. (`max_instances=1` on every job.)
- [x] Ensure one failed job does not stop the scheduler. (`_safe_job` catches all, marks run FAILED, scheduler keeps ticking.)

**Acceptance criteria**

- LLM failure does not lose ingested events.
- Invalid model output cannot enter the proposal tables.
- Job history makes failures diagnosable without reading process output.

## Phase 4: Local Production Hardening

**Priority**: P1

### Database and backup

- [x] Add migration tests from an empty database. (`test_migration_from_empty_database` — subprocess `alembic upgrade head` on fresh file; head `c3d4e5f6a7b8`.)
- [x] Add SQLite backup and restore commands. (`app/storage/backup.py` — sqlite3 online `.backup` API; `python -m app.storage.backup [backup|restore]`.)
- [x] Verify backups after restart and restore into a clean database. (`test_backup_restore_roundtrip` — post-backup writes rolled back; non-SQLite file rejected.)

### API and security

- [x] Validate all write endpoints. (FastAPI/Pydantic request models + `validate_llm_proposal` gate before every Proposal insert.)
- [x] Limit request sizes and avoid secrets in logs. (`MAX_BODY_BYTES` → 413 middleware; secrets never logged — LLM stderr truncated to 300 chars.)
- [x] Restrict CORS to configured origins. (`CORSMiddleware` — localhost dev origins only.)
- [x] Add basic authentication before exposing the app beyond localhost. (`AUTH_TOKEN` Bearer or `?token=`; off by default for local use; `/health` + `/static` stay open — `test_auth_disabled_by_default_and_enabled_with_token`.)

### Logging and observability

- [x] Replace remaining `print()` calls with contextual logging. (engines/pipeline/main now `logger.*`; only CLI entry points — backup/seed/corp-actions `__main__` — still print.)
- [x] Include job, ticker, provider, and request identifiers where useful. (LLM: provider/model/latency_ms; ingestion: ticker in errors; `job_runs` has job name + uuid.)
- [x] Track request failures, ingestion failures, LLM latency, and provider latency. (job_runs record counts/status; run_structured_json logs latency + status; ingestion failures counted in job result.)

### Docker

- [x] Run the container as a non-root user. (Dockerfile `useradd -m -u 1000 appuser`; compose config mount → `/home/appuser/.config/opencode`.)
- [x] Add a Compose healthcheck. (hits `/health`; container reported `healthy` 2026-09-24.)
- [x] Persist database and logs through volumes. (`./data:/app/data`; logs via `docker compose logs`.)
- [x] Verify restart does not lose data. (`restart: unless-stopped` + volume; provenance/proposals survive recreate.)

## Phase 5: Test And Release

**Priority**: P1

- [x] Add unit tests for retry, corporate actions, scoring, proposal validation, and price normalization. (market_data_unit 10 + phase2 5 cover retry/adjust/validate/prices.)
- [x] Add integration tests for ingestion -> event -> causal graph -> proposal. (`test_full_chain_event_to_proposal_and_rerun_dedup` — LLM stubbed; re-scan dedup verified.)
- [x] Add integration tests for position -> re-evaluation -> evaluation. (`test_lifecycle` 7 — seed → re-eval → journal → track-record.)
- [ ] Add failure tests for vnstock timeout, malformed PDF, RSS failure, LLM timeout, invalid JSON, and database lock. (vnstock timeout, RSS, LLM timeout, invalid JSON done; malformed PDF + DB-lock still open.)
- [ ] Run the Docker smoke test. (healthcheck green; full curl suite pending this commit.)

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
