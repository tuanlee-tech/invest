"""Phase 3 / remaining Phase 2 tests — hit levels, decision journal, job history,
track-record slicing, LLM_FAILED scan status. Temp DB; no network.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP_DIR = tempfile.mkdtemp(prefix="invest_phase3_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test_phase3.db"

from datetime import date, datetime, timezone  # noqa: E402

from app.core.models.schema import (  # noqa: E402
    init_db, SessionLocal, Fund, FundHoldingSnapshot, Event, Position,
    Proposal, ProposalEvaluation, PositionDecision, JobRun,
)
from app.core.engines.evaluation_engine import compute_hit_levels  # noqa: E402


def test_compute_hit_levels():
    closes = [26000, 27500, 31000, 29000]
    hits = compute_hit_levels(closes, entry_max=27000, target_min=30000, stop_reference=25000)
    assert hits["entry_hit"] is True      # low 26000 <= 27000
    assert hits["target_hit"] is True     # high 31000 >= 30000
    assert hits["stop_hit"] is False      # low 26000 > 25000

    miss = compute_hit_levels([28000, 29000], entry_max=27000, target_min=30000, stop_reference=25000)
    assert miss == {"entry_hit": False, "target_hit": False, "stop_hit": False}

    # Missing levels are never reported as hits
    partial = compute_hit_levels([24000], entry_max=None, target_min=None, stop_reference=25000)
    assert partial["entry_hit"] is False and partial["target_hit"] is False
    assert partial["stop_hit"] is True

    # No data → all False
    assert compute_hit_levels(None) == {"entry_hit": False, "target_hit": False, "stop_hit": False}
    assert compute_hit_levels([])["entry_hit"] is False


def _seed_position_and_proposal(db, ticker="HPG", price_cond=None):
    pos = Position(
        id=f"pos-{ticker.lower()}-test", ticker=ticker, quantity=100,
        avg_buy_price=27000.0, buy_date=date(2026, 8, 1), status="ACTIVE",
    )
    conditions = price_cond if price_cond is not None else [
        {"condition_id": "inv_1", "description": "no trigger", "severity": "CRITICAL"}
    ]
    prop = Proposal(
        id=f"{ticker}-2026-999-v1", proposal_group_id=f"{ticker}-2026-999",
        ticker=ticker, version=1, status="ACTIVE", action="BUY",
        entry_min=26000, entry_max=29000, target_min=32000, target_max=36000,
        stop_reference=25000, horizon_days=365,
        valid_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        valid_until=datetime(2027, 8, 1, tzinfo=timezone.utc),
        confidence=75.0, thesis="test thesis",
        invalidation_conditions=conditions,
    )
    db.add(pos)
    db.add(prop)
    db.commit()
    return pos, prop


def test_position_decision_journal():
    init_db()
    db = SessionLocal()
    try:
        pos, _ = _seed_position_and_proposal(db, ticker="HPT")

        from app.core.engines.portfolio_engine import PortfolioEngine
        eng = PortfolioEngine()
        try:
            eng.llm.reevaluate_position = lambda **kw: {
                "action": "HOLD", "thesis_health": "HEALTHY",
                "invalidation_triggered": False, "explanation": "luận điểm còn nguyên vẹn",
                "confidence": 80,
            }
            eng.get_current_price = lambda t: 28000.0
            result = eng.reevaluate_all_positions()
        finally:
            eng.close()

        assert result["decisions_recorded"] >= 1, result
        rows = db.query(PositionDecision).filter(
            PositionDecision.position_id == pos.id
        ).order_by(PositionDecision.decided_at).all()
        assert rows, "decision must be journaled"
        last = rows[-1]
        assert last.action == "HOLD"
        assert last.thesis_health == "HEALTHY"
        assert last.source == "reeval"
        assert last.current_price == 28000.0
        assert last.reason and "nguyên vẹn" in last.reason

        # Unchanged HOLD is journaled again on the next run (append-only history)
        from app.core.engines.portfolio_engine import PortfolioEngine as PE
        eng2 = PE()
        try:
            eng2.llm.reevaluate_position = lambda **kw: {
                "action": "HOLD", "thesis_health": "HEALTHY",
                "invalidation_triggered": False, "explanation": "vẫn ổn",
                "confidence": 80,
            }
            eng2.get_current_price = lambda t: 28500.0
            eng2.reevaluate_all_positions()
        finally:
            eng2.close()
        count = db.query(PositionDecision).filter(
            PositionDecision.position_id == pos.id
        ).count()
        assert count >= 2, f"expected append-only history, got {count} rows"
    finally:
        db.close()


def test_critical_price_condition_overrides_llm():
    init_db()
    db = SessionLocal()
    try:
        cond = [{
            "condition_id": "inv_stop", "description": "giá dưới 30000",
            "data_source": "price:close", "threshold_value": 30000,
            "comparison": "<", "severity": "CRITICAL",
        }]
        pos, prop = _seed_position_and_proposal(db, ticker="HDX", price_cond=cond)

        from app.core.engines.portfolio_engine import PortfolioEngine
        eng = PortfolioEngine()
        try:
            # LLM is optimistic — deterministic CRITICAL trigger must win
            eng.llm.reevaluate_position = lambda **kw: {
                "action": "ADD", "thesis_health": "HEALTHY",
                "invalidation_triggered": False, "explanation": "LLM says buy more",
                "confidence": 90,
            }
            eng.get_current_price = lambda t: 25000.0  # < 30000 → trigger
            result = eng.reevaluate_all_positions()
        finally:
            eng.close()

        db.refresh(pos)
        assert pos.thesis_health == "INVALIDATED", pos.thesis_health
        assert pos.current_action == "EXIT", pos.current_action
        assert any(a.get("ticker") == "HDX" for a in result["invalidation_alerts"]), result

        decision = db.query(PositionDecision).filter(
            PositionDecision.position_id == pos.id
        ).order_by(PositionDecision.decided_at.desc()).first()
        assert decision.action == "EXIT"
        assert decision.thesis_health == "INVALIDATED"
        assert decision.invalidation_triggered is True
        assert decision.triggered_conditions, "triggered conditions must be recorded"
        assert decision.triggered_conditions[0]["condition_id"] == "inv_stop"
        # Revision created because action changed BUY → EXIT
        assert result["revisions_created"] >= 1, result
        db.refresh(prop)  # old proposal must be REVISED, new ACTIVE exists
    finally:
        db.close()


def test_job_run_history_success_and_failure():
    init_db()
    from app.scheduler import EngineScheduler
    sched = EngineScheduler()

    sched._safe_job(lambda: {"evaluated": 2, "errors": [], "note": "ok"}, "TestOK")()
    def _boom():
        raise RuntimeError("boom failure")
    sched._safe_job(_boom, "TestFail")()

    db = SessionLocal()
    try:
        ok = db.query(JobRun).filter(JobRun.job_name == "TestOK").order_by(JobRun.id.desc()).first()
        assert ok is not None, "success run must be recorded"
        assert ok.status == "SUCCESS"
        assert ok.job_id and len(ok.job_id) == 32
        assert ok.started_at and ok.finished_at and ok.finished_at >= ok.started_at
        assert ok.record_counts["evaluated"] == 2
        assert ok.record_counts["errors_count"] == 0  # lists become counts
        assert ok.record_counts["note"] == "ok"
        assert ok.error is None

        fail = db.query(JobRun).filter(JobRun.job_name == "TestFail").order_by(JobRun.id.desc()).first()
        assert fail is not None, "failed run must be recorded"
        assert fail.status == "FAILED"
        assert fail.error and "boom failure" in fail.error
        assert fail.finished_at is not None
    finally:
        db.close()


def test_track_record_slices_and_filter():
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for pid, ticker, action, ret, outcome in [
            ("P-HPG-1", "HPG", "BUY", 12.5, "SUCCESS"),
            ("P-HPG-2", "HPG", "BUY", -5.0, "FAILED"),
            ("P-MWG-1", "MWG", "WATCH", 8.0, "SUCCESS"),
        ]:
            db.add(Proposal(
                id=pid, proposal_group_id=pid.rsplit("-v", 1)[0], ticker=ticker,
                version=1, status="EXPIRED", action=action,
                valid_from=now, valid_until=now, confidence=70.0, thesis="t",
            ))
            db.add(ProposalEvaluation(
                proposal_id=pid, ticker=ticker, evaluated_at=now,
                evaluation_window_days=90, realized_return_pct=ret,
                benchmark_return_pct=2.0, alpha_pct=ret - 2.0,
                max_drawdown_pct=-3.0, entry_hit=True,
                target_hit=(outcome == "SUCCESS"), stop_hit=False,
                outcome_status=outcome,
            ))
        db.commit()

        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

        r = client.get("/api/track-record")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3
        assert body["slices"]["by_ticker"]["HPG"]["total"] == 2
        assert body["slices"]["by_ticker"]["MWG"]["total"] == 1
        assert body["slices"]["by_ticker"]["HPG"]["win_rate"] == 50.0
        assert body["slices"]["by_action"]["BUY"]["total"] == 2
        assert body["slices"]["by_action"]["WATCH"]["total"] == 1
        assert "target_hit_rate" in body["slices"]["by_ticker"]["HPG"]

        r2 = client.get("/api/track-record", params={"ticker": "hpg"})
        b2 = r2.json()
        assert b2["total"] == 2 and b2["filters"]["ticker"] == "hpg"
        assert all(d["ticker"] == "HPG" for d in b2["details"])

        r3 = client.get("/api/track-record", params={"action": "BUY"})
        assert r3.json()["total"] == 2
    finally:
        db.close()


def test_scan_reports_llm_failed_without_fabricating():
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        if not db.query(Fund).filter(Fund.id == "TESTF").first():
            db.add(Fund(id="TESTF", name="Test Fund", manager="Test"))
        if not db.query(FundHoldingSnapshot).filter(
            FundHoldingSnapshot.fund_id == "TESTF"
        ).first():
            db.add(FundHoldingSnapshot(
                fund_id="TESTF", as_of_date=date(2026, 9, 1),
                source_url="seed:test", source_hash="x",
                holdings_json=[{"ticker": "HPG", "weight_pct": 10.0}],
            ))
        if not db.query(Event).filter(Event.id == "evt-hrc-test").first():
            db.add(Event(
                id="evt-hrc-test", occurred_at=now, source_type="news",
                source_url="https://example.com/e", source_name="test",
                headline="HRC giá thép tăng mạnh", summary="HRC outlook tích cực",
            ))
        db.commit()

        import app.core.engines.fundamentals as fund_mod
        fund_mod.get_fundamentals = lambda t: {"income": {}, "ratios": {}}

        proposals_before = db.query(Proposal).filter(Proposal.ticker == "HPG").count()

        from app.core.engines.opportunity_engine import OpportunityEngine
        eng = OpportunityEngine()
        try:
            def _llm_down(*a, **k):
                raise RuntimeError("All models failed. Last error: provider timeout")
            eng.llm.analyze_event_impact = _llm_down
            eng.llm.generate_proposal = _llm_down
            eng.get_market_data = lambda t: {"close": 28000.0}
            result = eng.run_opportunity_scan()
        finally:
            eng.close()

        assert result["status"] == "LLM_FAILED", result
        assert result["relevant_events"] >= 1, "graph must still mark event relevant"
        assert result["llm_failures"] >= 1, "LLM analysis failure counted"
        assert result["llm_failed"] and result["llm_failed"][0]["ticker"] == "HPG"
        assert "provider timeout" in result["llm_failed"][0]["error"]
        assert result["proposals_created"] == 0, "must never invent a proposal"

        # Events stay persisted despite LLM failure
        stored = db.query(Event).filter(Event.id == "evt-hrc-test").first()
        assert stored is not None
        assert stored.causal_links, "graph links stored on the event"
        assert any(l.get("target_ticker") == "HPG" for l in stored.causal_links)
        # No proposal was fabricated for HPG
        proposals_after = db.query(Proposal).filter(Proposal.ticker == "HPG").count()
        assert proposals_after == proposals_before, \
            f"fabricated {proposals_after - proposals_before} proposal(s)"
    finally:
        db.close()


if __name__ == "__main__":
    tests = [
        test_compute_hit_levels,
        test_position_decision_journal,
        test_critical_price_condition_overrides_llm,
        test_job_run_history_success_and_failure,
        test_track_record_slices_and_filter,
        test_scan_reports_llm_failed_without_fabricating,
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
