# modules/gov_builder/gov_ai.py
#
# Timeframe-aware Governance "Agents" with Enhanced Executive Narrative
# Intelligent inference + professional governance language
#
# Version: v4.1

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Any, Optional, Dict, Tuple
import datetime as dt
import json
import re


# ============================================================
# SAFE SNIPPET FORMATTER
# ============================================================

def _snippet_to_text(item: Any) -> str:
    """Coerce a snippet into a safe, readable string."""
    if item is None:
        return ""

    if isinstance(item, str):
        return item.strip()

    if isinstance(item, dict):
        title = (item.get("title") or item.get("Title") or "").strip()
        status = (item.get("status") or item.get("Status") or "").strip()
        raid_type = (item.get("raid_type") or item.get("type") or item.get("raidType") or "").strip()
        score = item.get("revised_score", item.get("score", ""))

        bits = []
        if raid_type:
            bits.append(str(raid_type))
        if title:
            bits.append(title)

        head = " — ".join([b for b in bits if b])

        tail_parts = []
        if status:
            tail_parts.append(f"Status: {status}")
        if score not in ("", None):
            tail_parts.append(f"Score: {score}")

        tail = f" ({', '.join(tail_parts)})" if tail_parts else ""

        if head:
            return f"{head}{tail}".strip()

        try:
            return json.dumps(item, ensure_ascii=False)
        except Exception:
            return str(item)

    try:
        return str(item).strip()
    except Exception:
        return ""


def _clean_snippets(snippets: List[Any], limit: int = 8) -> List[str]:
    """Convert a list of mixed objects into a list of non-empty strings."""
    if not snippets:
        return []
    cleaned: List[str] = []
    for s in snippets[:limit]:
        text = _snippet_to_text(s)
        if text:
            cleaned.append(text)
    return cleaned


# ============================================================
# DATE PARSING + TIMEFRAME FILTERING
# ============================================================

def _parse_date(val: Any) -> Optional[dt.date]:
    """Best-effort parse into date (supports date/datetime/ISO strings)."""
    if val is None:
        return None

    if isinstance(val, dt.date) and not isinstance(val, dt.datetime):
        return val

    if isinstance(val, dt.datetime):
        return val.date()

    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None

        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            pass

        try:
            import pandas as pd  # optional
            x = pd.to_datetime(s, errors="coerce")
            if str(x) != "NaT":
                return x.to_pydatetime().date()
        except Exception:
            return None

    return None


def _in_range(d: Optional[dt.date], start: dt.date, end: dt.date) -> bool:
    return d is not None and start <= d <= end


def _overlaps(start_a: Optional[dt.date], end_a: Optional[dt.date], start_b: dt.date, end_b: dt.date) -> bool:
    """Return True if [start_a, end_a] overlaps [start_b, end_b]."""
    if start_a is None or end_a is None:
        return False
    return start_a <= end_b and end_a >= start_b


def filter_records_for_period(
        records: List[Dict[str, Any]],
        period_start: dt.date,
        period_end: dt.date,
        *,
        kind: str,
) -> List[Dict[str, Any]]:
    """Timeframe filtering for different record types."""
    if not records:
        return []

    out: List[Dict[str, Any]] = []
    today = dt.date.today()

    for r in records:
        rr = r or {}

        if kind == "weekly_nfr":
            wc = _parse_date(rr.get("week_commencing")) or _parse_date(rr.get("created_at")) or _parse_date(rr.get("date"))
            if _in_range(wc, period_start, period_end):
                out.append(rr)
            continue

        if kind == "tasks":
            s = _parse_date(rr.get("start_date"))
            e = _parse_date(rr.get("end_date"))
            if _overlaps(s, e, period_start, period_end):
                out.append(rr)
            continue

        if kind == "raids":
            created = _parse_date(rr.get("created_at"))
            updated = _parse_date(rr.get("updated_at"))

            status = str(rr.get("status", "")).strip().lower()
            is_open = status in ("open", "in progress", "active")

            if _in_range(created, period_start, period_end) or _in_range(updated, period_start, period_end) or is_open:
                out.append(rr)
            continue

        if kind == "actions":
            created = _parse_date(rr.get("created_at"))
            updated = _parse_date(rr.get("updated_at"))
            due = _parse_date(rr.get("due_date"))

            status = str(rr.get("status", "")).strip().lower()
            is_open = status not in ("closed", "done", "completed", "resolved")

            overdue_open = is_open and due is not None and due < today

            if (
                    _in_range(created, period_start, period_end)
                    or _in_range(updated, period_start, period_end)
                    or _in_range(due, period_start, period_end)
                    or overdue_open
            ):
                out.append(rr)
            continue

        out.append(rr)

    return out


# ============================================================
# BRIEF + AGENT INTERFACES
# ============================================================

@dataclass
class GovBrief:
    client_name: str
    project_name: Optional[str]
    period_start: dt.date
    period_end: dt.date

    weekly_nfr: List[Dict[str, Any]]
    raids: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]

    kpis: Dict[str, Any]


class SummaryAgent:
    name: str = "Agent"

    def run(self, brief: GovBrief) -> str:
        raise NotImplementedError


# ============================================================
# BASIC RANKING / UTILS
# ============================================================

def _score_raid(r: Dict[str, Any]) -> float:
    v = r.get("revised_score", r.get("score", 0))
    try:
        return float(v)
    except Exception:
        return 0.0


def _due_date(action: Dict[str, Any]) -> Optional[dt.date]:
    return _parse_date(action.get("due_date"))


def _is_open_status(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return s not in ("closed", "done", "completed", "resolved")


def _is_closed_status(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return s in ("closed", "done", "completed", "resolved")


def _as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            j = json.loads(s)
            return j if isinstance(j, list) else [j]
        except Exception:
            return [s]
    return [v]


def _as_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v).strip()


def _dedup_preserve(items: List[str], limit: int = 30) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        k = (x or "").strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
        if len(out) >= limit:
            break
    return out


def _sent_join(bits: List[str]) -> str:
    bits = [b.strip() for b in bits if b and b.strip()]
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} and {bits[1]}"
    return ", ".join(bits[:-1]) + f", and {bits[-1]}"


# ============================================================
# EXEC / RAID TEXT SHAPING HELPERS
# ============================================================

def _compact(text: str, *, max_sentences: int = 2, max_chars: int = 260) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    parts = re.split(r"(?<=[.!?])\s+", t)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return t[:max_chars].rstrip(". ") + "."
    out = " ".join(parts[:max_sentences]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip(". ") + "."
    return out


def _labelled_line(label: str, text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = _compact(t)
    return f"* {label}: {t}"


def _pick_first_nonempty(d: dict, keys: List[str]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if v is not None and not isinstance(v, (dict, list)) and str(v).strip():
            return str(v).strip()
    return ""


def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\s:/\-]", "", s)
    return s


def _record_date(r: Dict[str, Any]) -> dt.date:
    return (
        _parse_date(r.get("updated_at"))
        or _parse_date(r.get("created_at"))
        or dt.date(1900, 1, 1)
    )


def _raid_group_key(r: Dict[str, Any]) -> str:
    rr = r or {}
    rid = rr.get("id") or rr.get("raid_id") or rr.get("item_id")
    if rid not in (None, "", "nan"):
        return f"id:{rid}"
    raw_type = (rr.get("raid_type") or rr.get("type") or rr.get("raidType") or "risk").strip()
    title = (rr.get("title") or rr.get("risk") or rr.get("issue") or rr.get("name") or "").strip()
    return f"{_norm_key(raw_type)}::{_norm_key(title)}"


def _best_text(*vals: Any) -> str:
    candidates = []
    for v in vals:
        t = (v or "").strip() if isinstance(v, str) else (str(v).strip() if v is not None else "")
        t = re.sub(r"\s+", " ", t)
        if not t:
            continue
        candidates.append(t)
    if not candidates:
        return ""

    def score(t: str) -> float:
        length = len(t)
        has_punct = 1.0 if re.search(r"[.!?]", t) else 0.0
        too_long_penalty = 0.0 if length <= 500 else (length - 500) / 500
        return (min(length, 500) / 500) + has_punct - too_long_penalty

    candidates.sort(key=score, reverse=True)
    return candidates[0]


# ============================================================
# OWNER INITIALS HELPERS (Actions Summary)
# ============================================================

def _owner_initials(owner: str) -> str:
    s = (owner or "").strip()
    if not s:
        return ""
    if "@" in s:
        s = s.split("@", 1)[0]
    s = s.replace(".", " ").replace("_", " ").replace("-", " ")
    parts = [p for p in s.split() if p]
    if not parts:
        return ""
    if len(parts) == 1 and len(parts[0]) <= 3 and parts[0].isalpha():
        return parts[0].upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _strip_owner_tokens(text: str) -> str:
    return re.sub(r"\s*\(\s*Owner\s*:\s*[^)]+\)\s*$", "", (text or "").strip(), flags=re.IGNORECASE)


# ============================================================
# WEEKLY/DAILY NFR FIELD EXTRACTION
# ============================================================

def _extract_nfr_delivery_points(nfr: Dict[str, Any]) -> List[str]:
    """Extract delivery points from NFR (weekly or daily)."""
    pts: List[str] = []

    # Objectives (common in weekly)
    obj = _as_text(nfr.get("objectives"))
    if obj:
        for line in [x.strip("•- \t") for x in obj.splitlines()]:
            if line.strip():
                pts.append(line.strip())

    # Discussion sections (weekly structure)
    ds = nfr.get("discussion_sections")
    for item in _as_list(ds):
        if isinstance(item, dict):
            title = (item.get("title") or item.get("heading") or "").strip()
            body = (item.get("content") or item.get("text") or item.get("summary") or "").strip()
            if title and body:
                pts.append(f"{title} – {body}")
            elif body:
                pts.append(body)
        else:
            t = _as_text(item)
            if t:
                pts.append(t)

    # Daily-NFR-ish fields (common variants)
    for k in ("summary", "highlights", "progress_update", "progress", "key_updates", "delivery_update", "delivery", "notes"):
        v = _as_text(nfr.get(k))
        if not v:
            continue
        for ln in v.splitlines():
            ln = ln.strip("•- \t").strip()
            if ln:
                pts.append(ln)

    return [p for p in pts if p]


def _extract_nfr_next_steps(nfr: Dict[str, Any]) -> List[str]:
    pts: List[str] = []
    acts = nfr.get("actions")
    for a in _as_list(acts):
        if isinstance(a, dict):
            title = (a.get("title") or a.get("action") or "").strip()
            owner = (a.get("owner") or a.get("assignee") or "").strip()
            due = _as_text(a.get("due_date") or a.get("due"))
            bits = [b for b in [title, (f"Owner: {owner}" if owner else ""), (f"Due: {due}" if due else "")] if b]
            if bits:
                pts.append(" – ".join(bits))
        else:
            t = _as_text(a)
            if t:
                pts.append(t)
    return [p for p in pts if p]


# ============================================================
# TASK SUMMARIES
# ============================================================

def _top_tasks_summary(tasks: List[Dict[str, Any]], limit: int = 12) -> List[str]:
    out: List[str] = []
    for t in tasks[:limit]:
        title = (t.get("title") or "Task").strip()
        ws = (t.get("workstream_name") or "").strip()

        if ws and title:
            out.append(f"{ws} – {title}")
        elif title:
            out.append(title)
    return out


# ============================================================
# INFERENCE + NARRATIVE GENERATION
# ============================================================

_PROGRESS_DONE = ("complete", "completed", "signed off", "finalised", "finalized", "delivered", "closed", "cascaded", "resolved")
_PROGRESS_INPROG = ("in progress", "underway", "commenced", "ongoing", "working", "draft", "developing", "progressing", "initiated")
_PROGRESS_NEXT = ("scheduled", "next", "will", "planned", "upcoming", "to be", "following", "focus on")


def _contains_any(text: str, needles: Tuple[str, ...]) -> bool:
    t = (text or "").lower()
    return any(n in t for n in needles)


def _infer_stage(text: str) -> str:
    t = (text or "").lower()
    if _contains_any(t, _PROGRESS_DONE):
        return "done"
    if _contains_any(t, _PROGRESS_INPROG):
        return "in_progress"
    if _contains_any(t, _PROGRESS_NEXT):
        return "next"
    return "unknown"


def _infer_theme(text: str) -> str:
    t = (text or "").lower()
    if "workshop" in t or "stakeholder" in t or "engagement" in t:
        return "stakeholder engagement"
    if "use case" in t or "catalogue" in t or "catalog" in t:
        return "use case development"
    if "data request" in t or "kpi" in t or "volume" in t or "forecast" in t:
        return "data and analytics"
    if "process map" in t or "process" in t or "tom" in t or "operating model" in t:
        return "operating model design"
    if "audit" in t or "internal audit" in t or "control" in t or "gap" in t:
        return "audit and controls"
    if "simulation" in t or "alert" in t or "response" in t:
        return "operational readiness"
    if "assessment" in t or "technology" in t or "vendor" in t or "platform" in t:
        return "technology assessment"
    if "framework" in t or "roadmap" in t:
        return "strategic planning"
    return "core delivery activities"


def _narrative_from_points(points: List[str], subject: str, period_start, period_end) -> str:
    pts = _dedup_preserve([p for p in points if isinstance(p, str) and p.strip()], limit=40)
    if not pts:
        return "No sufficiently detailed delivery evidence was captured in the selected period."

    buckets: Dict[str, Dict[str, List[str]]] = {"done": {}, "in_progress": {}, "next": {}, "unknown": {}}
    for p in pts:
        stage = _infer_stage(p)
        theme = _infer_theme(p)
        buckets[stage].setdefault(theme, []).append(p)

    def pick(bucket: str, themes_cap: int = 3, per_theme: int = 2) -> List[str]:
        themes = list(buckets[bucket].keys())
        themes.sort(key=lambda th: len(buckets[bucket][th]), reverse=True)
        out: List[str] = []
        for th in themes[:themes_cap]:
            out.extend(buckets[bucket][th][:per_theme])
        return out

    done = pick("done", themes_cap=3, per_theme=2)
    inprog = pick("in_progress", themes_cap=3, per_theme=3)
    nxt = pick("next", themes_cap=2, per_theme=2)
    unknown = pick("unknown", themes_cap=1, per_theme=2)

    opening_themes = []
    for p in inprog[:4]:
        opening_themes.append(_infer_theme(p))
    opening_themes = _dedup_preserve(opening_themes, limit=3)

    opening = (
        f"{subject} is progressing well, with discovery activities underway across "
        f"{_sent_join(opening_themes) if opening_themes else 'key workstreams'}. "
        f"Clear objectives and delivery milestones have been established, and early engagement "
        f"with relevant stakeholders has helped identify priorities and pain points."
    )

    all_items = []
    for item in done[:5]:
        all_items.append(f"* {item.strip().rstrip('.')}.")
    for item in inprog[:5]:
        all_items.append(f"* {item.strip().rstrip('.')}.")
    if len(all_items) < 3 and unknown:
        for item in unknown[:3]:
            all_items.append(f"* {item.strip().rstrip('.')}.")
    paragraphs = [opening]
    if all_items:
        paragraphs.append("\n".join(all_items))
    if nxt:
        next_items = [item.strip().rstrip(".") for item in nxt[:4]]
        lookahead = "The upcoming period will focus on " + _sent_join(next_items) + "."
        paragraphs.append(lookahead)

    return "\n\n".join(paragraphs)


# ============================================================
# DELIVERY EVIDENCE FROM CLOSED/COMPLETED ACTIONS + CLOSED/RESOLVED RAIDs
# ============================================================

def _action_completed_in_period(a: Dict[str, Any], start: dt.date, end: dt.date) -> bool:
    if not _is_closed_status(a.get("status")):
        return False
    d = (
        _parse_date(a.get("updated_at"))
        or _parse_date(a.get("completed_at"))
        or _parse_date(a.get("closed_at"))
        or _parse_date(a.get("created_at"))
    )
    return _in_range(d, start, end)


def _raid_closed_in_period(r: Dict[str, Any], start: dt.date, end: dt.date) -> bool:
    if not _is_closed_status(r.get("status")):
        return False
    d = (
        _parse_date(r.get("updated_at"))
        or _parse_date(r.get("closed_at"))
        or _parse_date(r.get("created_at"))
    )
    return _in_range(d, start, end)


def _extract_delivery_from_closed_actions(actions: List[Dict[str, Any]], start: dt.date, end: dt.date) -> List[str]:
    pts: List[str] = []
    for a in actions or []:
        if not _action_completed_in_period(a, start, end):
            continue
        title = (a.get("title") or a.get("action") or "").strip()
        if not title:
            continue
        title = _strip_owner_tokens(title).rstrip(".")
        pts.append(f"{title} – completed")
    return pts


def _extract_delivery_from_closed_raids(raids: List[Dict[str, Any]], start: dt.date, end: dt.date) -> List[str]:
    pts: List[str] = []
    for r in raids or []:
        if not _raid_closed_in_period(r, start, end):
            continue

        raid_type = (r.get("raid_type") or r.get("type") or "RAID").strip()
        title = (r.get("title") or r.get("risk") or r.get("issue") or "").strip()
        if not title:
            continue

        outcome = _pick_first_nonempty(
            r,
            ["resolution", "mitigation", "response", "mitigation_plan", "next_steps", "actions", "details", "description"]
        )

        if outcome:
            pts.append(f"{raid_type}: {title} – {outcome}")
        else:
            pts.append(f"{raid_type}: {title} – closed")
    return pts


# ============================================================
# AGENTS
# ============================================================

class DeliverySummaryAgent(SummaryAgent):
    name = "DeliverySummaryAgent"

    def run(self, brief: GovBrief) -> str:
        points: List[str] = []

        # 1) NFR evidence (weekly + daily should be merged into brief.weekly_nfr by the dashboard)
        for nfr in (brief.weekly_nfr or [])[:12]:
            points.extend(_extract_nfr_delivery_points(nfr))

        # 2) Closed/completed actions in the reporting period = delivery evidence
        points.extend(_extract_delivery_from_closed_actions(brief.actions or [], brief.period_start, brief.period_end))

        # 3) Closed/resolved raids in the reporting period = delivery evidence
        points.extend(_extract_delivery_from_closed_raids(brief.raids or [], brief.period_start, brief.period_end))

        # 4) Fallback to tasks (titles only)
        if len(points) < 5 and brief.tasks:
            points.extend(_top_tasks_summary(brief.tasks, limit=12))

        points = _dedup_preserve([p for p in points if isinstance(p, str) and p.strip()], limit=60)

        if not points:
            return "No delivery updates were captured in the selected period."

        # Bucket by inferred stage
        buckets: Dict[str, List[str]] = {"in_progress": [], "done": [], "next": [], "unknown": []}
        for p in points:
            buckets[_infer_stage(p)].append(p.strip().rstrip("."))

        # ----------------------------
        # Focus for upcoming period:
        # - NFR points inferred as "next"
        # - plus open actions due in the next ~21 days after period end
        # ----------------------------
        pe = brief.period_end
        lookahead_end = pe + dt.timedelta(days=21)

        upcoming_from_actions: List[str] = []
        for a in (brief.actions or [])[:50]:
            if not _is_open_status(a.get("status")):
                continue
            d = _due_date(a)
            if d and pe < d <= lookahead_end:
                t = (a.get("title") or a.get("action") or "").strip()
                if t:
                    upcoming_from_actions.append(_strip_owner_tokens(t).rstrip("."))

        upcoming_from_actions = _dedup_preserve(upcoming_from_actions, limit=8)

        focus_items = _dedup_preserve(buckets["next"] + upcoming_from_actions, limit=8)

        # ----------------------------
        # Progress made so far:
        # - in_progress first, then done, then unknown
        # ----------------------------
        progress_items = _dedup_preserve(
            buckets["in_progress"] + buckets["done"] + buckets["unknown"],
            limit=8
        )

        # Format sections
        out_lines: List[str] = []

        out_lines.append("**Progress made so far**")
        if progress_items:
            out_lines.extend([f"* {x}." for x in progress_items[:7]])
        else:
            out_lines.append("* Delivery activity is underway; however, no detailed progress updates were captured in the selected period.")

        out_lines.append("")  # spacer line

        out_lines.append("**Focus for the upcoming period**")
        if focus_items:
            out_lines.extend([f"* {x}." for x in focus_items[:7]])
        else:
            out_lines.append("* No specific forward-looking delivery items were captured for the upcoming period.")

        return "\n".join(out_lines)

class ExecSummaryAgent(SummaryAgent):
    name = "ExecSummaryAgent"

    def run(self, brief: GovBrief) -> str:
        subject = brief.project_name or "The programme"

        delivery_points: List[str] = []
        for nfr in (brief.weekly_nfr or [])[:8]:
            delivery_points.extend(_extract_nfr_delivery_points(nfr))

        if len(delivery_points) < 4 and brief.tasks:
            delivery_points.extend(_top_tasks_summary(brief.tasks, limit=10))

        delivery_points = _dedup_preserve([p for p in delivery_points if isinstance(p, str) and p.strip()], limit=35)
        delivery_narr = _narrative_from_points(delivery_points, subject, brief.period_start, brief.period_end) if delivery_points else (
            f"{subject} continues to progress in line with agreed objectives."
        )

        # One key risk sentence
        risks_sorted = sorted(brief.raids or [], key=_score_raid, reverse=True)
        top_risk = None
        for r in risks_sorted:
            if _score_raid(r) >= 10:
                top_risk = r
                break

        risk_sentence = ""
        if top_risk:
            title = (top_risk.get("title") or top_risk.get("risk") or top_risk.get("issue") or "").strip()
            impact = _pick_first_nonempty(top_risk, ["impact", "business_impact", "consequence", "effect", "implication"])
            cause = _pick_first_nonempty(top_risk, ["cause", "root_cause", "description", "details", "summary", "context"])

            if title:
                if impact:
                    risk_sentence = (
                        f"One key risk has been noted relating to {title.lower()}, which may "
                        f"{_compact(impact, max_sentences=1, max_chars=220).rstrip('.')}."
                    )
                elif cause:
                    risk_sentence = (
                        f"One key risk has been noted relating to {title.lower()}, driven by "
                        f"{_compact(cause, max_sentences=1, max_chars=220).rstrip('.')}."
                    )
                else:
                    risk_sentence = f"One key risk has been noted relating to {title.lower()}."

        # Upcoming focus: actions due within 21 days after period end
        pe = brief.period_end
        lookahead_end = pe + dt.timedelta(days=21)

        upcoming_actions: List[str] = []
        for a in (brief.actions or [])[:25]:
            if not _is_open_status(a.get("status")):
                continue
            d = _due_date(a)
            if not d or not (pe < d <= lookahead_end):
                continue
            title = (a.get("title") or a.get("action") or "").strip()
            if title:
                upcoming_actions.append(_strip_owner_tokens(title).rstrip("."))

        upcoming_actions = _dedup_preserve(upcoming_actions, limit=6)

        upcoming_statement = ""
        if upcoming_actions:
            upcoming_statement = f"The upcoming period will focus on {_sent_join(upcoming_actions)}."

        parts = [delivery_narr]
        if risk_sentence:
            parts.append(risk_sentence)
        if upcoming_statement:
            parts.append(upcoming_statement)

        return "\n\n".join(parts)


class RisksIssuesAgent(SummaryAgent):
    name = "RisksIssuesAgent"

    def run(self, brief: GovBrief) -> str:
        if not brief.raids:
            return "No material risk or issue changes were identified this period."

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in (brief.raids or []):
            rr = r or {}
            title = (rr.get("title") or rr.get("risk") or rr.get("issue") or rr.get("name") or "").strip()
            if not title:
                continue
            grouped.setdefault(_raid_group_key(rr), []).append(rr)

        merged: List[Dict[str, Any]] = []
        for _, items in grouped.items():
            items_sorted = sorted(items, key=_record_date, reverse=True)
            base = dict(items_sorted[0])

            best_score = max((_score_raid(x) for x in items_sorted), default=0.0)
            base["revised_score"] = best_score

            statuses_l = [str(x.get("status", "")).strip().lower() for x in items_sorted if x.get("status")]
            if any(s in ("open", "in progress", "active") for s in statuses_l):
                base["status"] = "Open"

            base["cause"] = _best_text(
                base.get("cause"),
                base.get("root_cause"),
                base.get("description"),
                base.get("details"),
                base.get("summary"),
                *[x.get("cause") or x.get("description") or x.get("details") or x.get("summary") for x in items_sorted]
            )

            base["impact"] = _best_text(
                base.get("impact"),
                base.get("business_impact"),
                base.get("consequence"),
                base.get("effect"),
                base.get("implication"),
                *[x.get("impact") or x.get("business_impact") or x.get("consequence") for x in items_sorted]
            )

            base["mitigation"] = _best_text(
                base.get("mitigation"),
                base.get("response"),
                base.get("mitigation_plan"),
                base.get("plan"),
                base.get("next_steps"),
                base.get("actions"),
                base.get("resolution"),
                *[x.get("mitigation") or x.get("response") or x.get("next_steps") or x.get("actions") for x in items_sorted]
            )

            merged.append(base)

        def sort_key(r: Dict[str, Any]) -> Tuple[float, int, dt.date]:
            score = _score_raid(r)
            status = str(r.get("status", "")).lower()
            is_open = 1 if status in ("open", "in progress", "active") else 0
            updated = _record_date(r)
            return (score, is_open, updated)

        top = sorted(merged, key=sort_key, reverse=True)[:6]

        blocks: List[str] = []

        for rr in top:
            raw_type = (rr.get("raid_type") or rr.get("type") or rr.get("raidType") or "Risk").strip()
            tnorm = raw_type.lower()
            if "issue" in tnorm:
                raid_label = "Issue"
            elif "depend" in tnorm:
                raid_label = "Dependency"
            else:
                raid_label = "Risk"

            title = (rr.get("title") or rr.get("risk") or rr.get("issue") or rr.get("name") or "").strip()
            if not title:
                continue

            cause = _pick_first_nonempty(rr, ["cause", "root_cause", "description", "details", "summary", "context"])
            impact = _pick_first_nonempty(rr, ["impact", "business_impact", "consequence", "effect", "implication"])
            mitigation = _pick_first_nonempty(rr, ["mitigation", "response", "mitigation_plan", "plan", "next_steps", "actions", "resolution"])

            cause = _compact(cause, max_sentences=2, max_chars=280)

            if not impact and cause:
                impact = _compact(
                    "This may constrain delivery confidence and reduce the completeness of the assessment and recommendations.",
                    max_sentences=1,
                    max_chars=220,
                )
            if not mitigation and cause:
                mitigation = _compact(
                    "Confirm required inputs with the client, agree decision points and timelines, and treat any follow-on remediation as a separate activity.",
                    max_sentences=1,
                    max_chars=240,
                )

            score = rr.get("revised_score", rr.get("score", None))
            status = (rr.get("status") or "").strip()

            meta_bits = []
            try:
                if score not in (None, "", "nan"):
                    meta_bits.append(
                        f"Score: {float(score):.0f}"
                        if str(score).replace(".", "", 1).isdigit()
                        else f"Score: {score}"
                    )
            except Exception:
                pass
            if status:
                meta_bits.append(f"Status: {status}")

            meta = f" ({', '.join(meta_bits)})" if meta_bits else ""

            lines = [f"**{raid_label}: {title}**{meta}"]
            for ln in [
                _labelled_line("Cause", cause),
                _labelled_line("Impact", impact),
                _labelled_line("Mitigation", mitigation),
            ]:
                if ln:
                    lines.append(ln)

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks) if blocks else "No significant risks requiring escalation."


class ActionsSummaryAgent(SummaryAgent):
    name = "ActionsSummaryAgent"

    def run(self, brief: GovBrief) -> str:
        actions = [a for a in (brief.actions or []) if _is_open_status(a.get("status"))]

        if len(actions) < 6:
            for nfr in (brief.weekly_nfr or [])[:8]:
                for line in _extract_nfr_next_steps(nfr):
                    actions.append({"title": line, "status": "open"})

        if not actions:
            return "No open actions to report in the selected period."

        action_items = []
        for a in actions[:10]:
            title = (a.get("title") or a.get("action") or "").strip()
            if not title:
                continue

            action_text = _strip_owner_tokens(title).rstrip(".")

            owner_raw = (a.get("owner") or a.get("assigned_to") or a.get("assignee") or "").strip()
            m = re.search(r"\bOwner\s*:\s*([^–\(\)]+)\b", title, flags=re.IGNORECASE)
            if not owner_raw and m:
                owner_raw = (m.group(1) or "").strip()

            initials = _owner_initials(owner_raw)
            if initials:
                action_text += f" (Owner: {initials})"

            action_items.append(f"* {action_text}.")

        return "\n".join(action_items) if action_items else "Actions are being managed as planned."


# ============================================================
# BACKWARDS-COMPAT FUNCTIONS
# ============================================================

def build_exec_summary(
        client: str,
        period_start,
        period_end,
        nfr_snippets: List[Any],
        raid_snippets: List[Any],
        action_snippets: List[Any],
) -> str:
    brief = GovBrief(
        client_name=client,
        project_name=None,
        period_start=period_start,
        period_end=period_end,
        weekly_nfr=nfr_snippets or [],
        raids=raid_snippets or [],
        actions=action_snippets or [],
        tasks=[],
        kpis={},
    )
    return ExecSummaryAgent().run(brief)


def build_delivery_summary(nfr_snippets: List[Any]) -> str:
    brief = GovBrief(
        client_name="",
        project_name=None,
        period_start=dt.date.today(),
        period_end=dt.date.today(),
        weekly_nfr=nfr_snippets or [],
        raids=[],
        actions=[],
        tasks=[],
        kpis={},
    )
    return DeliverySummaryAgent().run(brief)


def build_risks_issues_summary(raid_snippets: List[Any]) -> str:
    brief = GovBrief(
        client_name="",
        project_name=None,
        period_start=dt.date.today(),
        period_end=dt.date.today(),
        weekly_nfr=[],
        raids=raid_snippets or [],
        actions=[],
        tasks=[],
        kpis={},
    )
    return RisksIssuesAgent().run(brief)


def build_actions_summary(action_snippets: List[Any]) -> str:
    brief = GovBrief(
        client_name="",
        project_name=None,
        period_start=dt.date.today(),
        period_end=dt.date.today(),
        weekly_nfr=[],
        raids=[],
        actions=action_snippets or [],
        tasks=[],
        kpis={},
    )
    return ActionsSummaryAgent().run(brief)
