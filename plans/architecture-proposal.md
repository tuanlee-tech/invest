# Architecture Proposal — VN Investment Intelligence (Fund-First Scope)

**Status**: MVP implemented. Core engines, web UI, real vnstock pricing, Docker — all working.
**Last updated**: 2026-09-22

## 1. System Overview

**Goal**: Local-first web app that tracks fund holdings (VEIL, VESAF, VCBF-BCF, PYN Elite), ingests market/news events, produces versioned investment proposals with evidence, manages portfolio positions, and evaluates outcomes.

**Core Constraints (from CONSTRAINTS.md)**:
- C1: Vietnam-first (HOSE/HNX/UPCoM)
- C2: Free baseline end-to-end
- C3: Local web UI on localhost
- C4: Cross-platform (Windows/macOS/Ubuntu)
- C5: Model-agnostic provider boundary
- C6: Harness-agnostic (OpenCode preferred, not required)
- C7: Evidence-first (provenance for every recommendation)
- C8: Point-in-time discipline
- C9: Versioned decisions (no overwrite)
- C10: Dynamic targets/stops/horizons
- C11: Deterministic finance where possible
- C12: No auto live trading V1
- C13: Reuse-first (REUSE/ADAPT/BUILD matrix)
- C14: Replaceable data providers

## 2. Logical Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        WEB UI (FastAPI + HTMX)                  │
│  Shortlist | Stock Detail | Portfolio | Events | Track Record  │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Opportunity │  │  Portfolio  │  │ Evaluation  │              │
│  │   Engine    │  │   Engine    │  │   Engine    │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
└─────────┼────────────────┼────────────────┼──────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DOMAIN CORE                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Decision   │  │  Evidence   │  │  Causal     │              │
│  │  Contract   │  │  Store      │  │  Graph      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  INGESTION      │ │  DATA PROVIDERS │ │  LLM PROVIDERS  │
│  PIPELINE       │ │  (Adapters)     │ │  (OpenCode)     │
│  - Fund holdings│ │  - vnstock      │ │  - big-pickle   │
│  - News/Events  │ │  - PDF sources  │ │  - mimo-v2.5    │
│  - Market data  │ │  - RSS/API      │ │  - local ollama │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## 3. Data Models (Domain Contracts)

### 3.1 Fund Holding Snapshot
```python
FundHolding:
  fund_id: str              # VEIL, VESAF, VCBF-BCF, PYN
  fund_name: str
  as_of_date: date          # Report date (chốt danh mục)
  retrieved_at: datetime    # When we fetched it
  source_url: str
  source_hash: str          # SHA-256 of PDF/HTML
  holdings: List[Holding]   # ticker, weight_pct, sector, market_cap, rank
  raw_text: str             # Full extracted text for audit
  parse_version: str        # Parser version used
```

### 3.2 Event / Evidence
```python
Event:
  event_id: str
  occurred_at: datetime
  source_type: str          # news, disclosure, filing, macro, corporate_action
  source_url: str
  source_hash: str
  headline: str
  summary: str
  raw_text: str
  entities: List[EntityRef] # tickers, sectors, commodities, policies
  causal_links: List[CausalLink]  # event → sector → ticker, with confidence
  classification: str       # FACT / COMPUTED / INFERENCE / FORECAST
  created_at: datetime
```

### 3.3 Investment Proposal (Versioned)
```python
Proposal:
  proposal_id: str          # FPT-2026-001
  ticker: str
  version: int              # 1, 2, 3...
  parent_version: int | None
  status: DRAFT | REVIEWED | ACTIVE | REVISED | EXECUTED | EXPIRED | INVALIDATED | CLOSED
  action: BUY | WATCH | AVOID | HOLD | ADD | REDUCE | EXIT
  entry_min: float
  entry_max: float
  target_min: float
  target_max: float
  stop_reference: float
  stop_method: str          # fixed_pct | trailing_atr | structure
  horizon_days: int
  valid_from: datetime
  valid_until: datetime
  confidence: float         # 0-100
  position_size_pct: float  # suggested % of portfolio

  thesis: str
  catalysts: List[str]
  risks: List[str]
  invalidation_conditions: List[InvalidationCondition]

  evidence_refs: List[str]  # event_ids
  data_snapshot_id: str     # point-in-time data bundle hash
  model_run_id: str         # model, prompt hash, output hash
  reasoning_summary: str

  created_at: datetime
  created_by: str           # engine, model, or user
  changed_from_previous: str # what changed and why
```

### 3.4 Portfolio Position
```python
Position:
  position_id: str
  ticker: str
  quantity: float
  avg_buy_price: float
  buy_date: date
  fees: float
  source_proposal_id: str | None
  current_recommendation: RecommendationRef
  recommendation_history: List[RecommendationRef]
  thesis_health: str        # HEALTHY | AT_RISK | INVALIDATED
  notes: str
```

### 3.5 Invalidation Condition (Structured)
```python
InvalidationCondition:
  condition_id: str
  description: str
  data_source: str          # e.g., "commodity_price:steel", "financial:margin"
  check_method: str         # threshold, trend, event
  threshold_value: float | None
  comparison: str           # >, <, crosses_above, crosses_below, pct_change
  lookback_days: int
  severity: CRITICAL | WARNING
  status: ACTIVE | TRIGGERED | EXPIRED
  last_checked: datetime
  last_value: float | None
```

## 4. Engine Responsibilities

### 4.1 Opportunity Engine
**Input**: Watchlist tickers (fund holdings + user watchlist + positions)
**Trigger**: New events, scheduled re-analysis, price/volume thresholds
**Process**:
1. Collect relevant events since last analysis
2. Run causal analysis to find affected tickers
3. For each affected ticker: fundamental + valuation + technical + risk
4. Bull/Bear debate (via OpenCode/LLM)
5. Synthesize into Proposal (versioned)
6. Score: opportunity_score = f(thesis_strength, valuation, catalysts, risks, confidence, liquidity)
**Output**: Ranked proposals with full evidence chain

### 4.2 Portfolio Engine
**Input**: User positions + current proposals + new events
**Trigger**: New event affecting held ticker, price threshold, earnings, proposal expiry, scheduled review
**Process**:
1. For each position: re-evaluate thesis health
2. Check invalidation conditions
3. Compare current price vs entry/target/stop
4. Run analysis with portfolio context (concentration, sector exposure, cash)
5. Generate revision or new recommendation: ADD | HOLD | REDUCE | EXIT
6. Version the recommendation, preserve history
**Output**: Portfolio actions with reasoning

### 4.3 Evaluation Engine
**Input**: Historical proposals + realized price paths
**Trigger**: Scheduled (daily), proposal expiry, position close
**Process**:
1. For each settled proposal: compute return, alpha, drawdown, MAE/MFE, time-to-target, hit/miss
2. Aggregate by signal type, horizon, market regime, confidence band
3. Calibration: predicted confidence vs realized hit rate
4. Update signal effectiveness metrics
**Output**: Track record dashboard, model calibration data, regime performance

## 5. Technology Stack

| Layer | Choice | Rationale | Status |
|-------|--------|-----------|--------|
| API/Web | FastAPI + HTMX + Tailwind | Local-first, minimal JS, server-rendered fragments, easy offline | ✅ |
| Database | SQLite (local file) + SQLAlchemy | Zero-config, portable, ACID, enough for single-user local | ✅ |
| ORM | SQLAlchemy 2.0 + Alembic | Type-safe, migrations, async support | ✅ |
| Scheduler | APScheduler | Cron + interval jobs, in-process | ✅ |
| Ingestion | Custom pipeline + vnstock | Vietnam data, replaceable adapters | ✅ |
| LLM | OpenCode CLI (subprocess) | Harness-agnostic, free models, local-first | ✅ |
| Validation | Pydantic v2 | Schema enforcement, serialization | ✅ |
| Charts | Chart.js (CDN) | Lightweight, works offline if cached | ✅ |

**Not used in V1**: Redis, Celery, Kafka, Kubernetes, vector DB, graph DB, cloud services.

## 6. Provider Adapters (Replaceable)

| Capability | Primary Adapter | Fallback | Status |
|------------|----------------|----------|--------|
| Fund holdings PDF | Custom PDF parser (pypdf) | Manual CSV import | ✅ DONE |
| Market data (OHLCV) | vnstock 4.0.8 Quote API | CSV import | ✅ DONE |
| Fundamentals | vnstock 4.0.8 Fundamental API | Manual import | ✅ DONE |
| News RSS (Vietnam) | feedparser | — | ✅ DONE |
| News RSS (Global) | feedparser | — | ✅ DONE |
| Corporate disclosures | SSC/HOSE/HNX RSS | Manual | TODO |
| Macro (VN) | GSO/SBV RSS/API | Manual | TODO |
| LLM | OpenCode (big-pickle, mimo-v2.5-free) | Ollama local | ✅ DONE |

## 7. Reuse/Adapt/Build Matrix

| Component | Source | Decision | Notes |
|-----------|--------|----------|-------|
| Multi-agent debate | TradingAgents | ADAPT | Use analyst roles, debate structure; replace data layer with vnstock |
| Backtesting | TradingAgents | ADAPT | Use point-in-time logic; wrap in our evaluation engine |
| Portfolio context | TradingAgents | ADAPT | Use portfolio-aware run concept |
| PDF parsing | pypdf | ✅ REUSE | Verified in feasibility, working in production |
| Market data | vnstock 4.0.8 | ✅ ADAPT | `vnstock.api.quote.Quote` — working with real pricing |
| UI framework | FastAPI+HTMX | ✅ BUILD | 6 views running, Tailwind+Chart.js CDN |
| Event extraction | LLM + patterns | ✅ BUILD | LLM-based causal analysis working |
| Causal graph | Custom | PARTIAL | Manual causal_links in SQLite; sector graph TODO |

## 8. Free Baseline Configuration

```
# Zero paid API required
LLM: OpenCode big-pickle (free) / mimo-v2.5-free (free) / local Ollama
Market data: vnstock guest mode (60 req/min, 4 periods financials)
Fund holdings: Public PDFs from fund websites
News: Public RSS feeds
Macro: Public GSO/SBV data
Database: Local SQLite file
UI: Local web server
Scheduler: In-process APScheduler
```

## 9. Cross-Platform Deployment

```bash
# Ubuntu/macOS
git clone git@github.com:tuanlee-tech/invest.git
cd invest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.storage.seed   # seed DB
python -m app.main            # http://localhost:8000

# Docker (one-shot)
docker compose up --build     # http://localhost:8000
```

## 10. Open Questions for Implementation

1. ~~**Fund holding parser**: Build generic table extractor or per-fund template?~~ → Per-fund templates (VESAF, VCBF-BCF, VEIL)
2. ~~**Event deduplication**: Hash-based + semantic similarity threshold?~~ → Hash-based (SHA256 of URL)
3. **Causal graph storage**: SQLite adjacency vs dedicated graph when needed?
4. ~~**LLM output validation**: Pydantic schema + retry loop vs structured output?~~ → Regex extraction from structured JSON
5. ~~**Checkpointing**: SQLite WAL mode for concurrent read/write?~~ → Single-user, not needed yet
6. **Portfolio import**: CSV schema for user positions?

---

*This proposal will be validated against CONSTRAINTS.md challenges before implementation.*