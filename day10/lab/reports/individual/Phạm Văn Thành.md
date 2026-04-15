# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Phạm Văn Thành
**MSSV:** 2A2026000272
**Vai trò:** Cleaning & Quality Owner
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

Là **Cleaning & Quality Owner**, tôi chịu trách nhiệm mở rộng `cleaning_rules.py` và `expectations.py`, đảm bảo mọi failure mode được phát hiện và có hành động phù hợp (quarantine/warn/halt).

**File / module:**
- `transform/cleaning_rules.py` — 11 rules (6 baseline + 5 new)
- `quality/expectations.py` — 8 expectations (6 baseline + 2 new)
- `artifacts/quarantine/quarantine_*.csv` — evidence của các record bị loại

**Kết nối với thành viên khác:**
- Cung cấp `quarantine_records` count cho Ingestion Owner log
- Đảm bảo cleaned CSV đúng format để Embed Owner upsert vào Chroma đúng chunk_id

---

## 2. Một quyết định kỹ thuật (100–150 từ)

**Quyết định: Phân biệt `warn` vs `halt` cho các rule mới.**

Với 5 rule mới, tôi phải quyết định mức độ nghiêm trọng:

| Rule | Severity | Lý do |
|------|----------|-------|
| `doc_id_format_invalid` | **Halt** | doc_id không hợp lệ → có thể là injection attack hoặc config error nghiêm trọng |
| `_flag_bom` | **Halt** | BOM ảnh hưởng trực tiếp đến vector embedding (encoding sai) |
| `_flag_mostly_uppercase` | **Warn only** | Có thể là OCR artifact không ảnh hưởng nghiêm trọng đến nội dung |
| `_flag_excess_special_chars` | **Warn only** | Có thể là ký hiệu toán học/pháp lý hợp lệ |

**Tại sao quan trọng:** Halt quá nhiều → pipeline không bao giờ xanh (error budget). Warn đủ để alert nhưng không block pipeline.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

**Triệu chứng:** Sau khi thêm rule `_strip_bom` và `_normalize_whitespace`, `write_cleaned_csv` không ghi các metadata flags mới (`_flag_bom`, `_flag_whitespace_normalized`) vì `fieldnames` cứng code chỉ 5 cột.

**Root cause:** `csv.DictWriter` chỉ ghi các key có trong `fieldnames`. Các flag mới bắt đầu bằng `_flag_` không được liệt kê.

**Fix:** Dynamic `fieldnames` — liệt kê `base_fields` + mọi key bắt đầu bằng `_flag_` từ các rows thực tế:
```python
extra_fields = sorted({k for r in rows for k in r.keys() if k.startswith("_flag_")})
fieldnames = base_fields + extra_fields
```

**Metric:** Sau fix, `cleaned_sprint2-extended.csv` có thêm các cột metadata flags (dùng data mẫu không có BOM nên giá trị FALSE).

---

## 4. Bằng chứng trước / sau (80–120 từ)

**Baseline (sprint1-clean) — 6 expectations:**
```
expectation[min_one_row] OK (halt)
expectation[no_empty_doc_id] OK (halt)
expectation[refund_no_stale_14d_window] OK (halt)
expectation[chunk_min_length_8] OK (warn)
expectation[effective_date_iso_yyyy_mm_dd] OK (halt)
expectation[hr_leave_no_stale_10d_annual] OK (halt)
```

**Extended (sprint2-extended) — 8 expectations:**
```
expectation[no_bom_flagged] OK (halt) :: bom_chunks=0
expectation[no_legacy_or_test_doc_id] OK (halt) :: legacy_doc_id_count=0
```

**Inject-bad (với --no-refund-fix):**
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
```
→ Chunk chứa "14 ngày làm việc" được phát hiện đúng bởi expectation.

File: `artifacts/logs/run_inject-bad.log`

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ: Đọc `hr_leave_min_effective_date` từ `contracts/data_contract.yaml` thay vì hard-code `"2026-01-01"` trong `cleaning_rules.py`. Điều này giúp policy versioning không phụ thuộc code — chỉ cần update contract yaml khi policy thay đổi tiếp (Distinction criterion c).
