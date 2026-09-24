"""VNStock fundamentals normalization — dedup quarters, standardize units."""
import logging
from typing import Dict, Any, Optional
from datetime import date

logger = logging.getLogger(__name__)


def get_fundamentals(ticker: str) -> Dict[str, Any]:
    """Fetch and normalize fundamentals for a ticker. Returns latest quarter data."""
    try:
        from vnstock import Fundamental
        f = Fundamental()

        result = {"ticker": ticker, "income": {}, "ratios": {}}

        # Income statement (has recent data, 4 periods)
        try:
            inc = f.equity(ticker).income_statement(period='quarter')
            if not inc.empty:
                # Take latest quarter (first data column after item columns)
                data_cols = [c for c in inc.columns if c not in ('item', 'item_en', 'item_id')]
                if data_cols:
                    latest_col = data_cols[0]
                    for _, row in inc.iterrows():
                        key = row.get('item_en', row.get('item', ''))
                        val = row.get(latest_col)
                        if key and val is not None:
                            # Convert raw VND to billions
                            try:
                                val = float(val)
                                if abs(val) > 1e6:
                                    val = round(val / 1e9, 1)  # to billions VND
                            except (ValueError, TypeError):
                                pass
                            result["income"][key] = val
                    result["income"]["quarter"] = latest_col
        except Exception as e:
            logger.error("fundamentals income error for %s: %s", ticker, e)

        # Ratios — only extract the latest value per metric
        try:
            ratios = f.equity(ticker).ratio()
            if not ratios.empty:
                data_cols = [c for c in ratios.columns if c not in ('item', 'item_en', 'item_id')]
                if data_cols:
                    latest_col = data_cols[-1]  # last quarter available
                    key_ratios = ['pe_ratio', 'pb_ratio', 'ps_ratio', 'roe', 'roa',
                                  'dividend_yield', 'outstanding_shares', 'market_cap']
                    for _, row in ratios.iterrows():
                        item_id = row.get('item_id', '')
                        if item_id in key_ratios:
                            val = row.get(latest_col)
                            try:
                                result["ratios"][item_id] = float(val)
                            except (ValueError, TypeError):
                                pass
        except Exception as e:
            logger.error("fundamentals ratio error for %s: %s", ticker, e)

        return result
    except Exception as e:
        logger.error("fundamentals fetch error for %s: %s", ticker, e)
        return {"ticker": ticker, "income": {}, "ratios": {}}


def normalize_income(raw_income: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize income statement to standard English keys with VND billions."""
    mapping = {
        "Net sales": "revenue",
        "Cost of sales": "cogs",
        "Gross Profit": "gross_profit",
        "Selling expenses": "selling_expense",
        "General and admin expenses": "admin_expense",
        "Financial expenses": "finance_expense",
        "Interest expenses": "interest_expense",
        "Operating profit/(loss)": "operating_profit",
        "Net accounting profit/(loss) before tax": "pretax_profit",
        "Net profit/(loss) after tax": "net_profit",
    }
    result = {}
    for vn_key, en_key in mapping.items():
        if vn_key in raw_income:
            result[en_key] = raw_income[vn_key]
    # Calculate margin if possible
    rev = result.get("revenue", 0)
    gp = result.get("gross_profit", 0)
    np_ = result.get("net_profit", 0)
    if rev and rev > 0:
        result["gross_margin_pct"] = round(gp / rev * 100, 1) if gp else None
        result["net_margin_pct"] = round(np_ / rev * 100, 1) if np_ else None
    result["quarter"] = raw_income.get("quarter", "unknown")
    return result
