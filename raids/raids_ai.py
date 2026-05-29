# ============================================================
# raids_ai.py — ScopeSight v3.1
# Advanced AI Expander for RAID Shorthand Entries
# ============================================================

import json
import os
import re
import datetime as dt
from typing import List, Dict, Any

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


SECTION_EXPLANATIONS = {
    "Risks": "A risk is a potential future event that could negatively impact delivery.",
    "Issues": "An issue is something actively happening that requires resolution.",
    "Assumptions": "An assumption is a condition believed to be true but not validated.",
    "Dependencies": "A dependency is an item requiring completion or support from another party.",
}


# ------------------------------------------------------------
# INTERNAL HELPERS
# ------------------------------------------------------------
def _get_api_key() -> str:
    return os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN") or ""


def _parse_section_and_tone(section_label: str) -> tuple[str, str]:
    s = (section_label or "").strip()
    tone = "Formal"
    for sep in ["—", "-", "|", ":"]:
        if sep in s:
            left, right = s.split(sep, 1)
            base = left.strip()
            t = right.strip()
            if t:
                tone = t
            return base, tone
    return s, tone


def _safe_parse_json(text: str) -> Dict[str, Any]:
    try:
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {
            "title": (text[:60] or "Untitled").strip(),
            "description": text.strip(),
            "comments": "",
            "status": "Open",
            "probability": 3,
            "severity": 3,
            "rag": "Amber",
            "priority": "Medium",
            "due_date": "",
            "mitigation_plan": "",
            "resolution": "",
            "owner_plen": "",
            "owner_client": "",
        }


def _coerce_1_5(v: Any, default: int = 3) -> int:
    try:
        i = int(v)
        return max(1, min(5, i))
    except Exception:
        return default


def _normalise_rag(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in ("red", "amber", "green"):
        return s.capitalize()
    return "Amber"


def _normalise_priority(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in ("high", "medium", "low"):
        return s.capitalize()
    return "Medium"


def _normalise_status(v: Any) -> str:
    """
    Your UI uses: Open / Amber / Red / Green / Closed.
    Keep "Open" default unless explicitly closed or explicitly rag-colour status.
    """
    s = str(v or "").strip()
    if not s:
        return "Open"
    low = s.lower()
    if low in ("closed", "resolved", "completed", "done"):
        return "Closed"
    if low in ("open",):
        return "Open"
    if low in ("red", "amber", "green"):
        return low.capitalize()
    return s


def _clean_text(v: Any) -> str:
    return str(v or "").strip()


def _infer_owner_from_initials(text: str) -> str:
    """
    Extract likely owner initials from shorthand while avoiding common abbreviations/acronyms
    (e.g. QC = Quality Check, UAT, TOM, etc.)

    Heuristics:
    1) Prefer initials in owner-like patterns: "HT to", "Owner: HT", "Action: HT"
    2) Exclude known abbreviations/acronyms.
    3) Fallback: any standalone 2–3 uppercase letters not blacklisted.
    """
    if not text:
        return ""

    blacklist = {
        # delivery/common
        "QC", "QA", "UAT", "SIT", "DEV", "PROD", "TOM", "BAU", "PMO", "RAG", "NFR", "SOW",
        "KPI", "OKR", "API", "ETL", "IAM", "SSO", "VPN", "DWH", "BI",
        # roles/titles
        "CEO", "CFO", "COO", "CTO", "CIO", "PM", "PO", "BA", "SME",
        # misc common
        "DB", "UI", "UX",
    }

    t = text.strip()

    patterns = [
        r"\bOwner\s*[:\-]\s*([A-Z]{2,3})\b",
        r"\bAction\s*[:\-]\s*([A-Z]{2,3})\b",
        r"\bAssigned\s*to\s*[:\-]?\s*([A-Z]{2,3})\b",
        r"\b([A-Z]{2,3})\b\s+(?:to|will|needs to|need to|must|should|can)\b",
        r"\b(?:by|from|with)\s+([A-Z]{2,3})\b",
    ]

    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            cand = m.group(1).upper()
            if cand not in blacklist:
                return cand

    candidates = re.findall(r"\b[A-Z]{2,3}\b", t)
    for cand in candidates:
        cand = cand.upper()
        if cand not in blacklist:
            return cand

    return ""


def _add_working_days(start: dt.date, days: int) -> dt.date:
    d = start
    added = 0
    while added < days:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:  # Mon=0 ... Fri=4
            added += 1
    return d


def _parse_ddmmyyyy(s: str) -> dt.date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:
        return None


_ROMAN = ["(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)", "(vii)", "(viii)", "(ix)", "(x)"]


def _ensure_mitigation_single_cell(text: str) -> str:
    """
    Enforce a single-cell mitigation style like:
    (i) ...
    <blank line>
    (ii) ...

    If the model returns bullets or unnumbered lines, we coerce them.
    """
    t = (text or "").strip()
    if not t:
        return ""

    t = t.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Already in (i) style?
    if re.search(r"\(\s*i\s*\)", t, flags=re.IGNORECASE):
        t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
        return t.strip()

    # Split into candidate steps
    raw_lines = [ln.strip() for ln in re.split(r"\n+", t) if ln.strip()]
    items: List[str] = []

    for ln in raw_lines:
        ln = re.sub(r"^\s*[-•*]\s+", "", ln).strip()
        parts = [p.strip() for p in re.split(r"\s*;\s+", ln) if p.strip()]
        if len(parts) > 1:
            items.extend(parts)
        else:
            items.append(ln)

    # If one big paragraph, try splitting on sentence-ish boundaries (light touch)
    if len(items) <= 1:
        parts = [p.strip() for p in re.split(r"\.\s+(?=[A-Z(])", t) if p.strip()]
        if len(parts) > 1:
            items = parts

    items = [re.sub(r"\s+", " ", it).strip() for it in items if it.strip()]
    if not items:
        return ""

    # Cap to keep it cell-friendly
    if len(items) > 5:
        items = items[:5]

    out_lines: List[str] = []
    for idx, it in enumerate(items, start=1):
        tag = _ROMAN[idx - 1] if idx - 1 < len(_ROMAN) else f"({idx})"
        if it and it[-1] not in ".!?":
            it += "."
        out_lines.append(f"{tag} {it}")

    return "\n\n".join(out_lines).strip()


# ------------------------------------------------------------
# PROMPTS
# ------------------------------------------------------------
def _build_system_prompt(section: str, tone: str) -> str:
    tone = (tone or "Formal").strip().lower()
    tone_guidance = {
        "concise": "Write briefly and directly. Minimal filler. Short sentences.",
        "detailed": "Write with context and clear rationale. Slightly longer narrative.",
        "formal": "Write in formal British English with polished PMO language.",
    }.get(tone, "Write in formal British English with polished PMO language.")

    # Section-specific mitigation hints (kept short so we don't over-constrain)
    section_hint = {
        "Risks": "For risks, include preventative controls and a contingency response.",
        "Issues": "For issues, include immediate containment and a path to resolution.",
        "Assumptions": "For assumptions, include validation steps and fallback if disproven.",
        "Dependencies": "For dependencies, include engagement actions and escalation path.",
    }.get(section, "")

    return f"""
You are the ScopeSight RAID Shorthand Expansion Engine.
You convert shorthand RAID entries into structured RAID records with professional PMO wording.

SECTION TYPE: {section}
Meaning: {SECTION_EXPLANATIONS.get(section, "")}

STYLE:
- {tone_guidance}
- Use formal British English.
- Use DD/MM/YYYY for any dates.

REQUIREMENTS:
- Produce a concise Title.
- Produce a professional Description expanding the shorthand.
- Produce concise Comments with factual next steps.
- Probability (1–5) and Severity (1–5).
  - For Issues: default Probability = 5 unless clearly otherwise.
- RAG (Red/Amber/Green) based on score/urgency.
- Priority (High/Medium/Low).
- Status must be one of: Open / Amber / Red / Green / Closed (default to Open if unsure).
- If a specific date is stated or can be confidently inferred, set due_date (DD/MM/YYYY).
  Otherwise, leave due_date blank.

MITIGATION PLAN (SINGLE CELL):
- Populate "mitigation_plan" as ONE plain-text cell written in PMO action style.
- Use roman numerals exactly like:
  (i) <action sentence>.
  (ii) <action sentence>.
- Keep to 2–4 steps where possible.
- Each step must be a complete action sentence (Verb + who/what + purpose).
- {section_hint}
- Do NOT invent names or dates. If an owner is unknown, use role-based wording (e.g., "PMO Lead", "Workstream Lead") or omit the name.

IMPORTANT:
- Do NOT invent unrealistic facts or names.
- ALWAYS return ONLY valid JSON. No commentary.

OUTPUT JSON:
{{
  "title": "",
  "description": "",
  "comments": "",
  "status": "Open",
  "probability": 3,
  "severity": 3,
  "rag": "Amber",
  "priority": "Medium",
  "due_date": "",
  "mitigation_plan": "",
  "resolution": "",
  "owner_plen": "",
  "owner_client": ""
}}
""".strip()


def _build_user_prompt(shorthand: str, history: List[str]) -> str:
    hist = ""
    if history:
        recent = "\n".join(f"- {h}" for h in history[-5:])
        hist = f"\nRecent examples in this RAID section:\n{recent}\n"

    return f"""
Expand and structure this RAID shorthand:

Shorthand:
\"\"\"{shorthand}\"\"\"

{hist}

Return ONLY a JSON object (no commentary).
""".strip()


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def expand_shorthand_entry(section: str, shorthand: str, history: List[str]) -> Dict[str, Any]:
    """
    Returns dict for UI prefill.

    Key detail for your app:
    - planned_close + next_review are returned as datetime.date objects
      so your Streamlit date_input widgets prefill correctly.
    """
    base_section, tone = _parse_section_and_tone(section)
    shorthand = (shorthand or "").strip()

    today = dt.date.today()
    default_due_dt = _add_working_days(today, 5)
    default_due_str = default_due_dt.strftime("%d/%m/%Y")
    fallback_owner = _infer_owner_from_initials(shorthand)

    fallback = {
        "title": f"Draft from shorthand: {(shorthand[:60] or 'Untitled')}",
        "description": shorthand,
        "comments": "",
        "status": "Open",
        "probability": 3,
        "severity": 3,
        "rag": "Amber",
        "priority": "Medium",
        "due_date": default_due_str,          # keep string too (for preview/export)
        "planned_close": default_due_dt,      # ✅ date_input uses this
        "next_review": default_due_dt,        # ✅ same default
        "date_raised": today,
        "mitigation_plan": "",
        "resolution": "",
        "owner_plen": fallback_owner,
        "owner_client": "",
        # legacy alias for safety
        "mitigation": "",
    }

    if not shorthand:
        return fallback

    api_key = _get_api_key()
    if not api_key or OpenAI is None:
        return fallback  # AI optional

    try:
        client = OpenAI(api_key=api_key)

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _build_system_prompt(base_section, tone)},
                {"role": "user", "content": _build_user_prompt(shorthand, history or [])},
            ],
            temperature=0.25,
            max_tokens=800,
        )

        raw = (resp.choices[0].message.content or "").strip()
        data = _safe_parse_json(raw)

        # --- Core text fields ---
        title = _clean_text(data.get("title") or fallback["title"])
        description = _clean_text(data.get("description") or fallback["description"])
        comments = _clean_text(data.get("comments") or "")

        # --- Scores (support legacy impact/likelihood) ---
        impact = data.get("impact", None)
        likelihood = data.get("likelihood", None)

        probability = data.get("probability", likelihood if likelihood is not None else fallback["probability"])
        severity = data.get("severity", impact if impact is not None else fallback["severity"])

        probability = _coerce_1_5(
            probability,
            default=5 if base_section.strip().lower() == "issues" else fallback["probability"],
        )
        severity = _coerce_1_5(severity, default=fallback["severity"])

        rag = _normalise_rag(data.get("rag"))
        priority = _normalise_priority(data.get("priority"))
        status = _normalise_status(data.get("status"))

        # --- Owners (initials rule + abbreviation-safe) ---
        owner_plen = _clean_text(data.get("owner_plen") or data.get("owner") or "")
        if not owner_plen:
            owner_plen = fallback_owner
        owner_client = _clean_text(data.get("owner_client") or "")

        # --- Due date rule (5 working days if none) ---
        due_date_raw = _clean_text(data.get("due_date") or data.get("due") or "")
        due_dt = _parse_ddmmyyyy(due_date_raw) if due_date_raw else None
        if due_dt is None:
            due_dt = default_due_dt
            due_date = default_due_str
        else:
            due_date = due_dt.strftime("%d/%m/%Y")

        # --- Mitigation: prefer mitigation_plan; accept legacy mitigation ---
        mitigation_plan_raw = _clean_text(
            data.get("mitigation_plan") or data.get("mitigation") or ""
        )
        mitigation_plan = _ensure_mitigation_single_cell(mitigation_plan_raw)

        resolution = _clean_text(data.get("resolution") or "")

        out = {
            "title": title,
            "description": description,
            "comments": comments,
            "status": status,
            "probability": probability,
            "severity": severity,
            "rag": rag,
            "priority": priority,
            "due_date": due_date,

            "planned_close": due_dt,
            "next_review": due_dt,
            "date_raised": today,

            "mitigation_plan": mitigation_plan,
            "resolution": resolution,
            "owner_plen": owner_plen,
            "owner_client": owner_client,

            # legacy aliases (kept for compatibility)
            "impact": severity,
            "likelihood": probability,
            "owner": owner_plen,
            "mitigation": mitigation_plan,
        }

        return out

    except Exception:
        # clean fallback (no error blob)
        return fallback