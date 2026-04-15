# Data Contract — Lab Day 10

> Mở rộng từ `contracts/data_contract.yaml` — đồng bộ source map, schema, và SLA.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `data/raw/policy_export_dirty.csv` | Batch CSV export hàng ngày (mock) | Duplicate rows, thiếu ngày, doc_id lạ, date format không ISO, stale version HR (10 ngày), stale refund (14 ngày) | `raw_records`, `quarantine_records` |
| HR system (CSV export) | Same CSV batch | Conflict version: 2025 (10 ngày) vs 2026 (12 ngày) | `hr_leave_policy` effective_date check |
| CS policy DB | Same CSV export | Stale refund window: v3 ghi 14 ngày thay vì v4 quy định 7 ngày | `refund_no_stale_14d_window` expectation |
| IT helpdesk FAQ | Same CSV export | Date format DMY vs ISO; missing effective_date | Quarantine rule on empty date |

**Source map framework (3 câu hỏi):**
- Nguồn nào? → CSV export batch (policy_export_dirty.csv)
- Hỏng kiểu gì? → Duplicate, stale version, date không chuẩn, BOM, doc_id không hợp lệ
- Đo cái gì? → `quarantine_records`, `expectation[refund_no_stale_14d_window]`, `freshness_check`

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | Stable ID: `doc_id_seq_sha256[0:16]` |
| `doc_id` | string | Có | Key format: `^[a-z0-9_]+$` |
| `chunk_text` | string | Có | Min 8 chars; BOM/whitespace đã normalize |
| `effective_date` | date (YYYY-MM-DD) | Có | ISO 8601; quarantine nếu parse fails |
| `exported_at` | datetime (ISO) | Có | Snapshot timestamp từ source |
| `_flag_bom` | bool | Không | TRUE nếu BOM đã bị strip |
| `_flag_whitespace_normalized` | bool | Không | TRUE nếu whitespace đã collapse |
| `_flag_mostly_uppercase` | float | Không | Uppercase ratio > 0.8 → WARN |
| `_flag_excess_special_chars` | float | Không | Special char ratio > 0.15 → WARN |

---

## 3. Quy tắc quarantine vs drop

| Scenario | Hành động | Ghi log | Ai approve |
|----------|-----------|---------|------------|
| `doc_id` không trong allowlist | **Quarantine** | `unknown_doc_id` + doc_id | Cleaning Owner |
| `effective_date` trống | **Quarantine** | `missing_effective_date` | Cleaning Owner |
| `effective_date` không parse được | **Quarantine** | `invalid_effective_date_format` + raw value | Cleaning Owner |
| HR policy effective < 2026-01-01 | **Quarantine** | `stale_hr_policy_effective_date` | Cleaning Owner |
| `chunk_text` trống | **Quarantine** | `missing_chunk_text` | Cleaning Owner |
| Duplicate `chunk_text` | **Quarantine** | `duplicate_chunk_text` | Cleaning Owner |
| `doc_id` format không hợp lệ (`[^a-z0-9_]`) | **Quarantine** | `doc_id_format_invalid:*` | Cleaning Owner |

> **Không silent drop.** Mọi quyết định loại bỏ đều ghi reason vào quarantine CSV + log.

---

## 4. Phiên bản & canonical

| Policy | File gốc (canonical) | Version | Quy tắc |
|--------|----------------------|---------|---------|
| Refund policy | `data/docs/policy_refund_v4.txt` | v4 | Cửa sổ hoàn tiền = **7 ngày làm việc** |
| P1 SLA | `data/docs/sla_p1_2026.txt` | 2026 | Phản hồi 15 phút, resolution 4 giờ |
| IT helpdesk FAQ | `data/docs/it_helpdesk_faq.txt` | current | Account lockout 5 lần, reset password 24h |
| HR leave policy | `data/docs/hr_leave_policy.txt` | 2026 | <3 năm: **12 ngày** phép năm |

> **Lưu ý conflict:** raw export chứa cả bản HR 2025 (10 ngày, effective 2025-01-01) và bản HR 2026 (12 ngày, effective 2026-02-01). Quarantine rule lọc bản 2025 bằng effective_date threshold từ contract.yaml (`hr_leave_min_effective_date: "2026-01-01"`).

---

## 5. Freshness SLA

- **SLA:** 24 giờ kể từ `latest_exported_at`
- **Điểm đo:** tại bước **publish** (sau embed hoàn tất) — không phải tại ingest
- **Trên manifest:** `freshness_check=FAIL` (data mẫu 120 giờ > 24h SLA) — **FAIL là hợp lệ** theo thiết kế lab
- **Alert channel:** ghi vào log + runbook (không có external webhook trong lab)
