"""Sector/supply-chain mapping for auto-generating causal links from events."""
from typing import List, Dict, Any

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


def infer_causal_links(headline: str, summary: str, tickers: List[str]) -> List[Dict[str, Any]]:
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
                    links.append({
                        "target_ticker": ticker,
                        "direction": info["direction"],
                        "confidence": 70,  # Base confidence for auto-generated
                        "mechanism": info["mechanism"],
                        "source": "causal_graph",  # Mark as auto-generated
                    })

    return links
