"""Phase 4/5 tests — migration-from-empty, auth, body limit, backup/restore,
failure paths (RSS/LLM/vnstock), material-change versioning, full chain.

Temp DB; network only local connection-refused + short vnstock retry sleeps.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP_DIR = tempfile.mkdtemp(prefix="invest_phase4_test_")
_DB_URL = f"sqlite:///{_TMP_DIR}/test_phase4.db"
os.environ["DATABASE_URL"] = _DB_URL

from datetime import date, datetime, timezone  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.models.schema import (  # noqa: E402
    init_db, SessionLocal, Fund, FundHoldingSnapshot, Event, Proposal,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_migration_from_empty_database():
    """`alembic upgrade head` on a brand-new file creates the full schema."""
    mig_db = Path(_TMP_DIR) / "mig_empty.db"
    if mig_db.exists():
        mig_db.unlink()
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{mig_db}")
    proc = subprocess.run(
        [str(PROJECT_ROOT / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"alembic failed:\n{proc.stdout}\n{proc.stderr}"
    assert mig_db.exists(), "migration DB not created"

    import sqlite3
    conn = sqlite3.connect(str(mig_db))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for required in ("proposals", "events", "fund_holding_snapshots",
                         "position_decisions", "job_runs", "alembic_version"):
            assert required in tables, f"missing table {required}; have {sorted(tables)}"
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == "c3d4e5f6a7b8", version
    finally:
        conn.close()


def test_body_size_limit_returns_413():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    payload = b"x" * (settings.MAX_BODY_BYTES + 1)
    r = client.post("/api/proposals", content=payload,
                    headers={"content-type": "application/json"})
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"]


def test_auth_disabled_by_default_and_enabled_with_token():
    init_db()
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    assert settings.AUTH_TOKEN is None, "default must be open local use"
    assert client.get("/api/funds").status_code == 200
    assert client.get("/health").status_code in (200, 503)

    settings.AUTH_TOKEN = "secret-token-xyz"
    try:
        r = client.get("/api/funds")
        assert r.status_code == 401, r.status_code
        r = client.get("/api/funds", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401
        r = client.get("/api/funds", headers={"Authorization": "Bearer secret-token-xyz"})
        assert r.status_code == 200, r.text
        r = client.get("/api/funds", params={"token": "secret-token-xyz"})
        assert r.status_code == 200
        # /health stays open for the container healthcheck
        assert client.get("/health").status_code in (200, 503)
    finally:
        settings.AUTH_TOKEN = None


def test_backup_restore_roundtrip():
    from app.storage.backup import backup, restore
    init_db()
    db = SessionLocal()
    try:
        db.add(Fund(id="BK-A", name="Before Backup", manager="T"))
        db.commit()

        out = backup(str(Path(_TMP_DIR) / "roundtrip.db"))
        assert out.exists() and out.stat().st_size > 0

        db.add(Fund(id="BK-B", name="After Backup", manager="T"))
        db.commit()

        restore(str(out))

        db2 = SessionLocal()
        try:
            assert db2.query(Fund).filter(Fund.id == "BK-A").first() is not None
            assert db2.query(Fund).filter(Fund.id == "BK-B").first() is None, \
                "restore must roll back post-backup writes"
        finally:
            db2.close()
    finally:
        db.close()

    # Non-sqlite file rejected
    junk = Path(_TMP_DIR) / "not.db"
    junk.write_bytes(b"hello not a database")
    try:
        restore(str(junk))
        assert False, "must reject non-sqlite file"
    except RuntimeError as e:
        assert "not a SQLite file" in str(e)


def test_rss_failure_raises_for_ingestion_error_recording():
    from app.ingestion.pipeline.main import NewsEventIngester
    ing = NewsEventIngester()
    try:
        # Connection refused on localhost:1 → feedparser bozo, no entries
        ing.fetch_rss("http://127.0.0.1:1/nope", "test-source")
        assert False, "unreachable RSS must raise so the job records an error"
    except RuntimeError as e:
        assert "RSS parse failed" in str(e)
        assert "test-source" in str(e)


def test_llm_invalid_json_rejected():
    from app.llm.client import OpenCodeClient
    client = OpenCodeClient()
    client.run_prompt = lambda *a, **k: "xin chào, đây không phải JSON"
    try:
        client.run_structured_json("prompt")
        assert False, "non-JSON output must raise ValueError"
    except ValueError as e:
        assert "could not be parsed" in str(e)


def test_llm_timeout_all_models_fail():
    import app.llm.client as client_mod
    from app.llm.client import OpenCodeClient
    client = OpenCodeClient()
    original = client_mod.subprocess.run

    def _timeout(*a, **k):
        raise client_mod.subprocess.TimeoutExpired(cmd="opencode", timeout=1)

    client_mod.subprocess.run = _timeout
    try:
        client.run_prompt("prompt", timeout=1)
        assert False, "must raise when every model times out"
    except RuntimeError as e:
        assert "All models failed" in str(e)
    finally:
        client_mod.subprocess.run = original


def test_vnstock_timeout_wraps_to_market_data_error():
    """Transient vnstock timeouts retry then surface as MarketDataError."""
    import vnstock.api.quote as quote_mod
    from app.core.engines import market_data
    from app.core.engines.market_data import MarketDataError, get_latest_price

    class _BoomQuote:
        def __init__(self, symbol, source=None):
            pass

        def history(self, start, end):
            raise TimeoutError("read timed out")

    original = quote_mod.Quote
    quote_mod.Quote = _BoomQuote
    market_data._CACHE.clear()
    try:
        get_latest_price("HPG")
        assert False, "exhausted retries must raise MarketDataError"
    except MarketDataError as e:
        assert "timed out" in str(e)
    finally:
        quote_mod.Quote = original
        market_data._CACHE.clear()


def _valid_llm_payload():
    return {
        "action": "BUY",
        "entry_min": 27000, "entry_max": 29000,
        "target_min": 36000, "target_max": 40000,
        "stop_reference": 25000, "stop_method": "structural_support",
        "horizon_days": 365, "confidence": 80,
        "position_size_suggestion": 5.0,
        "thesis": "Luận điểm rõ ràng với dữ kiện mới.",
        "catalysts": ["c1"], "risks": ["r1"],
        "invalidation_conditions": [
            {"condition_id": "inv_x", "description": "biên gộp giảm dưới 8%", "severity": "CRITICAL"}
        ],
        "reasoning_summary": "ok",
    }


def test_material_change_versioning():
    """Same evidence → skip; genuinely new event → v2 + old REVISED."""
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if not db.query(Fund).filter(Fund.id == "MCF").first():
            db.add(Fund(id="MCF", name="MC Fund", manager="T"))
        if not db.query(FundHoldingSnapshot).filter(
            FundHoldingSnapshot.fund_id == "MCF"
        ).first():
            db.add(FundHoldingSnapshot(
                fund_id="MCF", as_of_date=date(2026, 9, 1),
                source_url="seed:t", source_hash="h",
                holdings_json=[{"ticker": "HMN", "weight_pct": 12.0}],
            ))
        for eid, headline in (("evt-mat-old", "Sự kiện cũ"), ("evt-mat-new", "Sự kiện mới")):
            if not db.query(Event).filter(Event.id == eid).first():
                db.add(Event(
                    id=eid, occurred_at=now, source_type="news",
                    source_url="https://example.com/m", source_name="t",
                    headline=headline,
                ))
        if not db.query(Proposal).filter(Proposal.id == "HMN-2026-777-v1").first():
            db.add(Proposal(
                id="HMN-2026-777-v1", proposal_group_id="HMN-2026-777",
                ticker="HMN", version=1, status="ACTIVE", action="BUY",
                valid_from=now, valid_until=now + timedelta(days=365)
                if False else now.replace(year=now.year + 1),
                confidence=75.0, thesis="v1",
                evidence_refs=["evt-mat-old"],
            ))
        db.commit()

        from app.core.engines.opportunity_engine import OpportunityEngine
        import app.core.engines.fundamentals as fund_mod
        fund_mod.get_fundamentals = lambda t: {"income": {}, "ratios": {}}

        eng = OpportunityEngine()
        try:
            eng.get_market_data = lambda t: {"close": 28000.0}
            eng.llm.generate_proposal = lambda **kw: _valid_llm_payload()

            evt_old = db.query(Event).filter(Event.id == "evt-mat-old").first()
            evt_new = db.query(Event).filter(Event.id == "evt-mat-new").first()

            # Same evidence already known → skip, no LLM, no new version
            skipped = eng._generate_proposal_for_ticker(
                "HMN", {"events": [evt_old], "links": []}
            )
            assert skipped is None, "same evidence must not create a new version"

            # Genuinely new event → material change → v2
            created = eng._generate_proposal_for_ticker(
                "HMN", {"events": [evt_old, evt_new], "links": []}
            )
            assert created is not None, "new evidence must create a revision"
            eng.db.commit()  # engine session must commit; test session reads via eng.db
            assert created.version == 2
            assert created.id == "HMN-2026-777-v2"
            assert created.status == "ACTIVE"
            assert "evt-mat-new" in created.evidence_refs
            assert "evt-mat-old" in created.evidence_refs, "old evidence preserved"
            assert created.changed_from_previous and "Material change" in created.changed_from_previous

            old = eng.db.query(Proposal).filter(Proposal.id == "HMN-2026-777-v1").first()
            assert old.status == "REVISED"

            # Only one ACTIVE left for the ticker
            actives = eng.db.query(Proposal).filter(
                Proposal.ticker == "HMN", Proposal.status == "ACTIVE"
            ).all()
            assert len(actives) == 1 and actives[0].id == "HMN-2026-777-v2"
        finally:
            eng.close()
    finally:
        db.close()


def test_full_chain_event_to_proposal_and_rerun_dedup():
    """ingestion-side event → causal link → proposal; re-scan creates nothing new."""
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if not db.query(Fund).filter(Fund.id == "CHN").first():
            db.add(Fund(id="CHN", name="Chain Fund", manager="T"))
        if not db.query(FundHoldingSnapshot).filter(
            FundHoldingSnapshot.fund_id == "CHN"
        ).first():
            db.add(FundHoldingSnapshot(
                fund_id="CHN", as_of_date=date(2026, 9, 2),
                source_url="seed:t", source_hash="h2",
                holdings_json=[{"ticker": "VCB", "weight_pct": 9.0}],
            ))
        if not db.query(Event).filter(Event.id == "evt-chain-1").first():
            db.add(Event(
                id="evt-chain-1", occurred_at=now, source_type="news",
                source_url="https://example.com/c", source_name="t",
                headline="FTSE nâng hạng thị trường Việt Nam",
                summary="Dòng vốn ngoại vào银行业 banking",
            ))
        db.commit()

        import app.core.engines.fundamentals as fund_mod
        fund_mod.get_fundamentals = lambda t: {"income": {}, "ratios": {}}

        from app.core.engines.opportunity_engine import OpportunityEngine
        eng = OpportunityEngine()
        try:
            eng.llm.analyze_event_impact = lambda *a, **k: {
                "classification": "FACT",
                "entities": ["VCB"],
                "causal_links": [{
                    "target_ticker": "VCB", "direction": "POSITIVE",
                    "confidence": 75, "mechanism": "FTSE -> foreign inflow -> banks",
                }],
            }
            eng.llm.generate_proposal = lambda **kw: _valid_llm_payload()
            eng.get_market_data = lambda t: {"close": 28000.0}

            result1 = eng.run_opportunity_scan()
            assert result1["status"] == "completed", result1
            assert result1["proposals_created"] == 1, result1

            created = db.query(Proposal).filter(
                Proposal.ticker == "VCB", Proposal.status == "ACTIVE"
            ).all()
            assert len(created) == 1, [p.id for p in created]
            prop = created[0]
            assert prop.version == 1
            assert "evt-chain-1" in (prop.evidence_refs or []), prop.evidence_refs
            assert prop.invalidation_conditions, "validated payload stored"

            # Event row carries the causal link (traceability)
            evt = db.query(Event).filter(Event.id == "evt-chain-1").first()
            assert any(l.get("target_ticker") == "VCB" for l in (evt.causal_links or []))

            # Re-run: same event, same evidence → skipped, still 1 proposal
            result2 = eng.run_opportunity_scan()
            assert result2["proposals_created"] == 0, result2
            assert result2["proposals_skipped"] >= 1, result2
            count = db.query(Proposal).filter(
                Proposal.ticker == "VCB", Proposal.status == "ACTIVE"
            ).count()
            assert count == 1, f"re-scan created duplicates: {count}"
        finally:
            eng.close()
    finally:
        db.close()


from datetime import timedelta  # noqa: E402


if __name__ == "__main__":
    tests = [
        test_migration_from_empty_database,
        test_body_size_limit_returns_413,
        test_auth_disabled_by_default_and_enabled_with_token,
        test_backup_restore_roundtrip,
        test_rss_failure_raises_for_ingestion_error_recording,
        test_llm_invalid_json_rejected,
        test_llm_timeout_all_models_fail,
        test_vnstock_timeout_wraps_to_market_data_error,
        test_material_change_versioning,
        test_full_chain_event_to_proposal_and_rerun_dedup,
    ]
    passed = failed = 0
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
