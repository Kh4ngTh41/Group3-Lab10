# Quality Report — Lab Day 10: Data Pipeline & Data Observability

**run_id:** sprint2-extended
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Baseline (sprint1-clean) | Extended (sprint2-extended) | Inject (`inject-bad`) |
|---------|--------------------------|----------------------------|-----------------------|
| raw_records | 10 | 10 | 10 |
| cleaned_records | 6 | 6 | 6 |
| quarantine_records | 4 | 4 | 4 |
| Expectations | 6 OK | **8 OK** | E3 FAIL (`refund_no_stale_14d_window`) |

**Quarantine breakdown** (`sprint2-extended`):
| doc_id | reason |
|--------|--------|
| `legacy_catalog_xyz_zzz` | `unknown_doc_id` |
| `policy_refund_v4` (dòng 5) | `missing_effective_date` |
| `hr_leave_policy` (dòng 7) | `stale_hr_policy_effective_date` (bản 2025: 10 ngày, effective 2025-01-01) |
| `policy_refund_v4` (dòng 2) | `duplicate_chunk_text` |

---

## 2. Before / after retrieval — Grading thật

Eval chạy với `data/grading_questions.json` trên Chroma sau `sprint2-extended`:

| Câu | Câu hỏi | top1_doc_id | Preview (180 chars) | contains_expected | hits_forbidden | top1_doc_expected |
|-----|---------|-------------|---------------------|-----------------|----------------|--------------------|
| `gq_d10_01` | "Theo policy hoàn tiền nội bộ, khách có tối đa bao nhiêu ngày làm việc để gửi yêu cầu hoàn tiền sau khi đơn được xác nhận?" | `policy_refund_v4` | "Yêu cầu được gửi trong vòng **7 ngày làm việc** kể từ thời điểm xác nhận đơn hàng." | ✅ `yes` | ✅ `no` | — |
| `gq_d10_02` | "Ticket P1: thời gian resolution SLA là bao nhiêu giờ?" | `sla_p1_2026` | "Ticket P1 có SLA phản hồi ban đầu 15 phút và resolution trong **4 giờ**." | ✅ `yes` | ✅ `no` | — |
| `gq_d10_03` | "Theo chính sách nghỉ phép hiện hành (2026), nhân viên dưới 3 năm kinh nghiệm được bao nhiêu ngày phép năm?" | `hr_leave_policy` | "Nhân viên dưới 3 năm kinh nghiệm được **12 ngày phép năm** theo chính sách 2026." | ✅ `yes` | ✅ `no` | ✅ `yes` |

**File:** `artifacts/eval/grading_retrieval_eval.csv`

---

## 3. Grading JSONL — Kết quả cuối cùng

File: `artifacts/eval/grading_run.jsonl`

```json
{"id":"gq_d10_01","top1_doc_id":"policy_refund_v4","contains_expected":true,"hits_forbidden":false,...}
{"id":"gq_d10_02","top1_doc_id":"sla_p1_2026","contains_expected":true,"hits_forbidden":false,...}
{"id":"gq_d10_03","top1_doc_id":"hr_leave_policy","contains_expected":true,"hits_forbidden":false,"top1_doc_matches":true,...}
```

| Câu | contains_expected | hits_forbidden | top1_doc_matches | Đạt |
|-----|-------------------|----------------|--------------------|-----|
| `gq_d10_01` | ✅ true | ✅ false | — | ✅ PASS |
| `gq_d10_02` | ✅ true | ✅ false | — | ✅ PASS |
| `gq_d10_03` | ✅ true | ✅ false | ✅ true | ✅ PASS |

---

## 4. Freshness & Monitor

```
freshness_check=FAIL
latest_exported_at: 2026-04-10T08:00:00
age_hours: 120.346
sla_hours: 24.0
reason: freshness_sla_exceeded
```

- Data mẫu export ngày `2026-04-10` → 5 ngày tuổi → vượt SLA 24h → **FAIL hợp lý theo thiết kế**
- Manifest: `artifacts/manifests/manifest_sprint2-extended.json`

---

## 5. Corruption Inject Evidence

**Lệnh:** `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`

**Kết quả pipeline:**
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
expectation[no_bom_flagged] OK (halt) :: bom_chunks=0
expectation[no_legacy_or_test_doc_id] OK (halt) :: legacy_doc_id_count=0
embed_prune_removed=1
PIPELINE_OK (skip-validate)
```

**Chunk stale còn trong cleaned** (`cleaned_inject-bad.csv`, row 2):
```
policy_refund_v4_2_45eb043f3cd16916 | policy_refund_v4 |
"Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn
(ghi chú: bản sync cũ policy-v3 — lỗi migration)."
```

**Tác động lên grading eval** (so sánh `grading_retrieval_eval.csv` clean vs inject-bad):

| Câu | Question | Clean (sprint2-extended) | Inject-bad | File tham chiếu |
|-----|----------|--------------------------|-----------|-----------------|
| `gq_d10_01` | Refund window — tối đa bao nhiêu ngày? | `top1=policy_refund_v4`, preview="**7 ngày**...", `contains_expected=yes`, `hits_forbidden=no` | Chunk "14 ngày" lọt vào top-k → `hits_forbidden=yes` nếu eval chạy trên Chroma inject-bad | `artifacts/eval/grading_retrieval_eval.csv` (clean) |
| `gq_d10_02` | P1 resolution SLA? | `top1=sla_p1_2026`, preview="resolution trong **4 giờ**", `contains_expected=yes`, `hits_forbidden=no` ✅ | Không bị ảnh hưởng — SLA chunk không bị corruption | `artifacts/eval/grading_retrieval_eval.csv` (clean) |
| `gq_d10_03` | HR leave — bao nhiêu ngày? | `top1=hr_leave_policy`, preview="**12 ngày** phép năm 2026", `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_matches=true` ✅ | Chunk "10 ngày phép năm" đã quarantine đúng — không ảnh hưởng | `artifacts/eval/grading_retrieval_eval.csv` (clean) |

**Evidence files:**
- Log: `artifacts/logs/run_inject-bad.log`
- Cleaned (stale): `artifacts/cleaned/cleaned_inject-bad.csv` — row 2 chứa "14 ngày"
- Quarantine: `artifacts/quarantine/quarantine_inject-bad.csv` — `stale_hr_policy_effective_date` (10 ngày), `unknown_doc_id` (legacy_catalog)
- Eval reference: `artifacts/eval/grading_retrieval_eval.csv` (chạy trên Chroma clean sau sprint2-extended)

---

## 6. Hạn chế

| Hạn chế | Cải tiến |
|---------|-----------|
| Freshness luôn FAIL (data mẫu cố ý cũ) | Production: kết nối API thật |
| Chỉ keyword matching eval | Mở rộng LLM-judge (+Distinction d) |
| Không Great Expectations | Thay bằng GE (+2 bonus Distinction a) |
| HR min_effective_date hard-coded | Đọc từ contract env (+Distinction c) |
