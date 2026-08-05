# Member Role Report — Day 9: Multi Agent A2A

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình. Không sao chép nguyên báo cáo chung hoặc báo cáo của thành viên khác. Thay nội dung trong dấu `[ ]` và xóa các dòng hướng dẫn không cần thiết trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin       | Nội dung      |
| --------------- | ------------  |
| Họ và tên       | Chu Thành Dũng|
| MSSV            | 2A202601405   |
| Khóa/Lớp        | K3            |
| Vai trò chính   | Payment + Policy Agent (Person C) |
| Ngày hoàn thành | 2026-08-05    |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao   | Trạng thái                            |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| Payment Agent      | `payment_agent.py` / `analyze_payment()` | `CaseContext` (chứa payments, items) | Dict `signals` chứa tổng tiền, cờ `is_split_payment` và danh sách `payment_evidences` | Hoàn thành |
| Policy Agent       | `policy_agent.py` / `decide()` | `CaseContext`, `signals` | Cập nhật trực tiếp `CaseContext` (refund, actions, confidence, root_cause) | Hoàn thành |
| Unit Tests         | `test_person_c.py` | Các mock objects của CaseContext | Báo cáo test pass cho cả 6 rules | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Tích hợp Coordinator      | Person A (`coordinator_agent.py`) | Đảm bảo Coordinator gọi đúng `analyze_payment` và truyền đủ `signals` cho `decide()`. Fix các conflict khi merge code lên `main`. |
| Gỡ lỗi Data Flow          | Person B và D                 | Đối soát chéo cờ `carrier_after_limit` và `delivered_after_estimate` từ Delivery Agent sang Policy Agent hoạt động đúng. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao          | Cách xác minh   |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Xử lý đối soát tài chính | `payment_agent.py` | Tính độ lệch tiền `payment_mismatch` và nhận diện `valid_split_payment` chính xác. | Chạy `python test_person_c.py` |
| Ra quyết định hoàn trả | `policy_agent.py` | Đảm bảo tính minh bạch, áp dụng chặt 6 policy rules của Olist. | Chạy `python test_person_c.py` |

Tôi đã bàn giao thành công 2 agent quan trọng nhất trong việc định đoạt tài chính của một case khiếu nại. Các agent của tôi đã sinh ra `evidence_ids` chuẩn xác dạng `payment:<id>:<seq>` và `policy:<root_cause>`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Trong quy trình Dispute Resolution, khách hàng có thể trả bằng nhiều phương thức (Split Payment) hoặc có sự sai lệch nhỏ về phí vận chuyển. Hơn nữa, Olist có bộ 6 chính sách hoàn tiền chồng chéo (Cancel, Hết hàng, Giao trễ do Seller, Giao trễ do Carrier, v.v.). Vai trò C cần giải quyết bài toán: Làm sao để đối soát tiền chính xác và áp dụng đúng Rule để bảo vệ tiền của sàn, đồng thời tìm đúng người chịu trách nhiệm.

### Cách triển khai

- **Payment Agent**: Lấy tổng `payment_value` trừ đi tổng `price` + `freight_value`. Nếu độ lệch tuyệt đối $\le 0.10$ BRL và có từ 2 thanh toán trở lên, bật cờ `valid_split_payment`.
- **Policy Agent**: Sử dụng kiến trúc "Chain of Responsibility" bằng các câu lệnh if/return tuần tự. Kiểm tra từ mức độ nghiêm trọng cao nhất (`canceled`, `unavailable`) xuống các lỗi vận hành (`late_delivery_seller`, `late_delivery_logistics`), và cuối cùng là các case từ chối hoàn tiền. Điểm `confidence` được tính động: giảm xuống `0.85` nếu đơn hàng có split payment hoặc multi-seller do rủi ro tranh chấp cao hơn.

### Input, output và contract

| Thành phần              | Mô tả                                  |
| ----------------------- | -------------------------------------- |
| Input                   | `CaseContext` tổng hợp dữ liệu từ 9 file CSV. |
| Output                  | Output trực tiếp vào `CaseContext` các trường: `primary_issue`, `case_status`, `recommended_refund`, `resolution_actions`. |
| Module phụ thuộc        | `Delivery Agent` (cần output về trạng thái giao hàng trễ). |
| Module sử dụng output   | `Coordinator Agent` và `Verifier Agent` (để kiểm tra giới hạn hoàn tiền). |
| Điều kiện lỗi cần xử lý | Đơn hàng không có sản phẩm (tránh lỗi logic chia cho 0 hoặc index rỗng). |

### Cách xác minh

```bash
python test_person_c.py
```

- **Kết quả mong đợi:** 8 bài tests passed, mỗi rule từ 1 đến 6 đều trả về đúng `root_cause_code` và số tiền `recommended_refund`.
- **Kết quả thực tế:** `Ran 8 tests in 0.001s. OK`
- **Artifact/log:** `test_person_c.py` (Source code trong repo).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần xử lý thứ tự ưu tiên của 6 policy rules theo đúng quy định.
- **Các phương án đã cân nhắc:** (1) Tính điểm độc lập cho từng rule và cho model tự quyết định, (2) Code cứng cấu trúc If/return tuần tự.
- **Phương án đã chọn:** Phương án 2 (Cấu trúc If/return).
- **Lý do:** Trade-off hoàn toàn thiên về tính chính xác (Correctness). Trong e-commerce, các rule như "Đơn bị hủy" mang tính tuyệt đối và phải override các rule giao hàng. Dùng if/return giúp khóa logic, tránh tình trạng "ảo giác" của LLM, tiết kiệm token và chạy deterministic 100%.
- **Bằng chứng quyết định phù hợp:** Toàn bộ 50 case khi qua `policy_agent` không có case nào vi phạm thứ tự rule, Verifier pass dễ dàng với thời gian chạy $O(1)$.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Có những đơn hàng bị lệch tiền rất nhỏ (ví dụ 115.01 BRL vs 115.00 BRL) làm hệ thống không nhận diện được `valid_split_payment`.
- **Lệnh hoặc bước tái hiện:** Chạy test đối soát với đơn hàng có `item_total` bị lẻ do số thập phân.
- **Nguyên nhân gốc:** Float point precision trong Python và sai lệch làm tròn từ hệ thống thanh toán gốc của Olist.
- **Cách xử lý:** Thay vì dùng phép bằng `==`, tôi sử dụng ngưỡng dung sai (tolerance): `abs(payment_total - (item_total + freight_total)) <= config.PAYMENT_TOLERANCE_BRL` (0.10 BRL).
- **Cách xác minh sau khi sửa:** `python test_person_c.py` cho test case `valid_split_payment` và passed thành công.
- **Điều học được:** Khi làm việc với dữ liệu tài chính dạng `float`, bắt buộc phải sử dụng dung sai hoặc dùng kiểu `Decimal` thay vì so sánh tuyệt đối.

## 7. Hiểu biết về luồng end-to-end

*(Ghi chú: Đã điều chỉnh lại các câu hỏi trong template mẫu cho phù hợp với bài lab Multi-Agent Dispute Resolution)*

**Luồng dữ liệu của hệ thống Dispute Resolution diễn ra như sau:**
1. Khi có request JSON (từ `input/EC_XXX.json`), **Coordinator Agent** tiếp nhận và khởi tạo `CaseContext`.
2. **Data Loader** lấy `claimed_order_id`, tra cứu $O(1)$ vào 9 bảng CSV (orders, items, payments...) để đắp dữ liệu vào `CaseContext`.
3. Coordinator truyền Context sang **Order/Seller & Delivery Agent** (Person B) để kiểm tra các mốc thời gian giao hàng.
4. Coordinator gọi tiếp **Payment & Policy Agent** (Vai trò của tôi - Person C) để đối soát tiền, áp dụng 6 luật e-commerce và đưa ra phán quyết cuối cùng (Hoàn tiền cho ai, lỗi do ai).
5. Cuối cùng, kết quả chạy qua **Verifier Agent** (Person D) để soát lỗi (số tiền hoàn không vượt quá số đã thu, ID evidence có thực) trước khi ghi ra file JSON cuối cùng vào thư mục `output/`.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Chu Thành Dũng
**Ngày xác nhận:** 2026-08-05
