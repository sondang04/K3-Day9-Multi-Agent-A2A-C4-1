# Member Role Report — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung |
| --------------- | -------- |
| Họ và tên       | `<Ten>` |
| MSSV            | `<MSSV_B>` |
| Khóa/Lớp        | K3 — Nhóm C4-1 |
| Vai trò chính   | Person B — Order/Seller Agent + Delivery Agent |
| Ngày hoàn thành | 2026-08-05 |

> Cần thay `<Ten>` và `<MSSV_B>` bằng thông tin thật trước khi nộp.

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ----------------- | ---------- |
| Phân tích cấu trúc đơn hàng và người bán | `order_seller_agent.py` — `analyze_order_seller(ctx)` | `CaseContext` đã được DataLoader dựng từ case input và dữ liệu Olist | `order_status`, `item_ids`, `seller_ids`, `multi_seller`, `evidence_ids` | Hoàn thành |
| Phân tích mốc giao hàng | `delivery_agent.py` — `analyze_delivery(ctx)` | `CaseContext` chứa order, items và các timestamp liên quan | `carrier_after_limit`, trạng thái theo từng item, `delivered_after_estimate`, item/seller giao trễ và evidence | Hoàn thành |
| Kiểm thử module Person B | `test_person_b.py` | Ba case `EC_001`, `EC_010`, `EC_025` và ba CSV tối thiểu cần thiết | Kết quả assertions và thông báo `[PASS]` | Hoàn thành |
| Báo cáo cá nhân | `individual_<MSSV_B>_<Ten>.md` | Phần việc đã triển khai và kết quả kiểm thử | Báo cáo vai trò, kỹ thuật và hiểu biết end-to-end | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Chuẩn hóa interface đầu ra dạng dictionary, JSON-serializable | Coordinator Agent của Person A | Coordinator có thể nhận signals trực tiếp mà không phải chuyển đổi dataclass riêng |
| Đồng bộ các computed fields về `CaseContext` | Policy Agent và Coordinator | `ctx.order_status`, `ctx.item_ids`, `ctx.seller_ids`, `ctx.carrier_after_limit`, `ctx.delivered_after_estimate` được cập nhật để tương thích kiến trúc hiện tại |
| Sinh evidence ID đúng convention | Verifier Agent của Person D | Evidence có dạng `order:<id>`, `item:<order_id>:<n>`, `seller:<id>` để verifier có thể đối chiếu |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Xây dựng Order/Seller Agent | `order_seller_agent.py` | Phân tích deterministic trạng thái đơn, danh sách item, seller và multi-seller | Chạy `python test_person_b.py` |
| Xây dựng Delivery Agent | `delivery_agent.py` | So sánh thời điểm bàn giao carrier với `shipping_limit_date` theo từng item; so sánh ngày giao thực tế với ngày dự kiến | Chạy `python test_person_b.py` |
| Sinh evidence ứng viên | Hai agent Person B | Evidence theo order/item/seller, không phát evidence order khi lookup order thất bại | Kiểm tra assertions trong `test_person_b.py` |
| Kiểm thử ba case yêu cầu | `test_person_b.py` | `EC_001`, `EC_010`, `EC_025` đều pass | Dòng cuối terminal: `[PASS] Person B tests passed for EC_001, EC_010, EC_025` |

Một output cụ thể của phần việc Person B:

- `EC_001`: carrier nhận hàng sau giới hạn của item và giao cho khách sau ngày dự kiến.
- `EC_010`: carrier không nhận hàng sau giới hạn item nhưng đơn vẫn được giao sau ngày dự kiến.
- `EC_025`: ba item cùng một seller; không item nào bàn giao carrier muộn và đơn không giao sau ngày dự kiến.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline cần tách các tín hiệu dữ liệu khách quan khỏi bước quyết định chính sách. Phần Person B chịu trách nhiệm xác định cấu trúc order/seller và các dấu hiệu giao hàng trễ từ dữ liệu gốc. Các agent này không tự quyết định hoàn tiền hay nguyên nhân cuối cùng; chúng bàn giao signals và evidence cho Coordinator/Policy Agent.

### Cách triển khai

#### Order/Seller Agent

1. Đọc `order_status` từ `ctx.order` nếu order tồn tại.
2. Tạo item ID chuẩn bằng `ctx.get_order_item_key(item)`, có dạng `<order_id>:<order_item_id>`.
3. Lấy danh sách seller theo thứ tự xuất hiện và loại trùng bằng `dict.fromkeys`.
4. Xác định `multi_seller = True` khi có từ hai seller khác nhau.
5. Sinh evidence cho order, item và seller.
6. Đồng bộ các trường tính toán trở lại `CaseContext` để các module sau có thể dùng chung.

#### Delivery Agent

1. Chuẩn hóa timestamp bằng `datetime.fromisoformat` và xử lý an toàn giá trị rỗng, `None`, `nan` hoặc timestamp không hợp lệ.
2. Với mỗi item, so sánh `order_delivered_carrier_date` với `shipping_limit_date`.
3. Chỉ đánh dấu bàn giao trễ khi cả hai timestamp đều tồn tại và carrier date lớn hơn giới hạn.
4. Tổng hợp `carrier_after_limit` bằng phép `any()` trên kết quả từng item.
5. So sánh `order_delivered_customer_date` với `order_estimated_delivery_date` để tính `delivered_after_estimate`.
6. Trả thêm `late_item_ids`, `late_seller_ids` và evidence để Policy/Verifier có thể giải thích quyết định.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | Một đối tượng `schema.CaseContext` chứa order, items, sellers và timestamps đã được DataLoader truy xuất |
| Output Order/Seller | Dictionary JSON-serializable gồm `order_status`, `item_ids`, `seller_ids`, `multi_seller`, `evidence_ids` |
| Output Delivery | Dictionary JSON-serializable gồm `carrier_after_limit`, `carrier_after_limit_by_item`, `delivered_after_estimate`, `late_item_ids`, `late_seller_ids`, `evidence_ids` |
| Module phụ thuộc | `schema.py`; dữ liệu context thường do `data_loader.py` dựng |
| Module sử dụng output | `coordinator_agent.py`, `policy_agent.py`, `verifier_agent.py` |
| Điều kiện lỗi cần xử lý | Order không tồn tại, order không có item, timestamp thiếu/sai định dạng, một order có nhiều item hoặc nhiều seller |

### Cách xác minh

```bash
python test_person_b.py
```

- **Kết quả mong đợi:** Ba case chạy hết, các assertions về order, item, seller, evidence và delivery signals đều đúng.
- **Kết quả thực tế:** `EC_001`, `EC_010`, `EC_025` đều được in kết quả hợp lý và kết thúc bằng `[PASS] Person B tests passed for EC_001, EC_010, EC_025`.
- **Artifact/log:** `test_person_b.py`; không chứa API key hoặc secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần biểu diễn trạng thái bàn giao carrier trễ cho order có thể chứa nhiều item với các `shipping_limit_date` khác nhau.
- **Các phương án đã cân nhắc:**
  1. Chỉ trả một boolean chung cho toàn order.
  2. Trả kết quả theo từng item rồi tổng hợp thêm boolean chung.
- **Phương án đã chọn:** Trả `carrier_after_limit_by_item` theo item, đồng thời trả `carrier_after_limit = any(...)`.
- **Lý do:** Kết quả theo item giữ được độ chi tiết để xác định đúng evidence và seller chịu trách nhiệm; boolean chung giúp Policy Agent áp dụng rule đơn giản. Cách này cân bằng giữa khả năng giải thích và tính thuận tiện khi tích hợp.
- **Bằng chứng quyết định phù hợp:** `EC_025` có ba item và test xác minh dictionary chứa đủ cả ba item; kết quả tổng hợp vẫn đúng và deterministic.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi:** Khi dùng `DataLoader` toàn cục cho unit test, chương trình phải đọc và materialize toàn bộ 9 CSV lớn bằng `iterrows()`, khiến test ba case chạy rất chậm và có thể trông như bị treo.
- **Lệnh hoặc bước tái hiện:** Dựng đầy đủ DataLoader rồi chạy test chỉ cho `EC_001`, `EC_010`, `EC_025`.
- **Nguyên nhân gốc:** Unit test chỉ cần một số ít order nhưng loader dự án tải toàn bộ dataset Olist trước khi trả context.
- **Cách xử lý:** Viết loader tối thiểu ngay trong `test_person_b.py`, chỉ quét ba CSV cần thiết và chỉ dựng context cho ba order mục tiêu. Logic agent và schema chính không bị thay đổi.
- **Cách xác minh sau khi sửa:** Chạy `python test_person_b.py`; cả ba case hoàn tất và báo `[PASS]`.
- **Điều học được:** Unit test nên cô lập module đang kiểm tra và giảm phụ thuộc I/O lớn; integration test có thể tiếp tục dùng DataLoader đầy đủ.

## 7. Hiểu biết về luồng end-to-end

1. **Case input đi vào pipeline như thế nào?**  
   Mỗi file `input/EC_XXX.json` cung cấp `case_id`, thời điểm mở case, order ID khách khai báo, nội dung khiếu nại, ngôn ngữ và policy version. Coordinator đọc file này rồi gọi DataLoader để truy xuất dữ liệu liên quan từ các CSV Olist và dựng `CaseContext`.

2. **Các agent phối hợp ra sao?**  
   Coordinator chuyển cùng một `CaseContext` cho các agent chuyên trách. Order/Seller Agent và Delivery Agent tạo các signals về order, item, seller và giao hàng. Payment Agent đối soát thanh toán. Policy Agent áp dụng các rule theo thứ tự ưu tiên để tạo quyết định sơ bộ.

3. **Evidence dùng để làm gì?**  
   Evidence ID nối kết kết luận với bản ghi dữ liệu gốc, ví dụ `order:<id>`, `item:<order_id>:<n>`, `seller:<id>` và `payment:<order_id>:<seq>`. Verifier dùng các ID này để kiểm tra chúng thực sự tồn tại và bảo đảm output có thể giải thích, truy vết.

4. **Verifier khác Policy Agent ở điểm nào?**  
   Policy Agent quyết định vấn đề chính, nguyên nhân, bên chịu trách nhiệm, hành động và mức hoàn tiền dựa trên signals. Verifier không thay rule nghiệp vụ mà kiểm tra schema, giới hạn số lượng, ID evidence, range confidence và các ràng buộc số tiền trước khi ghi output.

5. **Luồng output và trace kết thúc thế nào?**  
   Khi output qua verifier, Coordinator ghi JSON tương ứng vào `output/EC_XXX.json`. Batch runner lặp qua 50 case. Trace module ghi lại các bước handoff, issue chính, confidence và trạng thái verifier để phục vụ audit. Cuối cùng folder output phải chứa đúng 50 JSON từ `EC_001.json` đến `EC_050.json`.

6. **Vai trò của Person B trong end-to-end là gì?**  
   Person B cung cấp các tín hiệu nền tảng để phân biệt lỗi cấu trúc đơn, nhiều seller, seller bàn giao carrier muộn và giao cho khách sau ngày dự kiến. Nếu tín hiệu hoặc evidence sai, Policy Agent có thể gán sai cause code hoặc Verifier có thể từ chối output; vì vậy module Person B phải deterministic và bám sát timestamp/item thực tế.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** `<Ten>`  
**Ngày xác nhận:** 2026-08-05
