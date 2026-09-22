"""Versioned prompt templates for LLM tasks."""

EVENT_ANALYSIS_VERSION = "1.0"


def event_analysis_prompt(headline: str, summary: str, tickers_str: str) -> str:
    return f"""Bạn là chuyên gia phân tích vĩ mô và chuỗi tác động thị trường chứng khoán Việt Nam.
Sự kiện: {headline}
Nội dung: {summary}
Danh sách cổ phiếu đang theo dõi (quỹ nắm giữ): [{tickers_str}]

Nhiệm vụ:
1. Phân loại sự kiện: FACT, INFERENCE hay FORECAST.
2. Xác định các cổ phiếu trong danh sách theo dõi có thể chịu tác động thực tế (trực tiếp hoặc qua chuỗi cung ứng/ngành).
3. Đưa ra chuỗi tác động nhân quả (causal reasoning) giải thích rõ: Ai hưởng lợi / thiệt hại, cơ chế ra sao?
4. Đánh giá độ tin cậy từ 0-100%.

Trả về JSON theo format:
{{
  "classification": "FACT",
  "entities": ["HPG", "FPT"],
  "causal_links": [
    {{
      "target_ticker": "HPG",
      "direction": "POSITIVE",
      "confidence": 75,
      "mechanism": "Giá thép thế giới tăng -> biên lợi nhuận cải thiện -> doanh thu kỳ vọng tăng"
    }}
  ]
}}"""


PROPOSAL_GENERATION_VERSION = "1.0"


def proposal_generation_prompt(
    ticker: str,
    current_price: float,
    funds_str: str,
    events_str: str,
    fundamentals_str: str,
) -> str:
    return f"""Bạn là hệ thống hỗ trợ quyết định đầu tư dài hạn (trên 1 năm) cho cổ phiếu Việt Nam.
Mã phân tích: {ticker}
Giá hiện tại tham chiếu: {current_price:,.0f} VND
Thông tin nắm giữ của các quỹ lớn: {funds_str}
Sự kiện / tin tức gần đây: {events_str}
Thông số tài chính (FUNDAMENTALS): {fundamentals_str}

Hãy tạo một Investment Proposal toàn diện:
1. Đề xuất action: BUY, WATCH, hoặc AVOID. (Ưu tiên BUY nếu có nhiều quỹ lớn cùng nắm giữ và luận điểm kinh doanh vững).
2. Vùng mua (entry_min, entry_max), vùng mục tiêu (target_min, target_max) dựa trên kỳ vọng tăng trưởng > 1 năm, mức bảo vệ rủi ro (stop_reference).
3. Luận điểm đầu tư (thesis), Catalysts (3 điểm), Risks (3 điểm).
4. Invalidation conditions: Ít nhất 2 điều kiện cụ thể khiến luận điểm này BỊ BÁC BỎ (ví dụ: biên lợi nhuận gộp giảm 2 quý liên tiếp, mất hợp đồng đối tác lớn, hoặc giá thép giảm dưới X).
5. Confidence (0-100), position_size_suggestion (tối đa 10%).

Trả về JSON theo format:
{{
  "action": "BUY",
  "entry_min": {current_price * 0.95:.0f},
  "entry_max": {current_price * 1.02:.0f},
  "target_min": {current_price * 1.20:.0f},
  "target_max": {current_price * 1.35:.0f},
  "stop_reference": {current_price * 0.88:.0f},
  "stop_method": "structural_support",
  "horizon_days": 365,
  "confidence": 78,
  "position_size_suggestion": 5.0,
  "thesis": "Mô tả chi tiết luận điểm tăng trưởng bền vững...",
  "catalysts": ["Xúc tác 1", "Xúc tác 2"],
  "risks": ["Rủi ro 1", "Rủi ro 2"],
  "invalidation_conditions": [
    {{
      "condition_id": "inv_1",
      "description": "Lợi nhuận ròng quý tới giảm hơn 15% so với cùng kỳ",
      "data_source": "financial:net_profit",
      "check_method": "yoy_change",
      "threshold_value": -15.0,
      "comparison": "<",
      "severity": "CRITICAL"
    }}
  ],
  "reasoning_summary": "Tóm lược lý do đưa ra mức giá và hành động..."
}}"""


POSITION_REEVAL_VERSION = "1.0"


def position_reeval_prompt(
    ticker: str,
    avg_buy_price: float,
    current_price: float,
    pnl_pct: float,
    current_thesis: str,
    conditions_summary: str,
    events_summary: str,
) -> str:
    return f"""Bạn là Portfolio Engine đánh giá lại vị thế đang nắm giữ.
Mã: {ticker}
Giá mua trung bình: {avg_buy_price:,.0f} VND
Giá hiện tại: {current_price:,.0f} VND (P&L: {pnl_pct:+.1f}%)
Luận điểm ban đầu: {current_thesis}
Các điều kiện invalidation đã đặt ra: {conditions_summary}
Các sự kiện / tin tức mới phát sinh: {events_summary}

Nhiệm vụ:
1. Kiểm tra xem có điều kiện Invalidation nào đã bị kích hoạt không?
2. Đánh giá sức khỏe luận điểm: HEALTHY, AT_RISK hay INVALIDATED.
3. Đưa ra hành động cập nhật:
   - ADD: Nếu giá điều chỉnh nhưng luận điểm mạnh hơn hoặc xuất hiện catalyst mới.
   - HOLD: Nếu luận điểm nguyên vẹn, giá đang đi đúng kỳ vọng.
   - REDUCE: Nếu đạt một phần mục tiêu và rủi ro gia tăng.
   - EXIT: Nếu luận điểm bị INVALIDATED hoặc chạm ngưỡng bảo vệ nghiêm trọng (kể cả khi chưa chạm stop loss nếu thesis đã hỏng).
4. Đưa ra giá mục tiêu và mức bảo vệ mới (nếu có revision).

Trả về JSON theo format:
{{
  "action": "HOLD",
  "thesis_health": "HEALTHY",
  "invalidation_triggered": false,
  "revised_target_min": {current_price * 1.15:.0f},
  "revised_target_max": {current_price * 1.30:.0f},
  "revised_stop": {current_price * 0.90:.0f},
  "explanation": "Giải thích chi tiết lý do quyết định...",
  "confidence": 80
}}"""
