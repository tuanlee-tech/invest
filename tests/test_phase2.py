"""Phase 2 tests — causal graph contract, proposal dedup, LLM validation,
deterministic invalidation. Temp DB; no network.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP_DIR = tempfile.mkdtemp(prefix="invest_phase2_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test_phase2.db"

from datetime import date, datetime, timezone  # noqa: E402

from app.core.models.schema import init_db, SessionLocal, Proposal  # noqa: E402
from app.core.engines.causal_graph import infer_causal_links, enrich_link  # noqa: E402
from app.core.engines.portfolio_engine import evaluate_invalidation_conditions  # noqa: E402
from app.schemas.domain import validate_llm_proposal  # noqa: E402


def test_causal_graph_positive_negative_irrelevant():
    tickers = ["HPG", "VCB", "FPT"]
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)

    # Positive: steel price up → HPG
    pos = infer_causal_links("Giá thép tăng mạnh 6%", "HRC outlook tích cực",
                             tickers, event_id="evt-1", occurred_at=now)
    assert pos, "steel event must link to HPG"
    hpg = next(l for l in pos if l["target_ticker"] == "HPG")
    assert hpg["direction"] == "POSITIVE"
    assert hpg["classification"] == "INFERENCE"
    assert hpg["mechanism"], "mechanism must be stored"
    assert hpg["source_event_id"] == "evt-1"
    assert hpg["timestamp"] == now.isoformat()
    assert hpg["source"] == "causal_graph"
    assert 0 <= hpg["confidence"] <= 100

    # Negative: iron ore cost up → steel producers hurt
    neg = infer_causal_links("Giá quặng sắt leo thang", "", tickers, event_id="evt-2")
    assert neg, "iron-ore event must link to HPG"
    assert all(l["direction"] == "NEGATIVE" for l in neg)

    # Irrelevant: no pattern match → no links
    none = infer_causal_links("Thời tiết đẹp cuối tuần ở Hà Nội", "Không liên quan thị trường",
                              tickers, event_id="evt-3")
    assert none == [], f"irrelevant event must produce no links, got {none}"

    # Out-of-universe ticker is never linked
    out = infer_causal_links("Giá thép tăng", "", ["FPT"])
    assert out == [], f"HPG not in watched universe, got {out}"


def test_enrich_link_idempotent_and_defaults():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    link = enrich_link({"target_ticker": "HPG"}, event_id="e1", occurred_at=now)
    assert link["classification"] == "INFERENCE"
    assert link["source_event_id"] == "e1"
    assert link["timestamp"] == now.isoformat()

    # Invalid classification downgraded; existing values kept
    link2 = enrich_link({"target_ticker": "HPG", "classification": "GUESS",
                         "confidence": 80, "source": "llm"},
                        event_id="e2", occurred_at=now, source="causal_graph")
    assert link2["classification"] == "INFERENCE"
    assert link2["confidence"] == 80
    assert link2["source"] == "llm"

    # Enriching twice does not change timestamps
    again = enrich_link(link, event_id="other")
    assert again["timestamp"] == link["timestamp"]
    assert again["source_event_id"] == "e1"


def _make_engine():
    from app.core.engines.opportunity_engine import OpportunityEngine
    return OpportunityEngine()


def test_proposal_dedup_blocks_active_regardless_of_age():
    init_db()
    db = SessionLocal()
    try:
        db.add(Proposal(
            id="HPG-2020-001-v1", proposal_group_id="HPG-2020-001",
            ticker="HPG", version=1, status="ACTIVE", action="BUY",
            valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
            valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
            confidence=80.0, thesis="old but still ACTIVE",
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # way past 7 days
        ))
        db.commit()

        eng = _make_engine()
        try:
            # ACTIVE proposal must block — even though created_at is years old
            assert eng._generate_proposal_for_ticker("HPG", {"events": [], "links": []}) is None

            # A ticker with only an EXPIRED proposal passes dedup (hits the
            # fund-universe check next — prove it by making that check raise)
            db.add(Proposal(
                id="MWG-2020-001-v1", proposal_group_id="MWG-2020-001",
                ticker="MWG", version=1, status="EXPIRED", action="BUY",
                valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2020, 6, 1, tzinfo=timezone.utc),
                confidence=70.0, thesis="expired",
                created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ))
            db.commit()

            class PassedDedup(Exception):
                pass

            def _raise(_ticker):
                raise PassedDedup()

            eng.get_fund_holdings_for_ticker = _raise
            try:
                eng._generate_proposal_for_ticker("MWG", {"events": [], "links": []})
                assert False, "EXPIRED proposal must not block a fresh scan"
            except PassedDedup:
                pass
        finally:
            eng.close()
    finally:
        db.close()


def _valid_payload():
    return {
        "action": "BUY",
        "entry_min": 27000, "entry_max": 29000,
        "target_min": 36000, "target_max": 40000,
        "stop_reference": 25000, "stop_method": "structural_support",
        "horizon_days": 365, "confidence": 78,
        "position_size_suggestion": 5.0,
        "thesis": "Luận điểm tăng trưởng rõ ràng.",
        "catalysts": ["a"], "risks": ["b"],
        "invalidation_conditions": [
            {"condition_id": "inv_1", "description": "biên gộp giảm dưới 8%", "severity": "CRITICAL"}
        ],
        "reasoning_summary": "ok",
    }


def test_validate_llm_proposal_accepts_good_rejects_bad():
    good = validate_llm_proposal(_valid_payload())
    assert good["action"] == "BUY" and good["confidence"] == 78.0

    cases = []
    bad = _valid_payload(); bad["action"] = "SELL_IT"; cases.append(bad)
    bad = _valid_payload(); bad["confidence"] = 150; cases.append(bad)
    bad = _valid_payload(); bad["confidence"] = "cao"; cases.append(bad)
    bad = _valid_payload(); bad["entry_min"] = 30000; bad["entry_max"] = 20000; cases.append(bad)
    bad = _valid_payload(); bad["target_min"] = 50000; bad["target_max"] = 40000; cases.append(bad)
    bad = _valid_payload(); bad["position_size_suggestion"] = 25; cases.append(bad)
    bad = _valid_payload(); bad["horizon_days"] = 0; cases.append(bad)
    bad = _valid_payload(); bad["thesis"] = "  "; cases.append(bad)
    bad = _valid_payload(); bad["invalidation_conditions"] = []; cases.append(bad)
    bad = _valid_payload(); bad["invalidation_conditions"] = [{"description": ""}]; cases.append(bad)
    bad = _valid_payload(); bad["entry_min"] = -1; cases.append(bad)
    bad = _valid_payload(); bad["catalysts"] = "not-a-list"; cases.append(bad)

    for i, payload in enumerate(cases):
        try:
            validate_llm_proposal(payload)
            assert False, f"case {i} must be rejected: {payload}"
        except ValueError:
            pass


def test_deterministic_invalidation_conditions():
    cond_critical = {
        "condition_id": "inv_price", "description": "giá dưới 25000",
        "data_source": "price:close", "threshold_value": 25000,
        "comparison": "<", "severity": "CRITICAL",
    }
    cond_warning = {
        "condition_id": "inv_price2", "description": "giá trên 40000",
        "data_source": "price:close", "threshold_value": 40000,
        "comparison": ">", "severity": "WARNING",
    }
    cond_financial = {
        "condition_id": "inv_np", "description": "lợi nhuận giảm 15%",
        "data_source": "financial:net_profit", "threshold_value": -15,
        "comparison": "<", "severity": "CRITICAL",
    }

    # Triggered: 24000 < 25000
    t = evaluate_invalidation_conditions([cond_critical, cond_warning, cond_financial], 24000)
    assert [c["condition_id"] for c in t] == ["inv_price"], t
    assert "inv_np" not in [c["condition_id"] for c in t], "financial conditions are not machine-checked"

    # Not triggered: 30000
    assert evaluate_invalidation_conditions([cond_critical, cond_warning], 30000) == []
    # WARNING direction check
    assert evaluate_invalidation_conditions([cond_warning], 41000)[0]["condition_id"] == "inv_price2"
    # No price / no conditions
    assert evaluate_invalidation_conditions(None, 30000) == []
    assert evaluate_invalidation_conditions([cond_critical], 0.0) == []
    # Missing threshold skipped safely
    assert evaluate_invalidation_conditions([{"data_source": "price:close"}], 30000) == []


if __name__ == "__main__":
    tests = [
        test_causal_graph_positive_negative_irrelevant,
        test_enrich_link_idempotent_and_defaults,
        test_proposal_dedup_blocks_active_regardless_of_age,
        test_validate_llm_proposal_accepts_good_rejects_bad,
        test_deterministic_invalidation_conditions,
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
