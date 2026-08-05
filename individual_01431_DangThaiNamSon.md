# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                       |
| --------------- | ---------------------------------------------- |
| Họ và tên       | Đặng Thái Nam Sơn                              |
| MSSV            | 2A202601431                                    |
| Khóa/Lớp        | K3                                             |
| Vai trò chính   | Person D — Verifier Agent, Trace, Batch Runner |
| Ngày hoàn thành | 2026-08-05                                     |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable   | File/hàm phụ trách                                                                                      | Input nhận vào                                             | Output bàn giao                                             | Trạng thái |
| -------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------ | ---------- |
| Verifier Agent       | `verifier_agent.py` — `verify()`, `VerificationResult`, `RULE_TABLE`                                    | Output dict của Coordinator + `CaseContext` + `DataLoader`  | `VerificationResult(passed, errors, warnings)`               | Hoàn thành |
| Trace                | `trace.py` — `TraceRecorder`, `TraceWriter`, `write_trace()`, `read_trace()`                            | Handoff step của từng agent + kết quả verifier               | `trace.jsonl` (1 dòng/case, ghi đè mỗi lượt chạy)            | Hoàn thành |
| Batch Runner         | `run_batch.py` — `run()`, `process_case()`, `local_pipeline()`, `assemble_output()`, `select_evidence()` | 50 file `input/EC_XXX.json`                                 | 50 file `output/EC_XXX.json` + `trace.jsonl` + danh sách fail | Hoàn thành |
| Unit test phần D     | `test_person_d.py` — 35 test                                                                            | `CaseContext` tổng hợp (không đọc CSV)                      | Kết quả test 35/35 pass                                       | Hoàn thành |
| File báo cáo cá nhân | `individual_<MSSV>_<HoTen>.md` (task 2D.7)                                                              | Template báo cáo                                            | File của tôi (`individual_01431_...`); B và C tự tạo file của họ | Hoàn thành (phần của tôi) |

Ranh giới phần việc của tôi: tôi **không** viết rule nghiệp vụ (C) và **không** tính tín hiệu domain (B). Tôi nhận output cuối và chứng minh nó dựng được từ dữ liệu thật, đồng thời cung cấp đường chạy end-to-end để cả nhóm có kết quả 50 case trước khi Coordinator của A hoàn thành.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                                          | Thành viên/module được hỗ trợ | Kết quả                                                                                                          |
| -------------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Pipeline tạm thay Coordinator trong `run_batch.py`  | A (task 3.2), B, C            | Nhóm chạy được full 50 case khi `coordinator_agent.py` chưa tồn tại; runner tự chuyển sang coordinator khi A push lên |
| Đối soát rule của C bằng verifier                   | C (`policy_agent.py`)         | 50/50 case khớp bảng README mục 4 (issue ↔ cause ↔ action ↔ party ↔ cơ sở refund), không case nào sai mapping        |
| Resolve conflict và merge `sondang` vào `main`      | Cả nhóm                       | Commit merge `1ea5be5`; chặn được việc merge ghi đè nhầm file báo cáo của A (chi tiết mục 6)                         |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện                          | File/hàm/artifact liên quan               | Kết quả bàn giao                                | Cách xác minh                                 |
| ---------------------------------------------- | ----------------------------------------- | ------------------------------------------------ | --------------------------------------------- |
| Verifier kiểm evidence, giới hạn, tiền, schema | `verifier_agent.py` (698 dòng)            | `VerificationResult` cho mỗi case; 50/50 pass    | `python run_batch.py` → "Verifier fail: 0"    |
| Sinh trace 1 dòng/case, ghi đè không append    | `trace.py`, `trace.jsonl`                 | 50 dòng JSONL, mỗi dòng 6 handoff step           | `wc -l trace.jsonl` → 50                      |
| Chạy batch 50 case, ghi output đúng schema     | `run_batch.py`, `output/EC_001..050.json` | 50 file JSON, không file lạ                      | `ls output \| wc -l` → 50                     |
| Chứng minh pipeline deterministic              | `output/`                                 | 2 lần chạy cho md5 tổng giống hệt nhau           | `md5sum output/*.json \| md5sum` (chạy 2 lần) |
| Unit test verifier + trace                     | `test_person_d.py` (438 dòng, 35 test)    | 35/35 pass trong ~0.5s                           | `python test_person_d.py`                     |
| Lọc case fail cho A (task 4.2)                 | `logging/verifier_report.json`            | Không sinh file vì fail = 0                      | Chạy batch, xem mục "Case Verifier fail"      |

Một output cụ thể mà phần việc của tôi tạo ra và giúp xác minh:

`trace.jsonl` — mỗi dòng là một case. Ví dụ EC_001 ghi lại 6 bước handoff `run_batch → data_loader → order_seller_agent → delivery_agent → payment_agent → policy_agent → verifier_agent`, kèm signal tóm tắt của từng agent (`carrier_after_limit: true`, `delivered_after_estimate: true`, `payment_total: 131.94`), kết luận `primary_issue: late_delivery_seller`, `confidence: 0.95` và `verifier_pass: true`. Nhờ file này có thể truy ngược vì sao một case ra kết luận đó mà không cần chạy lại batch.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Đề bài chấm rất nặng phần bằng chứng: evidence ID không tồn tại trong CSV hoặc sai định dạng bị tính là false positive, và case bị hard gate nhận 0 điểm. Nghĩa là một agent "nói hay" nhưng bịa ID hoặc lệch schema sẽ phá điểm cả case. Phần của tôi là lớp chặn cuối cùng: trước khi bất kỳ file nào được ghi vào `output/`, phải chứng minh được từng ID trong đó dựng từ một row có thật, từng con số khớp dữ liệu, và cấu trúc đúng README mục 6. Song song đó, hệ nhiều agent rất khó debug nếu không biết agent nào đưa ra tín hiệu gì, nên tôi làm thêm lớp trace.

### Cách triển khai

**Verifier — đối chiếu hai chiều, không tin output.** `verify(output, ctx, loader=None, check_csv=True)` không đọc lại logic của agent khác mà đối chiếu output với hai nguồn độc lập: CSV gốc (qua `data_loader`, lookup O(1)) và `CaseContext` của case đó. Bốn nhóm kiểm tra:

1. **Evidence và entity ID.** Mỗi ID được parse bằng regex theo đúng 5 dạng của README mục 5, sau đó tra ngược: `order:` phải có trong bảng orders; `item:<order>:<n>` phải có row item đúng `order_item_id`; `payment:<order>:<seq>` phải có row payment đúng `payment_sequential`; `seller:` phải có trong bảng sellers; `policy:` phải nằm trong 6 root cause code. Tôi thêm một tầng nữa là **phạm vi**: ID có thật trong CSV nhưng thuộc order khác vẫn bị coi là lỗi, vì với case này nó vẫn là false positive.
2. **Giới hạn.** ≤5 ID cho mỗi entity set và cho mỗi loại evidence, ≤10 evidence, ≤3 root cause, ≤3 responsible party, ≤5 action, và không được trùng lặp.
3. **Số tiền và confidence.** `confidence ∈ [0,1]`; `recommended_refund ≤ payment_total`; ba tổng tiền phải khớp giá trị tính lại từ CSV trong sai số 0.01; mọi số làm tròn 2 chữ số; `case_status` nhất quán với refund (`action_required` ⟺ refund > 0).
4. **Schema.** Đủ field, đúng kiểu, `currency = BRL`, `rank` là int không trùng, và edge case order không có item row thì `item_ids`/`seller_ids` rỗng còn `item_total_brl`/`freight_total_brl` bằng 0.0.

Phần tôi làm thêm ngoài phân công là `RULE_TABLE`: bảng 6 hàng của README mục 4 được mã hóa thành dữ liệu, nên verifier kiểm được cả **mapping** — `primary_issue` nào thì bắt buộc cause code nào, action nào, loại responsible party nào, và refund phải bằng tổng payment hay tổng freight hay 0. Nhờ vậy verifier không chỉ bắt lỗi schema mà bắt được cả lỗi rule của Policy Agent, thứ chiếm phần lớn trọng số điểm mỗi case.

**Trace — quan sát handoff.** `TraceRecorder.step(agent)` là context manager: đo thời gian, nhận `step["summary"]` là các signal quan trọng của agent đó, và nếu agent ném exception thì ghi step trạng thái `error` kèm loại lỗi rồi ném tiếp (không nuốt lỗi). `TraceWriter` mở file bằng mode `"w"` nên mỗi lượt chạy ghi đè, đúng yêu cầu "chỉ cần lượt chạy mới nhất", đồng thời mirror sang `logging/trace.jsonl`.

**Batch runner — chọn evidence.** Khi tổng hợp output phải chọn ≤10 evidence từ tập ứng viên có thể nhiều hơn. Thuật toán: luôn giữ `order:` và `policy:`, phần còn lại chia round-robin cho item/payment/seller để không loại hẳn một loại nào; trong mỗi loại, item và seller vi phạm hạn bàn giao được xếp trước vì đó là bằng chứng có giá trị nhất cho rule `late_delivery_seller`.

### Input, output và contract

| Thành phần              | Mô tả                                                                                                                                                                                                                                       |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input                   | `verify(output: dict, ctx: CaseContext, loader: DataLoader = None, check_csv: bool = True)`                                                                                                                                                 |
| Output                  | `VerificationResult(case_id, passed, errors, warnings, checked_evidence, checked_entities)`; có `to_dict()` để đưa vào trace                                                                                                                 |
| Module phụ thuộc        | `schema.CaseContext`, `data_loader.DataLoader`, `config` (giới hạn, `ROOT_CAUSE_CODES`, `PAYMENT_TOLERANCE_BRL`)                                                                                                                            |
| Module sử dụng output   | `run_batch.py` (chặn trước khi ghi file, lọc case fail cho A), `trace.py` (`verifier_pass`), `coordinator_agent.py` của A khi tích hợp Phase 3                                                                                               |
| Điều kiện lỗi cần xử lý | Order không tìm thấy trong CSV; order không có item row (total = 0, list rỗng); split payment nhiều row; seller không bán item nào trong order; evidence thuộc order khác; số tiền chưa làm tròn; một case ném exception giữa batch (ghi trace lỗi, batch vẫn chạy tiếp) |

Một chi tiết nhỏ nhưng quan trọng của contract: tham số `check_csv=False` cho phép verify dựa trên `CaseContext` thay vì nạp CSV. Nhờ đó 35 unit test chạy hết trong khoảng 0.5 giây, thay vì phải chờ nạp 9 file CSV (99.441 order, 112.650 item, 103.886 payment) ở mỗi lần chạy test.

### Cách xác minh

```bash
# 1. Unit test verifier + trace
python test_person_d.py

# 2. Chạy thử 5 case đầu
python run_batch.py --limit 5

# 3. Chạy full 50 case
python run_batch.py

# 4. Kiểm tra artifact
ls output | wc -l
wc -l trace.jsonl

# 5. Kiểm tra deterministic: chạy lệnh dưới, chạy lại batch, chạy lại lệnh dưới rồi so 2 chuỗi
md5sum output/*.json | md5sum
```

- **Kết quả mong đợi:** 35 test pass; 50 file output; verifier fail = 0; `trace.jsonl` 50 dòng; hai lần chạy cho cùng một md5.
- **Kết quả thực tế:** `Ran 35 tests — OK`; `File output ghi: 50`; `Verifier pass: 50 / Verifier fail: 0`; `50 trace.jsonl`; md5 hai lần chạy giống hệt nhau. Phân bố kết luận: canceled 8, unavailable 8, late_delivery_seller 8, late_delivery_logistics 8, valid_split_payment 9, unsupported_late_claim 9 — mỗi rule 8–9 case.
- **Artifact/log:** `output/EC_001.json` … `output/EC_050.json`, `trace.jsonl`, `logging/trace.jsonl`, `logging/verifier_report.json` (chỉ sinh khi có case fail — lượt chạy cuối không sinh vì fail = 0). Không artifact nào chứa secret; `.env` nằm trong `.gitignore`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Task 2D.8 yêu cầu `run_batch.py` "gọi Coordinator", nhưng `coordinator_agent.py` là task 3.2 của A và lúc tôi làm thì chưa tồn tại. Nếu chờ, cả nhóm không có file output nào để kiểm tra, và mọi task Phase 4 của tôi (đếm output, lọc case fail, kiểm deterministic, sinh trace cuối) đều bị chặn.
- **Các phương án đã cân nhắc:**
  1. Chờ A xong Coordinator rồi mới chạy batch.
  2. Tôi tự viết luôn `coordinator_agent.py` cho nhanh.
  3. `run_batch.py` tự dò `coordinator_agent`; chưa có thì chạy pipeline nội bộ gọi trực tiếp 4 sub-agent của B/C theo đúng thứ tự handoff.
- **Phương án đã chọn:** phương án 3, kèm cờ `--pipeline auto|coordinator|local`. Khi coordinator xuất hiện, runner khớp tham số theo **tên** tham số (`inspect.signature`) nên không phụ thuộc chữ ký hàm cụ thể của A.
- **Lý do:** phương án 1 làm cả nhóm mất một khoảng thời gian dài không có artifact để đối chiếu, trong khi deadline là 12:30. Phương án 2 giẫm chân lên phần việc của A, dễ tạo conflict lớn và phá nguyên tắc phân công của bài (mỗi agent một domain, có handoff thật). Phương án 3 giữ nguyên ranh giới sở hữu: pipeline nội bộ chỉ *điều phối*, mọi quyết định vẫn nằm ở agent của B và C, và nó tự nhường chỗ cho Coordinator thật.
- **Bằng chứng quyết định phù hợp:** chạy được full 50 case với verifier pass 50/50 trước khi Phase 3 hoàn thành; nhờ đó xác nhận sớm rằng rule mapping của C khớp hoàn toàn bảng README (0 lỗi mapping trên 50 case) và phân bố 6 rule cân bằng 8–9 case. Sau khi A push `coordinator_agent.py` lên `main`, tôi chạy `python run_batch.py --pipeline coordinator` và runner tự bắt được entrypoint `process_case` của A, chạy 50/50 case pass verifier mà không phải sửa dòng code nào ở phía tôi — đúng như thiết kế ban đầu.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** khi merge nhánh `sondang` vào `main`, git báo conflict ở `PROGRESS.md`:

  ```text
  Auto-merging PROGRESS.md
  CONFLICT (content): Merge conflict in PROGRESS.md
  Automatic merge failed; fix conflicts and then commit the result.
  ```

  Nhưng vấn đề nghiêm trọng hơn lại **không** được git báo: `git status` cho thấy `individual_01998_TranDinhDang.md` bị đánh dấu `M`, tức merge tự động sẽ ghi đè file báo cáo của A.

- **Lệnh hoặc bước tái hiện:**

  ```bash
  git merge --ff-only origin/main
  git merge sondang
  git diff --cached HEAD -- individual_01998_TranDinhDang.md
  ```

- **Nguyên nhân gốc:** các file báo cáo cá nhân được tạo bằng cách copy template, và trên nhánh `sondang` file của A (`individual_01998_...`) bị điền nhầm thông tin của tôi. Trên `main`, A đã reset file đó về template trắng. Do phía `sondang` có sửa đổi so với merge base còn phía `main` thì không, git chọn phía `sondang` — đúng theo thuật toán merge nhưng sai theo ý nghĩa dữ liệu, và loại lỗi này im lặng vì nó không tạo conflict.

- **Cách xử lý:** lấy lại bản của `main` cho đúng file đó trước khi commit merge, và chỉ resolve thủ công phần conflict thật trong `PROGRESS.md` (danh sách thành viên):

  ```bash
  git checkout HEAD -- individual_01998_TranDinhDang.md
  ```

  Ngoài ra tôi làm lại merge cho gọn: trạng thái ban đầu là octopus merge (`sondang` + `origin/main` vào một `main` cũ hơn 8 commit), tôi `git merge --abort`, fast-forward `main` lên `origin/main` rồi mới merge `sondang` — cùng nội dung nhưng history 2 cha thay vì 3.

- **Cách xác minh sau khi sửa:** kiểm tra file của A đã về đúng template trắng, không còn tên tôi:

  ```bash
  sed -n '8,13p' individual_01998_TranDinhDang.md
  # | Họ và tên | [Họ và tên] |
  # | MSSV      | [MSSV]      |
  ```

  Sau đó chạy lại toàn bộ test trên cây đã merge: `test_person_d.py` 35/35, `test_person_c.py` 8/8, `test_person_b.py` pass, và `python run_batch.py --quiet --no-trace` cho 50/50 verifier pass.

- **Điều học được:** conflict mà git báo thường là phần dễ; phần nguy hiểm là những file được merge "thành công" theo thuật toán nhưng sai theo ngữ nghĩa. Sau merge phải đọc `git status` / `git diff --cached` cho **mọi** file thay đổi chứ không chỉ file có dấu conflict, nhất là với tài liệu do người khác sở hữu.

## 7. Hiểu biết về luồng end-to-end

Năm câu hỏi trong template thuộc một lab khác (Crossref → vector index, retrieval evaluation, freshness monitoring). Dưới đây tôi trả lời đúng tinh thần từng câu nhưng ánh xạ sang pipeline thực tế của lab này.

**1. Dữ liệu đi từ nguồn đến chỗ agent dùng được như thế nào?**
9 file CSV Olist trong `data/` được `DataLoader.load_all()` nạp một lần vào 7 dict lookup O(1) (orders theo `order_id`; order_items và payments theo `order_id` dạng list; sellers, customers, products, reviews theo khóa riêng). Với mỗi case, `build_case_context()` lấy `claimed_order_id` từ file input rồi join sang item, seller, payment, review, product và tính sẵn `item_total`, `freight_total`, `payment_total`, `payment_mismatch`. Kết quả là một `CaseContext` — đây là ranh giới quan trọng: từ đó trở đi **không agent nào đọc CSV trực tiếp**, tất cả cùng nhìn một snapshot dữ liệu nên kết quả không phụ thuộc thứ tự chạy. Sau đó Order/Seller Agent, Delivery Agent, Payment Agent sinh signal; Policy Agent áp 6 rule theo thứ tự ưu tiên; runner tổng hợp thành JSON theo README mục 6; Verifier đối chiếu ngược về CSV; cuối cùng ghi `output/EC_XXX.json` và một dòng `trace.jsonl`.

**2. Tập đánh giá và "ground truth" dùng để đo chất lượng ra sao?**
Tập đánh giá là 50 file `input/EC_001.json` … `EC_050.json`. "Ground truth" ở lab này không phải một file nhãn mà chính là các row CSV: một evidence ID chỉ hợp lệ khi dựng được trực tiếp từ row có thật (`order:`, `item:<order>:<n>`, `payment:<order>:<seq>`, `seller:`, `policy:<CODE>`); ID không tồn tại hoặc sai định dạng bị tính là false positive. Vì vậy Verifier chính là thước đo precision của evidence trước khi nộp. Điểm mỗi case là tổng có trọng số của 6 thành phần (primary issue + confidence 20%, affected entities 20%, financial resolution 20%, root cause + responsible parties 15%, evidence 15%, actions 10%); điểm cuối là trung bình 50 case; case bị hard gate nhận 0.

**3. Kiểm tra chất lượng khác giám sát quá trình ở điểm nào?**
Hai lớp này đều do tôi làm và cố tình tách rời. `verifier_agent.py` là kiểm tra chất lượng: nó **phán xét đúng/sai** theo dữ liệu và rule, chạy trước khi ghi file, và `passed=False` là tín hiệu case sẽ mất điểm. `trace.py` là giám sát: nó **không phán xét**, chỉ ghi lại quá trình — agent nào chạy, nhận signal gì, mất bao lâu, verifier kết luận ra sao. Verifier trả lời "output này có sai không", trace trả lời "nếu sai thì sai từ bước nào". Một case fail verifier mà không có trace thì phải chạy lại cả batch mới biết agent nào gây ra.

**4. Vì sao phải dùng cùng một tập test qua các lần chạy?**
Vì Phase 4 là vòng lặp sửa – chạy lại: C sửa rule hoặc confidence, B sửa evidence, rồi tôi chạy lại batch. Nếu mỗi lần đổi input thì không thể biết số liệu thay đổi do code tốt lên hay do dữ liệu khác đi. Giữ nguyên 50 case và giữ pipeline deterministic thì mọi khác biệt trong `output/` đều quy được về đúng thay đổi code vừa làm. Đó cũng là lý do `trace.jsonl` ghi đè chứ không append: file luôn mô tả đúng lượt chạy mới nhất, không lẫn kết quả cũ.

**5. Dựa vào artifact và metric nào để kết luận là đã ổn?**
Bốn điều kiện, tất cả kiểm được bằng lệnh: (a) `output/` đúng 50 file `EC_001.json`–`EC_050.json`, không file lạ; (b) verifier fail = 0, tức không sinh `logging/verifier_report.json`; (c) chạy batch hai lần cho md5 tổng của `output/` giống hệt nhau — chứng minh deterministic; (d) `trace.jsonl` đúng 50 dòng và mọi dòng có `verifier_pass: true`. Lượt chạy cuối trên nhánh `main` đã merge đạt cả bốn điều kiện.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đặng Thái Nam Sơn
**Ngày xác nhận:** 2026-08-05
