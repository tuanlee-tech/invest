import hashlib
import io
import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
from pypdf import PdfReader
import feedparser

from app.config import settings
from app.core.models.schema import get_db, Fund, FundHoldingSnapshot, Security, Event
from app.core.models.schema import SessionLocal


class FundHoldingParser:
    """Parse fund holdings from PDF factsheets"""
    
    def __init__(self):
        self.fund_patterns = {
            "VESAF": self._parse_vesaf,
            "VCBF-BCF": self._parse_vcbf_bcf,
            "VEIL": self._parse_veil,
        }
    
    def parse(self, fund_id: str, pdf_path: Path, raw_text: str) -> List[Dict[str, Any]]:
        parser = self.fund_patterns.get(fund_id)
        if parser:
            return parser(raw_text)
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
            occurred_at = datetime.utcnow()
        
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
        from vnstock import Market, Fundamental
        self.market = Market()
        self.fundamental = Fundamental()
    
    def fetch_ohlcv(self, ticker: str, start: date, end: date) -> List[Dict]:
        """Fetch OHLCV data for a ticker"""
        try:
            df = self.market.equity(ticker).ohlcv(
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d'),
                count=400  # Get enough for 1+ year
            )
            return df.to_dict('records')
        except Exception as e:
            print(f"Error fetching OHLCV for {ticker}: {e}")
            return []
    
    def fetch_fundamentals(self, ticker: str) -> Dict:
        """Fetch financial statements and ratios"""
        try:
            income = self.fundamental.equity(ticker).income_statement(period='year')
            ratios = self.fundamental.equity(ticker).ratio()
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
        
        for fund_id, fund_config in settings.FUND_SOURCES.items():
            try:
                url = fund_config["factsheet_url"]
                print(f"Downloading {fund_id} from {url}")
                
                response = requests.get(url, timeout=60)
                if response.status_code != 200:
                    print(f"  Failed: HTTP {response.status_code}")
                    results["errors"] += 1
                    continue
                
                raw_content = response.content
                if not raw_content.startswith(b'%PDF-'):
                    print(f"  Not a PDF")
                    results["errors"] += 1
                    continue
                
                # Save PDF
                source_hash = hashlib.sha256(raw_content).hexdigest()
                pdf_path = settings.FUND_PDF_DIR / f"{fund_id}_{date.today().isoformat()}.pdf"
                pdf_path.write_bytes(raw_content)
                
                # Extract text
                reader = PdfReader(io.BytesIO(raw_content))
                text = "\n".join(f"--- PAGE {i} ---\n{p.extract_text() or ''}" 
                                 for i, p in enumerate(reader.pages, 1))
                
                # Parse holdings
                holdings = self.fund_parser.parse(fund_id, pdf_path, text)
                if not holdings:
                    print(f"  No holdings parsed")
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
                        raw_text=text,
                        holdings_json=holdings
                    )
                    self.db.add(snapshot)
                    self.db.commit()
                    results["new_snapshots"] += 1
                    print(f"  Saved {len(holdings)} holdings for {fund_id} as of {as_of}")
                else:
                    print(f"  Snapshot already exists for {as_of}")
                
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
                print(f"Error fetching {source_name}: {e}")
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
        print(f"\n=== Ingestion Cycle Started at {datetime.utcnow()} ===")
        results = {
            "started_at": datetime.utcnow().isoformat(),
            "fund_ingestion": self.run_fund_ingestion(),
            "news_ingestion": self.run_news_ingestion(),
            "universe_updated": self.update_fund_universe(),
        }
        results["completed_at"] = datetime.utcnow().isoformat()
        print(f"=== Ingestion Cycle Completed ===")
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