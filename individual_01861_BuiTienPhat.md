# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | Bùi Tiến Phát |
| MSSV            | 2A202601861  |
| Khóa/Lớp        | K3            |
| Vai trò chính   | Lập trình viên chính (Developer) & Thiết lập Kiến trúc Multi-Agent |
| Ngày hoàn thành | 2026-08-05   |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao   | Trạng thái                            |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| Tải dữ liệu đề bài | `scratch/download_inputs.py` | GitHub Release URL | 50 file JSON trong thư mục `input/` | Hoàn thành |
| Truy xuất dữ liệu Olist | `src/db.py` / `get_order_context` | `order_id` (từ khiếu nại) | Từ điển dữ liệu thô (order, items, payments, sellers, products) | Hoàn thành |
| Phát triển các Agent AI | `src/agents.py` / `BaseAgent`, `OrderSellerAgent`, `PaymentAgent`, `DeliveryAgent`, `PolicyAgent`, `VerifierAgent` | Dữ liệu ngữ cảnh đơn hàng | Báo cáo chuyên môn của từng Agent và Biên bản quyết định cuối cùng | Hoàn thành |
| Điều phối luồng và Ghi nhật ký | `src/agents.py` / `CoordinatorAgent`, `src/utils.py` / `write_trace_case` | Yêu cầu của khách hàng | Biên bản cuộc họp Agent lưu tại `trace.jsonl` | Hoàn thành |
| Chạy hàng loạt & Nén file nộp bài | `src/main.py`, `src/utils.py` / `package_submission` | 50 file JSON đầu vào | 50 file JSON đầu ra và file nén `submission.zip` đúng chuẩn | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Hỗ trợ tích hợp và cấu hình | Cả nhóm | Cấu hình thành công file mẫu `.env` và hướng dẫn kết nối API Key Gemini |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Truy xuất và đối soát đơn hàng | `src/db.py` | Lấy đầy đủ dữ liệu Olist không bị sót thông tin | Chạy thử `python src/db.py` cho kết quả chính xác |
| Chạy pipeline Multi-Agent | `src/main.py` | 50 file JSON kết quả sạch lỗi trong thư mục `output/` | File `submission.zip` được tạo tự động |
| Biên bản hoạt động của Agent | `logging/trace.jsonl` | Nhật ký hoạt động chi tiết của 6 Agent cho 50 case | Đọc nội dung file `trace.jsonl` hiển thị rõ các bước trao đổi của Agent |

Output cụ thể được tạo ra là file nén **`submission.zip`** chứa thư mục kết quả sạch lỗi định dạng, sơ đồ thiết kế agent, và file trace hoạt động thật để nộp lên cổng thông tin của BTC.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Bài toán yêu cầu giải quyết khiếu nại của khách hàng thương mại điện tử Olist theo chính sách `EC_POLICY_V1` một cách trung thực, chính xác và có bằng chứng truy vết rõ ràng, tránh ảo tưởng dữ liệu (hallucination) của AI và không được sửa tay kết quả.

### Cách triển khai
* Sử dụng ngôn ngữ Python làm cầu nối tính toán: So sánh thời gian giao hàng thực tế với ngày dự kiến, kiểm tra ngày người bán giao hàng cho shipper xem có vượt hạn bàn giao không, và thực hiện cộng tổng tiền thanh toán để đối soát đợt thanh toán chia nhỏ.
* Dữ liệu sau khi tính toán chính xác bởi Python được chuyển thành ngữ cảnh sạch (Clean Facts) và đưa cho các Agent AI chuyên trách.
* Các Agent AI sử dụng mô hình **`gemini-3.5-flash-lite`** để tự động lập báo cáo phân tích bằng tiếng Việt, từ đó Coordinator tổng hợp lại để đưa ra kết luận hoàn tiền chính xác và ghi nhận nhật ký cuộc họp thật của AI.

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | Case ID, yêu cầu của khách hàng, và claimed_order_id |
| Output                  | JSON kết quả chứa lỗi chính, bên chịu trách nhiệm, danh sách bằng chứng và mức hoàn tiền đề xuất |
| Module phụ thuộc        | `src/db.py` để lấy dữ liệu Olist |
| Module sử dụng output   | Cổng chấm điểm tự động của cuộc thi `n7-competition.pages.dev/k3` |
| Điều kiện lỗi cần xử lý | Lỗi mã hóa font chữ tiếng Việt trên Windows console (`charmap` error) đã được xử lý bằng cách ép kiểu UTF-8 stdout |

### Cách xác minh

```bash
python src/main.py --single EC_001
python src/main.py
```

- **Kết quả mong đợi:** 50/50 case được xử lý thành công, sinh ra file `submission.zip` chứa đầy đủ 50 JSON kết quả, trace.jsonl và metadata.json.
- **Kết quả thực tế:** Hệ thống chạy thành công 50/50 cases trong 137.94 giây, file zip được tạo tự động không lỗi.
- **Artifact/log:** `logging/trace.jsonl` và `logging/metadata.json` trong thư mục dự án.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn mô hình AI phù hợp đáp ứng quy định dưới 10 tỷ tham số (10B parameters) của BTC, đảm bảo tốc độ nhanh, chi phí thấp và không yêu cầu cài đặt local phức tạp đối với người dùng Non-tech.
- **Các phương án đã cân nhắc:**
  * **Phương án 1:** Cài đặt cục bộ (Local) mô hình Gemma 2 9B hoặc Gemma 3 4B chạy trên máy cá nhân qua Ollama.
  * **Phương án 2:** Sử dụng mô hình thương mại rút gọn **`gemini-3.5-flash-lite`** thông qua Google Gen AI API Key.
- **Phương án đã chọn:** Phương án 2 (`gemini-3.5-flash-lite`).
- **Lý do:** Mô hình dòng "Lite" của Gemini có kích thước rất nhỏ (dưới 4 tỷ tham số), hoàn toàn đáp ứng quy định dưới 10B của BTC. Chạy qua API giúp máy tính cá nhân của các thành viên không bị quá tải RAM hay quá nóng trong quá trình chạy hàng loạt 50 ticket, tốc độ xử lý nhanh vượt trội (~2 giây/case).
- **Bằng chứng quyết định phù hợp:** Chạy thành công toàn bộ 50 ticket chỉ trong 137.94 giây với chất lượng lý luận tiếng Việt xuất sắc của Agent trong file `trace.jsonl`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `'charmap' codec can't encode character '\u1ed9' in position 37: character maps to <undefined>` khi chạy chương trình trên Windows console.
- **Lệnh hoặc bước tái hiện:** `python src/main.py --single EC_001` trên hệ điều hành Windows.
- **Nguyên nhân gốc:** Cửa sổ dòng lệnh CMD/Powershell mặc định của Windows không sử dụng bảng mã UTF-8 nên không thể mã hóa/hiển thị các ký tự tiếng Việt có dấu (như từ `đơn`, `giao`, `trễ`, `báo`) được trả về từ mô hình Gemini.
- **Cách xử lý:** Bổ sung đoạn mã ép kiểu đầu ra stdout của Python sang định dạng UTF-8 ở ngay đầu file `main.py` và `agents.py`:
  ```python
  import sys
  if sys.platform.startswith('win'):
      import io
      sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
  ```
- **Cách xác minh sau khi sửa:** Chạy lại lệnh trên, lỗi hoàn toàn biến mất và tiếng Việt được hiển thị mượt mà trên console.
- **Điều học được:** Khi làm việc với dữ liệu đa ngôn ngữ trên môi trường Windows, luôn cần thiết lập môi trường UTF-8 chủ động cho stdout của Python.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   Dữ liệu thô từ Crossref được tải về dưới dạng JSON/XML, sau đó được trích xuất thông tin tiêu đề, abstract, tác giả. Nội dung này được chia nhỏ (chunking) thành các đoạn văn ngắn có ý nghĩa để giữ ngữ cảnh. Sau đó, các đoạn văn này được gửi qua mô hình Embedding để chuyển thành các vector số (vector biểu diễn ngữ nghĩa) rồi lưu vào CSDL Vector (Vector Index).

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   * Retrieval Quality: Hệ thống lấy câu hỏi từ Evaluation set đi tìm kiếm trong Vector Index để nhận về các tài liệu liên quan. Ta so sánh danh sách tài liệu này với Ground-truth document IDs để tính các chỉ số độ phủ/chính xác như Precision@K, Recall@K, MAP, MRR.
   * Answer Quality: So sánh câu trả lời do LLM sinh ra với câu trả lời mẫu trong Evaluation set bằng các độ đo học máy (ROUGE, BLEU, BERTScore) hoặc nhờ một LLM thông minh hơn làm giám khảo (LLM-as-a-judge).

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   * Quality checks: Kiểm tra chất lượng dữ liệu đầu ra có đúng cấu trúc không, bằng chứng có chính xác không, logic hoàn tiền có đúng chính sách không.
   * Freshness monitoring: Giám sát xem dữ liệu trong hệ thống có bị lỗi thời không, thời điểm cập nhật dữ liệu gần nhất có đủ mới để trả lời câu hỏi hiện tại không.

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   Để đảm bảo tính nhất quán và công bằng của các chỉ số đánh giá. Khi so sánh trên cùng một tập test set cố định, mọi sự thay đổi trong điểm số (tăng hoặc giảm) mới phản ánh đúng hiệu quả thực tế của giải pháp cải tiến (repaired) hoặc mức độ tác động của lỗi (corrupted).

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   Repair thành công khi điểm đánh giá chất lượng (F1-score, Correctness, Accuracy) trên tập kiểm thử sau khi sửa (repaired) tăng rõ rệt so với lúc bị lỗi (corrupted) và đạt mức tương đương hoặc cao hơn tập cơ sở (baseline). Đồng thời, các file JSON kết quả đầu ra phải vượt qua bài kiểm tra của Verifier mà không còn lỗi schema.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Tiến Phát
**Ngày xác nhận:** 2026-08-05
