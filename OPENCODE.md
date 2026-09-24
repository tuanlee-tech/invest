# VN Investment Intelligence — Project Context for AI Assistant

## Project Identity
**VN Investment Intelligence** — Fund-first investment decision support for Vietnam market.
Local-first, free-baseline, evidence-based, point-in-time disciplined.

## Quick Start (Ubuntu)
```bash
git clone git@github.com:tuanlee-tech/invest.git
cd invest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.storage.seed
python -m app.main
# Open http://localhost:8000
```

## Core Philosophy
- **Fund-first**: Chỉ theo dõi cổ phiếu trong danh mục quỹ lớn (VEIL, VESAF, VCBF-BCF, PYN)
- **Evidence-first**: Mọi recommendation phải có evidence_refs, invalidation conditions, versioned history
- **Free baseline**: Chạy được không API key (OpenCode big-pickle, vnstock guest)
- **Point-in-time**: Không look-ahead bias, evaluation strict
- **Versioned decisions**: Proposal v1→v2→v3... không overwrite, audit trail đầy đủ
- **No auto-trade V1**: Advisory only, human-in-the-loop

## Architecture Overview
```
FastAPI + SQLite (SQLAlchemy 2.0)
├── Ingestion Pipeline    → Fund PDF (pypdf) + RSS feeds
├── Opportunity Engine    → Event → Causal → LLM Proposal
├── Portfolio Engine      → Position re-eval → ADD/HOLD/REDUCE/EXIT
├── Evaluation Engine     → Point-in-time outcome scoring
├── LLM Client            → OpenCode CLI (free models)
├── Background Scheduler  → APScheduler (ingestion/scan/reeval/eval)
└── Web UI                → HTMX + Tailwind + Chart.js
```

## Key Data Models (SQLAlchemy)
- **Fund** / **FundHoldingSnapshot** (PDF parsed, versioned by as_of_date)
- **Security** (master ticker list from fund universes)
- **Event** (RSS + causal_links: target_ticker, direction, confidence, mechanism)
- **Proposal** (versioned, immutable, evidence_refs, invalidation_conditions[])
- **Position** / **Transaction** (user portfolio, thesis_health tracking)
- **ProposalEvaluation** (point-in-time outcome, calibration metrics)

## API Endpoints (All Tested 200 OK)
```
GET  /api/funds, /api/funds/{id}/holdings
GET  /api/events, /api/proposals, /api/positions, /api/evaluations
POST /api/proposals/{id}/revise
POST /api/positions, /api/positions/{id}/transact
POST /api/jobs/ingestion | opportunity-scan | portfolio-reeval | evaluation
GET  /ui/{dashboard|shortlist|portfolio|events|track-record|settings}
```

## LLM Integration (Free Tier)
- **OpenCode CLI** subprocess with `--pure -m opencode/big-pickle`
- Fallback: `mimo-v2.5-free`, `nemotron-3-ultra-free`
- Structured JSON output via strict prompt + regex extraction
- Tasks: event causal analysis, proposal generation, portfolio re-eval

## Web UI Stack
- **FastAPI** + **Jinja2** (sync rendering, cache_size=0 to avoid unhashable dict bug)
- **HTMX** for partial updates, **Tailwind CSS** (CDN), **Chart.js** (CDN)
- Views: Dashboard, Shortlist, Portfolio, Events, Track Record, Settings
- Proposal detail modal with revision history, evidence links

## Current Data (counts + provenance, verified 2026-09-24)
Legend: **LIVE** = fetched at runtime (vnstock/PDF/RSS); **SEED** = hardcoded `app/storage/seed.py`; **MANUAL** = hand-entered.

| Record | Actual state | Provenance |
|--------|--------------|------------|
| Funds | 6: VEIL, VESAF, VCBF-BCF, PYN, SSI-SCA, DCDS | SEED |
| Holdings snapshots | 9 = VEIL/VESAF/VCBF-BCF × {Jul, Aug, Sep 2026}; `source_url`/`source_hash` NULL | SEED |
| PYN / SSI-SCA / DCDS snapshots | **0 rows** (PYN parser exists but seed never inserts; no SSI-SCA/DCDS parser) | — |
| Securities | 17 tickers (… + GAS, NVL) | SEED |
| Events | 4 (steel→HPG, retail→MWG, FPT-AI, CTG-capital) | SEED + MANUAL causal links |
| Proposals | 4, all `version=1` `ACTIVE`: HPG-v1, MWG-v1, FPT-v1, CTG-v1. **No HPG v3 in DB** | SEED (`model_run_id=NULL`) |
| Positions | 3: HPG open 2000 @ 27,500; FPT + CTG CLOSED (hand-set prices/PnL) | MANUAL |
| Transactions | 0 | — |
| Proposal evaluations | 2 (FPT +54.2%, CTG +37.4%) computed from vnstock, persisted | LIVE-derived |
| Prices / OHLCV / fundamentals | not persisted; hit vnstock on demand | LIVE |
| Corporate actions | in-code dict, 8 tickers, split-only; dividends no-op | MANUAL |

## Test Suite
```bash
python -m tests.test_lifecycle
# Tests: seed → API → proposal revision → position transaction → events → track record
# All pass
```

## Known Gaps (verified against code/DB 2026-09-24)
1. **Provenance**: `source_url`/`source_hash` columns exist but NULL on all 9 snapshots — nothing is marked LIVE vs SEED (roadmap Phase 0/1).
2. **Holdings coverage**: only 3 funds have snapshots (seeded). PYN = 0 rows despite parser; SSI-SCA/DCDS = no parser.
3. **`GET /health`**: endpoint does not exist yet.
4. **Proposal status**: expired FPT/CTG still `ACTIVE`; no auto-expire.
5. **Corporate actions**: module exists (`corporate_actions.py`) but MANUAL dict, split-only, dividend adjust is a no-op, unverified.
6. **Track record**: only 2/4 proposals evaluated (FPT, CTG); HPG/MWG pending.
7. **LLM benchmark**: Vietnamese eval set (extraction/causal/valuation) — not started.
8. **Prices not persisted**: every valuation/evaluation call hits vnstock live (rate-limit exposure; retries exist, no cache).

Done since earlier version of this list: real valuation via vnstock, fundamentals normalization, 3-month historical snapshots, auto causal graph, Dockerfile+compose, DISCLAIMER/`/api/disclaimer`.

## Immediate Next Steps (If Continuing)
1. Add `GET /health` + persist snapshot provenance + mark/flip expired proposals (roadmap Phase 0/1).
2. Insert or ingest PYN snapshot; add SSI-SCA/DCDS parsers or mark them manual-format.
3. Run evaluation for HPG + MWG → full track record.
4. Docker hardening: non-root user, healthcheck (roadmap Phase 4).

## Key Files to Read
- `HANDOFF.md` — Complete project summary
- `plans/architecture-proposal.md` — Technical design decisions
- `research/fund-following-feasibility.md` — Evidence from feasibility probes
- `tests/test_lifecycle.py` — Integration test flow
- `app/main.py` — App entry point, template config, routes
- `app/core/engines/*.py` — Three engines implementation

## Ubuntu-Specific Notes
- Use `python3 -m venv .venv` (not `python`)
- `source .venv/bin/activate` (not `.venv\Scripts\activate`)
- OpenCode binary: ensure `opencode` in PATH (`npm install -g @opencode/opencode` or download binary)
- vnstock works on Linux (tested)
- Chart.js/Tailwind via CDN — no build step needed

## Commands Cheat Sheet
```bash
# Run server
python -m app.main

# Seed DB
python -m app.storage.seed

# Run tests
python -m tests.test_lifecycle

# Manual job triggers (via curl or UI)
curl -X POST http://localhost:8000/api/jobs/ingestion
curl -X POST http://localhost:8000/api/jobs/opportunity-scan
curl -X POST http://localhost:8000/api/jobs/portfolio-reeval
curl -X POST http://localhost:8000/api/jobs/evaluation
```

---

**This file is the complete context. Read HANDOFF.md first for full project summary.**