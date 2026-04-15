# Quality Report — Lab Day 10: Data Pipeline & Data Observability

**run_id:** sprint2-extended
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (inject-bad) | Sau (sprint2-extended) | Ghi chú |
|--------|--------------------|------------------------|---------|
| raw_records | 10 | 10 | Không đổi |
| cleaned_records | 6 | 6 | Baseline ổn định |
| quarantine_records | 4 | 4 | 4 rows loại: unknown_doc_id(1), stale_HR(1), dup(1), missing_date(1) |
| Expectation halt? | **CÓ** (`refund_no_stale_14d_window FAIL`) | Không | Inject `--no-refund-fix` để lộ stale chunk 14 ngày |
| Freshness | FAIL | FAIL | Data mẫu 120h > 24h SLA (design hợp lý) |

**Sprint comparison:**

| Run | raw | cleaned | quarantine | Expectations |
|-----|-----|---------|------------|--------------|
| `sprint1-clean` | 10 | 6 | 4 | 6 OK |
| `inject-bad` | 10 | 6 | 4 | E3 FAIL (violations=1) |
| `sprint2-extended` | 10 | 6 | 4 | 8 OK (6 baseline + 2 new) |

---

## 2. Before / after retrieval (bắt buộc)

### Câu hỏi then chốt: `q_refund_window` (refund window = 7 ngày)

**Before (inject-bad — data chưa fix):**
- Row 2 trong `cleaned_inject-bad.csv`: `"Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc..."`
- `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`
- Eval: nếu embed được → `hits_forbidden=yes` (chunk chứa "14 ngày" trong top-k)

**After (sprint2-extended — data đã fix):**
- Row 2 trong `cleaned_sprint2-extended.csv`: `"Yêu cầu hoàn tiền được chấp nhận trong vòng 7 ngày làm việc... [cleaned: stale_refund_window]"`
- `expectation[refund_no_stale_14d_window] OK (halt) :: violations=0`
- **Grading:** `gq_d10_01`: `contains_expected=true`, `hits_forbidden=false` ✅

### Merit — `q_leave_version` (HR policy 12 ngày vs 10 ngày cũ)

**Before (inject-bad):**
- Row 7 trong quarantine: `reason=stale_hr_policy_effective_date` (bản HR 2025 có "10 ngày phép năm")
- Chunk "12 ngày" (bản 2026) vẫn trong cleaned → nhưng bản cũ đã bị quarantine đúng

**After (sprint2-extended):**
- `expectation[hr_leave_no_stale_10d_annual] OK (halt) :: violations=0`
- **Grading:** `gq_d10_03`: `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true` ✅
- `top1_doc_id=hr_leave_policy` ✅

---

## 3. Freshness & monitor

**Manifest:** `manifest_sprint2-extended.json`

```
freshness_check=FAIL
latest_exported_at: 2026-04-10T08:00:00
age_hours: 120.214
sla_hours: 24.0
reason: freshness_sla_exceeded
```

**Giải thích SLA:**
- SLA 24h áp cho `latest_exported_at` (data snapshot timestamp), không phải pipeline run timestamp.
- Data mẫu được export vào `2026-04-10` — 5 ngày trước lab → FAIL là **hợp lý theo thiết kế**.
- Trong production thực tế: trigger re-ingest từ nguồn mới hơn hoặc điều chỉnh `FRESHNESS_SLA_HOURS` nếu business chấp nhận data cũ hơn.

**Debug order (từ slide Day 10):**
```
Freshness → Volume → Schema/contract → Lineage/run_id → Model/prompt
```

---

## 4. Corruption inject (Sprint 3)

**Kịch bạnh inject:** `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`

**Mục đích:** Cố ý bỏ qua fix refund 14→7 ngày để:
1. Chứng minh expectation `refund_no_stale_14d_window` phát hiện được stale data
2. Tạo bằng chứng "before" vs "after" cho quality report

**Kết quả:**
- `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1` — chunk 14 ngày còn trong cleaned
- Pipeline exit 2 (halt) khi không dùng `--skip-validate`
- Dùng `--skip-validate` thì embed tiếp tục với stale chunk → `hits_forbidden=yes` trong eval

**Detection:**
```bash
# Phát hiện bằng expectation
grep "refund_no_stale_14d_window.*FAIL" artifacts/logs/run_inject-bad.log

# Phát hiện bằng eval retrieval
python eval_retrieval.py
grep "hits_forbidden.*yes" artifacts/eval/*.csv
```

---

## 5. Hạn chế & việc chưa làm

| Hạn chế | Lý do | Cải tiến |
|---------|-------|-----------|
| Freshness luôn FAIL trên data mẫu | `exported_at` cố ý cũ | Production: kết nối API thật hoặc update timestamp thủ công |
| Không có external alert (webhook/Slack) | Lab giới hạn scope | Thêm `requests.post` tới webhook khi `freshness_check=FAIL` |
| Không dùng Great Expectations library | Baseline đủ cho requirement | Có thể thay bằng GE để được +2 bonus (Distinction) |
| Không test LLM-judge cho eval | Chỉ dùng keyword matching | Mở rộng eval bằng LLM judge (Distinction option d) |
