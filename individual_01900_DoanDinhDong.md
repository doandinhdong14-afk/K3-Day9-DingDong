# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | Đoàn Đình Đông |
| MSSV            | 2A202601900  |
| Khóa/Lớp        | K3            |
| Vai trò chính   | Trưởng nhóm (Team Leader) kiêm phụ trách CoordinatorAgent & Pipeline chạy hàng loạt |
| Ngày hoàn thành | 2026-08-05   |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao   | Trạng thái                            |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| Chốt kiến trúc Multi-Agent & phân công module | Sơ đồ thiết kế agent, bảng phân công công việc | Đề bài Day 9 và chính sách `EC_POLICY_V1` | Sơ đồ 6 Agent (Coordinator, OrderSeller, Payment, Delivery, Policy, Verifier) và bảng phân công rõ người – rõ việc – rõ deadline | Hoàn thành |
| Điều phối luồng A2A giữa các Agent | `src/agents.py` / `CoordinatorAgent` | Yêu cầu khiếu nại của khách hàng và báo cáo từ các Agent chuyên môn | Biên bản cuộc họp Agent và quyết định hoàn tiền cuối cùng cho từng case | Hoàn thành |
| Pipeline chạy hàng loạt 50 case | `src/main.py` | 50 file JSON trong thư mục `input/` | 50 file JSON kết quả trong thư mục `output/` | Hoàn thành |
| Đóng gói và nộp bài | `src/utils.py` / `package_submission` | Thư mục `output/`, `trace.jsonl`, `metadata.json` | File nén `submission.zip` đúng chuẩn nộp lên cổng BTC | Hoàn thành |
| Review code và quản lý tiến độ nhóm | Checklist review, theo dõi tiến độ theo từng buổi | Code và kết quả từ các thành viên | Code được review trước khi gộp, tiến độ nhóm hoàn thành đúng hạn nộp | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Hỗ trợ tinh chỉnh prompt cho các Agent chuyên môn | Thành viên phụ trách `src/agents.py` | Báo cáo của Agent bám sát Clean Facts, giảm hẳn hiện tượng bịa dữ liệu |
| Kiểm tra chéo dữ liệu truy xuất Olist | Thành viên phụ trách `src/db.py` | Đối soát ngẫu nhiên 10 case, dữ liệu order/payment/delivery khớp với CSDL gốc |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Chốt kiến trúc và phân công công việc | Sơ đồ thiết kế agent, bảng phân công | Cả nhóm làm đúng module được giao, không giẫm chân nhau, ghép hệ thống một lần là chạy | Đối chiếu bảng phân công với commit/module thực tế của từng thành viên |
| Điều phối A2A qua CoordinatorAgent | `src/agents.py` / `CoordinatorAgent` | Coordinator gọi lần lượt các Agent chuyên môn, tổng hợp báo cáo và ra quyết định cuối có kèm bằng chứng | Đọc `logging/trace.jsonl` thấy rõ trình tự trao đổi giữa các Agent cho từng case |
| Chạy pipeline hàng loạt và đóng gói | `src/main.py`, `src/utils.py` / `package_submission` | 50/50 case chạy thành công, `submission.zip` được tạo tự động đúng chuẩn | Chạy `python src/main.py`, kiểm tra thư mục `output/` và file zip sinh ra |
| Kiểm tra chất lượng trước khi nộp | Checklist review + `VerifierAgent` | 50 file JSON đầu ra đúng schema, không case nào lỗi định dạng | Verifier báo pass toàn bộ, cổng chấm của BTC nhận bài không báo lỗi |

Output cụ thể được tạo ra là file nén **`submission.zip`** chứa 50 JSON kết quả, sơ đồ thiết kế agent và file `trace.jsonl` ghi lại hoạt động thật của hệ thống, đã nộp lên cổng thông tin của BTC.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Với vai trò leader, tôi cần đảm bảo hai việc: (1) các Agent chuyên môn hoạt động độc lập nhưng phải phối hợp được với nhau theo một luồng thống nhất để ra quyết định hoàn tiền đúng chính sách `EC_POLICY_V1`, và (2) toàn bộ 50 case phải chạy tự động từ đầu đến cuối, sinh ra kết quả đúng chuẩn nộp bài mà không sửa tay bất kỳ file nào.

### Cách triển khai
* Thiết kế `CoordinatorAgent` theo mô hình điều phối tập trung: Coordinator nhận khiếu nại, lần lượt yêu cầu `OrderSellerAgent`, `PaymentAgent`, `DeliveryAgent`, `PolicyAgent` phân tích theo chuyên môn của mình, sau đó chuyển toàn bộ báo cáo cho `VerifierAgent` kiểm tra chéo trước khi chốt kết luận cuối cùng.
* Xây dựng vòng lặp xử lý hàng loạt trong `src/main.py`: đọc từng file JSON trong `input/`, gọi Coordinator xử lý, ghi kết quả ra `output/` và ghi nhật ký trao đổi của các Agent vào `trace.jsonl` ngay sau mỗi case để không mất dữ liệu nếu chương trình dừng giữa chừng.
* Các Agent sử dụng mô hình **`gemini-3.5-flash-lite`**, còn phần tính toán số liệu (so sánh ngày giao hàng, cộng tổng thanh toán) do Python đảm nhận trước và đưa vào ngữ cảnh dưới dạng Clean Facts để tránh AI tự bịa số liệu.

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | Case ID, nội dung khiếu nại của khách hàng và `claimed_order_id` |
| Output                  | JSON kết quả gồm lỗi chính, bên chịu trách nhiệm, danh sách bằng chứng và mức hoàn tiền đề xuất |
| Module phụ thuộc        | `src/db.py` (dữ liệu Olist) và các Agent chuyên môn trong `src/agents.py` |
| Module sử dụng output   | `package_submission` để đóng gói và cổng chấm điểm tự động `n7-competition.pages.dev/k3` |
| Điều kiện lỗi cần xử lý | API Gemini trả lỗi giới hạn tốc độ (429) khi chạy liên tục 50 case — đã xử lý bằng cơ chế tự thử lại có giãn cách |

### Cách xác minh

```bash
python src/main.py --single EC_001
python src/main.py
```

- **Kết quả mong đợi:** 50/50 case được xử lý thành công, sinh ra `submission.zip` chứa đầy đủ 50 JSON kết quả, `trace.jsonl` và `metadata.json`.
- **Kết quả thực tế:** Hệ thống chạy trọn vẹn 50/50 case, file zip được tạo tự động, cổng chấm của BTC nhận bài hợp lệ.
- **Artifact/log:** `logging/trace.jsonl` và `logging/metadata.json` trong thư mục dự án.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chọn mô hình giao tiếp giữa các Agent (A2A): để các Agent trao đổi tự do với nhau, hay để một Agent trung tâm điều phối toàn bộ luồng.
- **Các phương án đã cân nhắc:**
  * **Phương án 1:** Giao tiếp tự do (peer-to-peer) — các Agent tự gọi nhau khi cần, luồng linh hoạt.
  * **Phương án 2:** Điều phối tập trung (hub-and-spoke) — `CoordinatorAgent` là đầu mối duy nhất, gọi từng Agent chuyên môn theo trình tự cố định rồi tổng hợp.
- **Phương án đã chọn:** Phương án 2 (điều phối tập trung qua `CoordinatorAgent`).
- **Lý do:** Với vai trò leader, tôi ưu tiên tính kiểm soát và khả năng truy vết: luồng cố định giúp `trace.jsonl` ghi lại đúng trình tự cuộc họp của các Agent, dễ debug khi một case ra kết quả sai, dễ chia việc cho từng thành viên phát triển Agent độc lập. Giao tiếp tự do linh hoạt hơn nhưng khó tái hiện lỗi, dễ vòng lặp vô hạn và tốn nhiều lượt gọi API hơn.
- **Bằng chứng quyết định phù hợp:** Cả nhóm tích hợp các Agent vào Coordinator mà không xung đột, 50/50 case chạy ổn định và biên bản trong `trace.jsonl` thể hiện trình tự trao đổi rõ ràng, nhất quán giữa các case.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'Generate Content API requests per minute'` xuất hiện rải rác khi chạy hàng loạt, khiến một số case bị dừng giữa chừng.
- **Lệnh hoặc bước tái hiện:** `python src/main.py` — chạy liên tục 50 case, mỗi case gọi API cho 6 Agent nên số request mỗi phút vượt hạn mức miễn phí của Gemini API.
- **Nguyên nhân gốc:** Pipeline gọi API dồn dập không có khoảng nghỉ, trong khi API Key miễn phí giới hạn số request mỗi phút; khi chạm ngưỡng, API trả lỗi 429 và case đang xử lý bị hỏng kết quả.
- **Cách xử lý:** Bổ sung cơ chế tự thử lại có giãn cách (retry với thời gian chờ tăng dần) quanh lời gọi API trong `src/agents.py`, đồng thời thêm khoảng nghỉ ngắn giữa các case trong `src/main.py`:
  ```python
  for attempt in range(MAX_RETRIES):
      try:
          response = model.generate_content(prompt)
          break
      except ResourceExhausted:
          time.sleep(2 ** attempt * 5)  # 5s, 10s, 20s...
  ```
- **Cách xác minh sau khi sửa:** Chạy lại toàn bộ pipeline, 50/50 case hoàn thành không còn case nào bị dừng vì lỗi 429; nhật ký cho thấy các lần thử lại đều thành công ở lần thứ hai.
- **Điều học được:** Khi thiết kế pipeline gọi API hàng loạt, phải coi giới hạn tốc độ (rate limit) là điều kiện vận hành bình thường và xây sẵn cơ chế thử lại, thay vì xem nó là lỗi bất ngờ.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?**
   Dữ liệu thô tải từ Crossref (JSON/XML) được làm sạch và trích các trường quan trọng như tiêu đề, abstract, tác giả. Văn bản sau đó được cắt thành các đoạn nhỏ (chunk) đủ ngắn để giữ trọn ngữ cảnh, rồi từng đoạn được đưa qua mô hình Embedding để chuyển thành vector ngữ nghĩa. Các vector này được ghi vào Vector Index kèm metadata để phục vụ tìm kiếm tương đồng về sau.

2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
   * Retrieval quality: Lấy từng câu hỏi trong Evaluation set truy vấn Vector Index, so sánh danh sách tài liệu trả về với Ground-truth document IDs để tính Precision@K, Recall@K, MRR, MAP.
   * Answer quality: So câu trả lời của LLM với đáp án mẫu trong Evaluation set bằng các độ đo như ROUGE, BLEU, BERTScore, hoặc dùng một LLM mạnh hơn chấm điểm (LLM-as-a-judge).

3. **Quality checks khác freshness monitoring ở điểm nào trong bài lab?**
   * Quality checks trả lời câu hỏi "kết quả có đúng không": schema đầu ra hợp lệ, bằng chứng chính xác, quyết định hoàn tiền khớp chính sách.
   * Freshness monitoring trả lời câu hỏi "dữ liệu có còn mới không": theo dõi thời điểm cập nhật gần nhất của dữ liệu để biết hệ thống có đang trả lời dựa trên thông tin lỗi thời hay không.

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   Vì chỉ khi cố định tập kiểm thử thì các con số mới so sánh được với nhau: mức sụt điểm ở bản corrupted phản ánh đúng tác hại của lỗi, và mức phục hồi ở bản repaired phản ánh đúng hiệu quả của việc sửa. Nếu đổi test set giữa các lần đo, chênh lệch điểm có thể chỉ do đề dễ/khó khác nhau chứ không phải do hệ thống.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   Khi các chỉ số chất lượng (F1-score, Correctness, Accuracy) trên tập repaired tăng rõ so với tập corrupted và quay về mức tương đương hoặc cao hơn baseline; đồng thời các artifact đầu ra (file JSON kết quả) phải vượt qua kiểm tra của Verifier, không còn lỗi schema hay bằng chứng sai.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đoàn Đình Đông
**Ngày xác nhận:** 2026-08-05
