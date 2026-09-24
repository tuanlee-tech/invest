from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
import json
import logging
import uuid

from app.config import settings
from app.core.models.schema import get_db, FundHoldingSnapshot, Security, Event, Proposal, SessionLocal
from app.llm.client import OpenCodeClient

logger = logging.getLogger(__name__)


class OpportunityEngine:
    """Finds and scores new investment opportunities from fund universe and events"""

    def __init__(self):
        self.db = SessionLocal()
        self.llm = OpenCodeClient()

    def get_watchlist_tickers(self) -> List[str]:
        """Get all unique tickers from fund holdings + user watchlist"""
        tickers = set()

        # From latest fund snapshots
        snapshots = self.db.query(FundHoldingSnapshot).order_by(
            FundHoldingSnapshot.retrieved_at.desc()
        ).limit(10).all()

        for snap in snapshots:
            for h in snap.holdings_json:
                tickers.add(h.get("ticker", ""))

        # From user watchlist
        from app.core.models.schema import Watchlist
        watchlist = self.db.query(Watchlist).all()
        for w in watchlist:
            tickers.add(w.ticker)

        # From active positions
        from app.core.models.schema import Position
        positions = self.db.query(Position).filter(Position.status == "ACTIVE").all()
        for p in positions:
            tickers.add(p.ticker)

        return sorted([t for t in tickers if t])

    def get_recent_events(self, days: int = 7) -> List[Event]:
        """Get events since last check"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return self.db.query(Event).filter(
            Event.occurred_at >= cutoff
        ).order_by(Event.occurred_at.desc()).limit(50).all()

    def get_fund_holdings_for_ticker(self, ticker: str) -> List[Dict[str, Any]]:
        """Get fund holding info for a specific ticker"""
        holdings = []
        snapshots = self.db.query(FundHoldingSnapshot).order_by(
            FundHoldingSnapshot.retrieved_at.desc()
        ).limit(10).all()

        for snap in snapshots:
            for h in snap.holdings_json:
                if h.get("ticker") == ticker:
                    holdings.append({
                        "fund_id": snap.fund_id,
                        "as_of_date": snap.as_of_date.isoformat(),
                        "weight_pct": h.get("weight_pct"),
                        "rank": h.get("rank"),
                    })
        return holdings

    def get_market_data(self, ticker: str) -> Optional[Dict]:
        """Get latest price for ticker from vnstock"""
        from app.core.engines.market_data import get_latest_price, MarketDataError
        try:
            price = get_latest_price(ticker)
        except MarketDataError as e:
            logger.warning("Market data unavailable for %s: %s", ticker, e)
            return None
        return {"close": price} if price else None

    def run_opportunity_scan(self) -> Dict[str, Any]:
        """Full scan cycle: find events, analyze impact, generate proposals"""
        logger.info("Starting opportunity scan...")

        tickers = self.get_watchlist_tickers()
        logger.info(f"Watching {len(tickers)} tickers: {tickers}")

        events = self.get_recent_events(days=14)
        logger.info(f"Found {len(events)} recent events")

        if not events:
            return {"status": "no_new_events", "proposals_created": 0}

        # Analyze events for impact on watched tickers
        from app.core.engines.causal_graph import enrich_link, infer_causal_links

        relevant_events = []
        llm_failures = 0
        for event in events:
            # LLM analysis is best-effort: on failure the deterministic causal
            # graph still runs — one bad event must not kill the scan.
            llm_links: List[Dict[str, Any]] = []
            llm_entities: List[str] = []
            try:
                analysis = self.llm.analyze_event_impact(
                    event.headline,
                    event.summary or "",
                    tickers
                )
                if not isinstance(analysis, dict):
                    raise ValueError(f"analysis is not an object: {type(analysis).__name__}")
                classification = str(analysis.get("classification") or "FACT").upper()
                event.classification = classification if classification in (
                    "FACT", "INFERENCE", "FORECAST", "COMPUTED"
                ) else "FACT"
                llm_entities = analysis.get("entities") or []
                llm_links = [
                    enrich_link(c, event_id=event.id, occurred_at=event.occurred_at, source="llm")
                    for c in (analysis.get("causal_links") or [])
                    if isinstance(c, dict) and c.get("target_ticker")
                ]
            except Exception as e:
                llm_failures += 1
                logger.warning("LLM analysis failed for event %s: %s — using causal graph only",
                               event.id, e)

            # Deterministic sector-graph links, merged with LLM links
            auto_links = infer_causal_links(
                event.headline, event.summary or "", tickers,
                event_id=event.id, occurred_at=event.occurred_at,
            )
            merged = list(llm_links)
            seen = {c.get("target_ticker") for c in merged}
            for link in auto_links:
                if link["target_ticker"] not in seen:
                    merged.append(link)
            event.causal_links = merged

            # Relevance comes from the MERGED set (graph-only matches count too)
            affected = [c for c in merged if c.get("target_ticker") in tickers]
            if affected:
                event.entities = sorted(set(
                    list(llm_entities) + list(event.entities or []) +
                    [c["target_ticker"] for c in affected]
                ))
                relevant_events.append((event, affected))

        logger.info(f"{len(relevant_events)} events affect watched universe")

        # Group by ticker and generate proposals
        proposals_created = 0
        ticker_events = {}
        for event, links in relevant_events:
            for link in links:
                ticker = link.get("target_ticker")
                if ticker not in ticker_events:
                    ticker_events[ticker] = {"events": [], "links": []}
                ticker_events[ticker]["events"].append(event)
                ticker_events[ticker]["links"].append(link)

        # Generate proposal for each affected ticker
        proposals_created = 0
        proposals_skipped = 0
        llm_failed: List[Dict[str, str]] = []
        for ticker, data in ticker_events.items():
            try:
                proposal = self._generate_proposal_for_ticker(ticker, data)
                if proposal:
                    proposals_created += 1
                else:
                    proposals_skipped += 1
            except (RuntimeError, ValueError) as e:
                # All models failed / unparseable output — never invent a proposal.
                # The source events stay persisted; this run reports LLM_FAILED.
                llm_failed.append({"ticker": ticker, "error": str(e)[:300]})
                logger.error("LLM_FAILED proposal generation for %s: %s", ticker, e)
            except Exception as e:
                logger.error(f"Error generating proposal for {ticker}: {e}")

        # Commit event updates
        self.db.commit()

        status = "completed"
        if llm_failed and proposals_created == 0 and relevant_events:
            status = "LLM_FAILED"

        return {
            "status": status,
            "tickers_scanned": len(tickers),
            "events_analyzed": len(events),
            "relevant_events": len(relevant_events),
            "llm_failures": llm_failures,
            "llm_failed": llm_failed,
            "proposals_created": proposals_created,
            "proposals_skipped": proposals_skipped,
        }

    def _generate_proposal_for_ticker(self, ticker: str, data: Dict) -> Optional[Proposal]:
        """Generate or revise a proposal for a ticker.

        Material-change rule: a new version is created only when an event
        arrives whose id is NOT already in the ACTIVE proposal's evidence_refs.
        Same evidence re-scanned → skip (no duplicate, no new version).
        """
        active = self.db.query(Proposal).filter(
            Proposal.ticker == ticker,
            Proposal.status == "ACTIVE",
        ).order_by(Proposal.version.desc()).first()

        new_evidence: List[str] = []
        if active:
            known = set(active.evidence_refs or [])
            new_evidence = [e.id for e in data["events"] if e.id not in known]
            if not new_evidence:
                logger.info(
                    f"{ticker}: ACTIVE proposal {active.id} already covers all evidence, skipping"
                )
                return None
            logger.info(
                f"{ticker}: material change — {len(new_evidence)} new event(s), bumping version"
            )

        # Get data needed for proposal
        fund_holdings = self.get_fund_holdings_for_ticker(ticker)
        market_data = self.get_market_data(ticker)

        if not fund_holdings:
            logger.info(f"{ticker}: Not in fund universe, skipping")
            return None

        # Fetch real fundamentals
        from app.core.engines.fundamentals import get_fundamentals, normalize_income
        raw_fund = get_fundamentals(ticker)
        fundamentals = normalize_income(raw_fund.get("income", {}))
        fundamentals["ratios"] = raw_fund.get("ratios", {})

        # Build proposal using LLM
        proposal_data = self.llm.generate_proposal(
            ticker=ticker,
            current_price=market_data.get("close", 0) if market_data else 0,
            holdings_info=fund_holdings,
            recent_events=data["events"],
            fundamentals=fundamentals,
        )

        # Phase 3 gate: invalid model output must never enter the proposals table
        from app.schemas.domain import validate_llm_proposal
        try:
            proposal_data = validate_llm_proposal(proposal_data)
        except ValueError as e:
            logger.error("Rejected LLM proposal for %s: %s | payload=%s",
                         ticker, e, json.dumps(proposal_data, ensure_ascii=False, default=str)[:500])
            return None

        now = datetime.now(timezone.utc)
        if active:
            # Material change → new version inside the same group; old becomes REVISED
            new_version = active.version + 1
            group_id = active.proposal_group_id
            parent_version = active.version
            known = list(active.evidence_refs or [])
            seen = set(known)
            evidence_refs = list(known)
            for eid in [e.id for e in data["events"]]:
                if eid not in seen:
                    evidence_refs.append(eid)
                    seen.add(eid)
            changed_from = (
                f"Material change: {len(new_evidence)} new event(s) "
                f"({', '.join(new_evidence[:5])})"
            )
            active.status = "REVISED"
        else:
            new_version = 1
            group_id = f"{ticker}-{now.strftime('%Y')}-{str(uuid.uuid4())[:8]}"
            parent_version = None
            evidence_refs = [e.id for e in data["events"]]
            changed_from = "Initial proposal from opportunity scan"

        proposal = Proposal(
            id=f"{group_id}-v{new_version}",
            proposal_group_id=group_id,
            ticker=ticker,
            version=new_version,
            parent_version=parent_version,
            status="ACTIVE",
            action=proposal_data.get("action", "WATCH"),
            entry_min=proposal_data.get("entry_min"),
            entry_max=proposal_data.get("entry_max"),
            target_min=proposal_data.get("target_min"),
            target_max=proposal_data.get("target_max"),
            stop_reference=proposal_data.get("stop_reference"),
            stop_method=proposal_data.get("stop_method", "structural_support"),
            horizon_days=proposal_data.get("horizon_days", 365),
            valid_from=now,
            valid_until=now + timedelta(days=proposal_data.get("horizon_days", 365)),
            confidence=proposal_data.get("confidence", 50),
            position_size_suggestion=proposal_data.get("position_size_suggestion", 3.0),
            thesis=proposal_data.get("thesis", ""),
            catalysts=proposal_data.get("catalysts", []),
            risks=proposal_data.get("risks", []),
            invalidation_conditions=proposal_data.get("invalidation_conditions", []),
            evidence_refs=evidence_refs,
            reasoning_summary=proposal_data.get("reasoning_summary", ""),
            changed_from_previous=changed_from,
        )

        self.db.add(proposal)
        return proposal

    def close(self):
        self.db.close()


def run_opportunity_scan_job():
    engine = OpportunityEngine()
    try:
        return engine.run_opportunity_scan()
    finally:
        engine.close()
