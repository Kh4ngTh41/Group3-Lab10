# Runbook — Lab Day 10: Data Pipeline & Data Observability

---

## Symptom

**Triệu chứng quan sát được:**
- Agent trả lời sai: "14 ngày làm việc" thay vì "7 ngày làm việc" cho câu hỏi refund window
- Agent trả lời: "10 ngày phép năm" thay vì "12 ngày phép năm" cho câu hỏi leave policy
- Retrieval eval: `hits_forbidden=yes` cho `q_refund_window` hoặc `q_leave_version`
- Pipeline exit code ≠ 0 (expectation halt)

---

## Detection

**Metric báo:**
1. `expectation[refund_no_stale_14d_window] FAIL` — log ghi `violations=N`
2. `expectation[hr_leave_no_stale_10d_annual] FAIL` — log ghi `violations=N`
3. `expectation[no_legacy_or_test_doc_id] FAIL` — doc_id lạ trong cleaned
4. `freshness_check=FAIL` — `age_hours > sla_hours`
5. `hits_forbidden=yes` trong `eval_retrieval.py` output CSV

**Lệnh kiểm tra:**
```bash
# Kiểm tra log expectation
grep "expectation\[" artifacts/logs/run_*.log

# Kiểm tra quarantine
cat artifacts/quarantine/quarantine_*.csv

# Chạy eval retrieval
python eval_retrieval.py --out artifacts/eval/check_eval.csv

# Kiểm tra manifest freshness
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Mở `artifacts/logs/run_<run-id>.log` | Tìm `expectation[...] FAIL` |
| 2 | Mở `artifacts/quarantine/quarantine_<run-id>.csv` | Xem reason: unknown_doc_id, stale_hr, duplicate… |
| 3 | Chạy `python eval_retrieval.py` | `hits_forbidden=yes` → chunk stale trong top-k |
| 4 | Kiểm tra cleaned CSV có chunk "14 ngày" | = root cause stale refund chưa fix |
| 5 | Kiểm tra cleaned CSV có chunk "10 ngày phép năm" | = HR policy version cũ chưa quarantine |

**Thứ tự debug (từ slide Day 10):**
```
Freshness → Volume → Schema & contract → Lineage / run_id → Model/prompt
```

---

## Mitigation

**Tức thì (P1):**
```bash
# Khôi phục pipeline sạch — fix data đã applied
python etl_pipeline.py run --run-id <tuỳ chọn>

# Nếu cần rollback embed (index chứa stale):
# Xóa chroma_db và re-run
rm -rf chroma_db/
python etl_pipeline.py run --run-id restore-clean

# Kiểm tra eval sau restore
python eval_retrieval.py --out artifacts/eval/post_restore_eval.csv
```

**Tạm thời (banner):**
- Gắn cờ "System đang bảo trì dữ liệu" trên UI agent nếu không thể restore ngay.

---

## Prevention

| Action | Chi tiết | Owner |
|--------|----------|-------|
| Thêm `expectation[refund_no_stale_14d_window]` | Baseline đã có — halt nếu chunk chứa "14 ngày" | Cleaning Owner |
| Thêm `expectation[hr_leave_no_stale_10d_annual]` | Baseline đã có — halt nếu HR chunk chứa "10 ngày phép năm" | Cleaning Owner |
| Quarantine rule cho `effective_date < 2026-01-01` (HR) | Baseline đã có | Cleaning Owner |
| Allowlist doc_id | Baseline đã có | Cleaning Owner |
| Embed idempotent + prune | Baseline đã có — upsert theo `chunk_id` + xoá vector không còn trong cleaned | Embed Owner |
| Freshness SLA alert | Baseline đã có — FAIL nếu `age_hours > 24` | Monitoring Owner |
| **Cải tiến thêm:** | Đọc `hr_leave_min_effective_date` từ contract env thay vì hard-code | Cleaning Owner |

---

## SLA Freshness — Giải thích PASS/WARN/FAIL

| Trạng thái | Điều kiện | Hành động |
|-----------|-----------|-----------|
| **PASS** | `age_hours <= 24` | Dữ liệu tươi — không cần can thiệp |
| **WARN** | Không timestamp trong manifest | Kiểm tra manifest có `latest_exported_at` |
| **FAIL** | `age_hours > 24` | Data stale — cần re-run pipeline hoặc kiểm tra ingest failure |

> **Ghi chú:** Data mẫu có `exported_at = 2026-04-10T08:00:00` → luôn FAIL freshness vì >120 giờ. Đây là hành vi **được thiết kế** để dạy rằng "FAIL ≠ lỗi pipeline" mà là "SLA đã bị breach". Ghi trong runbook: "SLA áp cho data snapshot chứ không phải cho pipeline run."
