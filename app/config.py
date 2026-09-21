import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///data/invest.db"
    
    # OpenCode
    OPENCODE_BIN: str = "opencode"
    OPENCODE_DEFAULT_MODEL: str = "opencode/big-pickle"
    OPENCODE_FREE_MODELS: list[str] = ["opencode/big-pickle", "opencode/mimo-v2.5-free", "opencode/nemotron-3-ultra-free"]
    
    # vnstock
    VNSTOCK_RATE_LIMIT: int = 60  # requests per minute
    
    # Paths
    DATA_DIR: Path = Path("data")
    FUND_PDF_DIR: Path = Path("data/fund_pdfs")
    EXPORT_DIR: Path = Path("data/exports")
    
    # Scheduler
    INGESTION_INTERVAL_MINUTES: int = 60
    REEVALUATION_INTERVAL_MINUTES: int = 120
    
    # Fund sources
    FUND_SOURCES: dict = {
        "VEIL": {
            "name": "Vietnam Enterprise Investments Limited",
            "manager": "Dragon Capital",
            "factsheet_url": "https://cdn.dragoncapital.com/media/2026/09/16111336/VEIL_Factsheet_202608.pdf",
            "base_url": "https://www.dragoncapital.com/individual/funds/veil/",
            "type": "closed_end",
        },
        "VESAF": {
            "name": "VinaCapital Strategic Growth Equity Fund",
            "manager": "VinaCapital",
            "factsheet_url": "https://vinacapital.com/wp-content/uploads/2026/09/20260915-VINACAPITAL-VESAF_Monthly-Factsheet_Aug-2026-EN.pdf",
            "base_url": "https://vinacapital.com/investment-solutions/onshore-funds/vesaf/",
            "type": "open_end",
        },
        "VCBF-BCF": {
            "name": "Quỹ đầu tư cổ phiếu hàng đầu VCBF",
            "manager": "VCBF",
            "factsheet_url": "https://www.vcbf.com/images/2026/b_ng_th_ng_tin_qu_u_t_c_phi_u_h_ng_u_vcbf_-_th_ng_082026.pdf",
            "base_url": "https://www.vcbf.com/don-tai-lieu-quy/ban-thong-tin-quy/",
            "type": "open_end",
        },
        "PYN": {
            "name": "PYN Elite Fund",
            "manager": "PYN Fund Management",
            "factsheet_url": "https://www.pyn.fi/en/pyn-elite-fund/portfolio/",
            "base_url": "https://www.pyn.fi/en/pyn-elite-fund/",
            "type": "specialized",
        },
    }
    
    # News sources (RSS)
    NEWS_SOURCES: dict = {
        "cafef": "https://cafef.vn/rss/thi-truong-chung-khoan.rss",
        "vtc": "https://vtc.vn/rss/kinh-te.rss",
        "vnexpress_kinhdoanh": "https://vnexpress.net/rss/kinh-doanh.rss",
        "dautu": "https://dautu.vn/rss/kinh-te.rss",
        "bizlive": "https://bizlive.vn/rss/co-phieu.rss",
    }
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(exist_ok=True)
settings.FUND_PDF_DIR.mkdir(exist_ok=True)
settings.EXPORT_DIR.mkdir(exist_ok=True)