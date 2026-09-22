from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
import json
import logging

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
        from app.core.engines.market_data import get_latest_price
        price = get_latest_price(ticker)
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
        relevant_events = []
        for event in events:
            analysis = self.llm.analyze_event_impact(
                event.headline,
                event.summary or "",
                tickers
            )

            # Update event with causal analysis
            event.classification = analysis.get("classification", "FACT")
            event.entities = analysis.get("entities", [])
            event.causal_links = analysis.get("causal_links", [])

            # Merge with auto-generated causal links from sector graph
            from app.core.engines.causal_graph import infer_causal_links
            auto_links = infer_causal_links(event.headline, event.summary or "", tickers)
            existing_targets = {c.get("target_ticker") for c in event.causal_links}
            for link in auto_links:
                if link["target_ticker"] not in existing_targets:
                    event.causal_links.append(link)

            # Check if any causal link affects watched tickers
            affected = [c for c in analysis.get("causal_links", [])
                       if c.get("target_ticker") in tickers]

            if affected:
                event.entities = list(set(event.entities + [c.get("target_ticker") for c in affected]))
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
        for ticker, data in ticker_events.items():
            try:
                proposal = self._generate_proposal_for_ticker(ticker, data)
                if proposal:
                    proposals_created += 1
            except Exception as e:
                logger.error(f"Error generating proposal for {ticker}: {e}")

        # Commit event updates
        self.db.commit()

        return {
            "status": "completed",
            "tickers_scanned": len(tickers),
            "events_analyzed": len(events),
            "relevant_events": len(relevant_events),
            "proposals_created": proposals_created,
        }

    def _generate_proposal_for_ticker(self, ticker: str, data: Dict) -> Optional[Proposal]:
        """Generate or update proposal for a ticker based on new info"""
        # Check if recent proposal exists (within 7 days)
        recent = self.db.query(Proposal).filter(
            Proposal.ticker == ticker,
            Proposal.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        ).order_by(Proposal.version.desc()).first()

        if recent and recent.status == "ACTIVE":
            logger.info(f"{ticker}: Already has ACTIVE proposal v{recent.version}, skipping")
            return None

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

        # Create proposal
        import uuid
        group_id = f"{ticker}-{datetime.now().strftime('%Y')}-{str(uuid.uuid4())[:8]}"
        proposal_id = f"{group_id}-v1"

        proposal = Proposal(
            id=proposal_id,
            proposal_group_id=group_id,
            ticker=ticker,
            version=1,
            status="ACTIVE",
            action=proposal_data.get("action", "WATCH"),
            entry_min=proposal_data.get("entry_min"),
            entry_max=proposal_data.get("entry_max"),
            target_min=proposal_data.get("target_min"),
            target_max=proposal_data.get("target_max"),
            stop_reference=proposal_data.get("stop_reference"),
            stop_method=proposal_data.get("stop_method", "structural_support"),
            horizon_days=proposal_data.get("horizon_days", 365),
            valid_from=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=proposal_data.get("horizon_days", 365)),
            confidence=proposal_data.get("confidence", 50),
            position_size_suggestion=proposal_data.get("position_size_suggestion", 3.0),
            thesis=proposal_data.get("thesis", ""),
            catalysts=proposal_data.get("catalysts", []),
            risks=proposal_data.get("risks", []),
            invalidation_conditions=proposal_data.get("invalidation_conditions", []),
            evidence_refs=[e.id for e in data["events"]],
            reasoning_summary=proposal_data.get("reasoning_summary", ""),
            changed_from_previous="Initial proposal from opportunity scan",
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
