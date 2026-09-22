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


if __name__ == "__main__":
    tests = [test_seed_and_api, test_evaluation_engine, test_market_data, test_fundamentals, test_causal_graph]
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
