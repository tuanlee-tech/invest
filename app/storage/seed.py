"""Seed initial sample data to get the system operational immediately"""
from datetime import datetime, date
from app.core.models.schema import get_db, Fund, FundHoldingSnapshot, Security, Proposal, Position, Event, SessionLocal

def seed():
    db = SessionLocal()
    try:
        # Create Funds
        funds = [
            Fund(id="VEIL", name="Vietnam Enterprise Investments Limited", manager="Dragon Capital", fund_type="closed_end"),
            Fund(id="VESAF", name="VinaCapital Strategic Growth Equity Fund", manager="VinaCapital", fund_type="open_end"),
            Fund(id="VCBF-BCF", name="Quỹ đầu tư cổ phiếu hàng đầu VCBF", manager="VCBF", fund_type="open_end"),
            Fund(id="PYN", name="PYN Elite Fund", manager="PYN Fund Management", fund_type="specialized"),
        ]
        for f in funds:
            if not db.query(Fund).filter(Fund.id == f.id).first():
                db.add(f)
        db.commit()
        print("Funds seeded.")

        # Seed Fund Holding Snapshots (verified sample data from our probe)
        snapshots = [
            FundHoldingSnapshot(
                fund_id="VESAF",
                as_of_date=date(2026, 8, 31),
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
                fund_id="VCBF-BCF",
                as_of_date=date(2026, 8, 31),
                holdings_json=[
                    {"ticker": "MBB", "sector": "Banks", "weight_pct": 9.21, "rank": 1},
                    {"ticker": "MWG", "sector": "Consumer Discretionary", "weight_pct": 6.06, "rank": 2},
                    {"ticker": "MSN", "sector": "Consumer Staples", "weight_pct": 5.89, "rank": 3},
                    {"ticker": "CTG", "sector": "Banks", "weight_pct": 5.77, "rank": 4},
                    {"ticker": "HPG", "sector": "Materials", "weight_pct": 5.76, "rank": 5},
                ]
            ),
            FundHoldingSnapshot(
                fund_id="VEIL",
                as_of_date=date(2026, 8, 30),
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
            )
        ]
        for s in snapshots:
            if not db.query(FundHoldingSnapshot).filter(
                FundHoldingSnapshot.fund_id == s.fund_id,
                FundHoldingSnapshot.as_of_date == s.as_of_date
            ).first():
                db.add(s)
        db.commit()
        print("Fund Holding Snapshots seeded.")

        # Seed Securities
        all_tickers = ["HPG", "MWG", "CTG", "MBB", "VCB", "FPT", "TCB", "ACB", "VIC", "VHM", "BID", "VPB", "MSN", "CTR", "BVH"]
        for t in all_tickers:
            if not db.query(Security).filter(Security.ticker == t).first():
                db.add(Security(ticker=t, name=t, exchange="HOSE", in_fund_universe=True))
        db.commit()
        print("Securities seeded.")

        # Seed sample Events with causal links
        events = [
            Event(
                id="evt-steel-01",
                occurred_at=datetime.utcnow(),
                source_type="news",
                source_url="https://cafef.vn/thep-hoi-phuc.html",
                source_name="CafeF",
                headline="Giá thép xây dựng thế giới tăng mạnh tuần thứ 3 liên tiếp, xuất khẩu khởi sắc",
                summary="Giá phôi thép và HRC tại châu Á bật tăng hơn 6% trong tháng qua nhờ nhu cầu hạ tầng và biện pháp phòng vệ thương mại có hiệu lực.",
                classification="FACT",
                entities=["HPG"],
                causal_links=[
                    {
                        "target_ticker": "HPG",
                        "direction": "POSITIVE",
                        "confidence": 85,
                        "mechanism": "Giá bán tăng + Dung Quất 2 chạy tối đa công suất -> Doanh thu và biên gộp phục hồi mạnh"
                    }
                ]
            ),
            Event(
                id="evt-retail-01",
                occurred_at=datetime.utcnow(),
                source_type="news",
                source_url="https://vnexpress.net/bach-hoa-xanh-co-lai.html",
                source_name="VnExpress",
                headline="Bách Hóa Xanh vượt mốc 2.500 cửa hàng, bắt đầu có lãi ròng toàn chuỗi",
                summary="Chuỗi bán lẻ thực phẩm của Thế Giới Di Động ghi nhận EBITDA dương liên tiếp 3 quý và chuẩn bị kế hoạch mở rộng ra miền Bắc.",
                classification="FACT",
                entities=["MWG"],
                causal_links=[
                    {
                        "target_ticker": "MWG",
                        "direction": "POSITIVE",
                        "confidence": 80,
                        "mechanism": "BHX chuyển từ điểm hòa vốn sang sinh lời -> Định giá toàn tập đoàn được re-rate"
                    }
                ]
            )
        ]
        for e in events:
            if not db.query(Event).filter(Event.id == e.id).first():
                db.add(e)
        db.commit()
        print("Events seeded.")

        # Seed sample Proposals (Versioned)
        proposals = [
            Proposal(
                id="HPG-2026-001-v1",
                proposal_group_id="HPG-2026-001",
                ticker="HPG",
                version=1,
                status="ACTIVE",
                action="BUY",
                entry_min=27000.0,
                entry_max=29000.0,
                target_min=36000.0,
                target_max=40000.0,
                stop_reference=25000.0,
                stop_method="structural_support",
                horizon_days=365,
                valid_from=datetime.utcnow(),
                valid_until=datetime.utcnow() + datetime.resolution * 365,
                confidence=82.0,
                position_size_suggestion=8.0,
                thesis="Dung Quất 2 đi vào hoạt động gia tăng công suất HRC; cả 3 quỹ lớn (VEIL, VESAF, VCBF-BCF) đều nắm giữ vị thế top 10; biên lợi nhuận tạo đáy và chu kỳ thép phục hồi kéo dài 2026-2028.",
                catalysts=[
                    "FTSE nâng hạng thị trường Việt Nam kích hoạt dòng vốn ngoại",
                    "Dự án đường sắt tốc độ cao và hạ tầng giao thông lớn giải ngân mạnh",
                    "Thuế chống bán phá giá HRC bảo hộ sản xuất trong nước"
                ],
                risks=[
                    "Bất động sản Trung Quốc phục hồi chậm gây áp lực giá thép thế giới",
                    "Giá quặng sắt và than cốc đầu vào biến động bất lợi"
                ],
                invalidation_conditions=[
                    {
                        "condition_id": "inv_hpg_margin",
                        "description": "Biên lợi nhuận gộp quý tới giảm dưới 8%",
                        "severity": "CRITICAL"
                    }
                ],
                evidence_refs=["evt-steel-01", "VESAF-2026-08", "VEIL-2026-08", "VCBF-BCF-2026-08"],
                reasoning_summary="Đồng thuận cao giữa các quỹ đầu tư lớn. Định giá P/B hiện tại 1.3x nằm ở nửa dưới dải lịch sử 10 năm trong khi ROE đang hồi phục lên 18%."
            ),
            Proposal(
                id="MWG-2026-001-v1",
                proposal_group_id="MWG-2026-001",
                ticker="MWG",
                version=1,
                status="ACTIVE",
                action="BUY",
                entry_min=62000.0,
                entry_max=66000.0,
                target_min=85000.0,
                target_max=95000.0,
                stop_reference=57000.0,
                stop_method="fixed_pct",
                horizon_days=365,
                valid_from=datetime.utcnow(),
                valid_until=datetime.utcnow() + datetime.resolution * 365,
                confidence=78.0,
                position_size_suggestion=7.0,
                thesis="BHX có lãi mở ra giai đoạn tăng trưởng thứ 2 cho MWG; top holding tại cả 3 quỹ lớn với tỷ trọng từ 6-7%; sức mua hàng tiêu dùng và điện máy phục hồi.",
                catalysts=[
                    "IPO hoặc gọi vốn riêng lẻ chuỗi Điện Máy Xanh / Bách Hóa Xanh",
                    "Mở rộng hệ thống chuỗi ra miền Trung và miền Bắc"
                ],
                risks=[
                    "Chi phí logistics gia tăng khi mở rộng địa bàn",
                    "Cạnh tranh gay gắt từ thương mại điện tử và siêu thị mini khác"
                ],
                invalidation_conditions=[
                    {
                        "condition_id": "inv_mwg_bhx",
                        "description": "Doanh thu trung bình/cửa hàng BHX giảm dưới 1.5 tỷ/tháng",
                        "severity": "CRITICAL"
                    }
                ],
                evidence_refs=["evt-retail-01", "VESAF-2026-08", "VEIL-2026-08", "VCBF-BCF-2026-08"],
                reasoning_summary="Sự đồng thuận của 3 quỹ độc lập cùng với catalyst cụ thể từ BHX tạo điểm tựa đầu tư trung-dài hạn vững chắc."
            )
        ]
        for p in proposals:
            if not db.query(Proposal).filter(Proposal.id == p.id).first():
                db.add(p)
        db.commit()
        print("Proposals seeded.")

        # Seed sample active Position
        positions = [
            Position(
                id="pos-hpg-01",
                ticker="HPG",
                quantity=2000,
                avg_buy_price=27500.0,
                buy_date=date(2026, 7, 15),
                fees=110000.0,
                source_proposal_id="HPG-2026-001-v1",
                current_action="HOLD",
                thesis_health="HEALTHY",
                notes="Mua theo proposal v1, tỷ trọng 5% NAV"
            )
        ]
        for p in positions:
            if not db.query(Position).filter(Position.id == p.id).first():
                db.add(p)
        db.commit()
        print("Positions seeded.")

        print("Database seeding completed successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    from app.core.models.schema import init_db
    init_db()
    seed()
