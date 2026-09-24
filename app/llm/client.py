import json
import logging
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class OpenCodeClient:
    """Wrapper to interact with OpenCode CLI for local-first, zero-paid LLM operations.

    Supports fallback to local Ollama if available and OpenCode fails.
    """

    def __init__(self, default_model: str = None, models: List[str] = None):
        self.default_model = default_model or settings.OPENCODE_DEFAULT_MODEL
        self.models = models or settings.OPENCODE_FREE_MODELS
        self.bin = settings.OPENCODE_BIN

        # Check for Ollama availability
        self.ollama_available = shutil.which("ollama") is not None
        self.ollama_models = ["llama3", "llama3.1", "gemma2", "qwen2.5"]
        if self.ollama_available:
            logger.info("Ollama detected as fallback LLM provider")
        else:
            logger.info("Ollama not available, using OpenCode free models only")

    def run_prompt(
        self, prompt: str, model: Optional[str] = None, timeout: int = 120
    ) -> str:
        """Execute a prompt through OpenCode CLI and return raw text response."""
        chosen_model = model or self.default_model
        models_to_try = [chosen_model] + [
            m for m in self.models if m != chosen_model
        ]

        last_error = None
        for m in models_to_try:
            started = time.monotonic()
            try:
                cmd = [
                    self.bin,
                    "run",
                    "--pure",
                    "-m",
                    m,
                    "--title",
                    "invest-task",
                    "--format",
                    "json",
                    prompt,
                ]
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                )
                latency_ms = int((time.monotonic() - started) * 1000)

                if res.returncode != 0:
                    last_error = (
                        f"Exit code {res.returncode}: {res.stderr.strip()}"
                    )
                    logger.warning(
                        "llm provider=opencode model=%s latency_ms=%d status=error reason=%s",
                        m, latency_ms, last_error[:300],
                    )
                    continue

                # Parse JSON stream lines to find 'text' events
                output_texts = []
                for line in res.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        evt = json.loads(line)
                        if evt.get("type") == "text":
                            part_text = evt.get("part", {}).get("text", "")
                            if part_text:
                                output_texts.append(part_text)
                    except json.JSONDecodeError:
                        continue

                full_text = "".join(output_texts).strip()
                if full_text:
                    logger.info(
                        "llm provider=opencode model=%s latency_ms=%d status=ok chars=%d",
                        m, latency_ms, len(full_text),
                    )
                    return full_text
                else:
                    last_error = "Empty text output from model stream"
                    logger.warning(
                        "llm provider=opencode model=%s latency_ms=%d status=error reason=%s",
                        m, latency_ms, last_error,
                    )
            except Exception as e:
                latency_ms = int((time.monotonic() - started) * 1000)
                last_error = str(e)
                logger.warning(
                    "llm provider=opencode model=%s latency_ms=%d status=error reason=%s",
                    m, latency_ms, last_error[:300],
                )

        # Try Ollama fallback if available
        if self.ollama_available:
            logger.info("Trying Ollama fallback...")
            for m in self.ollama_models:
                try:
                    return self._run_ollama(prompt, m, timeout)
                except Exception as e:
                    logger.warning(f"Ollama model {m} failed: {e}")

        raise RuntimeError(f"All models failed. Last error: {last_error}")

    def _run_ollama(self, prompt: str, model: str, timeout: int = 120) -> str:
        """Run prompt via Ollama CLI."""
        cmd = [
            "ollama",
            "run",
            model,
            prompt,
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )

        if res.returncode != 0:
            raise RuntimeError(f"Ollama exit code {res.returncode}: {res.stderr.strip()}")

        output = res.stdout.strip()
        if not output:
            raise RuntimeError("Empty output from Ollama")

        return output

    def run_structured_json(
        self, prompt: str, model: Optional[str] = None, timeout: int = 120
    ) -> Dict[str, Any]:
        """Execute a prompt expecting pure JSON and safely extract the dict."""
        json_instruction = (
            prompt
            + "\n\nQUAN TRỌNG: Chỉ trả về duy nhất 1 JSON object hợp lệ. "
            "Không kèm theo markdown ```json, không giải thích mở đầu hay kết luận."
        )
        raw = self.run_prompt(json_instruction, model=model, timeout=timeout)

        # Clean code fences if model enclosed it anyway
        cleaned = re.sub(
            r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE
        )
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

        # Find first { and last }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                f"Failed to decode JSON from output: {raw[:200]}... Error: {exc}"
            )
            # Try basic recovery or raise
            raise ValueError(
                f"Model response could not be parsed as JSON: {raw[:200]}"
            )

    # -------------------------------------------------------------
    # Domain Specific LLM Tasks
    # -------------------------------------------------------------

    def analyze_event_impact(
        self, headline: str, summary: str, watched_tickers: List[str]
    ) -> Dict[str, Any]:
        """Extract entities and causal impact chain for an event against watched tickers."""
        tickers_str = ", ".join(watched_tickers)
        prompt = f"""Bạn là chuyên gia phân tích vĩ mô và chuỗi tác động thị trường chứng khoán Việt Nam.
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
        return self.run_structured_json(prompt)

    def generate_proposal(
        self,
        ticker: str,
        current_price: float,
        holdings_info: List[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
        fundamentals: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a full versioned investment proposal with Bull/Bear and invalidation conditions."""
        funds_str = json.dumps(holdings_info, ensure_ascii=False)
        events_str = json.dumps(
            [e.get("headline") for e in recent_events[:5]], ensure_ascii=False
        )
        fundamentals_str = json.dumps(fundamentals, ensure_ascii=False, default=str)

        prompt = f"""Bạn là hệ thống hỗ trợ quyết định đầu tư dài hạn (trên 1 năm) cho cổ phiếu Việt Nam.
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
        return self.run_structured_json(prompt)

    def reevaluate_position(
        self,
        ticker: str,
        avg_buy_price: float,
        current_price: float,
        current_thesis: str,
        invalidation_conditions: List[Dict[str, Any]],
        new_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Re-evaluate an active portfolio position. Yields ADD, HOLD, REDUCE, or EXIT."""
        pnl_pct = ((current_price - avg_buy_price) / avg_buy_price) * 100
        events_summary = json.dumps(
            [e.get("headline") for e in new_events[:5]], ensure_ascii=False
        )
        conditions_summary = json.dumps(
            invalidation_conditions, ensure_ascii=False
        )

        prompt = f"""Bạn là Portfolio Engine đánh giá lại vị thế đang nắm giữ.
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
        return self.run_structured_json(prompt)
