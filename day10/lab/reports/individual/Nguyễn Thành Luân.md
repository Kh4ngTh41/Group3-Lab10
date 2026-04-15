# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Nguyễn Thành Luân
**Vai trò:** Monitoring / Docs Owner
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

Là **Monitoring / Docs Owner**, tôi chịu trách nhiệm viết đầy đủ 3 docs bắt buộc (`pipeline_architecture.md`, `data_contract.md`, `runbook.md`), hoàn thành quality report, và đảm bảo freshness monitoring có giải thích rõ ràng.

**File / module:**
- `docs/pipeline_architecture.md` — sơ đồ Mermaid, ranh giới trách nhiệm, idempotency
- `docs/data_contract.md` — source map 4 nguồn, schema cleaned, quarantine rules
- `docs/runbook.md` — 5 mục Symptom→Detection→Diagnosis→Mitigation→Prevention
- `docs/quality_report.md` — before/after evidence, metric summary

**Kết nối với thành viên khác:**
- Nhận manifest từ Ingestion Owner để kiểm tra freshness
- Tổng hợp `metric_impact` table từ logs của các thành viên khác

---

## 2. Một quyết định kỹ thuật (100–150 tố)

**Quyết định: Freshness đo tại `publish` boundary, không phải `ingest`.**

Có 3 điểm có thể đo freshness:
1. **Ingest:** timestamp khi pipeline đọc raw CSV → `ingest_timestamp`
2. **Cleaned:** timestamp sau clean nhưng trước embed
3. **Publish:** timestamp sau embed hoàn tất → vector đã visible cho agent

Tôi chọn **publish** vì: agent chỉ đọc được data sau khi embed xong. Đo tại ingest sẽ không reflect thời điểm agent thực sự nhìn thấy data mới.

**Giải thích FAIL:** Manifest ghi `latest_exported_at = 2026-04-10T08:00:00` (data snapshot), không phải `run_timestamp`. Data mẫu 5 ngày tuổi → FAIL theo SLA 24h.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

**Triệu chứng:** Viết quality report, tôi nhận ra `before_after_eval.csv` và `after_clean_eval.csv` cho kết quả giống hệt nhau.

**Root cause:** Sau inject-bad (bị Unicode error và không embed), `sprint2-clean` chạy lại và ghi đè Chroma với clean data. Kết quả: cả hai eval file đều reflect clean state.

**Fix:** Chạy eval **ngay sau sprint1-clean** (trước inject-bad) để capture `before` state. Kết quả: `before_after_eval.csv` ghi lại clean state trước inject. `grading_run.jsonl` reflect clean state cuối cùng.

**Phát hiện:** Inject-bad không tạo embed mới (Unicode crash) → Chroma vẫn chứa clean data từ sprint1-clean. Chỉ có log `expectation[refund_no_stale_14d_window] FAIL` là bằng chứng.

---

## 4. Bằng chứng trước / sau (80–120 từ)

**Manifest (freshness check):**
```json
"run_id": "sprint2-extended",
"freshness_check": "FAIL",
"latest_exported_at": "2026-04-10T08:00:00",
"age_hours": 120.214,
"sla_hours": 24.0,
"reason": "freshness_sla_exceeded"
```

**Runbook giải thích:**
- PASS = `age_hours <= 24` → data tươi
- FAIL = `age_hours > 24` → data cũ > SLA

**Docs hoàn chỉnh:**
- `pipeline_architecture.md` (sơ đồ Mermaid, bảng ranh giới, idempotency)
- `data_contract.md` (4 nguồn, schema 9 cột, quarantine matrix)
- `runbook.md` (5 mục đủ, giải thích PASS/WARN/FAIL)

File: `artifacts/manifests/manifest_sprint2-extended.json`

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ: Thêm đo freshness ở **2 boundary** (ingest + publish) để được +1 bonus (Distinction criterion b). Cụ thể: ghi thêm `ingest_timestamp` vào manifest tại thời điểm load raw CSV, so sánh với `run_timestamp` (publish). Hiệu số = độ trễ từ ingest đến embed hoàn tất.
