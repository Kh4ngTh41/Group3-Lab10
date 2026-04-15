# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Lab03-Day10-Team
**Thành viên:**
| Tên | Vai trò (Day 10) |
|-----|------------------|
| Vũ Hoàng Minh | Ingestion / Raw Owner |
| Phạm Văn Thành | Cleaning & Quality Owner |
| Thái Tuấn Khang  | Embed & Idempotency Owner |
| Nguyễn Thành Luân | Monitoring / Docs Owner |

**Ngày nộp:** 2026-04-15
**Repo:** `f:\Lab03-Day10\Lecture-Day-08-09-10\day10\lab`
**Độ dài khuyến nghị:** 600–1000 từ

---

## 1. Pipeline tổng quan (150–200 từ)

Pipeline xử lý batch export CSV từ hệ thống nguồn (CS + IT Helpdesk), clean và validate qua 8 expectation, rồi embed vào Chroma vector store để phục vụ RAG retrieval cho agent Day 09.

**Tóm tắt luồng:**
```
raw CSV (policy_export_dirty.csv)
  → load_raw_csv (log raw_records=10)
  → clean_rows (6 cleaned + 4 quarantine)
  → run_expectations (8 expectations)
  → embed_chroma (idempotent upsert)
  → write_manifest (run_id, timestamps)
  → freshness_check (SLA 24h)
```

**Lệnh chạy một dòng:**
```bash
python etl_pipeline.py run --run-id <run-id>
```

**run_id** được ghi ở mọi bước: log file (`run_<run-id>.log`), cleaned CSV, quarantine CSV, manifest JSON (`manifest_<run-id>.json`), và Chroma metadata (`run_id` field trong mỗi vector).

---

## 2. Cleaning & expectation (150–200 từ)

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới | Trước (sprint1-clean) | Sau (sprint2-extended) | Inject (`inject-bad`) | Chứng cứ |
|------------------------|----------------------|------------------------|---------------------|----------|
| `no_bom_flagged` (E7) | OK (bom_chunks=0) | OK (bom_chunks=0) | OK (bom_chunks=0) | Log sprint1-clean vs sprint2-extended |
| `no_legacy_or_test_doc_id` (E8) | OK (legacy_doc_id_count=0) | OK (legacy_doc_id_count=0) | OK | Log |
| `refund_no_stale_14d_window` (E3) | OK (violations=0) | OK (violations=0) | **FAIL (violations=1)** | Log: `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1` |
| Quarantine: `unknown_doc_id` | quarantine_records=4 | quarantine_records=4 | quarantine_records=4 | `legacy_catalog_xyz_zzz` luôn bị quarantine |
| `quarantine_records` tổng | 4 | 4 | 4 | Không đổi — data mẫu ổn định |

**Rule mới có impact đo được:**
- Rule doc_id format (`^[a-z0-9_]+$`) — phòng ngừa injection qua tên doc_id bất thường. Impact: nếu data có doc_id `Legacy_Policy!@#` → quarantine với reason `doc_id_format_invalid`.
- BOM stripping — nếu CSV export từ Excel có BOM, `_flag_bom=TRUE` và bị strip trước embed.

**Expectation halt/warn phân biệt:**
- `refund_no_stale_14d_window`, `no_bom_flagged`, `no_legacy_or_test_doc_id`: **halt** (dừng pipeline)
- `chunk_min_length_8`: **warn** (tiếp tục được)

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

### Kịch bạnh inject

**Lệnh:** `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`

**Mô tả:** Chạy pipeline mà không áp dụng rule fix stale refund (14→7 ngày) và bỏ qua validation halt. Mục đích: tạo bằng chứng "before" khi agent đọc chunk chứa policy sai.

### Kết quả định lượng

| Trạng thái | `q_refund_window` | `q_leave_version` |
|------------|-------------------|-------------------|
| **Clean (sprint2-extended)** | `contains_expected=yes`, `hits_forbidden=no` ✅ | `contains_expected=yes`, `hits_forbidden=no`, `top1_doc=hr_leave_policy` ✅ |
| **Inject-bad** | `expectation[refund_no_stale_14d_window] FAIL (halt)` ❌ | Chunk "10 ngày" đã quarantine đúng — không có stale HR trong cleaned |

**Chunk stale 14 ngày sau clean (inject-bad):**
```
Row 2: "Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn (ghi chú: bản sync cũ policy-v3)"
```

**Chunk đã fix sau clean (sprint2-extended):**
```
Row 2: "Yêu cầu hoàn tiền được chấp nhận trong vòng 7 ngày làm việc kể từ xác nhận đơn (ghi chú: bản sync cũ policy-v3 — lỗi migration). [cleaned: stale_refund_window]"
```

**Grading JSONL** (`artifacts/eval/grading_run.jsonl`):
- `gq_d10_01`: `contains_expected=true`, `hits_forbidden=false` ✅
- `gq_d10_02`: `contains_expected=true` ✅
- `gq_d10_03`: `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true` ✅

---

## 4. Freshness & monitoring (100–150 từ)

**SLA chọn:** 24 giờ cho `latest_exported_at` (data snapshot timestamp).

**Điểm đo:** tại bước **publish** — sau khi embed hoàn tất, không phải tại ingest.

**Kết quả trên manifest mẫu:**
```
freshness_check=FAIL
latest_exported_at: 2026-04-10T08:00:00
age_hours: 120.214 (5 ngày)
sla_hours: 24.0
```

**Giải thích:** FAIL là **hợp lý** — data mẫu được export 5 ngày trước buổi lab, vượt SLA 24h. Đây là design có chủ đích của GV để dạy "FAIL freshness không phải lỗi pipeline mà là breach SLA data".

**Debug order khi freshness fail:**
```
Freshness (age_hours > SLA?) → Volume (raw_records?) → Schema (contract match?) → Lineage (run_id correct?)
```

---

## 5. Liên hệ Day 09 (50–100 từ)

Pipeline Day 10 cung cấp vector index cho agent Day 09:

- **Collection:** `day10_kb` (tách khỏi `day09_kb`)
- **Corpus:** 5 docs trong `data/docs/*.txt` — cùng CS + IT Helpdesk case
- **Tích hợp:** sau mỗi `etl_pipeline.py run`, Chroma được cập nhật → agent Day 09 truy vấn corpus đã clean + validate
- **Eval:** `eval_retrieval.py` đo bằng keyword matching trên top-k — tương đương cách agent đánh giá context quality

Nếu policy refund thay đổi (7→14 ngày), re-run pipeline Day 10 → vector store cập nhật → agent Day 09 tự động đọc version mới.

---

## 6. Rủi ro còn lại & việc chưa làm

- **Great Expectations library:** có thể thay thế expectation suite hiện tại để được +2 bonus (Distinction a)
- **Freshness 2 boundary:** hiện chỉ đo ở publish boundary; có thể thêm ingest timestamp để được +1 bonus (Distinction b)
- **LLM-judge eval:** keyword matching đơn giản; mở rộng bằng LLM judge cho độ chính xác cao hơn (Distinction d)
- **Rule versioning không hard-code:** đọc `hr_leave_min_effective_date` từ env/contract thay vì hard-code trong `cleaning_rules.py`
