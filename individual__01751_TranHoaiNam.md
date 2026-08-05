# Member Role Report — Day 9: Multi Agent A2A

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình. Không sao chép nguyên báo cáo chung hoặc báo cáo của thành viên khác. Thay nội dung trong dấu `[ ]` và xóa các dòng hướng dẫn không cần thiết trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | [Trần Hoài Nam]  |
| MSSV            | [01751]       |
| Khóa/Lớp        | [K3]         |
| Vai trò chính   | [Xây dựng Multi-Agent System & Policy Engine]    |
| Ngày hoàn thành | [2026-05@08] |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Load Dữ liệu & Tra cứu CSV | `main.py` / Data Loader | Files CSV Olist (`data/`) | DataFrames đã index | Hoàn thành |
| Multi-Agent Policy Engine | `main.py` / `process_case()` | Ticket JSON (`input/input/`) | 50 Output JSON (`output/`) | Hoàn thành |
| Evidence & Trace Generator | `main.py` / Log Writer | Kết quả đánh giá | `trace.jsonl` & `metadata.json` | Hoàn thành |
### Việc hỗ trợ ngoài phạm vi chính
| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Sửa lỗi đường dẫn linh hoạt | Module Data Path | Khắc phục `FileNotFoundError` khi chạy từ các thư mục khác nhau |
| Cập nhật tài liệu kiến trúc | `architecture.md` | Hoàn thiện sơ đồ luồng Hand-off và phân vai Agent |
## 3. Kết quả theo vai trò
| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Phân loại 6 quy tắc EC_POLICY_V1 | `main.py` / `process_case()` | 50 file JSON trong `output/` | `python main.py` |
| Tạo Evidence ID chuẩn | `main.py` / Grounding logic | Evidence IDs khớp dữ liệu thật | So sánh ID với file CSV |
| Ghi Log Trace & Metadata | `logging/trace.jsonl`, `metadata.json` | Lịch sử chạy 50 cases | Đọc file log trong `logging/` |
**Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:**
Đã xử lý thành công toàn bộ 50 ticket khiếu nại (`EC_001.json` đến `EC_050.json`), xuất ra 50 file JSON tuân thủ chuẩn Output Schema với tỉ lệ chính xác 100%, không bị lỗi false positive về Evidence ID.
## 4. Giải thích phần kỹ thuật đã thực hiện
### Vấn đề cần giải quyết
Xây dựng pipeline điều tra tự động các khiếu nại thương mại điện tử dựa trên bằng chứng có thể kiểm chứng từ 9 bảng dữ liệu Olist, áp dụng chính xác quy tắc `EC_POLICY_V1` để đưa ra quyết định hoàn tiền và bên chịu trách nhiệm.
### Cách triển khai
- **Order & Delivery Logic**: So sánh mốc `order_delivered_customer_date` với `order_estimated_delivery_date`. Nếu trễ, kiểm tra `order_delivered_carrier_date` với `shipping_limit_date` để xác định lỗi do Seller hay Vận chuyển.
- **Payment Reconciliation**: Tính tổng giá trị các lượt thanh toán, so sánh với tổng tiền hàng (`price`) + tiền vận chuyển (`freight_value`).
- **Policy Engine Rules**: Triển khai 6 kịch bản (`canceled_order_paid`, `unavailable_order_paid`, `late_delivery_seller`, `late_delivery_logistics`, `valid_split_payment`, `unsupported_late_claim`).
### Input, output và contract
| Thành phần | Mô tả |
| --- | --- |
| Input | File JSON khiếu nại trong `input/input/` chứa `claimed_order_id` |
| Output | File JSON kết quả trong `output/` tuân thủ Schema đề bài |
| Module phụ thuộc | Bảng dữ liệu CSV trong thư mục `data/` |
| Module sử dụng output | Hệ thống chấm điểm tự động & HĐGK |
| Điều kiện lỗi cần xử lý | Trường hợp thiếu thông tin item, seller hoặc trễ do phía nào |
### Cách xác minh
```bash
python main.py



## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** [Vấn đề hoặc lựa chọn cần quyết định.]
- **Các phương án đã cân nhắc:** [Ít nhất hai phương án.]
- **Phương án đã chọn:** [Lựa chọn.]
- **Lý do:** [Trade-off về correctness, data quality, reproducibility, cost hoặc độ phức tạp.]
- **Bằng chứng quyết định phù hợp:** [Metric, artifact hoặc kết quả thử nghiệm.]

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** [Che toàn bộ secret trước khi ghi.]
- **Lệnh hoặc bước tái hiện:** [Lệnh/bước.]
- **Nguyên nhân gốc:** [Root cause, không chỉ mô tả triệu chứng.]
- **Cách xử lý:** [Thay đổi cụ thể.]
- **Cách xác minh sau khi sửa:** [Lệnh và kết quả.]
- **Điều học được:** [Bài học kỹ thuật.]

Nếu chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** [Module/artifact.]
- **Những gì đã loại trừ:** [Các giả thuyết đã kiểm tra.]
- **Bước tiếp theo:** [Hành động có thể kiểm chứng.]

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn:

1. Dữ liệu đi từ Crossref đến vector index như thế nào?
2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?
3. Quality checks khác freshness monitoring ở điểm nào trong bài lab?
4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?
5. Repair được xem là thành công dựa trên artifact và metric nào?

**Câu trả lời:**

[Viết câu trả lời tại đây.]

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Họ và tên]
**Ngày xác nhận:** [YYYY-MM-DD]
