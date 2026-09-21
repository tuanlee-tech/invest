# Kiểm chứng nguyên liệu — web chọn cổ phiếu theo quỹ

Ngày kiểm tra: **21/09/2026**. Đây là báo cáo feasibility vòng 1, không phải architecture hay implementation plan đã chốt.

## 1. Yêu cầu đã xác nhận

- Người dùng giao việc chọn quỹ cho agent.
- Cổ phiếu Việt Nam, thời gian nắm giữ trên một năm.
- Chỉ tìm trong tập mã được nhóm quỹ theo dõi công bố nắm giữ; không scan toàn thị trường để tìm cơ hội.
- Web localhost; OpenCode + provider/model miễn phí.
- Kiểm thử nguồn và thành phần trước khi xây sản phẩm.
- Mục tiêu: thu hẹp lựa chọn bằng nghiên cứu công khai của quỹ, sau đó kiểm tra mức giá và chất lượng hiện tại.

## 2. Kết luận

**GO cho PoC dữ liệu shortlist theo quỹ. Chưa đủ bằng chứng để chốt web tự động xếp hạng “giá tốt” end-to-end.**

Đã chứng minh tại máy Windows hiện tại:

1. Tải sáu factsheet của ba đơn vị quản lý độc lập, hai kỳ/quỹ; trích được text bằng thư viện miễn phí, chưa cần OCR/model.
2. Trích bảng holdings tháng 8: VESAF 10 mã, VCBF-BCF 5 mã, VEIL 10 doanh nghiệp. Có ba mã giao nhau trong mẫu.
3. Lấy được OHLCV hơn một năm cho ba mã thử và BCTC bốn năm của FPT ở chế độ guest.
4. OpenCode gọi được hai model miễn phí; CLI báo cost=0 cho cả hai lần. Chưa audit mọi background request/billing hay đo quota lâu dài.

Chưa chứng minh: toàn bộ danh mục quỹ, lịch sử liên tục trên một năm của holdings, giá vốn/mua bán thực tế, độ đúng độc lập của dữ liệu thị trường, valuation đáng tin cậy, nguồn dự phòng độc lập, benchmark LLM đọc báo cáo thật, tích hợp web, macOS/Ubuntu.

## 3. Nhóm quỹ lựa chọn

Chọn theo chiến lược và khả năng kiểm chứng công bố, không tuyên bố đây là bảng xếp hạng các quỹ lớn nhất hay sinh lời tốt nhất.

| Ưu tiên | Quỹ / đơn vị | Lý do phù hợp | Kết quả nguồn |
|---|---|---|---|
| Chính | **VEIL / Dragon Capital** | Mục tiêu tăng trưởng vốn trung-dài hạn, doanh nghiệp đầu ngành, nghiên cứu growth/value | PDF tháng 7 và 8/2026 tải và đọc được; top 10 bằng tên doanh nghiệp |
| Chính | **VESAF / VinaCapital** | Nền tảng tốt, tăng trưởng nhiều năm, định giá hợp lý hoặc tài sản chưa được đánh giá đúng | PDF tháng 7 và 8/2026 đọc được; top 10 bằng ticker; có commentary về luận điểm và thay đổi vị thế |
| Chính | **VCBF-BCF / VCBF** | Cổ phiếu vốn hóa lớn/thanh khoản cao, bổ sung một đội ngũ quản lý độc lập | PDF tháng 7 và 8/2026 đọc được; chỉ top 5 |
| Có điều kiện | **PYN Elite / PYN** | Chiến lược value dài hạn, công khai luận điểm từng doanh nghiệp | HTML đọc được nhưng có dấu hiệu trộn nội dung cũ/mới; cần factsheet theo kỳ trước khi tính điểm |

V1 research bắt đầu với ba quỹ chính; thêm PYN khi kiểm chứng snapshot cùng kỳ. Không cần tăng số quỹ bằng cách lấy nhiều quỹ cùng một công ty quản lý. Khi bổ sung VEOF/VCBF-MGF hoặc quỹ khác, số đơn vị quản lý độc lập là metric riêng với số quỹ.

### Nguồn chính thức

- VESAF: https://vinacapital.com/investment-solutions/onshore-funds/vesaf/
- VCBF: https://www.vcbf.com/don-tai-lieu-quy/ban-thong-tin-quy/
- VEIL: https://www.dragoncapital.com/individual/funds/veil/
- PYN strategy: https://www.pyn.fi/pyn-elite/
- PYN portfolio: https://www.pyn.fi/en/pyn-elite-fund/portfolio/

## 4. Thử tải và đọc báo cáo thật

Môi trường: Python 3.12, pypdf **6.19.0**, requests **2.34.2**, Windows. URL PDF chính xác nằm trong `probes/fund_materials.py`.

| Mẫu | HTTP cuối | Trang | Số ký tự text | Ghi chú |
|---|---:|---:|---:|---|
| VESAF 08/2026 | 200 | 2 | 11.940 | Top 10 và commentary đọc được |
| VESAF 07/2026 | 200 | 2 | 10.119 | Lần đầu connection reset; retry riêng một lần thành công |
| VCBF-BCF 08/2026 | 200 | 1 | 2.692 | Top 5; công bố trên index ngày 17/09 |
| VCBF-BCF 07/2026 | 200 | 1 | 2.685 | Top 5; công bố trên index ngày 18/08 |
| VEIL 08/2026 | 200 | 3 | 10.042 | Top 10; tên công ty cần map sang security master |
| VEIL 07/2026 | 200 | 3 | 10.309 | Top 10; có thêm text layout không liên quan |

Files gốc, text và SHA-256 lưu local trong `probes/runs/`, gitignored:
- `20260921T133940135683Z/`: đợt đầu và lỗi VESAF tháng 7.
- `20260921T134152456547Z/`: retry VESAF tháng 7.

### Kết quả overlap có thể tái lập

`check_samples.py` trích bảng bằng regex theo layout cụ thể và map thủ công mười tên doanh nghiệp VEIL. Đây là parser mẫu, chưa phải parser tổng quát hoặc security master đã kiểm chứng.

| Mã | VESAF (% NAV) | VCBF-BCF (% NAV) | VEIL (% NAV) |
|---|---:|---:|---:|
| CTG | 5,5 | 5,77 | 3,8 |
| HPG | 5,9 | 5,76 | 3,7 |
| MWG | 6,0 | 6,06 | 7,0 |

Nguồn: trang 1 của ba factsheet 08/2026 nêu trên. VESAF/VCBF ghi 31/08/2026; VEIL ghi kỳ August 2026 nhưng phần price/NAV ghi 30/08/2026. Phải lưu nguyên date semantics, không tự sửa thành cùng ngày.

Đây là **mẫu chứng minh phép lọc**, không phải shortlist đầu tư đã nghiên cứu. Không suy ra các quỹ đang muốn mua hôm nay hoặc các mã đang rẻ.

### Các lỗi dữ liệu phát hiện

- HTML VEIL hiển thị top holdings 30/06/2026 trong khi PDF mới là tháng 8. Không lấy ngày NAV mới nhất làm ngày danh mục.
- PYN ghi updated 10/09/2026 nhưng trang có nhiều khối thông tin mang số liệu 2023/2024/2025 và tỷ trọng không thể mặc nhiên ghép thành một danh mục đồng thời. Cần đối chiếu báo cáo theo kỳ trước khi ingest holdings.
- VCBF chỉ công bố top 5 trong factsheet: thiếu một mã không chứng minh quỹ không sở hữu hoặc đã bán.
- Tăng tỷ trọng không chứng minh mua thêm. Chỉ gắn nhãn “quỹ công bố mua/tăng vị thế” khi có lời công bố cụ thể hoặc share count đã điều chỉnh corporate action; không tự suy ra giá vốn.
- VESAF commentary tháng 8 trang 2 có mô tả tăng vị thế MWG và vị thế GAS mới. Đây là phát biểu của quỹ về giai đoạn trước, không phải giao dịch realtime.

## 5. Kiểm thử giá và tài chính miễn phí

Installed **vnstock 4.0.8**, pandas **2.3.3**, source thực tế trả về **KBS**. Không đăng ký hoặc thêm API key trong lượt thử này.

Tài liệu chính thức đọc ngày 21/09:
- https://vnstocks.com/docs/vnstock/gioi-thieu-vnstock (trang ghi 4.0.6).
- https://vnstocks.com/docs/vnstock/du-lieu-thi-truong-market-data
- https://vnstocks.com/docs/vnstock/phan-tich-co-ban-fundamental

| Probe | Kết quả | Đánh giá |
|---|---|---|
| OHLCV FPT, SHS, ACV từ 01/09/2025–18/09/2026, mặc định | Mỗi mã chỉ 100 dòng, bắt đầu 24/04/2026 | Có response không đồng nghĩa đủ coverage |
| Cùng truy vấn với `count=400` | Mỗi mã 260 dòng, 03/09/2025–18/09/2026 | PASS availability; chưa đối chiếu lịch giao dịch độc lập |
| FPT annual income statement | 25 dòng chỉ tiêu, 2022–2025; metadata hợp nhất/kiểm toán | PASS availability; đơn vị cần xác minh |
| FPT ratios | 58 dòng; cột `2026-Q2`, `2025-Q4`, `2026-Q1`, `2025-Q4_1` | FAIL readiness cho valuation: trùng kỳ và thứ tự không chuẩn |

Offline checks cho cả ba series giá: ngày không trùng, tăng dần, giá dương, volume không âm, OHLC bounds hợp lệ, không thiếu OHLCV — **18/18 điều kiện đạt**. Chưa xác nhận giá điều chỉnh, units, exchange hiện tại, missing sessions hay độ đúng của giá so với nguồn khác.

Evidence: `probes/runs/market-20260921T134116815916Z/` và `market-20260921T134156036588Z/`. CSV giữ dữ liệu; `results.json` giữ source/params và metadata.

Free coverage theo docs: guest BCTC 4 kỳ; có API key miễn phí tối đa 8 kỳ và tối đa 60 requests/phút. Những hạn mức có key chưa thử. Historical valuation analytics được website phân loại Sponsor; không đưa vào golden path miễn phí.

Để đánh giá trên một năm: ưu tiên BCTC năm và dữ liệu mới nhất, kiểm tra ngành riêng biệt; bốn quý không đủ tự động suy ra lịch sử tăng trưởng dài hạn. Không lấy P/E tại kỳ báo cáo làm P/E hiện tại nếu chưa cập nhật giá và shares/EPS tương ứng.

Package có chức năng tự ghi agent instructions khi import; probe dùng env opt-out do chính package cung cấp. Không gọi setup/upgrade sponsor.

## 6. Kiểm thử OpenCode miễn phí

Local CLI **1.18.23**, `opencode models opencode` liệt kê model; docs chính thức:
- https://opencode.ai/docs/zen/ (pricing free và limited-time).
- https://opencode.ai/docs/providers/

Hai lệnh `opencode run --pure`, chỉ định model và title, chạy ngoài repo; chỉ đưa synthetic fixture, yêu cầu không dùng tools/files.

Fixture: quỹ giả định A có mã TEST tăng tỷ trọng 8% → 10%, không có share count. Expected: increased_weight=true, confirmed_purchase=false, lý do bằng tiếng Việt.

| Model | Request | Nội dung | Strict JSON | CLI step cost |
|---|---|---|---|---:|
| `opencode/big-pickle` | Thành công | Hai boolean đúng, lý do chính đúng | FAIL: code fence và văn bản ngoài JSON | 0 |
| `opencode/mimo-v2.5-free` | Thành công | Hai boolean đúng; ví dụ “rebalancing” trong lời giải chưa chính xác/rõ ràng | PASS định dạng quan sát được; chưa benchmark schema tự động | 0 |

Session receipts: `ses_f3bcfebeaffe68nQwLFVr4ooPO`, `ses_f3bcc5d30ffen9FnGOFnteTMqB`.

Kết luận: chạy free inference qua OpenCode trên máy này khả thi; chưa chứng minh inference với tài khoản mới không billing, không có route dự phòng độc lập đã thử. Hai model cùng Zen không phải hai provider độc lập. Không mặc định toàn bộ Zen miễn phí; không tự chuyển sang paid model khi free lỗi. Free offers có thể kết thúc.

Trước tích hợp web: test extraction/citation trên báo cáo được phép gửi tới remote provider, schema validation, từ chối thiếu evidence, timeout/quota và cách đặt model cho background tasks. GPU không cần cho route remote đã thử; local CPU route chưa benchmark.

## 7. Terms và phạm vi dùng dữ liệu

- Public download thành công không đồng nghĩa có quyền redistribute hoặc gửi toàn bộ tài liệu đến dịch vụ AI.
- VEIL PDF trang 3 có điều khoản hạn chế phân phối cho bên thứ ba. Giữ PDF local; chưa gửi các PDF này vào model remote. Cần làm rõ cách dùng trích đoạn/dữ liệu với remote AI trước production.
- Vnstock website hiện nêu community license cho cá nhân/học tập/nghiên cứu, không mặc định MIT như README cũ. License phần mềm không cấp quyền dữ liệu KBS. Terms upstream và nhu cầu lưu/cache cần kiểm tra riêng.
- Nguồn quỹ có thể thay layout, gián đoạn hoặc sửa báo cáo: lưu original hash, ngày retrieval và version; không overwrite snapshot cũ.

## 8. Quyết định capability sơ bộ trong phạm vi mới

| Capability | Quyết định | Cơ sở / điều kiện |
|---|---|---|
| PDF text extraction | REUSE pypdf | Sáu mẫu đọc được; benchmark layout/OCR sau |
| Giá/fundamentals | ADAPT vnstock | Live guest thành công; bọc units, date, period và source metadata |
| Luận điểm quỹ | ADAPT nội dung công bố có provenance | Tách lời quỹ, dự báo quỹ và suy luận model |
| Free analysis | ADAPT OpenCode | CLI smoke thành công, cần output validation và terms phù hợp |
| Fund identity/holdings snapshots/overlap | BUILD phần domain mỏng, provisional | Rules đặc thù top-N và manager independence; còn cần so sánh thư viện fund-data trước chốt |
| Valuation dài hạn | DEFER kết luận chọn engine | Ratios chưa sạch, units/current basis chưa xác minh |
| Portfolio engine/multi-agent debate/backtest toàn diện | DEFER | Chưa phục vụ câu hỏi hẹp ở vòng đầu |
| UI/storage/framework | DEFER lựa chọn | Chốt sau data gate, không cần cloud database cho probe |

## 9. Data gate trước khi xây web

1. **Holdings:** ba đơn vị độc lập, tối thiểu ba kỳ liên tiếp/quỹ; kiểm tra thủ công toàn bộ hàng được dùng. Hiện hai kỳ/quỹ tải được, bảng tự động mới kiểm tra tháng 8.
2. **Dài hạn:** có ít nhất 12 kỳ để tính “nắm giữ bền”; thiếu thì hiển thị “chưa đủ lịch sử”, không suy diễn từ hai kỳ.
3. **Chất lượng tài chính:** kiểm tra income/balance/cash flow cho ít nhất một ngân hàng và hai doanh nghiệp phi tài chính; đối chiếu units, kỳ, restatement và publication dates với báo cáo gốc.
4. **Định giá:** tính lại current P/E hoặc P/B phù hợp ngành bằng input xác định; xử lý lỗ, pha loãng, corporate actions; không định nghĩa “rẻ” bằng mức giảm giá đơn thuần.
5. **Provider fallback:** thử ít nhất một đường dữ liệu độc lập hoặc import tài liệu/CSV có provenance; không coi đổi library nhưng cùng KBS là fallback độc lập.
6. **LLM:** bộ 10–20 case tiếng Việt trên evidence hợp lệ; không sai số quan trọng, mọi assertion chính có nguồn, schema valid sau tối đa một repair, thiếu evidence phải từ chối. Smoke test hiện tại chưa đạt gate này.
7. **Free path:** thử fresh setup, xác nhận credentials/quota và background model không tạo paid dependency. Có báo lỗi rõ thay vì silent paid fallback.

Sau các gate mới lập compatibility matrix hoàn chỉnh, đề xuất kiến trúc localhost và implementation plan. Mốc sản phẩm đầu tiên: quỹ → snapshot công bố → overlap → kiểm tra giá/chất lượng → giải thích → watchlist. Chưa có UI/server production trong lượt feasibility này.
