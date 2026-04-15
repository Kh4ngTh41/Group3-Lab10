# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Vũ Hoàng Minh
**Vai trò:** Ingestion / Raw Owner
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

Là **Ingestion Owner**, tôi chịu trách nhiệm thiết lập pipeline entrypoint, quản lý raw data paths, và đảm bảo log đầy đủ `run_id`, `raw_records`, `cleaned_records`, `quarantine_records` cho mọi run.

**File / module:**
- `etl_pipeline.py` — entrypoint chính (`cmd_run`, `cmd_freshness`)
- `artifacts/logs/run_<run-id>.log` — log tất cả pipeline steps
- `artifacts/manifests/manifest_<run-id>.json` — metadata mỗi run
- `data/raw/policy_export_dirty.csv` — raw data source

**Kết nối với thành viên khác:**
- Cung cấp `raw_records` count cho Cleaning Owner để đối chiếu quarantine coverage
- Cung cấp manifest cho Monitoring Owner kiểm tra freshness SLA

---

## 2. Một quyết định kỹ thuật (100–150 từ)

**Quyết định: đặt `run_id` tại đầu pipeline và ghi vào mọi artifact.**

Mỗi lần chạy pipeline đều tạo `run_id` duy nhất (UTC timestamp hoặc do người dùng chỉ định). `run_id` xuất hiện trong:
- Tên file log: `run_<run-id>.log`
- Tên file cleaned/quarantine CSV
- Trường `run_id` trong manifest JSON
- Trường `run_id` trong Chroma vector metadata

**Tại sao quan trọng:** Khi có sự cố (eval fail, expectation fail), `run_id` là duy nhất cách trace artifact về đúng pipeline run. Nếu không có `run_id`, không thể phân biệt log của run "tốt" và run "bị inject corruption".

**Evidence:** `run_id=sprint1-clean` trong `artifacts/logs/run_sprint1-clean.log` có `raw_records=10`, `cleaned_records=6`.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

**Triệu chứng:** Chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate` trên console Windows bị UnicodeEncodeError: `cp1252 codec can't encode character '\u2192'` tại dòng log `WARN: expectation failed but --skip-validate → tiếp tục embed`.

**Root cause:** Ký tự Unicode arrow (`→`) trong chuỗi log không được Windows cp1252 encoding hỗ trợ.

**Fix:** Thay `\u2192` bằng `->` trong chuỗi log tại `etl_pipeline.py:91`. Pipeline tiếp tục embed thay vì crash.

**Metric phát hiện:** Exit code 1 từ console — không phải từ expectation. Nếu không fix, inject-bad scenario không tạo được evidence trên Windows.

---

## 4. Bằng chứng trước / sau (80–120 từ)

**Sprint 1 (clean baseline):**
```
run_id=sprint1-clean
raw_records=10
cleaned_records=6
quarantine_records=4
cleaned_csv=artifacts\cleaned\cleaned_sprint1-clean.csv
```

**Sprint 2 (extended):**
```
run_id=sprint2-extended
raw_records=10
cleaned_records=6
quarantine_records=4
cleaned_csv=artifacts\cleaned\cleaned_sprint2-extended.csv
```

**Inject-bad (corruption):**
```
run_id=inject-bad
raw_records=10
cleaned_records=6
quarantine_records=4
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
```

File: `artifacts/logs/run_sprint1-clean.log`, `artifacts/logs/run_inject-bad.log`

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ: Thêm `raw_records_hash` (SHA256 của raw CSV) vào manifest để detect xem nguồn export có thay đổi nội dung giữa các lần chạy hay không mà không cần so sánh toàn bộ file. Điều này giúp phát hiện "nguồn trả về đúng data cũ" trong trường hợp API bị cache.
