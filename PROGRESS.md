# Checklist Theo dõi Tiến độ — Multi-Agent E-commerce Dispute Resolution

> **Quy ước:** Tick `[x]` vào task đã xong. Mỗi block thời gian tương ứng 1 phần công việc. Sau khi tick xong, ghi tên người phụ trách vào cột "Owner".

---

## Thông tin chung


| Mục      | Giá trị                        |
| -------- | ------------------------------ |
| Nhóm     | C4-1                           |
| Ngày     | 2026-08-05                     |
| Deadline | 12:30 (UTC+7) — còn 2 tiếng    |
| Repo     | `K3-Day9-Multi-Agent-A2A-C4-1` |


**Thành viên:**

- [ ] **A — Trần Đình Đăng (01998)** — Lead / Coordinator / Data Foundation
- [ ] **B — Dương Mạnh Phong (01557)**  — Order/Seller + Delivery Agent
- [ ] **C — Chu Thành Dũng**  — Payment + Policy Agent
- [ ] **D —**  — Verifier + Trace + Individual Reports

---



## Phase 0 — Setup chung (0–15 phút)


| #   | Task                                                                         | Owner   | Tick |
| --- | ---------------------------------------------------------------------------- | ------- | ---- |
| 0.1 | Clone repo, tạo nhánh `main` sạch                                            | A       | [x]  |
| 0.2 | Tạo `.gitignore` (`.env`, `__pycache__`, `*.pyc`)                            | A       | [x]  |
| 0.3 | Khảo sát 9 CSV trong `data/`, ghi nhận schema quan trọng                     | A       | [x]  |
| 0.4 | Tạo file `requirements.txt` (pandas, numpy, python-dotenv)                   | A       | [x]  |
| 0.5 | Tạo `.env.example` (không có key thật)                                       | A       | [x]  |
| 0.6 | Tạo `config.py` chứa `MODEL_NAME` (vd `"qwen2.5:7b"`)                        | A       | [x]  |
| 0.7 | Mỗi người tạo nhánh riêng: `feat/person-B`, `feat/person-C`, `feat/person-D` | A/B/C/D | [x]  |


---



## Phase 1 — Schema & Data Loader (15–30 phút)


| #   | Task                                                                                                                          | Owner | Tick |
| --- | ----------------------------------------------------------------------------------------------------------------------------- | ----- | ---- |
| 1.1 | Định nghĩa `CaseContext` dataclass trong `schema.py` (order, items, payments, seller, timestamps)                             | A     | [x]  |
| 1.2 | Code `data_loader.py` — load 9 CSV thành dict lookup O(1) theo `order_id`, `order_item_id`, `seller_id`, `payment_sequential` | A     | [x]  |
| 1.3 | Test load với 1 order thật, in ra `CaseContext` đầy đủ                                                                        | A     | [x]  |
| 1.4 | Push `schema.py` + `data_loader.py` lên `main`                                                                                | A     | [x]  |
| 1.5 | B/C/D pull code mới về nhánh của mình                                                                                         | B/C/D | [x]  |


---



## Phase 2 — Agents lõi (30–60 phút, làm song song)



### Person B — Order/Seller + Delivery Agent


| #    | Task                                                                                            | Tick |
| ---- | ----------------------------------------------------------------------------------------------- | ---- |
| 2B.1 | Tạo file `order_seller_agent.py`                                                                | [x]  |
| 2B.2 | Hàm `analyze_order_seller(ctx)` trả `order_status`, `item_ids`, `seller_ids`, `multi_seller`    | [x]  |
| 2B.3 | Tạo file `delivery_agent.py`                                                                    | [x]  |
| 2B.4 | Hàm `analyze_delivery(ctx)` tính `carrier_after_limit` (per item) và `delivered_after_estimate` | [x]  |
| 2B.5 | Sinh evidence ứng viên: `order:<id>`, `item:<id>:<n>`, `seller:<id>`                            | [x]  |
| 2B.6 | Unit test trên `EC_001`, `EC_010`, `EC_025` — chạy được, kết quả hợp lý                         | [x]  |
| 2B.7 | Commit + push nhánh `feat/person-B`                                                             | [x]  |




### Person C — Payment + Policy Agent


| #     | Task                                                                                                         | Tick |
| ----- | ------------------------------------------------------------------------------------------------------------ | ---- |
| 2C.1  | Tạo file `payment_agent.py`                                                                                  | [x]  |
| 2C.2  | Hàm `analyze_payment(ctx)` tính `payment_total`, đối soát với `item_total + freight_total` (sai số 0.10 BRL) | [x]  |
| 2C.3  | Phát hiện `valid_split_payment` khi ≥2 payment row                                                           | [x]  |
| 2C.4  | Sinh evidence `payment:<order_id>:<seq>`                                                                     | [x]  |
| 2C.5  | Tạo file `policy_agent.py`                                                                                   | [x]  |
| 2C.6  | Hàm `decide(ctx, signals)` áp dụng đúng thứ tự 6 rule trong README mục 4                                     | [x]  |
| 2C.7  | Map `primary_issue` ↔ `cause_code` (bảng 6 hàng README mục 4 cuối)                                           | [x]  |
| 2C.8  | Xử lý edge case "order không có item → total=0, list rỗng"                                                   | [x]  |
| 2C.9  | Tính `recommended_refund_brl`, `resolution_actions`, `case_status`, `confidence`                             | [x]  |
| 2C.10 | Unit test 6 case mô phỏng (mỗi rule 1 case) — pass hết                                                       | [x]  |
| 2C.11 | Commit + push nhánh `feat/person-C`                                                                          | [x]  |




### Person D — Verifier + Trace + Templates


| #    | Task                                                                                                                   | Tick |
| ---- | ---------------------------------------------------------------------------------------------------------------------- | ---- |
| 2D.1 | Tạo file `verifier_agent.py`                                                                                           | [ ]  |
| 2D.2 | Hàm `verify(output, ctx)` kiểm tra evidence ID tồn tại trong CSV (lookup `data_loader`)                                | [ ]  |
| 2D.3 | Kiểm tra giới hạn: ≤5 ID/loại, ≤10 evidence, ≤3 root causes, ≤3 parties, ≤5 actions                                    | [ ]  |
| 2D.4 | Kiểm tra `confidence ∈ [0,1]`, số tiền `recommended_refund ≤ payment_total`                                            | [ ]  |
| 2D.5 | Kiểm tra schema đúng README mục 6 (đủ field, đúng kiểu)                                                                | [ ]  |
| 2D.6 | Tạo file `trace.py` sinh `trace.jsonl` (1 dòng/case: case_id, handoff steps, primary_issue, confidence, verifier_pass) | [ ]  |
| 2D.7 | Copy `individual_01998_TranDinhDang.md` → `individual_<MSSV>_<Ten>.md` cho 4 người                                     | [ ]  |
| 2D.8 | Tạo file `run_batch.py` — loop 50 case, gọi Coordinator, ghi `output/EC_XXX.json`                                      | [ ]  |
| 2D.9 | Commit + push nhánh `feat/person-D`                                                                                    | [ ]  |


---



## Phase 3 — Coordinator + Tích hợp (60–90 phút)


| #   | Task                                                                                                                           | Owner     | Tick |
| --- | ------------------------------------------------------------------------------------------------------------------------------ | --------- | ---- |
| 3.1 | A merge 3 nhánh B/C/D vào `main`, resolve conflict                                                                             | A         | [ ]  |
| 3.2 | Code `coordinator_agent.py`: nhận `EC_XXX.json` → build `CaseContext` → gọi 4 sub-agent → tổng hợp → gọi Verifier → ghi output | A         | [ ]  |
| 3.3 | Test 1 case đầu (`EC_001`), output khớp schema                                                                                 | A         | [ ]  |
| 3.4 | Chạy batch 5 case đầu, kiểm tra 5 file output                                                                                  | D         | [ ]  |
| 3.5 | Fix bug interface / data flow nếu có                                                                                           | A + B/C/D | [ ]  |
| 3.6 | Chạy full 50 case                                                                                                              | D         | [ ]  |


---



## Phase 4 — Kiểm thử & Tinh chỉnh (90–105 phút)


| #   | Task                                                      | Owner | Tick |
| --- | --------------------------------------------------------- | ----- | ---- |
| 4.1 | Đếm output: đúng 50 file, không file lạ                   | D     | [ ]  |
| 4.2 | Lọc các case bị Verifier fail, liệt kê cho A              | D     | [ ]  |
| 4.3 | Đối chiếu bảng rule với 3–5 case bất kỳ (sample thủ công) | C     | [ ]  |
| 4.4 | Sửa rule/evidence sai (nếu có)                            | B + C | [ ]  |
| 4.5 | Sửa `confidence` nếu nhiều case >0.95 không hợp lý        | C     | [ ]  |
| 4.6 | Chạy lại batch sau khi sửa, đảm bảo deterministic         | D     | [ ]  |
| 4.7 | Sinh `trace.jsonl` cuối cùng (đè file cũ, không append)   | D     | [ ]  |


---



## Phase 5 — Tài liệu & Nộp bài (105–120 phút)


| #    | Task                                                                      | Owner | Tick |
| ---- | ------------------------------------------------------------------------- | ----- | ---- |
| 5.1  | Viết `architecture.md` (sơ đồ agent ASCII, vai trò, data access, handoff) | A     | [ ]  |
| 5.2  | Viết `metadata.json` (model name, params, framework, runtime)             | A     | [ ]  |
| 5.3  | Commit toàn bộ source code lên repo (KHÔNG commit `.env`)                 | A     | [ ]  |
| 5.4  | B điền `individual_<MSSV_B>_<Ten>.md` (phần việc + end-to-end)            | B     | [ ]  |
| 5.5  | C điền `individual_<MSSV_C>_<Ten>.md`                                     | C     | [ ]  |
| 5.6  | D điền `individual_<MSSV_D>_<Ten>.md`                                     | D     | [ ]  |
| 5.7  | A review 4 file individual, đảm bảo không trùng lặp nguyên văn            | A     | [ ]  |
| 5.8  | Nén folder `output/` thành `output.zip` (chỉ chứa 50 JSON)                | A     | [ ]  |
| 5.9  | Kiểm tra zip: mở thử, đếm file = 50, không có file khác                   | A     | [ ]  |
| 5.10 | Final commit + push repo, nộp zip                                         | A     | [ ]  |


---



## Tiến độ tổng (đếm tick)


| Phase                    | Tổng task | Đã xong | %       |
| ------------------------ | --------- | ------- | ------- |
| Phase 0 — Setup          | 7         | 6       | 86%     |
| Phase 1 — Schema & Data  | 5         | 0       | 0%      |
| Phase 2 — Agents lõi     | 27        | 0       | 0%      |
| Phase 3 — Coordinator    | 6         | 0       | 0%      |
| Phase 4 — Kiểm thử       | 7         | 0       | 0%     |
| Phase 5 — Tài liệu & Nộp | 10        | 0       | 0%     |
| **TỔNG**                 | **62**    | **11**  | **18%** |


---



## Những việc cần xử lý NGAY nếu kẹt (escalate lên A)

- [ ] Conflict giữa các nhánh khi merge
- [ ] Policy cho ra kết quả trái ngược bảng README mục 4
- [ ] ≥10 case bị Verifier fail cùng lúc
- [ ] Output không khớp schema khi chạy full batch
- [ ] Không tìm thấy order trong CSV (case_id không map được)

---



## Quy tắc confidence (gợi ý)


| Tình huống                            | Confidence  |
| ------------------------------------- | ----------- |
| Evidence rõ ràng, 1 seller, 1 payment | 0.90 – 0.95 |
| Có split payment hoặc multi-seller    | 0.85        |
| Phải suy diễn từ dữ liệu thiếu        | 0.70        |


---



## Ghi chú trong buổi


| Giờ   | Sự kiện                                  | Ghi chú |
| ----- | ---------------------------------------- | ------- |
| 9:00  | Checkpoint 1 — công bố input             |         |
| 9:30  | Checkpoint 2 — competition bắt đầu       |         |
| 11:30 | Còn 1 tiếng — chạy full batch            |         |
| 12:00 | Còn 30' — chỉ tinh chỉnh + viết tài liệu |         |
| 12:30 | Checkpoint 3 — chốt leaderboard, nộp zip |         |


