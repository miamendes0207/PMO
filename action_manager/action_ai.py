# ============================================================
# action_ai.py — ScopeSight v3.6
# AI Expander for Action Shorthand Entries
# ============================================================

import json
import os
import re
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


# ------------------------------------------------------------
# INTERNAL HELPERS
# ------------------------------------------------------------
def _get_api_key() -> str:
    return os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN") or ""


def _safe_parse_json(text: str) -> Dict[str, Any]:
    """Extract first {...} blob and parse; fallback to minimal structure."""
    try:
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {
            "title": (text[:60] or "Untitled").strip(),
            "detail": text.strip(),
            "comments": "",
            "owner": "",
            "status": "",
            "priority": "",
            "due_date": "",
            "actual_close_date": "",
        }


def _clean_text(v: Any) -> str:
    return str(v or "").strip()


def _normalise_status(v: Any, status_options: List[str]) -> str:
    s = _clean_text(v)
    if not s:
        return ""
    low = s.lower()

    if low in ("done", "completed", "resolved", "closed"):
        return "Closed" if "Closed" in status_options else s

    for opt in status_options:
        if opt.lower() == low:
            return opt

    for opt in status_options:
        if opt.lower() in low:
            return opt

    return ""


def _normalise_priority(v: Any, priority_options: List[str]) -> str:
    s = _clean_text(v)
    if not s:
        return ""
    low = s.lower()

    if low in ("p1", "high"):
        return "High" if "High" in priority_options else ""
    if low in ("p2", "medium", "med"):
        return "Medium" if "Medium" in priority_options else ""
    if low in ("p3", "low"):
        return "Low" if "Low" in priority_options else ""

    for opt in priority_options:
        if opt.lower() == low:
            return opt

    for opt in priority_options:
        if opt.lower() in low:
            return opt

    return ""


def _add_working_days(start: dt.date, days: int) -> dt.date:
    d = start
    added = 0
    while added < days:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _parse_ddmmyyyy(s: str) -> Optional[dt.date]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


# ------------------------------------------------------------
# OWNER EXTRACTION (IMPROVED)
# ------------------------------------------------------------
_OWNER_BLACKLIST = {
    # delivery/common
    "QC", "QA", "UAT", "SIT", "DEV", "PROD", "TOM", "BAU", "PMO", "RAG", "NFR", "SOW",
    "KPI", "OKR", "API", "ETL", "IAM", "SSO", "VPN", "DWH", "BI",
    # roles/titles
    "CEO", "CFO", "COO", "CTO", "CIO", "PM", "PO", "BA", "SME",
    # misc
    "DB", "UI", "UX",
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)

# crude “name-ish” pattern: First Last / First L.
_NAME_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}|[A-Z][a-z]+\s+[A-Z]\.)\b"
)

def _is_bad_initials(tok: str) -> bool:
    t = (tok or "").strip().upper()
    if not t:
        return True
    if t in _OWNER_BLACKLIST:
        return True
    # avoid things like "FYI", "ASAP"
    if t in {"FYI", "ASAP", "TBC", "TBD"}:
        return True
    return False


def _extract_owner_from_text(text: str) -> Tuple[str, str]:
    """
    Returns (owner, confidence) where confidence is one of:
    - "explicit" (Owner: X / Assigned to X / @X)
    - "implied"  (X to do..., X - do..., (X) do...)
    - "" if none
    """
    if not text:
        return "", ""

    t = text.strip()

    # 1) Email (treat as explicit)
    m = _EMAIL_RE.search(t)
    if m:
        return m.group(0).strip(), "explicit"

    # 2) Explicit labelled owner/assignee (initials OR name)
    explicit_patterns = [
        r"\bowner\s*[:\-]\s*([A-Z]{2,3})\b",
        r"\bowner\s*[:\-]\s*(" + _NAME_RE.pattern + r")",
        r"\bassigned\s*to\s*[:\-]?\s*([A-Z]{2,3})\b",
        r"\bassigned\s*to\s*[:\-]?\s*(" + _NAME_RE.pattern + r")",
        r"\bassignee\s*[:\-]\s*([A-Z]{2,3})\b",
        r"\bassignee\s*[:\-]\s*(" + _NAME_RE.pattern + r")",
        r"\baction\s*[:\-]\s*([A-Z]{2,3})\b",
        r"\baction\s*[:\-]\s*(" + _NAME_RE.pattern + r")",
        r"@([A-Z]{2,3})\b",
    ]

    for p in explicit_patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            # if matched initials, normalise to uppercase
            if re.fullmatch(r"[A-Z]{2,3}", cand, flags=re.IGNORECASE):
                cand = cand.upper()
                if _is_bad_initials(cand):
                    continue
            return cand, "explicit"

    # 3) Implied patterns (common shorthand):
    #    "HT to chase X", "HT - chase X", "(HT) chase X", "HT: chase X"
    implied_patterns = [
        r"\b([A-Z]{2,3})\b\s+(?:to|will|needs to|need to|must|should|can)\b",
        r"\b([A-Z]{2,3})\b\s*[:\-–]\s*\w+",
        r"\(\s*([A-Z]{2,3})\s*\)\s*\w+",
        r"\b(" + _NAME_RE.pattern + r")\b\s+(?:to|will|needs to|must|should)\b",
        r"\b(" + _NAME_RE.pattern + r")\b\s*[:\-–]\s*\w+",
    ]

    for p in implied_patterns:
        m = re.search(p, t)
        if m:
            cand = m.group(1).strip()
            if re.fullmatch(r"[A-Z]{2,3}", cand):
                cand = cand.upper()
                if _is_bad_initials(cand):
                    continue
            return cand, "implied"

    return "", ""


# ------------------------------------------------------------
# PROMPTS
# ------------------------------------------------------------
def _build_system_prompt(status_options: List[str], priority_options: List[str]) -> str:
    # Align prompt with your extraction logic (so AI doesn't blank-out owner unnecessarily)
    return f"""
You are the ScopeSight Action Shorthand Expansion Engine.
Convert shorthand action notes into structured action fields in professional PMO language (formal British English).

REQUIREMENTS:
- Return ONLY valid JSON (no commentary).
- Do NOT invent people, roles, or emails.
- Owner must be extracted ONLY if it appears in the shorthand:
  - Explicit: "Owner: X", "Assigned to X", "@X", or an email address.
  - Implied shorthand is allowed ONLY for initials/names that clearly read as a person doing the action,
    e.g. "HT to chase ...", "HT - chase ...", "(HT) chase ...".
  - Avoid common abbreviations like QC/UAT/BAU/PMO etc.

FIELDS:
- title: short subject
- detail: expanded description
- comments: optional notes
- owner: email OR initials OR name if present, otherwise blank
- status: choose from: {status_options}
- priority: choose from: {priority_options}
- due_date: DD/MM/YYYY if explicitly stated or confidently inferred, otherwise blank
- actual_close_date: DD/MM/YYYY only if explicitly provided, otherwise blank

OUTPUT JSON:
{{
  "title": "",
  "detail": "",
  "comments": "",
  "owner": "",
  "status": "",
  "priority": "",
  "due_date": "",
  "actual_close_date": ""
}}
""".strip()


def _build_user_prompt(shorthand: str) -> str:
    return f"""
Expand and structure this action shorthand:

Shorthand:
\"\"\"{shorthand}\"\"\"

Return ONLY a JSON object (no commentary).
""".strip()


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def expand_action_shorthand(
    shorthand: str,
    status_options: List[str],
    priority_options: List[str],
    history: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Returns dict for UI prefill.

    Key detail for your app:
    - due_date_dt + actual_close_date_dt returned as datetime.date objects
      so your Streamlit date_input widgets prefill correctly.
    """
    shorthand = (shorthand or "").strip()
    today = dt.date.today()

    default_due_dt = _add_working_days(today, 5)
    default_due_str = default_due_dt.strftime("%d/%m/%Y")

    # NEW: deterministic owner extraction from the shorthand + confidence
    extracted_owner, owner_conf = _extract_owner_from_text(shorthand)

    fallback = {
        "title": f"Draft from shorthand: {(shorthand[:60] or 'Untitled')}",
        "detail": shorthand,
        "comments": "",
        "owner": extracted_owner or "",  # better fallback
        "status": "",
        "priority": "",
        "due_date": default_due_str,
        "due_date_dt": default_due_dt,
        "actual_close_date": "",
        "actual_close_date_dt": None,
        "date_raised": today,
    }

    if not shorthand:
        return fallback

    api_key = _get_api_key()
    if not api_key or OpenAI is None:
        return fallback

    try:
        client = OpenAI(api_key=api_key)

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _build_system_prompt(status_options, priority_options)},
                {"role": "user", "content": _build_user_prompt(shorthand)},
            ],
            temperature=0.25,
            max_tokens=450,
        )

        raw = (resp.choices[0].message.content or "").strip()
        data = _safe_parse_json(raw)

        title = _clean_text(data.get("title") or fallback["title"])
        detail = _clean_text(data.get("detail") or fallback["detail"])
        comments = _clean_text(data.get("comments") or "")

        # --- OWNER MERGE RULES (FIXES YOUR ISSUE) ---
        ai_owner = _clean_text(data.get("owner") or "")

        # If shorthand contains an explicit owner, always use it.
        if owner_conf == "explicit" and extracted_owner:
            owner = extracted_owner
        else:
            # Otherwise: prefer AI owner, fallback to extracted_owner (implied) if AI blank.
            owner = ai_owner or extracted_owner or ""

        status = _normalise_status(data.get("status"), status_options)
        priority = _normalise_priority(data.get("priority"), priority_options)

        # --- Due date rule (5 working days if none) ---
        due_raw = _clean_text(data.get("due_date") or "")
        due_dt = _parse_ddmmyyyy(due_raw) if due_raw else None
        if due_dt is None:
            due_dt = default_due_dt
            due_str = default_due_str
        else:
            due_str = due_dt.strftime("%d/%m/%Y")

        # --- Actual close date (only if explicitly present) ---
        ac_raw = _clean_text(data.get("actual_close_date") or "")
        ac_dt = _parse_ddmmyyyy(ac_raw) if ac_raw else None
        ac_str = ac_dt.strftime("%d/%m/%Y") if ac_dt else ""

        return {
            "title": title,
            "detail": detail,
            "comments": comments,
            "owner": owner,
            "status": status,
            "priority": priority,
            "due_date": due_str,
            "due_date_dt": due_dt,
            "actual_close_date": ac_str,
            "actual_close_date_dt": ac_dt,
            "date_raised": today,
        }

    except Exception:
        return fallback
