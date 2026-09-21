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

## Current Seed Data
- **Funds**: VEIL, VESAF, VCBF-BCF, PYN
- **Holdings**: Tháng 8/2026 (VEIL 10, VESAF 10, VCBF-BCF 5)
- **Securities**: 15 tickers (HPG, MWG, CTG, MBB, VCB, FPT, TCB, ACB, VIC, VHM, BID, VPB, MSN, CTR, BVH)
- **Events**: 2 (steel price ↑ → HPG positive, BHX profitable → MWG positive)
- **Proposals**: HPG v3 (BUY), MWG v1 (BUY)
- **Position**: HPG 2000 shares @ 27,500

## Test Suite
```bash
python -m tests.test_lifecycle
# Tests: seed → API → proposal revision → position transaction → events → track record
# All pass
```

## Known Gaps (Priority Order)
1. **Valuation engine**: Mock price → real DCF/comps/residual income
2. **Fundamentals normalization**: vnstock ratios duplicate quarters, unit mapping
3. **Corporate actions**: Split/dividend/rights price adjustment
4. **Historical holdings**: Need ≥3 snapshots/fund for trend detection
5. **Causal graph**: Manual links → sector/supply-chain knowledge graph
6. **LLM benchmark**: Vietnamese eval set (extraction/causal/valuation)
7. **Docker**: Dockerfile + compose.yml for one-shot deploy
8. **Legal**: Disclaimer, data license audit (vnstock, RSS, PDF sources)

## Immediate Next Steps (If Continuing)
1. Hook vnstock fundamental vào Opportunity Engine (replace mock price)
2. Run evaluation job on seeded proposals → populate track record
3. Add PYN Elite (verify PDF snapshot parsing)
4. Dockerize: `Dockerfile` + `docker-compose.yml`

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