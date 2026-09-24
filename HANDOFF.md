# Handoff Document — VN Investment Intelligence (Fund-First MVP)

**Date**: 2026-09-24 (docs reconciled against `data/invest.db` + code)
**Status**: MVP running locally on Ubuntu, all endpoints 200 OK, real vnstock pricing

**Provenance legend** (used in every table below):
- **LIVE** — fetched at runtime from vnstock / fund PDF / RSS (not stored, or stored with source)
- **SEED** — hardcoded row from `app/storage/seed.py`, no provenance (`source_url`/`source_hash` are NULL)
- **MANUAL** — hand-entered outside any pipeline (trades, curated dicts, hand-written causal links)

---

## 1. What Works (Verified)

### Core Stack
- **FastAPI + SQLite** (SQLAlchemy 2.0) — localhost, single-file DB, zero-config
- **Background scheduler** (APScheduler): ingestion, opportunity scan, portfolio re-eval, evaluation
- **vnstock 4.0.8** (KBS source, guest mode) — market data adapter
- **OpenCode CLI** + free models (`big-pickle`, `mimo-v2.5-free`) — LLM inference

### Data Layer — actual DB counts + provenance (`data/invest.db`, checked 2026-09-24)

| Entity | Count (DB) | Provenance | Notes |
|--------|-----------|------------|-------|
| Funds | 6 (VEIL, VESAF, VCBF-BCF, PYN, SSI-SCA, DCDS) | SEED | Configured in `app/config.py` |
| Holdings snapshots | 13 total — VEIL/VESAF × 4, VCBF-BCF × 3, PYN × 1 (live), SSI-SCA/DCDS × 1 each (sample) | SEED/LIVE, **13/13 provenance populated** | `source_url`/`source_hash`/`reporting_period`/`effective_date` never NULL; live ingestion adds real URL+sha256; re-ingest never overwrites `(fund_id, as_of_date)` |
| Securities master | 17 tickers | SEED | |
| Events | 4 (steel, retail, FPT-AI, CTG-capital) | SEED + MANUAL causal links | Live RSS path (`run_news_ingestion`) works: last run fetched 20, 0 new |
| Proposals | 4: FPT/CTG = `EXPIRED` (evaluated), HPG/MWG = `ACTIVE` (valid_until 2027) | SEED + LIVE evaluation | Evaluation job flips `ACTIVE → EXPIRED` past `valid_until` |
| Positions | 3: HPG open 2000 @ 27,500; FPT + CTG CLOSED | MANUAL | Closed prices/PnL hand-set in seed, not market-verified |
| Transactions | 0 | — | Position edits go through API, none recorded |
| Proposal evaluations | 2 (FPT, CTG) | LIVE-derived | Computed from live vnstock returns, then persisted |
| Prices / OHLCV / fundamentals | not persisted (60s price / 300s history TTL cache) | LIVE | `GET /api/prices`, evaluation, valuation hit vnstock on demand (`vnstock_retry` = transient-only) |
| Corporate actions | in-code dict, 8 tickers, documented manual format | MANUAL | split/rights/bonus `ratio`, dividend `amount`; windowed to `(start, end]` in return calcs; incomplete records skipped |
| Watchlist | 0 | — | Table + API exist, empty |

### Engines (Runnable via API)
- **Ingestion**: `POST /api/jobs/ingestion` — downloads fund PDFs + RSS. Live parsers: VEIL, VESAF, PYN ✓; VCBF-BCF fails visibly (`parser produced 0 rows`); SSI-SCA/DCDS listed in `not_implemented` (no free source, no fabrication). Job result includes `failures`, `not_implemented`, per-fund `normalization` (duplicates + allocation).
- **Opportunity Scan**: `POST /api/jobs/opportunity-scan` — event → causal → proposal
- **Portfolio Re-eval**: `POST /api/jobs/portfolio-reeval` — position review → ADD/HOLD/REDUCE/EXIT
- **Evaluation**: `POST /api/jobs/evaluation` — point-in-time outcome scoring (2 rows so far)

### Proposal Contract (Enforced)
```python
Proposal:  # example shape; current DB rows are all version=1 (HPG-2026-001-v1 etc.)
  id: "HPG-2026-001-v3"
  action: BUY | WATCH | AVOID | HOLD | ADD | REDUCE | EXIT
  entry_min/max, target_min/max, stop_reference, stop_method
  horizon_days, confidence, position_size_suggestion
  thesis, catalysts[], risks[], invalidation_conditions[]
  evidence_refs[]  # event_ids + fund snapshot IDs
  changed_from_previous: str  # required for revisions
```
**Versioning**: v1 → v2 → v3... original preserved as `REVISED`, new row `ACTIVE`.

### Web UI (FastAPI + HTMX + Tailwind + Chart.js)
| Route | Status |
|-------|--------|
| `/` Dashboard | ✅ |
| `/ui/shortlist` | ✅ |
| `/ui/portfolio` | ✅ |
| `/ui/events` | ✅ |
| `/ui/track-record` | ✅ |
| `/ui/settings` | ✅ |

---

## 2. How to Run

```bash
cd invest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # optional, free baseline works without keys
python -m app.storage.seed  # seed DB
python -m app.main        # http://localhost:8000
```

**requirements.txt** (pinned):
```
fastapi==0.141.1
uvicorn==0.53.0
sqlalchemy==2.0.54
alembic==1.20.0
pydantic==2.13.5
pydantic-settings==2.15.0
python-multipart==0.0.32
httpx==0.28.1
feedparser==6.0.14
pypdf==6.19.0
vnstock==4.0.8
apscheduler==3.11.3
python-dotenv==1.2.3
jinja2==3.1.6
markdown2==2.5.5
requests>=2.31.0
```

**Free baseline**: No API keys required. OpenCode uses `big-pickle` (free). vnstock guest mode: 60 req/min, 4 financial periods.

---

## 3. Key Files Structure

```
invest/
├── app/
│   ├── main.py                 # FastAPI app, templates, scheduler
│   ├── config.py               # Settings, fund sources, RSS feeds
│   ├── scheduler.py            # APScheduler jobs
│   ├── api/routes.py           # All REST endpoints
│   ├── core/
│   │   ├── models/schema.py    # SQLAlchemy models + SessionLocal
│   │   └── engines/
│   │       ├── market_data.py      # vnstock wrapper (OHLCV, price, drawdown)
│   │       ├── fundamentals.py     # vnstock fundamentals normalization
│   │       ├── causal_graph.py     # Sector→ticker causal mapping
│   │       ├── opportunity_engine.py
│   │       ├── portfolio_engine.py
│   │       └── evaluation_engine.py
│   ├── ingestion/
│   │   └── pipeline/main.py    # Fund PDF + HTML ingestion
│   ├── llm/
│   │   ├── client.py           # OpenCodeClient wrapper
│   │   └── prompts.py          # Versioned prompt templates (v1.0)
│   ├── storage/seed.py         # Sample data loader
│   ├── templates/              # Jinja2 (sync rendering)
│   └── schemas/domain.py       # Pydantic request models
├── tests/test_lifecycle.py     # Integration tests (5 tests, all pass)
├── data/invest.db              # SQLite (auto-created)
├── research/                   # Feasibility reports
├── plans/architecture-proposal.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── DISCLAIMER.md
├── .env.example
└── HANDOFF.md
```

---

## 4. Known Gaps (verified against code/DB 2026-09-24)

| Area | Status | Priority |
|------|--------|----------|
| **Valuation** | ✅ Real vnstock pricing + fundamentals | Done |
| **Fundamentals** | ✅ Normalized (dedup quarters, VND→billions) in `fundamentals.py` | Done |
| **Historical holdings** | ✅ 13 snapshots, all with provenance; PYN live-parsed; SSI-SCA/DCDS sample rows + explicit not-implemented parsers | Done |
| **Provenance** | ✅ `source_url`/`source_hash`/`reporting_period`/`effective_date` on 13/13 rows; backfill only fills NULLs | Done |
| **Causal graph** | ✅ Auto-generated from sector mapping; seeded event links are MANUAL | Done |
| **Prompts** | ✅ Versioned templates (v1.0) | Done |
| **Track record** | ✅ FPT, CTG evaluated + flipped `EXPIRED`; HPG, MWG not yet settled (2027) | Done |
| **Proposal status** | ✅ Evaluation job auto-flips `ACTIVE → EXPIRED` past `valid_until` | Done |
| **Market data** | ✅ 60s/300s TTL cache; transient-only retry; `MarketDataError` → HTTP 502 | Done |
| **Corporate actions** | ✅ Documented manual format; split/rights/bonus `ratio` + dividend `amount`; windowed adjustments; unit tests | Done (source still MANUAL/unverified) |
| **`GET /health`** | ✅ DB + vnstock + LLM probes; 503 with per-dependency errors | Done |
| **Docker** | ✅ Dockerfile + docker-compose.yml (runs as root, no healthcheck) | Partial |
| **Legal** | ✅ DISCLAIMER.md + `/api/disclaimer` | Done |
| **Tests** | ✅ 26 tests (lifecycle 7, ingestion 4, market-data/corp-actions 10, phase2 5) | Done |
| **Causal graph** | ✅ Link contract: classification/mechanism/direction/confidence/source_event_id/timestamp; merged LLM + graph relevance | Done |
| **Proposal dedup** | ✅ One ACTIVE proposal per ticker; `proposals_skipped` in scan result | Done |
| **LLM output gate** | ✅ `validate_llm_proposal` rejects bad action/confidence/prices/size/missing invalidation before insert | Done |
| **Invalidation (deterministic)** | ✅ Price-based conditions checked in code; CRITICAL → force `INVALIDATED`+`EXIT`; financial-series conditions still LLM-judged | Done (financial checks pending persisted series) |
| **Local LLM** | ⚠️ Ollama fallback routing implemented in `client.py`; Ollama not installed/tested | Low |
| **Config/secrets** | No secret rotation | Low |

---

## 5. Immediate Next Steps (Owner: Next Agent)

1. ~~**Real valuation data** — hook vnstock fundamental vào Opportunity Engine~~ ✅ Done
2. ~~**Dockerize** — `Dockerfile` + `docker-compose.yml`~~ ✅ Done
3. ~~**Track record with real data** — run evaluation job~~ ✅ Done (FPT, CTG; HPG/MWG not settled yet)
4. ~~**VNStock fundamental normalization**~~ ✅ Done (`fundamentals.py`)
5. ~~**PYN/SSI-SCA/DCDS snapshots + provenance + `GET /health` + auto-expire**~~ ✅ Done (see Phase 0/1 in roadmap)
6. ~~**PYN/SSI-SCA/DCDS snapshots + provenance + `GET /health` + auto-expire**~~ ✅ Done (Phase 0/1)
7. ~~**Phase 2 core** — causal-graph contract, proposal dedup, LLM output validation, deterministic price invalidation**~~ ✅ Done
8. **Next (roadmap Phase 2/3 còn lại)** — material-change auto-versioning, decision history journal, `entry_hit`/`target_hit`/`stop_hit` + track-record slicing, scheduler job history, LLM latency logging, `LLM_FAILED` persistence

---

## 6. Architecture Decisions (Locked)

| Decision | Rationale |
|----------|-----------|
| SQLite + SQLAlchemy | Zero-config, portable, ACID, enough for single-user local |
| Sync Jinja2 rendering | Async causes `unhashable type: dict` cache bug in Jinja2/Starlette |
| OpenCode CLI (subprocess) | Harness-agnostic, free models, no SDK dependency |
| Versioned proposals (immutable) | Audit trail, point-in-time evaluation, no overwrite |
| Invalidation conditions structured | Machine-checkable thesis health, not just narrative |
| Fund-first universe | User requirement: "chỉ copy quỹ đã research" |
| Free baseline mandatory | No paid API in golden path |
| vnstock 4.0.8 Quote API | New API (`vnstock.api.quote.Quote`), replaces deprecated `Vnstock().stock()` |

---

## 7. Test Evidence

```bash
# Run all tests (26 total)
cd invest
.venv/bin/python -m tests.test_lifecycle         # 7 passed
.venv/bin/python -m tests.test_ingestion         # 4 passed
.venv/bin/python -m tests.test_market_data_unit  # 10 passed (no network)
.venv/bin/python -m tests.test_phase2            # 5 passed (no network)

# Manual smoke test
.venv/bin/alembic upgrade head
.venv/bin/python -m app.storage.seed
.venv/bin/python -m app.main
# → http://localhost:8000/health 200 (503 + per-dep errors if vnstock/LLM down)
# → /api/prices?tickers=HPG,MWG 200; invalid symbol → 502 MarketDataError
```

---

## 8. Contact / Context

- **User requirement**: "Web localhost, OpenCode + free providers, theo dõi quỹ lớn, hold >1 năm, early insight từ tin tức"
- **Philosophy**: Evidence-first, deterministic finance, point-in-time, no auto-trade V1
- **Constraints**: Vietnam-first, free baseline, cross-platform, harness-agnostic

---

*End of handoff. System ready for incremental hardening.*