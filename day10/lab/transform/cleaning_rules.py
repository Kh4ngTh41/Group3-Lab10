"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
SINH VIÊN THÊM ≥3 RULE MỚI:
  1. strip_bom           — loại bỏ BOM UTF-8 ở đầu chunk_text
  2. normalize_whitespace — collapse multiple spaces/tabs/newlines vào 1 space
  3. validate_doc_id_format — doc_id phải match ^[a-z0-9_]+$ (chặn injection qua tên lạ)
  4. flag_mostly_uppercase  — chunk >80% KÝ TỰ VIẾT HOA → potential parser/OCR error
  5. reject_excess_special — chunk chứa >15% ký tự đặc biệt (không phải tiếng Việt/hợp lệ)

Mỗi rule ghi impact trong bảng metric_impact của group_report.
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

# --- NEW RULES constants ---
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
# Rule 3: doc_id format validation
_DOC_ID_FORMAT = re.compile(r"^[a-z0-9_]+$")
# Rule 5: count special characters (Vietnamese letters a-z A-Z 0-9 plus Vietnamese diacritics are "normal")
_SPECIAL_CHAR_RE = re.compile(r"[^a-zA-Z0-9àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ\s]")
# Rule 4: mostly uppercase detection (>80% uppercase Latin letters of all Latin letters)
_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


# =====================================================================
# NEW CLEANING RULES (3+ required)
# =====================================================================

def _strip_bom(text: str) -> Tuple[str, bool]:
    """
    Rule 1: Loại bỏ BOM UTF-8 (\\ufeff) ở đầu chunk_text.
    Returns (cleaned, had_bom).
    BOM có thể xuất hiện khi export CSV từ Excel hoặc editors lưu with BOM.
    """
    had_bom = text.startswith("\ufeff")
    if had_bom:
        text = text[1:]
    return text, had_bom


def _normalize_whitespace(text: str) -> Tuple[str, bool]:
    """
    Rule 2: Collapse multiple spaces/tabs/newlines thành 1 space.
    Returns (normalized, was_changed).
    """
    # Collapse any whitespace sequence into single space
    original = text
    text = re.sub(r"\s+", " ", text).strip()
    return text, text != original


def _validate_doc_id_format(doc_id: str) -> Tuple[bool, str]:
    """
    Rule 3: doc_id phải match ^[a-z0-9_]+$ (không hoa, không ký tự lạ).
    Returns (is_valid, reason).
    Ngăn injection doc_id giả mạo qua export CSV.
    """
    if not doc_id:
        return False, "empty_doc_id"
    if not _DOC_ID_FORMAT.match(doc_id):
        return False, "invalid_doc_id_format"
    return True, ""


def _check_mostly_uppercase(text: str) -> Tuple[bool, float]:
    """
    Rule 4: Flag chunk có >80% ký tự Latin là HOA → potential OCR/parser error.
    Returns (is_mostly_uppercase, uppercase_ratio).
    Chỉ tính các ký tự a-zA-Z (bỏ qua số, dấu, tiếng Việt).
    """
    if not text:
        return False, 0.0
    letters = [c for c in text if _UPPERCASE_RE.match(c) or _LOWERCASE_RE.match(c)]
    if not letters:
        return False, 0.0
    upper_count = sum(1 for c in letters if _UPPERCASE_RE.match(c))
    ratio = upper_count / len(letters)
    return ratio > 0.8, round(ratio, 3)


def _check_excess_special_chars(text: str) -> Tuple[bool, float]:
    """
    Rule 5: Flag chunk có >15% ký tự đặc biệt (không phải a-zA-Z0-9/Việt/whitespace).
    Returns (has_excess_special, special_ratio).
    """
    if not text:
        return False, 0.0
    specials = _SPECIAL_CHAR_RE.findall(text)
    ratio = len(specials) / len(text)
    return ratio > 0.15, round(ratio, 3)


# =====================================================================


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline rules (1-6):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ / conflict version).
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    5) Loại trùng nội dung chunk_text (giữ bản đầu).
    6) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.

    NEW rules (7-11) — mỗi rule ghi impact trong metric_impact table:
    7) strip_bom: loại BOM UTF-8 ở đầu chunk_text
    8) normalize_whitespace: collapse multiple whitespace thành 1 space
    9) validate_doc_id_format: doc_id phải match ^[a-z0-9_]+$ — quarantine nếu không hợp lệ
   10) check_mostly_uppercase: flag chunk >80% HOA → metadata flag (WARN)
   11) check_excess_special_chars: flag chunk >15% ký tự đặc biệt → metadata flag (WARN)
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # NEW Rule 9: validate doc_id format BEFORE further processing
        doc_id_valid, doc_id_reason = _validate_doc_id_format(doc_id)
        if not doc_id_valid:
            quarantine.append({**raw, "reason": f"doc_id_format_invalid:{doc_id_reason}"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # NEW Rule 7: strip BOM
        text, had_bom = _strip_bom(text)
        # NEW Rule 8: normalize whitespace
        text, ws_normalized = _normalize_whitespace(text)

        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        # NEW Rule 10: check mostly uppercase (WARN — metadata only, not quarantine)
        mostly_upper, upper_ratio = _check_mostly_uppercase(fixed_text)
        # NEW Rule 11: check excess special chars (WARN — metadata only, not quarantine)
        excess_special, special_ratio = _check_excess_special_chars(fixed_text)

        seq += 1
        cleaned_row: Dict[str, Any] = {
            "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
            "doc_id": doc_id,
            "chunk_text": fixed_text,
            "effective_date": eff_norm,
            "exported_at": exported_at or "",
        }
        # Metadata flags for new rules (WARN level — pipeline continues)
        if had_bom:
            cleaned_row["_flag_bom"] = True
        if ws_normalized:
            cleaned_row["_flag_whitespace_normalized"] = True
        if mostly_upper:
            cleaned_row["_flag_mostly_uppercase"] = upper_ratio
        if excess_special:
            cleaned_row["_flag_excess_special_chars"] = special_ratio

        cleaned.append(cleaned_row)

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    # Core fields + any metadata flags from new rules
    base_fields = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    extra_fields = sorted(
        {k for r in rows for k in r.keys() if k.startswith("_flag_")}
    )
    fieldnames = base_fields + extra_fields
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
