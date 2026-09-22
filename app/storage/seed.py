"""Seed initial sample data to get the system operational immediately"""
from datetime import datetime, timezone, date, timedelta
from app.core.models.schema import get_db, Fund, FundHoldingSnapshot, Security, Proposal, Position, Event, SessionLocal

def seed():
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        # Create Funds
        funds = [
            Fund(id="VEIL", name="Vietnam Enterprise Investments Limited", manager="Dragon Capital", fund_type="closed_end"),
            Fund(id="VESAF", name="VinaCapital Strategic Growth Equity Fund", manager="VinaCapital", fund_type="open_end"),
            Fund(id="VCBF-BCF", name="Quỹ đầu tư cổ phiếu hàng đầu VCBF", manager="VCBF", fund_type="open_end"),
            Fund(id="PYN", name="PYN Elite Fund", manager="PYN Fund Management", fund_type="specialized"),
            Fund(id="SSI-SCA", name="SSI Sustainable Competitive Advantage Fund", manager="SSIAM", fund_type="open_end"),
            Fund(id="DCDS", name="Dragon Capital Dividend Select Fund", manager="Dragon Capital", fund_type="open_end"),
        ]
        for f in funds:
            if not db.query(Fund).filter(Fund.id == f.id).first():
                db.add(f)
        db.commit()
        print("Funds seeded.")

        # Seed Fund Holding Snapshots — 3 months historical (Jul, Aug, Sep 2026)
        snapshots = [
            # --- VESAF ---
            FundHoldingSnapshot(
                fund_id="VESAF", as_of_date=date(2026, 7, 31),
                holdings_json=[
                    {"ticker": "BVH", "sector": "Non-bank Financials", "weight_pct": 6.8, "rank": 1},
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 6.1, "rank": 2},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 5.8, "rank": 3},
                    {"ticker": "VCB", "sector": "Banks", "weight_pct": 6.2, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 5.5, "rank": 5},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.3, "rank": 6},
                    {"ticker": "TCB", "sector": "Banks", "weight_pct": 4.5, "rank": 7},
                    {"ticker": "FPT", "sector": "Information Technology", "weight_pct": 4.8, "rank": 8},
                    {"ticker": "CTR", "sector": "Industrials", "weight_pct": 3.9, "rank": 9},
                    {"ticker": "ACB", "sector": "Banks", "weight_pct": 4.1, "rank": 10},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VESAF", as_of_date=date(2026, 8, 31),
                holdings_json=[
                    {"ticker": "BVH", "sector": "Non-bank Financials", "weight_pct": 7.0, "rank": 1},
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 6.3, "rank": 2},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 6.0, "rank": 3},
                    {"ticker": "VCB", "sector": "Banks", "weight_pct": 6.0, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 5.9, "rank": 5},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.5, "rank": 6},
                    {"ticker": "TCB", "sector": "Banks", "weight_pct": 4.7, "rank": 7},
                    {"ticker": "FPT", "sector": "Information Technology", "weight_pct": 4.6, "rank": 8},
                    {"ticker": "CTR", "sector": "Industrials", "weight_pct": 4.1, "rank": 9},
                    {"ticker": "ACB", "sector": "Banks", "weight_pct": 4.0, "rank": 10},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VESAF", as_of_date=date(2026, 9, 15),
                holdings_json=[
                    {"ticker": "BVH", "sector": "Non-bank Financials", "weight_pct": 7.2, "rank": 1},
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 6.5, "rank": 2},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 6.1, "rank": 3},
                    {"ticker": "VCB", "sector": "Banks", "weight_pct": 5.9, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 6.0, "rank": 5},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.4, "rank": 6},
                    {"ticker": "TCB", "sector": "Banks", "weight_pct": 4.8, "rank": 7},
                    {"ticker": "FPT", "sector": "Information Technology", "weight_pct": 4.5, "rank": 8},
                    {"ticker": "CTR", "sector": "Industrials", "weight_pct": 4.2, "rank": 9},
                    {"ticker": "ACB", "sector": "Banks", "weight_pct": 3.9, "rank": 10},
                ]
            ),
            # --- VCBF-BCF ---
            FundHoldingSnapshot(
                fund_id="VCBF-BCF", as_of_date=date(2026, 7, 31),
                holdings_json=[
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 8.95, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 5.80, "rank": 2},
                    {"ticker": "MSN", "sector": "Consumer Staples", "weight_pct": 5.75, "rank": 3},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.60, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 5.50, "rank": 5},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VCBF-BCF", as_of_date=date(2026, 8, 31),
                holdings_json=[
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 9.21, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 6.06, "rank": 2},
                    {"ticker": "MSN", "sector": "Consumer Staples", "weight_pct": 5.89, "rank": 3},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.77, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 5.76, "rank": 5},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VCBF-BCF", as_of_date=date(2026, 9, 15),
                holdings_json=[
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 9.40, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 6.20, "rank": 2},
                    {"ticker": "MSN", "sector": "Consumer Staples", "weight_pct": 5.95, "rank": 3},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.85, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 5.90, "rank": 5},
                ]
            ),
            # --- VEIL ---
            FundHoldingSnapshot(
                fund_id="VEIL", as_of_date=date(2026, 7, 31),
                holdings_json=[
                    {"ticker": "VIC", "sector": "Real Estate", "weight_pct": 10.8, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 6.8, "rank": 2},
                    {"ticker": "BID", "sector": "Banks", "weight_pct": 6.4, "rank": 3},
                    {"ticker": "VCB", "sector": "Banks", "weight_pct": 6.1, "rank": 4},
                    {"ticker": "VPB", "sector": "Banks", "weight_pct": 4.6, "rank": 5},
                    {"ticker": "VHM", "sector": "Real Estate", "weight_pct": 4.3, "rank": 6},
                    {"ticker": "TCB", "sector": "Banks", "weight_pct": 4.0, "rank": 7},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 3.7, "rank": 8},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 3.5, "rank": 9},
                    {"ticker": "ACB", "sector": "Banks", "weight_pct": 3.4, "rank": 10},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VEIL", as_of_date=date(2026, 8, 30),
                holdings_json=[
                    {"ticker": "VIC", "sector": "Real Estate", "weight_pct": 11.2, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 7.0, "rank": 2},
                    {"ticker": "BID", "sector": "Banks", "weight_pct": 6.6, "rank": 3},
                    {"ticker": "VCB", "sector": "Banks", "weight_pct": 6.3, "rank": 4},
                    {"ticker": "VPB", "sector": "Banks", "weight_pct": 4.8, "rank": 5},
                    {"ticker": "VHM", "sector": "Real Estate", "weight_pct": 4.5, "rank": 6},
                    {"ticker": "TCB", "sector": "Banks", "weight_pct": 4.1, "rank": 7},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 3.8, "rank": 8},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 3.7, "rank": 9},
                    {"ticker": "ACB", "sector": "Banks", "weight_pct": 3.5, "rank": 10},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VEIL", as_of_date=date(2026, 9, 15),
                holdings_json=[
                    {"ticker": "VIC", "sector": "Real Estate", "weight_pct": 11.4, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 7.1, "rank": 2},
                    {"ticker": "BID", "sector": "Banks", "weight_pct": 6.7, "rank": 3},
                    {"ticker": "VCB", "sector": "Banks", "weight_pct": 6.2, "rank": 4},
                    {"ticker": "VPB", "sector": "Banks", "weight_pct": 4.9, "rank": 5},
                    {"ticker": "VHM", "sector": "Real Estate", "weight_pct": 4.6, "rank": 6},
                    {"ticker": "TCB", "sector": "Banks", "weight_pct": 4.2, "rank": 7},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 3.9, "rank": 8},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 3.8, "rank": 9},
                    {"ticker": "ACB", "sector": "Banks", "weight_pct": 3.6, "rank": 10},
                ]
            ),
        ]
        for s in snapshots:
            if not db.query(FundHoldingSnapshot).filter(
                FundHoldingSnapshot.fund_id == s.fund_id,
                FundHoldingSnapshot.as_of_date == s.as_of_date
            ).first():
                db.add(s)
        db.commit()
        print("Fund Holding Snapshots seeded (3 months x 3 funds = 9 snapshots).")

        # Seed Securities
        all_tickers = ["HPG", "MWG", "CTG", "MBB", "VCB", "FPT", "TCB", "ACB", "VIC", "VHM", "BID", "VPB", "MSN", "CTR", "BVH", "GAS", "NVL"]
        for t in all_tickers:
            if not db.query(Security).filter(Security.ticker == t).first():
                db.add(Security(ticker=t, name=t, exchange="HOSE", in_fund_universe=True))
        db.commit()
        print("Securities seeded.")

        # Seed sample Events with causal links
        now = datetime.now(timezone.utc)
        events = [
            Event(
                id="evt-steel-01",
                occurred_at=now,
                source_type="news",
                source_url="https://cafef.vn/thep-hoi-phuc.html",
                source_name="CafeF",
                headline="Giá thép xây dựng thế giới tăng mạnh tuần thứ 3 liên tiếp, xuất khẩu khởi sắc",
                summary="Giá phôi thép và HRC tại châu Á bật tăng hơn 6% trong tháng qua nhờ nhu cầu hạ tầng và biện pháp phòng vệ thương mại có hiệu lực.",
                classification="FACT",
                entities=["HPG"],
                causal_links=[{"target_ticker": "HPG", "direction": "POSITIVE", "confidence": 85, "mechanism": "Giá bán tăng + Dung Quất 2 chạy tối đa công suất -> Doanh thu và biên gộp phục hồi mạnh"}]
            ),
            Event(
                id="evt-retail-01",
                occurred_at=now,
                source_type="news",
                source_url="https://vnexpress.net/bach-hoa-xanh-co-lai.html",
                source_name="VnExpress",
                headline="Bách Hóa Xanh vượt mốc 2.500 cửa hàng, bắt đầu có lãi ròng toàn chuỗi",
                summary="Chuỗi bán lẻ thực phẩm của Thế Giới Di Động ghi nhận EBITDA dương liên tiếp 3 quý và chuẩn bị kế hoạch mở rộng ra miền Bắc.",
                classification="FACT",
                entities=["MWG"],
                causal_links=[{"target_ticker": "MWG", "direction": "POSITIVE", "confidence": 80, "mechanism": "BHX chuyển từ điểm hòa vốn sang sinh lời -> Định giá toàn tập đoàn được re-rate"}]
            ),
            # Events for expired proposals
            Event(
                id="evt-fpt-ai-01",
                occurred_at=now - timedelta(days=100),
                source_type="news",
                source_url="https://cafef.vn/fpt-ai-quy1.html",
                source_name="CafeF",
                headline="FPT Smart Cloud đạt doanh thu AI tăng 45% YoY, ký hợp đồng lớn với doanh nghiệp Nhật",
                summary="Lĩnh vực AI và chuyển đổi số của FPT ghi nhận tăng trưởng mạnh với biên lợi nhuận cao hơn mảng truyền thống.",
                classification="FACT",
                entities=["FPT"],
                causal_links=[{"target_ticker": "FPT", "direction": "POSITIVE", "confidence": 82, "mechanism": "AI margin cao + contract backlog tăng -> re-rating EPS"}]
            ),
            Event(
                id="evt-ctg-bank-01",
                occurred_at=now - timedelta(days=80),
                source_type="news",
                source_url="https://vnexpress.net/ctg-tang-von.html",
                source_name="VnExpress",
                headline="Vietinbank hoàn tất tăng vốn điều lệ lên 75,000 tỷ,_RATIO CAR đạt 12%",
                summary="Vietinbank tăng vốn thành công, mở room tín dụng cho Q3/Q4 2026.",
                classification="FACT",
                entities=["CTG"],
                causal_links=[{"target_ticker": "CTG", "direction": "POSITIVE", "confidence": 70, "mechanism": "Tăng vốn -> room tín dụng -> tăng trưởng lợi nhuận"}]
            ),
        ]
        for e in events:
            if not db.query(Event).filter(Event.id == e.id).first():
                db.add(e)
        db.commit()
        print("Events seeded.")

        # Seed Proposals — 3 expired (for track record) + 2 active (current)
        expired_proposals = [
            Proposal(
                id="FPT-2026-001-v1",
                proposal_group_id="FPT-2026-001",
                ticker="FPT", version=1, status="ACTIVE", action="BUY",
                entry_min=115000.0, entry_max=125000.0,
                target_min=150000.0, target_max=170000.0,
                stop_reference=105000.0, stop_method="structural_support",
                horizon_days=90,
                valid_from=now - timedelta(days=110),
                valid_until=now - timedelta(days=20),
                confidence=80.0, position_size_suggestion=6.0,
                thesis="FPT Smart Cloud tăng trưởng AI 45% YoY, hợp đồng lớn với DN Nhật. AI margin cao hơn mảng truyền thống.",
                catalysts=["Ký hợp đồng AI lớn với DN Nhật", "Doanh thu cloud tăng trưởng 40%+"],
                risks=["Cạnh tranh từ các đối thủ CNTT lớn", "Chi phí nhân sự AI cao"],
                invalidation_conditions=[{"condition_id": "inv_fpt_ai", "description": "Doanh thu AI quý giảm 20% YoY", "severity": "CRITICAL"}],
                evidence_refs=["evt-fpt-ai-01"],
                reasoning_summary="AI tailwind rõ ràng, backlog tăng mạnh."
            ),
            Proposal(
                id="CTG-2026-001-v1",
                proposal_group_id="CTG-2026-001",
                ticker="CTG", version=1, status="ACTIVE", action="BUY",
                entry_min=32000.0, entry_max=35000.0,
                target_min=42000.0, target_max=48000.0,
                stop_reference=29000.0, stop_method="fixed_pct",
                horizon_days=90,
                valid_from=now - timedelta(days=90),
                valid_until=now - timedelta(days=0),
                confidence=72.0, position_size_suggestion=5.0,
                thesis="Vietinbank tăng vốn 75,000 tỷ, room tín dụng mở, NIM cải thiện.",
                catalysts=["Tăng vốn hoàn tất", "Room tín dụng mở Q3/Q4"],
                risks=["NPL tăng trong bối cảnh kinh tế", "Cạnh tranh lãi suất"],
                invalidation_conditions=[{"condition_id": "inv_ctg_npl", "description": "NPL ratio tăng trên 2.5%", "severity": "CRITICAL"}],
                evidence_refs=["evt-ctg-bank-01"],
                reasoning_summary="Tăng vốn + room credit + NIM improvement."
            ),
        ]
        for p in expired_proposals:
            if not db.query(Proposal).filter(Proposal.id == p.id).first():
                db.add(p)

        # Active proposals (current)
        active_proposals = [
            Proposal(
                id="HPG-2026-001-v1",
                proposal_group_id="HPG-2026-001",
                ticker="HPG", version=1, status="ACTIVE", action="BUY",
                entry_min=27000.0, entry_max=29000.0,
                target_min=36000.0, target_max=40000.0,
                stop_reference=25000.0, stop_method="structural_support",
                horizon_days=365,
                valid_from=now, valid_until=now + timedelta(days=365),
                confidence=82.0, position_size_suggestion=8.0,
                thesis="Dung Quất 2 đi vào hoạt động gia tăng công suất HRC; cả 3 quỹ lớn đều nắm giữ top 10; biên lợi nhuận tạo đáy và chu kỳ thép phục hồi 2026-2028.",
                catalysts=["FTSE nâng hạng thị trường VN", "Đường sắt tốc độ cao giải ngân", "Thuế chống bán phá giá HRC"],
                risks=["BĐS TQ phục hồi chậm", "Giá quặng sắt biến động"],
                invalidation_conditions=[{"condition_id": "inv_hpg_margin", "description": "Biên lợi nhuận gộp quý tới giảm dưới 8%", "severity": "CRITICAL"}],
                evidence_refs=["evt-steel-01"],
                reasoning_summary="Đồng thuận cao giữa 3 quỹ lớn. P/B 1.3x ở nửa dưới dải lịch sử."
            ),
            Proposal(
                id="MWG-2026-001-v1",
                proposal_group_id="MWG-2026-001",
                ticker="MWG", version=1, status="ACTIVE", action="BUY",
                entry_min=62000.0, entry_max=66000.0,
                target_min=85000.0, target_max=95000.0,
                stop_reference=57000.0, stop_method="fixed_pct",
                horizon_days=365,
                valid_from=now, valid_until=now + timedelta(days=365),
                confidence=78.0, position_size_suggestion=7.0,
                thesis="BHX có lãi mở ra giai đoạn tăng trưởng thứ 2 cho MWG; top holding tại cả 3 quỹ lớn.",
                catalysts=["IPO/gọi vốn DMX/BHX", "Mở rộng ra miền Trung/Bắc"],
                risks=["Chi phí logistics tăng", "Cạnh tranh TMĐT"],
                invalidation_conditions=[{"condition_id": "inv_mwg_bhx", "description": "Doanh thu TB/cửa hàng BHX giảm dưới 1.5 tỷ/tháng", "severity": "CRITICAL"}],
                evidence_refs=["evt-retail-01"],
                reasoning_summary="Đồng thuận 3 quỹ + catalyst BHX cụ thể."
            ),
        ]
        for p in active_proposals:
            if not db.query(Proposal).filter(Proposal.id == p.id).first():
                db.add(p)
        db.commit()
        print("Proposals seeded (2 expired + 2 active).")

        # Seed Positions — 1 active + 2 closed (for track record)
        positions = [
            Position(
                id="pos-hpg-01",
                ticker="HPG", quantity=2000, avg_buy_price=27500.0,
                buy_date=date(2026, 7, 15), fees=110000.0,
                source_proposal_id="HPG-2026-001-v1",
                current_action="HOLD", thesis_health="HEALTHY",
                notes="Mua theo proposal v1, tỷ trọng 5% NAV"
            ),
            Position(
                id="pos-fpt-01",
                ticker="FPT", quantity=500, avg_buy_price=118000.0,
                buy_date=date(2026, 6, 1), fees=59000.0,
                source_proposal_id="FPT-2026-001-v1",
                status="CLOSED", current_action="EXIT", thesis_health="HEALTHY",
                closed_at=now - timedelta(days=15),
                closed_price=142000.0,
                realized_pnl=(142000.0 - 118000.0) * 500 - 59000,
                notes="Chốt lời theo proposal hết hạn"
            ),
            Position(
                id="pos-ctg-01",
                ticker="CTG", quantity=1500, avg_buy_price=33000.0,
                buy_date=date(2026, 5, 15), fees=49500.0,
                source_proposal_id="CTG-2026-001-v1",
                status="CLOSED", current_action="EXIT", thesis_health="HEALTHY",
                closed_at=now - timedelta(days=2),
                closed_price=38500.0,
                realized_pnl=(38500.0 - 33000.0) * 1500 - 49500,
                notes="Chốt lời theo proposal hết hạn"
            ),
        ]
        for p in positions:
            if not db.query(Position).filter(Position.id == p.id).first():
                db.add(p)
        db.commit()
        print("Positions seeded (1 active + 2 closed).")

        # Seed SSI-SCA holdings (sample data)
        ssi_sca_holdings = [
            {"ticker": "VCB", "sector": "Banks", "weight_pct": 9.5, "rank": 1},
            {"ticker": "HPG", "sector": "Materials", "weight_pct": 8.8, "rank": 2},
            {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 7.5, "rank": 3},
            {"ticker": "FPT", "sector": "Information Technology", "weight_pct": 7.2, "rank": 4},
            {"ticker": "CTG", "sector": "Banks", "weight_pct": 6.8, "rank": 5},
            {"ticker": "MBB", "sector": "Banks", "weight_pct": 6.5, "rank": 6},
            {"ticker": "BVH", "sector": "Non-bank Financials", "weight_pct": 5.9, "rank": 7},
            {"ticker": "ACB", "sector": "Banks", "weight_pct": 5.5, "rank": 8},
            {"ticker": "TCB", "sector": "Banks", "weight_pct": 5.2, "rank": 9},
            {"ticker": "VPB", "sector": "Banks", "weight_pct": 4.8, "rank": 10},
        ]
        ssi_sca_snapshot = FundHoldingSnapshot(
            fund_id="SSI-SCA", as_of_date=date(2026, 9, 10),
            source_url="https://www.ssiam.com.vn/fund/ssi-sca",
            holdings_json=ssi_sca_holdings,
            raw_text="SSI-SCA Fund top 10 holdings as of Sep 2026 (sample data)"
        )
        if not db.query(FundHoldingSnapshot).filter(
            FundHoldingSnapshot.fund_id == "SSI-SCA",
            FundHoldingSnapshot.as_of_date == date(2026, 9, 10)
        ).first():
            db.add(ssi_sca_snapshot)

        # Seed DCDS holdings (sample data)
        dcds_holdings = [
            {"ticker": "VCB", "sector": "Banks", "weight_pct": 10.2, "rank": 1},
            {"ticker": "HPG", "sector": "Materials", "weight_pct": 9.5, "rank": 2},
            {"ticker": "BVH", "sector": "Non-bank Financials", "weight_pct": 8.8, "rank": 3},
            {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 8.0, "rank": 4},
            {"ticker": "CTG", "sector": "Banks", "weight_pct": 7.5, "rank": 5},
            {"ticker": "MBB", "sector": "Banks", "weight_pct": 7.2, "rank": 6},
            {"ticker": "FPT", "sector": "Information Technology", "weight_pct": 6.8, "rank": 7},
            {"ticker": "GAS", "sector": "Energy", "weight_pct": 6.2, "rank": 8},
            {"ticker": "NVL", "sector": "Real Estate", "weight_pct": 5.8, "rank": 9},
            {"ticker": "VPB", "sector": "Banks", "weight_pct": 5.2, "rank": 10},
        ]
        dcds_snapshot = FundHoldingSnapshot(
            fund_id="DCDS", as_of_date=date(2026, 9, 10),
            source_url="https://www.dragoncapital.com/individual/funds/dcds/",
            holdings_json=dcds_holdings,
            raw_text="DCDS Fund top 10 holdings as of Sep 2026 (sample data)"
        )
        if not db.query(FundHoldingSnapshot).filter(
            FundHoldingSnapshot.fund_id == "DCDS",
            FundHoldingSnapshot.as_of_date == date(2026, 9, 10)
        ).first():
            db.add(dcds_snapshot)

        print("PYN, SSI-SCA, DCDS Holdings seeded.")

        print("Database seeding completed successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    from app.core.models.schema import init_db
    init_db()
    seed()
