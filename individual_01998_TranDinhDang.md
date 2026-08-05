# Member Role Report — Day 9: Multi Agent A2A

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình.

## 1. Thông tin cá nhân


| Thông tin       | Nội dung                  |
| --------------- | ------------------------- |
| Họ và tên       | Trần Đình Đăng            |
| MSSV            | 01998                     |
| Khóa/Lớp        | K3                        |
| Vai trò chính   | Lead / Coordinator / Data Foundation |
| Ngày hoàn thành | 2026-08-05                |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ----------------- | ---------- |
| Data Loader        | `data_loader.py`          | data/*.csv     | CaseContext với O(1) lookup | Hoàn thành |
| Schema Definition  | `schema.py`                | Yêu cầu nghiệp vụ | CaseContext dataclass | Hoàn thành |
| Config             | `config.py`                | .env           | Cấu hình central | Hoàn thành |
| Coordinator Agent  | `coordinator_agent.py`      | case_data, ctx | Output JSON theo schema | Hoàn thành |
| Architecture Doc   | `architecture.md`           | Mã nguồn      | Sơ đồ agent + luồng dữ liệu | Hoàn thành |
| Metadata           | `metadata.json`             | Config + code | Thông tin model/framework | Hoàn thành |
| Batch Runner (tích hợp) | `run_batch.py` + `coordinator_agent.py` | input/*.json | output/*.json + trace.jsonl | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Tích hợp agents B/C/D     | Nhóm                          | Merge 3 nhánh, resolve conflicts |
| Review code               | B, C, D                       | Đảm bảo interface nhất quán |
| Chạy batch full 50 cases  | Toàn nhóm                     | 50/50 pass Verifier |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ----------------- | ------------- |
| Xây dựng Data Loader với O(1) lookup | `data_loader.py` | 9 CSV loaded, O(1) get_order/get_item/get_payment | Test 1 case |
| Định nghĩa CaseContext schema | `schema.py` | Dataclass với đầy đủ fields cho tất cả agents | Import across modules |
| Tạo Coordinator Agent | `coordinator_agent.py` | Handoff 5 agents theo đúng thứ tự | Chạy EC_001 thành công |
| Tích hợp coordinator vào batch | `run_batch.py` + `coordinator_agent.py` | --pipeline coordinator hoạt động | 50/50 pass |
| Viết architecture.md | `architecture.md` | Sơ đồ agent + data flow + evidence format | Review doc |
| Viết metadata.json | `metadata.json` | Model name, framework, runtime | Submit zip |

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Làm Lead, tôi cần thiết kế Data Foundation để tất cả agents có thể truy cập dữ liệu Olist một cách hiệu quả. Vấn đề cốt lõi:
- 9 CSV files với hàng trăm nghìn rows cần join theo order_id
- Mỗi agent cần lookup độc lập mà không rescan toàn bộ data
- CaseContext phải chứa đủ thông tin cho Policy Agent đưa ra quyết định

### Cách triển khai

1. **Data Loader Pattern**: Load tất cả 9 CSV vào dict lookup O(1) theo key chính:
   - `_orders`: order_id → OrderInfo
   - `_order_items`: order_id → list[OrderItemInfo]
   - `_payments`: order_id → list[PaymentInfo]
   - `_sellers`: seller_id → SellerInfo

2. **CaseContext Dataclass**: Tập hợp tất cả data cần thiết:
   - Order info, items, payments, sellers, reviews, products
   - Computed fields: item_total, freight_total, payment_total
   - Assessment results: primary_issue, root_cause, responsible_parties, etc.

3. **Coordinator Handoff Pattern**:
   ```
   Order/Seller → Delivery → Payment → Policy → Verifier
   ```
   Mỗi agent nhận CaseContext, bổ sung signals, pass cho agent tiếp theo

4. **Evidence Selection**: Round-robin selection với cap 5/entity, 10 total

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | `input/EC_XXX.json` (case_id, claimed_order_id, message) |
| Output                  | Output JSON theo schema README mục 6 |
| Module phụ thuộc        | B: order_seller_agent, delivery_agent; C: payment_agent, policy_agent; D: verifier_agent |
| Module sử dụng output   | run_batch.py, trace.py |
| Điều kiện lỗi cần xử lý | Order không tìm thấy → item_ids/seller_ids rỗng, totals = 0 |

### Cách xác minh

```bash
python run_batch.py --cases EC_001 --pipeline coordinator
```

- **Kết quả mong đợi:** EC_001 pass verifier, refund = freight
- **Kết quả thực tế:** OK, late_delivery_seller, refund=12.04
- **Artifact/log:** `output/EC_001.json`, `trace.jsonl`

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Thiết kế Data Foundation - dùng singleton pattern cho DataLoader hay instantiate mỗi lần?
- **Các phương án đã cân nhắc:**
  1. Singleton với global `_loader` - load một lần, cache forever
  2. Instantiate mỗi lần - clean nhưng chậm (load 9 CSV x 50 = 450 lần)
  3. Factory pattern với reset() - linh hoạt cho testing
- **Phương án đã chọn:** Singleton với `get_loader()` và `reset_loader()`
- **Lý do:** Performance critical - 50 cases cần load data nhanh. Singleton tránh 450 lần đọc CSV. `reset_loader()` hỗ trợ unit testing.
- **Bằng chứng quyết định phù hợp:** Batch 50 cases chạy trong ~80s, mỗi case chỉ lookup không rescan

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `coordinator_agent.py` không tìm thấy khi chạy `run_batch.py --pipeline coordinator`
- **Lệnh hoặc bước tái hiện:** Chạy batch với pipeline=coordinator trả về lỗi import
- **Nguyên nhân gốc:** File chưa tồn tại (Phase 3.2 chưa làm)
- **Cách xử lý:** Tạo `coordinator_agent.py` với entrypoint `process_case()` và integration vào `run_batch.py`
- **Cách xác minh sau khi sửa:** `python run_batch.py --cases EC_001 --pipeline coordinator` → pass
- **Điều học được:** run_batch.py đã có logic detect coordinator_agent.py, chỉ cần tạo file đúng interface

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn:

1. **Dữ liệu đi từ CSV đến CaseContext như thế nào?**
   - DataLoader đọc 9 CSV vào memory dict
   - `build_case_context(case_data)` join theo claimed_order_id
   - CaseContext chứa order + items + payments + sellers + computed totals

2. **Evaluation dùng để đo quality ra sao?**
   - Verifier Agent check evidence IDs có tồn tại trong CSV không
   - So sánh financial totals với CSV (epsilon = 0.01)
   - Validate primary_issue ↔ cause_code ↔ action ↔ party mapping

3. **Quality checks khác freshness monitoring ở điểm nào?**
   - Quality checks: schema validation, evidence existence, financial accuracy
   - Freshness: không áp dụng - dữ liệu Olist là static snapshot

4. **Vì sao phải dùng cùng test set?**
   - Để so sánh deterministic giữa các runs
   - Đảm bảo reproducibility của kết quả

5. **Repair được xem là thành công dựa trên artifact nào?**
   - Verifier pass 50/50
   - Trace.jsonl ghi đầy đủ handoff steps
   - Output files khớp schema README mục 6

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Đình Đăng
**Ngày xác nhận:** 2026-08-05
