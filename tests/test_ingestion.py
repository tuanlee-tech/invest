"""Ingestion tests — provenance backfill, duplicates, allocation, no-overwrite.

Runs against a temp SQLite DB (DATABASE_URL set before app imports), not data/invest.db.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Temp DB must be configured before any app import binds the engine
_TMP_DIR = tempfile.mkdtemp(prefix="invest_ingestion_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test_ingestion.db"

from datetime import date, datetime, timezone  # noqa: E402

from app.core.models.schema import init_db, SessionLocal, Fund, FundHoldingSnapshot  # noqa: E402
from app.storage.seed import (  # noqa: E402
    seed, backfill_snapshot_provenance, holdings_hash, SEED_SOURCE_URL,
)
from app.ingestion.pipeline.main import normalize_holdings, save_snapshot  # noqa: E402


def test_provenance_backfill():
    """Every seeded snapshot has truthful provenance; NULL provenance is backfilled."""
    init_db()
    seed()

    db = SessionLocal()
    try:
        rows = db.query(FundHoldingSnapshot).all()
        assert len(rows) >= 9, f"expected >=9 snapshots, got {len(rows)}"

        for row in rows:
            assert row.source_url, f"row {row.id} missing source_url"
            assert row.source_hash == holdings_hash(row.holdings_json), \
                f"row {row.id} source_hash mismatch"
            assert row.reporting_period == row.as_of_date.strftime("%Y-%m"), \
                f"row {row.id} reporting_period mismatch"
            assert row.effective_date == row.as_of_date, \
                f"row {row.id} effective_date mismatch"
            assert row.retrieved_at is not None, f"row {row.id} missing retrieved_at"

        # Simulate un-provenanced legacy row, then backfill (NULLs only)
        target = rows[0]
        holdings_before = holdings_hash(target.holdings_json)
        target.source_url = None
        target.source_hash = None
        target.reporting_period = None
        target.effective_date = None
        db.commit()

        updated = backfill_snapshot_provenance(db)
        assert updated >= 1, "backfill should update the nulled row"
        db.refresh(target)
        assert target.source_url == SEED_SOURCE_URL
        assert target.source_hash == holdings_before, "backfill must not change holdings"
        assert target.reporting_period == target.as_of_date.strftime("%Y-%m")
        assert target.effective_date == target.as_of_date
        # Idempotent: second run finds nothing to fix
        assert backfill_snapshot_provenance(db) == 0
    finally:
        db.close()


def test_duplicate_detection():
    """Duplicate tickers within one snapshot are detected after normalization."""
    holdings = [
        {"ticker": " hpg ", "weight_pct": "5%"},
        {"ticker": "HPG", "weight_pct": 5},
        {"ticker": "VCB", "weight_pct": "95,0%"},
    ]
    norm = normalize_holdings(holdings, snapshot_date=date(2026, 9, 15))

    assert norm["duplicates"] == ["HPG"], f"duplicates: {norm['duplicates']}"
    tickers = [h["ticker"] for h in norm["holdings"]]
    assert tickers == ["HPG", "HPG", "VCB"], f"tickers not normalized: {tickers}"
    assert norm["holdings"][0]["weight_pct"] == 5.0, "'5%' not parsed to float"
    assert norm["holdings"][2]["weight_pct"] == 95.0, "'95,0%' not parsed to float"
    assert all(h["currency"] == "VND" for h in norm["holdings"])
    assert all(h["snapshot_date"] == "2026-09-15" for h in norm["holdings"])

    no_dups = normalize_holdings([{"ticker": "HPG", "weight_pct": 10}])
    assert no_dups["duplicates"] == []


def test_allocation_validation():
    """Allocation total validated vs 100% (0.5% tolerance); cash reported separately."""
    ok = normalize_holdings([
        {"ticker": "HPG", "weight_pct": 40},
        {"ticker": "VCB", "weight_pct": 60},
    ])
    assert ok["allocation"]["within_tolerance"] is True, ok["allocation"]
    assert ok["allocation"]["total_pct"] == 100.0

    off = normalize_holdings([
        {"ticker": "HPG", "weight_pct": 30},
        {"ticker": "VCB", "weight_pct": 30},
    ])
    assert off["allocation"]["within_tolerance"] is False, off["allocation"]
    assert off["allocation"]["total_pct"] == 60.0

    with_cash = normalize_holdings([
        {"ticker": "HPG", "weight_pct": 60},
        {"ticker": "VCB", "weight_pct": 35},
        {"ticker": "CASH", "weight_pct": 5},
    ])
    assert with_cash["allocation"]["within_tolerance"] is True, with_cash["allocation"]
    assert with_cash["allocation"]["cash_pct"] == 5.0, with_cash["allocation"]
    assert with_cash["allocation"]["equities_pct"] == 95.0, with_cash["allocation"]

    # Borderline: |100.4 - 100| = 0.4 <= 0.5 passes; 100.6 fails
    borderline = normalize_holdings([
        {"ticker": "HPG", "weight_pct": 50.4},
        {"ticker": "VCB", "weight_pct": 50},
    ])
    assert borderline["allocation"]["within_tolerance"] is True, borderline["allocation"]
    just_over = normalize_holdings([
        {"ticker": "HPG", "weight_pct": 50.6},
        {"ticker": "VCB", "weight_pct": 50},
    ])
    assert just_over["allocation"]["within_tolerance"] is False, just_over["allocation"]


def test_no_overwrite_on_reingest():
    """Re-ingesting the same (fund, as_of) preserves the original point-in-time row."""
    init_db()
    db = SessionLocal()
    try:
        if not db.query(Fund).filter(Fund.id == "TESTF").first():
            db.add(Fund(id="TESTF", name="Test Fund", manager="Test"))
            db.commit()

        as_of = date(2026, 1, 31)
        original = [{"ticker": "HPG", "weight_pct": 10.0, "snapshot_date": "2026-01-31"}]
        created = save_snapshot(
            db, "TESTF", as_of, original,
            source_url="https://example.com/first", source_hash="hash-first",
        )
        assert created is True, "first insert should create"

        incoming = [{"ticker": "VCB", "weight_pct": 99.0, "snapshot_date": "2026-01-31"}]
        created_again = save_snapshot(
            db, "TESTF", as_of, incoming,
            source_url="https://example.com/second", source_hash="hash-second",
        )
        assert created_again is False, "second insert must be skipped, not overwrite"

        rows = db.query(FundHoldingSnapshot).filter(
            FundHoldingSnapshot.fund_id == "TESTF",
            FundHoldingSnapshot.as_of_date == as_of,
        ).all()
        assert len(rows) == 1, f"expected exactly 1 row, got {len(rows)}"
        assert rows[0].holdings_json == original, "original holdings were overwritten!"
        assert rows[0].source_hash == "hash-first", "original provenance was overwritten!"
        assert rows[0].source_url == "https://example.com/first"

        # A different period still inserts a new row
        created_other = save_snapshot(
            db, "TESTF", date(2026, 2, 28), incoming,
            source_url="https://example.com/feb", source_hash="hash-feb",
        )
        assert created_other is True, "different as_of_date must create a new snapshot"
    finally:
        db.close()


if __name__ == "__main__":
    tests = [test_provenance_backfill, test_duplicate_detection,
             test_allocation_validation, test_no_overwrite_on_reingest]
    passed = 0
    failed = 0
    for t in tests:
        try:
            print(f"Running {t.__name__}...", end=" ")
            t()
            print("PASS")
            passed += 1
        except Exception as e:
            print(f"FAIL: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
