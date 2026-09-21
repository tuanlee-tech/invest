# Feasibility probes

Các script kiểm tra nguyên liệu thực tế, không phải production ingestion. Chạy theo thứ tự dưới đây, giới hạn vài requests. Output mỗi lần dùng timestamp mới để giữ lịch sử.

## Môi trường đã thử

Windows, Python 3.12. Venv thử nghiệm nằm ngoài repo:
`C:\Users\tuanlee\AppData\Local\Temp\opencode\invest-feasibility`.

Direct dependencies đã dùng: `pypdf==6.19.0`, `requests==2.34.2`, `vnstock==4.0.8`, `pandas==2.3.3`.
Đây là pin phục vụ tái thử, chưa phải production dependency lock.

Ví dụ PowerShell từ root repo với Python trong venv đã cài dependencies:

```powershell
python research/probes/fund_materials.py
# Retry riêng một mẫu khi cần:
python research/probes/fund_materials.py --only vesaf-202607
python research/probes/market_materials.py
# Thay hai đường dẫn bằng các run thực tế vừa tạo:
python research/probes/check_samples.py research/probes/runs/<fund-run> research/probes/runs/<market-run>
```

`fund_materials.py`: sáu PDF từ link chính thức, HTTP status, SHA-256, PDF và text. Text extractable không chứng minh parsing holdings chính xác.

`market_materials.py`: ba OHLCV, một income statement và một ratios; guest access, không thêm API key. Tắt optional agent-instruction bootstrap bằng env do package hỗ trợ. Không vượt hoặc né hạn mức; provider có thể lỗi hoặc thay schema.

`check_samples.py`: kiểm tra layout cụ thể tháng 8/2026, overlap và invariants giá. Company-name mapping VEIL là mapping minh bạch của mẫu, cần thay bằng security master trong sản phẩm. Exit code khác 0 nếu checks thất bại. Không chứng minh giá đúng so với nguồn khác.

Raw PDFs/CSVs/text nằm trong `runs/` gitignored để giữ local; không tự phát hành lại tài liệu nguồn.

## OpenCode smoke tests đã chạy

```powershell
opencode --version
opencode models opencode
opencode run --pure -m opencode/big-pickle --title feasibility-smoke --format json "Do not use tools or access files. This is a synthetic test, not market data. Fund A reports stock TEST at 8 percent in June and 10 percent in July, with no share count. Return JSON only with increased_weight:boolean, confirmed_purchase:boolean, reason_vi:string. Explain in Vietnamese why weight change alone cannot prove buying."
opencode run --pure -m opencode/mimo-v2.5-free --title feasibility-json-smoke --format json "Do not use tools or access files. Synthetic fixture only, not real market data: Fund A TEST weight June 8 percent July 10 percent, no share count. Return exactly one JSON object and nothing else, no markdown: increased_weight boolean, confirmed_purchase boolean, reason_vi string. Explain in Vietnamese why higher weight cannot prove buying. Do not invent other evidence."
```

Hai inference chạy với working directory thư mục temp bên ngoài repo; không phải child agent được giao triển khai task. `--format json` là format event stream của CLI, không bảo đảm nội dung model là strict JSON. Phải kiểm tra riêng trường text.

Xem kết quả và giới hạn tại [báo cáo feasibility](../fund-following-feasibility.md).
