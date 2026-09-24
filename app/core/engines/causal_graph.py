"""Sector/supply-chain mapping for auto-generating causal links from events.

Link contract (stored in Event.causal_links JSON):
    {target_ticker, direction: POSITIVE|NEGATIVE|MIXED, confidence: 0-100,
     mechanism, classification: FACT|INFERENCE|FORECAST,
     source_event_id, timestamp, source: causal_graph|llm}
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

VALID_CLASSIFICATIONS = {"FACT", "INFERENCE", "FORECAST", "COMPUTED"}

# Sector → tickers mapping (HOSE-listed, top holdings)
SECTOR_TICKERS = {
    "steel": ["HPG"],
    "banking": ["VCB", "CTG", "MBB", "TCB", "ACB", "BID", "VPB", "STB", "VIB", "OCB", "HDB", "TPB"],
    "real_estate": ["VIC", "VHM", "HDG"],
    "technology": ["FPT", "CMG"],
    "retail": ["MWG"],
    "airlines": ["HVN"],
    "airports": ["ACV"],
    "securities": ["VCI", "SHS", "TCX", "VIX", "DNSE"],
    "consumer": ["MSN", "DBC"],
    "industrials": ["CTR", "VEA"],
    "insurance": ["BVH"],
    "telecom": ["CMG"],
}

# Commodity/event patterns → sector impact
EVENT_PATTERNS = {
    "thep": {"sector": "steel", "direction": "POSITIVE", "mechanism": "Giá thép tăng -> doanh thu/biên gộp cải thiện"},
    "steel": {"sector": "steel", "direction": "POSITIVE", "mechanism": "Steel price up -> revenue/margin improvement"},
    "hrc": {"sector": "steel", "direction": "POSITIVE", "mechanism": "HRC price up -> HPG revenue uplift"},
    "quặng sắt": {"sector": "steel", "direction": "NEGATIVE", "mechanism": "Iron ore price up -> input cost increase for steel producers"},
    "lãi suất": {"sector": "banking", "direction": "MIXED", "mechanism": "Interest rate change -> NIM impact on banks"},
    "interest rate": {"sector": "banking", "direction": "MIXED", "mechanism": "Interest rate change -> NIM impact"},
    "bất động sản": {"sector": "real_estate", "direction": "POSITIVE", "mechanism": "BĐS phục hồi -> doanh thu bán hàng"},
    "real estate": {"sector": "real_estate", "direction": "POSITIVE", "mechanism": "Real estate recovery -> sales uplift"},
    "hàng không": {"sector": "airlines", "direction": "POSITIVE", "mechanism": "Air traffic up -> HVN revenue"},
    "aviation": {"sector": "airlines", "direction": "POSITIVE", "mechanism": "Air traffic growth -> airline revenue"},
    "bán lẻ": {"sector": "retail", "direction": "POSITIVE", "mechanism": "Retail sales up -> MWG revenue"},
    "retail": {"sector": "retail", "direction": "POSITIVE", "mechanism": "Consumer spending up -> retail revenue"},
    "AI": {"sector": "technology", "direction": "POSITIVE", "mechanism": "AI demand -> FPT tech revenue growth"},
    "chứng khoán": {"sector": "securities", "direction": "POSITIVE", "mechanism": "Market activity up -> broker revenue"},
    "FTSE": {"sector": "banking", "direction": "POSITIVE", "mechanism": "FTSE upgrade -> foreign inflow to VN, especially banks"},
}


def enrich_link(link: Dict[str, Any], event_id: Optional[str] = None,
                occurred_at: Optional[datetime] = None,
                source: str = "llm") -> Dict[str, Any]:
    """Fill contract fields on a causal link (idempotent; never overwrites valid values)."""
    out = dict(link)
    cls = str(out.get("classification") or "").upper()
    out["classification"] = cls if cls in VALID_CLASSIFICATIONS else "INFERENCE"
    out.setdefault("direction", "MIXED")
    out.setdefault("confidence", 50)
    out.setdefault("mechanism", "")
    out["source_event_id"] = out.get("source_event_id") or event_id
    if not out.get("timestamp"):
        out["timestamp"] = (occurred_at or datetime.now(timezone.utc)).isoformat()
    out["source"] = out.get("source") or source
    return out


def infer_causal_links(headline: str, summary: str, tickers: List[str],
                       event_id: Optional[str] = None,
                       occurred_at: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Auto-generate causal links from event headline/summary based on sector mapping."""
    text = f"{headline} {summary}".lower()
    links = []

    for pattern, info in EVENT_PATTERNS.items():
        if pattern.lower() in text:
            sector = info["sector"]
            affected_tickers = SECTOR_TICKERS.get(sector, [])
            # Only include tickers that are in the watched universe
            for ticker in affected_tickers:
                if ticker in tickers:
                    links.append(enrich_link({
                        "target_ticker": ticker,
                        "direction": info["direction"],
                        "confidence": 70,  # Base confidence for auto-generated
                        "mechanism": info["mechanism"],
                        "classification": "INFERENCE",
                        "source": "causal_graph",
                    }, event_id=event_id, occurred_at=occurred_at, source="causal_graph"))

    return links
