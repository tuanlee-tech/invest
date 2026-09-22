import hashlib
import io
import json
import re
import logging
from datetime import datetime, timezone, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
from pypdf import PdfReader
import feedparser

from app.config import settings
from app.core.models.schema import get_db, Fund, FundHoldingSnapshot, Security, Event
from app.core.models.schema import SessionLocal

logger = logging.getLogger(__name__)


class FundHoldingParser:
    """Parse fund holdings from PDF factsheets and HTML pages"""

    def __init__(self):
        self.fund_patterns = {
            "VESAF": self._parse_vesaf,
            "VCBF-BCF": self._parse_vcbf_bcf,
            "VEIL": self._parse_veil,
            "PYN": self._parse_pyn_html,
        }

    def parse(self, fund_id: str, pdf_path: Path, raw_text: str) -> List[Dict[str, Any]]:
        parser = self.fund_patterns.get(fund_id)
        if parser:
            return parser(raw_text)
        return []

    def parse_html(self, fund_id: str, html: str) -> List[Dict[str, Any]]:
        """Parse holdings from HTML content (used for PYN)"""
        parser = self.fund_patterns.get(fund_id)
        if parser:
            return parser(html)
        return []

    def _parse_vesaf(self, text: str) -> List[Dict[str, Any]]:
        """Parse VESAF top holdings from factsheet"""
        holdings = []
        # Pattern: TICKER Sector % of NAV
        lines = text.split('\n')
        in_holdings = False
        for line in lines:
            if 'Top 10 Holdings' in line or 'Ticker Sector % of NAV' in line:
                in_holdings = True
                continue
            if in_holdings and 'TOTAL' in line:
                break
            if in_holdings:
                # Match: BVH Non-bank Financials 7.0
                match = re.match(r'^([A-Z]{3})\s+(.+?)\s+(\d+\.\d+)$', line.strip())
                if match:
                    ticker, sector, weight = match.groups()
                    holdings.append({
                        "ticker": ticker,
                        "sector": sector.strip(),
                        "weight_pct": float(weight),
                        "rank": len(holdings) + 1,
                    })
        return holdings

    def _parse_vcbf_bcf(self, text: str) -> List[Dict[str, Any]]:
        """Parse VCBF-BCF top 5 holdings"""
        holdings = []
        lines = text.split('\n')
        in_top5 = False
        for line in lines:
            if '5 MÃ CHỨNG KHOÁN CÓ GIÁ TRỊ CAO NHẤT' in line:
                in_top5 = True
                continue
            if in_top5 and 'Tổng' in line:
                break
            if in_top5:
                match = re.match(r'^([A-Z]{3})\s+(\d+[,.]\d+)$', line.strip())
                if match:
                    ticker, weight = match.groups()
                    weight = float(weight.replace(',', '.'))
                    holdings.append({
                        "ticker": ticker,
                        "weight_pct": weight,
                        "sector": "Unknown",
                        "rank": len(holdings) + 1,
                    })
        return holdings

    def _parse_veil(self, text: str) -> List[Dict[str, Any]]:
        """Parse VEIL top 10 holdings"""
        holdings = []
        # VEIL uses company names, need mapping
        name_to_ticker = {
            "Vingroup": "VIC", "Mobile World": "MWG", "BIDV": "BID",
            "Vietcombank": "VCB", "VP Bank": "VPB", "Vinhomes": "VHM",
            "Techcombank": "TCB", "Vietinbank": "CTG", "Hoa Phat Group": "HPG",
            "Asia Com. Bank": "ACB",
        }

        lines = text.split('\n')
        for line in lines:
            for name, ticker in name_to_ticker.items():
                if line.startswith(name + " "):
                    match = re.search(r' (\d+\.\d+) \$', line)
                    if match:
                        weight = float(match.group(1))
                        holdings.append({
                            "ticker": ticker,
                            "weight_pct": weight,
                            "sector": "Mapped from company name",
                            "rank": len(holdings) + 1,
                        })
        return holdings

    def _parse_pyn_html(self, html: str) -> List[Dict[str, Any]]:
        """Parse PYN Elite portfolio from HTML page.
        Looks for 'Portfolio weight XX.X%' patterns with nearby tickers."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        name_to_ticker = {
            "Sacombank": "STB", "Hoa Phat Group": "HPG",
            "Vietnam Airlines": "HVN", "Airports of Vietnam": "ACV",
            "Techcom Securities": "TCX", "Hado Group": "HDG",
            "Vietinbank": "CTG", "Vietcap": "VCI",
        }

        holdings = []
        text = soup.get_text()

        # Split text into blocks around "Portfolio weight"
        blocks = re.split(r'(Portfolio weight)', text, flags=re.IGNORECASE)
        seen = set()

        for i, block in enumerate(blocks):
            if block.strip().lower() != 'portfolio weight':
                continue
            # Weight is in the next block
            weight_match = re.search(r'(\d+\.?\d*)%', blocks[i + 1] if i + 1 < len(blocks) else '')
            if not weight_match:
                continue
            weight = float(weight_match.group(1))

            # Look backwards in previous block for ticker
            prev = blocks[i - 1] if i > 0 else ''
            # Try "TICKER - Name" pattern
            ticker_match = re.search(r'([A-Z]{2,4})\s*[-–]', prev[-200:])
            if ticker_match:
                raw_ticker = ticker_match.group(1)
            else:
                # Try standalone 2-4 letter ticker at end of previous block
                ticker_match = re.search(r'\b([A-Z]{2,4})\b\s*$', prev[-100:].strip())
                raw_ticker = ticker_match.group(1) if ticker_match else None

            if not raw_ticker:
                continue

            resolved = name_to_ticker.get(raw_ticker, raw_ticker)
            if resolved in seen or weight <= 0:
                continue
            seen.add(resolved)
            holdings.append({
                "ticker": resolved,
                "sector": "PYN Portfolio",
                "weight_pct": weight,
                "rank": len(holdings) + 1,
            })

        return holdings


class NewsEventIngester:
    """Ingest events from RSS feeds"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VN-Investment-Intelligence/1.0 (+local)'
        })

    def fetch_rss(self, url: str, source_name: str) -> List[Dict[str, Any]]:
        """Parse RSS feed and return list of event dicts"""
        try:
            feed = feedparser.parse(url)
            events = []
            for entry in feed.entries[:20]:  # Limit to 20 latest
                event = self._parse_entry(entry, source_name)
                if event:
                    events.append(event)
            return events
        except Exception as e:
            print(f"Error fetching RSS {url}: {e}")
            return []

    def _parse_entry(self, entry, source_name: str) -> Optional[Dict[str, Any]]:
        # Generate deterministic ID from URL
        event_id = hashlib.sha256(entry.link.encode()).hexdigest()[:32]

        # Parse published date
        occurred_at = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            occurred_at = datetime(*entry.published_parsed[:6])
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            occurred_at = datetime(*entry.updated_parsed[:6])
        else:
            occurred_at = datetime.now(timezone.utc)

        # Extract summary
        summary = entry.get('summary', '')
        # Clean HTML tags
        summary = re.sub(r'<[^>]+>', '', summary)[:500]

        return {
            "id": event_id,
            "occurred_at": occurred_at,
            "source_type": "news",
            "source_url": entry.link,
            "source_name": source_name,
            "headline": entry.title,
            "summary": summary,
            "raw_text": entry.get('description', '')[:2000],
            "classification": "FACT",
            "entities": [],  # Will be enriched by LLM
            "causal_links": [],
        }


class MarketDataIngester:
    """Ingest market data via vnstock"""

    def __init__(self):
        from vnstock.api.quote import Quote
        self.Quote = Quote

    def fetch_ohlcv(self, ticker: str, start: date, end: date) -> List[Dict]:
        """Fetch OHLCV data for a ticker"""
        try:
            q = self.Quote(symbol=ticker, source='VCI')
            df = q.history(
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d'),
            )
            return df.to_dict('records') if not df.empty else []
        except Exception as e:
            print(f"Error fetching OHLCV for {ticker}: {e}")
            return []

    def fetch_fundamentals(self, ticker: str) -> Dict:
        """Fetch financial statements and ratios"""
        try:
            from vnstock.api.fundamental import Fundamental
            f = Fundamental(symbol=ticker, source='VCI')
            income = f.income_statement(period='year')
            ratios = f.ratio()
            return {
                "income_statement": income.to_dict('records') if not income.empty else [],
                "ratios": ratios.to_dict('records') if not ratios.empty else [],
            }
        except Exception as e:
            print(f"Error fetching fundamentals for {ticker}: {e}")
            return {"income_statement": [], "ratios": []}


class IngestionPipeline:
    """Main ingestion orchestration"""

    def __init__(self):
        self.fund_parser = FundHoldingParser()
        self.news_ingester = NewsEventIngester()
        self.market_ingester = MarketDataIngester()
        self.db = SessionLocal()

    def run_fund_ingestion(self) -> Dict[str, int]:
        """Download and parse latest fund factsheets"""
        results = {"downloaded": 0, "parsed": 0, "new_snapshots": 0, "errors": 0}

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }

        for fund_id, fund_config in settings.FUND_SOURCES.items():
            try:
                url = fund_config["factsheet_url"]
                logger.info(f"Downloading {fund_id} from {url}")

                response = requests.get(url, headers=headers, timeout=60)
                if response.status_code != 200:
                    logger.warning(f"  Failed: HTTP {response.status_code}")
                    results["errors"] += 1
                    continue

                raw_content = response.content
                content_type = response.headers.get('Content-Type', '')
                is_pdf = raw_content.startswith(b'%PDF-') or 'pdf' in content_type
                is_html = 'html' in content_type or (not is_pdf and len(raw_content) > 1000)

                source_hash = hashlib.sha256(raw_content).hexdigest()
                raw_text = ""

                if is_pdf:
                    # Save PDF
                    pdf_path = settings.FUND_PDF_DIR / f"{fund_id}_{date.today().isoformat()}.pdf"
                    pdf_path.write_bytes(raw_content)
                    reader = PdfReader(io.BytesIO(raw_content))
                    raw_text = "\n".join(f"--- PAGE {i} ---\n{p.extract_text() or ''}"
                                         for i, p in enumerate(reader.pages, 1))
                    holdings = self.fund_parser.parse(fund_id, pdf_path, raw_text)
                elif is_html:
                    raw_text = raw_content.decode('utf-8', errors='replace')
                    holdings = self.fund_parser.parse_html(fund_id, raw_text)
                else:
                    logger.warning(f"  Unknown content type")
                    results["errors"] += 1
                    continue
                if not holdings:
                    logger.warning(f"  No holdings parsed")
                    results["errors"] += 1
                    continue

                # Get as_of_date from filename or use today
                as_of = date.today()

                # Check if already exists
                existing = self.db.query(FundHoldingSnapshot).filter(
                    FundHoldingSnapshot.fund_id == fund_id,
                    FundHoldingSnapshot.as_of_date == as_of
                ).first()

                if not existing:
                    snapshot = FundHoldingSnapshot(
                        fund_id=fund_id,
                        as_of_date=as_of,
                        source_url=url,
                        source_hash=source_hash,
                        raw_text=raw_text[:10000],
                        holdings_json=holdings
                    )
                    self.db.add(snapshot)
                    self.db.commit()
                    results["new_snapshots"] += 1
                    logger.info(f"  Saved {len(holdings)} holdings for {fund_id} as of {as_of}")
                else:
                    logger.info(f"  Snapshot already exists for {as_of}")

                results["downloaded"] += 1
                results["parsed"] += 1

            except Exception as e:
                print(f"Error processing {fund_id}: {e}")
                results["errors"] += 1

        return results

    def run_news_ingestion(self) -> Dict[str, int]:
        """Fetch news from RSS feeds"""
        results = {"fetched": 0, "new_events": 0, "errors": 0}

        for source_name, url in settings.NEWS_SOURCES.items():
            try:
                events = self.news_ingester.fetch_rss(url, source_name)
                for evt in events:
                    # Check if exists
                    existing = self.db.query(Event).filter(Event.id == evt["id"]).first()
                    if not existing:
                        event = Event(**evt)
                        self.db.add(event)
                        results["new_events"] += 1
                results["fetched"] += len(events)
            except Exception as e:
                logger.error(f"Error fetching {source_name}: {e}")
                results["errors"] += 1

        if results["new_events"] > 0:
            self.db.commit()

        return results

    def update_fund_universe(self) -> int:
        """Update securities table with fund holdings"""
        count = 0
        snapshots = self.db.query(FundHoldingSnapshot).order_by(
            FundHoldingSnapshot.retrieved_at.desc()
        ).limit(20).all()

        tickers_seen = set()
        for snap in snapshots:
            for h in snap.holdings_json:
                ticker = h.get("ticker")
                if ticker and ticker not in tickers_seen:
                    tickers_seen.add(ticker)
                    sec = self.db.query(Security).filter(Security.ticker == ticker).first()
                    if not sec:
                        sec = Security(
                            ticker=ticker,
                            name=ticker,
                            exchange="HOSE",  # Default, should enrich later
                            sector=h.get("sector", "Unknown"),
                            in_fund_universe=True
                        )
                        self.db.add(sec)
                    else:
                        sec.in_fund_universe = True
                        sec.sector = h.get("sector", sec.sector)
                    count += 1

        self.db.commit()
        return count

    def run_full_cycle(self) -> Dict[str, Any]:
        """Run complete ingestion cycle"""
        logger.info(f"=== Ingestion Cycle Started at {datetime.now(timezone.utc)} ===")
        results = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "fund_ingestion": self.run_fund_ingestion(),
            "news_ingestion": self.run_news_ingestion(),
            "universe_updated": self.update_fund_universe(),
        }
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"=== Ingestion Cycle Completed ===")
        return results

    def close(self):
        self.db.close()


# For scheduler integration
def run_ingestion_job():
    pipeline = IngestionPipeline()
    try:
        return pipeline.run_full_cycle()
    finally:
        pipeline.close()
