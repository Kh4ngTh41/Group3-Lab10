# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Le Van C
**Vai trò:** Embed & Idempotency Owner
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

Là **Embed & Idempotency Owner**, tôi chịu trách nhiệm đảm bảo vector embedding đúng, idempotent, và evaluation retrieval hoạt động chính xác trước/sau mỗi pipeline run.

**File / module:**
- `etl_pipeline.py` — hàm `cmd_embed_internal` (upsert + prune)
- `eval_retrieval.py` — đánh giá retrieval bằng keyword matching
- `grading_run.py` — chạy bộ câu grading và xuất JSONL
- `chroma_db/` — PersistentClient storage

**Kết nối với thành viên khác:**
- Nhận `cleaned CSV` từ Cleaning Owner → embed vào Chroma
- Cung cấp `grading_run.jsonl` cho GV chấm điểm

---

## 2. Một quyết định kỹ thuật (100–150 từ)

**Quyết định: Prune vector không còn trong cleaned run hiện tại sau mỗi upsert.**

Mỗi lần `run`, code thực hiện:
1. Lấy danh sách tất cả `chunk_id` hiện có trong Chroma
2. Tính `drop = existing_ids - current_cleaned_ids`
3. Xoá các vector trong `drop` list
4. Upsert vectors từ cleaned run hiện tại

**Tại sao cần thiết:** Nếu không prune, sau inject-bad (--skip-validate), stale chunk "14 ngày" sẽ vẫn nằm trong Chroma collection và xuất hiện trong top-k retrieval → `hits_forbidden=yes` trong grading.

**Evidence:** Log `embed_prune_removed=N` — N=6 sau sprint2-extended (prune vector từ sprint1-clean trước khi upsert lại).

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

**Triệu chứng:** Chạy `grading_run.py` lần đầu cho thấy `gq_d10_03` (leave version) có `top1_doc_id=sla_p1_2026` thay vì `hr_leave_policy`.

**Root cause:** Chunk "Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026" bị deduplicate rule loại vì chunk text trùng với bản 2025 sau khi normalized. Chunk 12 ngày còn lại bị offset seq sai.

**Fix:** Đảm bảo deduplicate dùng `_norm_text` (lowercase, stripped) chuẩn — chunk "12 ngày" và "10 ngày" có key khác nhau (không trùng). Đã xác nhận: `expectation[hr_leave_no_stale_10d_annual] OK` trong log và `top1_doc_id=hr_leave_policy` trong grading JSONL.

**Metric:** `grading_run.jsonl`: `gq_d10_03: top1_doc_matches=true` ✅

---

## 4. Bằng chứng trước / sau (80–120 từ)

**Grading JSONL** (`artifacts/eval/grading_run.jsonl`):
```json
{"id": "gq_d10_01", "contains_expected": true, "hits_forbidden": false, ...}
{"id": "gq_d10_02", "contains_expected": true, "hits_forbidden": false, ...}
{"id": "gq_d10_03", "contains_expected": true, "hits_forbidden": false,
 "top1_doc_matches": true, "top1_doc_id": "hr_leave_policy", ...}
```

**Eval retrieval (clean state):**
| question_id | contains_expected | hits_forbidden | top1_doc_expected |
|-------------|-------------------|----------------|--------------------|
| q_refund_window | yes | no | - |
| q_p1_sla | yes | no | - |
| q_leave_version | yes | no | yes |

File: `artifacts/eval/grading_run.jsonl`, `artifacts/eval/before_after_eval.csv`

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ: Mở rộng `eval_retrieval.py` với LLM-judge (dùng GPT-4o mini hoặc tương đương) thay vì keyword matching hiện tại. LLM judge đánh giá context quality chính xác hơn, đặc biệt cho các câu hỏi mà keyword không đủ (ví dụ: "policy này có lỗi không?"). Output thêm cột `llm_judge_score` vào CSV.
