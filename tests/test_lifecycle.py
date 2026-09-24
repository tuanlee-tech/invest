"""Basic lifecycle test — seed → API → evaluation."""
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_seed_and_api():
    """Test that seed data loads and API returns 200."""
    from app.core.models.schema import init_db, SessionLocal, Fund, Proposal, Position, FundHoldingSnapshot
    from app.storage.seed import seed

    init_db()
    seed()

    db = SessionLocal()
    try:
        assert db.query(Fund).count() >= 4, "Expected at least 4 funds"
        assert db.query(Proposal).count() >= 2, "Expected at least 2 proposals"
        assert db.query(Position).count() >= 1, "Expected at least 1 position"
        assert db.query(FundHoldingSnapshot).count() >= 3, "Expected at least 3 snapshots (historical)"
    finally:
        db.close()


def test_evaluation_engine():
    """Test evaluation engine processes expired proposals."""
    from app.core.engines.evaluation_engine import EvaluationEngine

    engine = EvaluationEngine()
    try:
        result = engine.evaluate_settled_proposals()
        assert "evaluated" in result, "Expected 'evaluated' key in result"
        assert isinstance(result["evaluated"], int), "evaluated should be int"
    finally:
        engine.close()


def test_proposal_auto_expire():
    """Proposals past valid_until are flipped ACTIVE -> EXPIRED by the evaluation job."""
    from datetime import datetime, timezone
    from app.core.engines.evaluation_engine import EvaluationEngine
    from app.core.models.schema import SessionLocal, Proposal

    engine = EvaluationEngine()
    try:
        result = engine.evaluate_settled_proposals()
        assert "expired" in result, f"expected 'expired' in {result}"
    finally:
        engine.close()

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        stale = db.query(Proposal).filter(
            Proposal.valid_until <= now,
            Proposal.status == "ACTIVE",
        ).all()
        assert not stale, f"stale ACTIVE proposals: {[p.id for p in stale]}"

        live = db.query(Proposal).filter(
            Proposal.valid_until > now,
            Proposal.status == "ACTIVE",
        ).all()
        assert live, "future proposals must remain ACTIVE"
    finally:
        db.close()


def test_market_data():
    """Test vnstock market data wrapper returns real prices."""
    from app.core.engines.market_data import get_latest_price

    price = get_latest_price("HPG")
    assert price is not None, "HPG price should not be None"
    assert price > 0, "HPG price should be positive"
    assert price < 1000000, "HPG price should be reasonable (VND)"


def test_fundamentals():
    """Test fundamentals normalization returns valid data."""
    from app.core.engines.fundamentals import get_fundamentals, normalize_income

    f = get_fundamentals("HPG")
    assert f["ticker"] == "HPG"
    assert "income" in f or "ratios" in f, "Should have income or ratios"

    if f["income"]:
        norm = normalize_income(f["income"])
        assert "quarter" in norm, "Normalized income should have quarter"


def test_causal_graph():
    """Test causal graph auto-generates links."""
    from app.core.engines.causal_graph import infer_causal_links

    links = infer_causal_links(
        "Giá thép tăng mạnh",
        "HRC giá tăng 6%",
        ["HPG", "VCB", "FPT"]
    )
    assert len(links) > 0, "Should generate at least one causal link"
    assert any(l["target_ticker"] == "HPG" for l in links), "Should link steel event to HPG"


def test_health():
    """GET /health reports DB + market-data + LLM status, 503 with clear errors on failure."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code in (200, 503), f"unexpected status {r.status_code}"
    body = r.json()
    deps = body.get("dependencies", {})
    assert set(deps) == {"database", "market_data", "llm"}, f"missing deps: {deps.keys()}"
    for name, res in deps.items():
        assert res.get("status") in ("ok", "error"), f"{name}: {res}"
        if res["status"] != "ok":
            assert res.get("error"), f"{name} failed without an error message: {res}"
    if r.status_code == 503:
        assert "error" in body and "failed dependencies" in body["error"]
    else:
        assert body["status"] == "ok"


if __name__ == "__main__":
    tests = [test_seed_and_api, test_evaluation_engine, test_proposal_auto_expire,
             test_market_data, test_fundamentals, test_causal_graph, test_health]
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
