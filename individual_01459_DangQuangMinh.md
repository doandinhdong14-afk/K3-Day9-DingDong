# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                          |
| --------------- | ------------------------------------------------- |
| Họ và tên       | Đặng Quang Minh                                   |
| MSSV            | 2A202601459                                       |
| Khóa/Lớp        | K3                                                |
| Nhóm            | DingDong                                          |
| Vai trò chính   | Verifier & Validation Owner (kiểm chứng + gate nộp bài) |
| Ngày hoàn thành | 2026-08-05                                        |

## 2. Vai trò và phạm vi công việc

Tôi sở hữu **lớp kiểm chứng cuối** của pipeline: bộ máy tái dựng kết luận độc lập từ CSV, schema validator, và gate chạy trước khi đóng gói `output/`. Nói ngắn gọn: các agent khác *đề xuất* câu trả lời, phần của tôi *quyết định* câu trả lời nào được ghi ra file.

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Bộ máy tái dựng độc lập (ground truth) | `src/ground_truth.py` — `derive()`, `_classify()` | `order_id` + quyền đọc toàn bộ CSV qua `OlistStore` | `document` tái dựng + dict `facts` (13 cờ sự kiện) | Hoàn thành |
| Verifier Agent | `src/agents/verifier_agent.py` — `VerifierAgent.run()` | Handoff `draft_document` từ Coordinator | Handoff `verified_document` (document + `repairs` + `schema_errors` + `pipeline_agreed`) | Hoàn thành |
| Schema + evidence validator | `src/assembly.py` — `validate_document()`, `diff_documents()`, `build_evidence()`, `confidence_for()` | Một document bất kỳ + `OlistStore` | List lỗi dạng chuỗi (rỗng = hợp lệ) | Hoàn thành |
| Gate trước khi nộp | `verify_output.py` | Thư mục `output/` | Exit code 0/1, thống kê issue mix + tổng refund, `output.zip` khi `--zip` | Hoàn thành |
| Chế độ kiểm nhanh không tốn API | `run.py` — `self_check()` | 50 file `input/EC_*.json` | Báo cáo 50 case / số schema failure / phân bố issue | Hoàn thành |

Phụ thuộc hai chiều: tôi **nhận** `draft_document` từ Coordinator (Orchestration), và **đọc** `AGENT_SCOPES` do người làm data layer định nghĩa (Verifier là agent duy nhất có scope full-read). Ngược lại, Coordinator chỉ ghi ra file cái mà Verifier trả về, nên mọi case sai ở tầng tôi là sai thẳng vào bài nộp.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Cung cấp `policy.ISSUE_SPEC` làm nguồn chung cho cả prompt lẫn verifier | `src/policy.py` (Domain agents + Policy Agent) | Prompt của Policy Agent và bộ tái dựng của tôi dùng **cùng một** bảng luật, nên hai đường chỉ có thể lệch nhau về *case*, không thể lệch về *policy* |
| Chuẩn hoá quy ước evidence ID + cap số lượng | `src/assembly.py` dùng chung cho cả Coordinator lẫn Verifier | Draft và bản tái dựng luôn so sánh được field-by-field bằng `diff_documents()` |
| Dọn `output/` tồn dư trước lần chạy chính thức | Toàn nhóm | Tránh file cũ của lần chạy thử lọt vào zip nộp (xem mục 6) |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tái dựng độc lập 50 case từ CSV, không nhìn ý kiến agent | `src/ground_truth.py` | 50 document, 0 lỗi schema | `python3 run.py --self-check` |
| Kiểm schema + policy coherence + evidence có thật | `src/assembly.py::validate_document` | Mọi evidence ID được tra ngược vào CSV bằng `store.entity_exists` | `python3 verify_output.py` |
| Đo độ chính xác thật của pipeline LLM | `logging/trace.jsonl` (`verifier_report`, `verifier_override`) | `quality.llm_pipeline_matched_verifier` trong `metadata.json` | `grep verifier_report logging/trace.jsonl` |
| Gate + đóng gói bài nộp | `verify_output.py --zip` | `output.zip` đúng 50 file `EC_001..EC_050.json`, không file lạ | `unzip -l output.zip` |

Một output cụ thể phần việc của tôi tạo ra:

**`logging/trace.jsonl` — dòng `verifier_report` của từng case.** Mỗi dòng ghi `deterministic_repairs` (số field draft của pipeline LLM bị lệch so với bản tái dựng), `llm_compliant`, `schema_errors` và `final_confidence`. Đây là artifact duy nhất trong repo cho biết pipeline 8B **thực sự** đúng bao nhiêu, thay vì chỉ thấy một file output đẹp mà không biết nó đến từ suy luận của model hay từ bản sửa của verifier.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Đây là bài toán compliance, không phải bài toán sinh văn bản: sai một con số tiền là sai cả case, và evidence ID bịa ra bị tính **false positive** (mất điểm hai lần). Trong khi đó ràng buộc của đề là mọi agent phải chạy trên model **≤ 10B tham số** — cỡ model rất dễ cộng sai tiền, đảo ngược so sánh timestamp và bịa ID 32 ký tự hex trông rất thật. Nếu tin thẳng output của chuỗi agent thì bài nộp không có gì bảo chứng.

Phần của tôi trả lời câu hỏi: **cái gì được quyền quyết định sự thật của một case?**

### Cách triển khai

Câu trả lời tôi chọn: **LLM đề xuất, dữ liệu phán quyết.** Verifier chạy ba tầng, theo đúng thứ tự:

1. **Tái dựng độc lập** (`ground_truth.derive`). Module này *không nhận* draft, không nhận handoff, không biết agent nào đã kết luận gì. Nó tự đọc `orders / order_items / order_payments / sellers`, tự dựng 13 cờ sự kiện (`delivered_after_estimate`, `seller_handoff_late`, `is_split_payment`, `reconciled`, `delta_brl`, …) rồi chạy `_classify()` — bảng ưu tiên EC_POLICY_V1, first match wins:

   ```
   canceled + payment > 0        -> canceled_order_paid        (refund = tổng payment)
   unavailable + payment > 0     -> unavailable_order_paid     (refund = tổng payment)
   delivered_after_estimate      -> late_delivery_seller nếu seller_handoff_late
                                    ngược lại late_delivery_logistics  (refund = freight)
   >=2 payment row + reconciled  -> valid_split_payment        (refund = 0)
   còn lại                       -> unsupported_late_claim     (refund = 0)
   ```

   Vì hai đường (chuỗi agent LLM và bộ tái dựng) hoàn toàn độc lập, chỗ chúng lệch nhau là **tín hiệu đo được**, không phải nhiễu. `diff_documents()` so sánh phẳng từng field, mọi field lệch được ghi thành `verifier_override` trong trace kèm giá trị trước/sau.

2. **LLM sign-off (tư vấn)**. Một model ≤10B đọc lại document đã tái dựng cùng đúng *một* dòng luật liên quan (`policy.rule_text`, không ném cả bảng vào để tiết kiệm ngân sách token/phút) và trả về `compliant` + `violations`. Verdict này **chỉ được hạ `confidence`**, không được lật một sự kiện đã tái dựng từ CSV. Đây là quyết định có chủ ý: sự kiện đến từ dữ liệu, không đến từ model.

3. **Schema + toàn vẹn tham chiếu** (`assembly.validate_document`). Kiểm ba nhóm:
   - *Schema*: đủ field, `confidence ∈ [0,1]`, cap 5 ID/entity · 10 evidence · 3 root cause · 3 responsible party · 5 action, tiền là số ≥ 0 và làm tròn đúng 2 chữ số (`round(v,2) == v`).
   - *Policy coherence* (chỗ dễ mất điểm nhất): `case_status`, `resolution_actions[0]` và `ranked_causes[0]` phải khớp với `primary_issue`; case `no_action` **bắt buộc** refund = 0 và case `action_required` **bắt buộc** refund > 0.
   - *Evidence có thật*: mỗi ID vừa phải khớp regex (`order:<32 hex>`, `item:<32 hex>:<int>`, `payment:<32 hex>:<int>`, `seller:<32 hex>`, `policy:<CODE>`), vừa phải tra ngược được vào CSV qua `store.entity_exists`. ID đúng định dạng nhưng không tồn tại trong dữ liệu vẫn bị chặn.

Một chi tiết cố ý: **định danh không do model sinh ra.** `item_ids` / `seller_ids` / `payment_ids` luôn lấy thẳng từ row CSV trong `ground_truth.derive`. Rủi ro lớn nhất của model 8B ở bài này là bịa ID, mà ID bịa vừa mất điểm evidence vừa bị tính false positive — không có lợi ích nào đủ bù rủi ro đó.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Handoff `draft_document` (payload chứa `document` chưa kiểm chứng) + `CaseContext(case_id, order_id)` + quyền full-read `OlistStore` |
| Output | Handoff `verified_document`: `{document, repairs[], llm_compliant, llm_violations[], schema_errors[], pipeline_agreed, facts}` |
| Module phụ thuộc | `src/olist_store.py` (scoped view + `entity_exists`), `src/policy.py` (`ISSUE_SPEC`, `rule_text`), `src/llm.py` (sign-off), `src/tracing.py` |
| Module sử dụng output | `src/agents/coordinator.py` (ghi file), `run.py` (thống kê + `metadata.json`), `verify_output.py` (gate cuối) |
| Điều kiện lỗi cần xử lý | Order không có item row (`item_ids`/`seller_ids` rỗng, `item_total`/`freight_total` = 0.0); LLM sign-off chết → `_ask` degrade sang fallback, verdict coi như advisory rỗng, kết luận **không** đổi; case ném exception → `run.py` dựng lại bằng `ground_truth.derive` và ghi `case_recovered`; `validate_document` báo lỗi trên chính bản tái dựng → emit `schema_violation` (đây là bug của chính builder nên phải ồn) |

### Cách xác minh

```bash
# 1. Kiểm bộ máy deterministic + schema trên cả 50 case, không gọi API
python3 run.py --self-check

# 2. Chạy thật 50 case qua đủ 6 agent
python3 run.py

# 3. Gate trước khi nộp: đúng 50 file, schema hợp lệ, evidence tra được vào CSV
python3 verify_output.py

# 4. Đóng gói
python3 verify_output.py --zip
```

- **Kết quả mong đợi:** `--self-check` báo 0 schema failure trên 50 case; `verify_output.py` exit 0 với thông báo 50/50 document hợp lệ và mọi evidence ID resolve được; zip chứa đúng 50 entry, không file lạ.
- **Kết quả thực tế:**

  ```
  <<SELF_CHECK>>
  ```

  ```
  <<VERIFY>>
  ```

- **Artifact/log:** `logging/trace.jsonl` (<<TRACE_EVENTS>> event của lần chạy mới nhất), `logging/metadata.json`, `output/EC_001..EC_050.json`, `output.zip`. Không file nào chứa secret; API key nằm trong `.env` và đã được `.gitignore` loại trừ.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Verifier có hai nguồn phán đoán trong tay — kết luận của chuỗi agent LLM, và một bộ luật có thể tự chạy lại trên CSV. Phải chọn nguồn nào là *authoritative* khi hai bên lệch nhau.
- **Các phương án đã cân nhắc:**
  1. **Tin pipeline LLM, verifier chỉ kiểm schema.** Đúng tinh thần "multi-agent" nhất, nhưng một lỗi cộng tiền của model 8B đi thẳng vào bài nộp.
  2. **LLM-as-judge**: để một model thứ hai phân xử khi có mâu thuẫn. Nghe hợp lý nhưng thực chất là lấy một model 8B khác đi kiểm một model 8B — cùng loại lỗi, không tạo thêm thông tin.
  3. **Tái dựng deterministic là quyết định, LLM sign-off là tư vấn.**
- **Phương án đã chọn:** phương án 3.
- **Lý do:** Bài này chấm bằng khớp chính xác con số và ID, không chấm bằng "lập luận nghe hợp lý". EC_POLICY_V1 là bảng luật đóng, hoàn toàn tính được từ CSV — nên chỗ nào tính được thì không có lý do gì đem đi hỏi model. Đổi lại, tôi mất khả năng "sáng tạo" ở tầng cuối, và điều đó là chấp nhận được với một bài compliance. Quan trọng hơn: giữ nguyên draft của LLM để **so sánh** thay vì vứt đi, nên chất lượng thật của pipeline vẫn đo được thay vì bị giấu sau một con số accuracy đẹp.
- **Bằng chứng quyết định phù hợp:** trace của lần chạy thật ghi lại đúng loại lỗi mà phương án 1 sẽ để lọt — ví dụ hai lần model tự mâu thuẫn với chính dữ liệu nó vừa được đưa:

  ```json
  {"event":"self_inconsistency","case_id":"EC_005","agent":"payment_agent",
   "stated_delta":-1191.5,"payment_total":1191.5,"expected_total":0.0,"resolved_to":1191.5}
  {"event":"self_inconsistency","case_id":"EC_006","agent":"delivery_agent",
   "stated_delivered_after_estimate":true,"actual_ymd":20171218,"promised_ymd":20180115,
   "resolved_to":false}
  ```

  Case EC_006 đặc biệt đắt: model khẳng định giao trễ trong khi đơn giao ngày 2017-12-18, sớm hơn hạn 2018-01-15 gần một tháng. Nếu tin model, case này thành `late_delivery_seller` với refund freight > 0 — sai `primary_issue`, sai `case_status`, sai root cause, sai responsible party, sai tiền và sai action cùng lúc, tức mất gần như toàn bộ trọng số của case.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** trước lần chạy chính thức, `output/` chỉ có 6 file (`EC_002, EC_004, EC_009, EC_029, EC_035, EC_047`) còn sót lại từ các lần chạy thử theo `--cases`. Gate báo:

  ```
  missing 44 file(s): ['EC_001.json', 'EC_003.json', 'EC_005.json', 'EC_006.json', 'EC_007.json']
  ```

- **Lệnh hoặc bước tái hiện:** `python3 run.py --cases EC_002 EC_004` rồi `python3 verify_output.py`.
- **Nguyên nhân gốc:** `run.py` ghi output theo từng `case_id` và **không dọn thư mục** trước khi chạy. Với `--cases`, thư mục `output/` trở thành hỗn hợp của nhiều lần chạy khác nhau. Nguy hiểm hơn trường hợp thiếu file: nếu một lần chạy sau chỉ chạy lại một phần case, các file cũ vẫn nằm nguyên và **vẫn hợp lệ về schema**, nên chỉ kiểm schema thôi sẽ không phát hiện được — bài nộp sẽ lẫn kết quả của các lần chạy khác nhau mà không ai biết.
- **Cách xử lý:** hai lớp. (1) Quy trình: xoá `output/EC_*.json` trước mỗi lần chạy đủ 50 case. (2) Cưỡng chế: `verify_output.py` kiểm **tập file chính xác** — đối chiếu với danh sách `EXPECTED = EC_001..EC_050`, báo lỗi cả file thiếu lẫn file lạ, và kiểm `case_id` bên trong mỗi file có khớp tên file hay không. Zip chỉ được tạo sau khi toàn bộ kiểm tra đã pass, và chỉ ghi đúng 50 entry trong `EXPECTED` (không `zip -r` cả thư mục, tránh nuốt phải `.DS_Store` hay `.gitkeep`).
- **Cách xác minh sau khi sửa:** `python3 verify_output.py` → xem kết quả ở mục 4; `unzip -l output.zip` → đúng 50 entry.
- **Điều học được:** validator phải kiểm **tập kết quả**, không chỉ kiểm từng phần tử. Mọi file trong `output/` đều có thể hợp lệ trong khi cả bộ vẫn sai — đây đúng là loại lỗi mà một schema validator thuần tuý không bao giờ thấy.

Còn tồn đọng (đã xác định, chưa xử lý):

- **Phạm vi bị ảnh hưởng:** `architecture.md`.
- **Vấn đề:** tài liệu ghi hệ thống chạy `meta-llama/llama-3.1-8b-instruct` qua OpenRouter và `CASE_WORKERS=4`, trong khi `src/config.py` đặt provider ưu tiên là Groq với `llama-3.1-8b-instant` và `CASE_WORKERS=3` — và lần chạy thật đúng là chạy trên Groq. Cả hai model đều 8B nên **không vi phạm ràng buộc ≤10B**, nhưng đề yêu cầu tên model khai trong source phải khớp `metadata.json`, nên để lệch là rủi ro không đáng có.
- **Những gì đã loại trừ:** không phải lỗi runtime — `metadata.json` được `run.py` sinh tự động từ `llm.primary_model` nên luôn đúng với model đã chạy; chỉ riêng phần văn xuôi trong `architecture.md` là cũ.
- **Bước tiếp theo:** sửa mục mở đầu và mục 8 của `architecture.md` cho khớp `src/config.py`, đối chiếu lại với `logging/metadata.json` sau lần chạy cuối.

## 7. Hiểu biết về luồng end-to-end

> Ghi chú: bộ câu hỏi in sẵn trong template thuộc lab RAG (Crossref → vector index → freshness monitoring), không có thành phần tương ứng trong lab Day 9. Tôi trả lời theo **câu hỏi tương đương của lab này**, giữ nguyên ý định của từng câu hỏi gốc.

**1. Dữ liệu đi từ `input/` đến `output/` như thế nào?** (tương ứng câu hỏi 1)

`input/EC_xxx.json` chỉ cho một thứ dùng được: `claimed_order_id`. Coordinator lấy ID đó dựng `CaseContext` rồi fan-out song song cho ba domain agent, mỗi agent chỉ được cấp đúng phần dữ liệu của mình qua `OlistStore.view()` — gọi ngoài scope là `AccessDenied`, không phải quy ước mà là cưỡng chế trong code. Order & Seller đọc status/item/seller và mốc `shipping_limit_date`; Payment đối soát payment với item + freight; Delivery so ngày giao thực tế với ngày cam kết. Ba handoff này đi vào Policy Agent — agent **không có quyền đọc CSV**, buộc phải kết luận dựa trên bằng chứng agent khác trình ra. Coordinator gộp thành `draft_document`, đẩy sang Verifier; Verifier tái dựng độc lập, sửa chỗ lệch, kiểm schema + evidence, trả về; Coordinator mới ghi `output/EC_xxx.json`.

**2. Đâu là "ground truth" và dùng để đo cái gì?** (tương ứng câu hỏi 2)

`src/ground_truth.py` đóng vai trò eval set: nó tái dựng kết luận đúng từ CSV mà không nhìn ý kiến agent nào. So sánh draft ↔ bản tái dựng bằng `diff_documents()` cho ra `deterministic_repairs`, cộng dồn thành `quality.llm_pipeline_matched_verifier` — tức là **đo chất lượng suy luận của pipeline LLM**, tách bạch với chất lượng bài nộp. Bài nộp luôn là bản tái dựng; con số agreement mới là thứ nói lên chuỗi agent chạy tốt tới đâu.

**3. Schema check khác gì với trace/monitoring trong lab này?** (tương ứng câu hỏi 3)

Schema check (`validate_document`) là **gate chặn**: sai thì file không được coi là hợp lệ, chạy trên từng document, trả lỗi cứng. Trace (`trace.jsonl`) là **quan sát**: nó không chặn gì cả, chỉ ghi lại agent nào gọi tool nào, model nào trả lời gì, verifier sửa field nào. Hai thứ bắt hai loại vấn đề khác nhau: schema bắt document sai *hình dạng*; trace bắt pipeline *suy luận sai* dù document vẫn đúng hình dạng — như hai case `self_inconsistency` ở mục 5, cả hai đều tạo ra JSON hợp lệ hoàn hảo.

**4. Vì sao phải chạy cùng một bộ 50 case cho cả `--self-check` lẫn lần chạy thật?** (tương ứng câu hỏi 4)

Vì `--self-check` là baseline. Nó chạy đúng bộ máy tái dựng mà Verifier sẽ dùng, trên đúng 50 input, nhưng không gọi API. Nếu baseline này đã sai schema thì lỗi nằm ở builder của tôi chứ không phải ở model — và phải sửa trước khi đốt token. Chạy trên tập khác thì mất tính so sánh: không biết chênh lệch đến từ thay đổi dữ liệu hay từ thay đổi code.

**5. Dựa vào artifact/metric nào để kết luận bài chạy thành công?** (tương ứng câu hỏi 5)

Ba điều kiện, phải đủ cả ba: (a) `python3 verify_output.py` exit 0 — 50/50 document hợp lệ và mọi evidence ID resolve được vào CSV; (b) `metadata.json` có `quality.schema_failures = 0` và khai đúng model ≤10B đã chạy; (c) `trace.jsonl` là trace của **một** lần chạy đủ 50 case (cùng một `run_id`, có `run_start` và `run_complete`), không phải log ghép của nhiều lần.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đặng Quang Minh
**Ngày xác nhận:** 2026-08-05
