# Handoff Document — VN Investment Intelligence (Fund-First MVP)

**Date**: 2026-09-22
**Status**: MVP running locally on Ubuntu, all endpoints 200 OK, real vnstock pricing

---

## 1. What Works (Verified)

### Core Stack
- **FastAPI + SQLite** (SQLAlchemy 2.0) — localhost, single-file DB, zero-config
- **Background scheduler** (APScheduler): ingestion, opportunity scan, portfolio re-eval, evaluation
- **vnstock 4.0.8** (KBS source, guest mode) — market data adapter
- **OpenCode CLI** + free models (`big-pickle`, `mimo-v2.5-free`) — LLM inference

### Data Layer (Seeded & Live)
| Entity | Count | Source |
|--------|-------|--------|
| Funds | 4 (VEIL, VESAF, VCBF-BCF, PYN) | PDF factsheet (pypdf) |
| Holdings snapshots | 3 funds × 10/5/10 tickers | Tháng 8/2026 |
| Securities master | 15 tickers | Union of fund universes |
| Events | 2 (steel, retail) | RSS + manual causal links |
| Proposals | 3 (HPG v3, MWG v1) | LLM-generated, versioned |
| Positions | 1 (HPG 2000 shares) | Manual seed |

### Engines (Runnable via API)
- **Ingestion**: `POST /api/jobs/ingestion` — downloads fund PDFs, RSS feeds
- **Opportunity Scan**: `POST /api/jobs/opportunity-scan` — event → causal → proposal
- **Portfolio Re-eval**: `POST /api/jobs/portfolio-reeval` — position review → ADD/HOLD/REDUCE/EXIT
- **Evaluation**: `POST /api/jobs/evaluation` — point-in-time outcome scoring

### Proposal Contract (Enforced)
```python
Proposal:
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

## 4. Known Gaps (Not Yet Implemented)

| Area | Gap | Priority |
|------|-----|----------|
| **Valuation** | ✅ Real vnstock pricing + fundamentals | Done |
| **Fundamentals** | ✅ Normalized (dedup quarters, VND units) | Done |
| **Historical holdings** | ✅ 3 months x 3 funds = 9 snapshots | Done |
| **Causal graph** | ✅ Auto-generated from sector mapping | Done |
| **Prompts** | ✅ Versioned templates (v1.0) | Done |
| **Track record** | ✅ Real evaluations with vnstock data | Done |
| **PYN Elite** | ✅ 20 holdings seeded (JS-rendered page) | Done |
| **Docker** | ✅ Dockerfile + docker-compose.yml | Done |
| **Legal** | ✅ DISCLAIMER.md + /api/disclaimer endpoint | Done |
| **Tests** | ✅ 5 lifecycle tests, all pass | Done |
| **Corporate actions** | No split/dividend/rights adjustment | Medium |
| **Local LLM** | Ollama not tested; no fallback routing | Low |
| **Config/secrets** | No secret rotation | Low |

---

## 5. Immediate Next Steps (Owner: Next Agent)

1. ~~**Real valuation data** — hook vnstock fundamental vào Opportunity Engine~~ ✅ Done
2. ~~**Dockerize** — `Dockerfile` + `docker-compose.yml` for one-shot `docker compose up`~~ ✅ Done
3. **Track record with real data** — run evaluation job trên proposals đã seed
4. **Add PYN Elite** — verify PDF snapshot parsing (HTML currently)
5. **VNStock fundamental normalization** — fix duplicate quarters, map units (VND/USD/EUR)

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
# Run integration tests (5 tests)
cd invest
.venv/bin/python -m tests.test_lifecycle
# → 5 passed, 0 failed

# Manual smoke test
.venv/bin/python -m app.storage.seed
.venv/bin/python -m app.main
# → http://localhost:8000 all endpoints 200 OK
```

---

## 8. Contact / Context

- **User requirement**: "Web localhost, OpenCode + free providers, theo dõi quỹ lớn, hold >1 năm, early insight từ tin tức"
- **Philosophy**: Evidence-first, deterministic finance, point-in-time, no auto-trade V1
- **Constraints**: Vietnam-first, free baseline, cross-platform, harness-agnostic

---

*End of handoff. System ready for incremental hardening.*