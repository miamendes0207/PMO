# modules/nfr/nfr_agent_T1.py
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
import os
import json
import logging
import re
import datetime as dt
from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI()  # uses OPENAI_API_KEY env var by default


# -----------------------------
# OUTPUT STRUCT
# -----------------------------
@dataclass
class AgentOutput:
    structured_data: Dict[str, Any]
    derived_overrides: Dict[str, Any]
    flags: List[str]
    cleaned_text: Optional[str] = None


# -----------------------------
# SCHEMA (unchanged)
# -----------------------------
def _nfr_json_schema() -> Dict[str, Any]:
    # Keep identical to T2 to ensure downstream compatibility
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["overview", "objectives_agenda", "attendees_table", "key_discussion_points", "new_actions"],
        "properties": {
            "overview": {
                "type": "object",
                "additionalProperties": False,
                "required": ["time", "agenda", "attendees", "discussion_points", "actions"],
                "properties": {
                    "time": {"type": "string"},
                    "agenda": {"type": "array", "items": {"type": "string"}},
                    "attendees": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["internal", "external"],
                        "properties": {
                            "internal": {"type": "array", "items": {"type": "string"}},
                            "external": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "discussion_points": {"type": "array", "items": {"type": "string"}},
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["title", "detail", "owner", "due_date"],
                            "properties": {
                                "title": {"type": "string"},
                                "detail": {"type": "string"},
                                "owner": {"type": "string"},
                                "due_date": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "objectives_agenda": {"type": "array", "items": {"type": "string"}},
            "attendees_table": {
                "type": "object",
                "additionalProperties": False,
                "required": ["internal", "external"],
                "properties": {
                    "internal": {"type": "array", "items": {"type": "string"}},
                    "external": {"type": "array", "items": {"type": "string"}},
                },
            },
            "key_discussion_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["heading", "bullets"],
                    "properties": {
                        "heading": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "new_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "detail", "owner", "due_date"],
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "owner": {"type": "string"},
                        "due_date": {"type": "string"},
                    },
                },
            },
        },
    }


# -----------------------------
# OPENAI CALL
# -----------------------------
def _call_openai_structured(
    *,
    model: str,
    system_instructions: str,
    user_text: str,
    temperature: float,
    max_retries: int = 2,
) -> Dict[str, Any]:
    schema = _nfr_json_schema()

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "nfr_structured_output",
            "schema": schema,
            "strict": True,
        },
    }

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_text},
                ],
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as e:
            last_err = e
            logger.exception("OpenAI structured call failed (attempt %s/%s)", attempt + 1, max_retries + 1)

    raise RuntimeError(f"OpenAI call failed after retries: {last_err}")


# -----------------------------
# PARTICIPANT + DATE HELPERS
# -----------------------------
_INTERNAL_INITIALS = {"OG", "DM", "HT", "MDO", "CB", "TJ", "MH", "NC", "AW", "TN"}
_EXTERNAL_INITIALS = {"SW", "CH", "AH"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _try_parse_meeting_date(date_str: str) -> Optional[dt.date]:
    """
    Accepts common formats:
      - YYYY-MM-DD
      - DD/MM/YYYY
      - DD-MM-YYYY
      - YYYY/MM/DD
    Returns a date or None.
    """
    ds = _norm(date_str)
    if not ds:
        return None

    fmts = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
    for f in fmts:
        try:
            return dt.datetime.strptime(ds, f).date()
        except Exception:
            pass
    return None


def _next_business_day(d: dt.date) -> dt.date:
    # Mon=0 .. Sun=6
    if d.weekday() <= 3:  # Mon-Thu
        return d + dt.timedelta(days=1)
    if d.weekday() == 4:  # Fri
        return d + dt.timedelta(days=3)
    if d.weekday() == 5:  # Sat
        return d + dt.timedelta(days=2)
    return d + dt.timedelta(days=1)  # Sun -> Mon


def _friday_of_week(d: dt.date) -> dt.date:
    # move forward/back to Friday of the same ISO week
    # weekday Fri=4
    return d + dt.timedelta(days=(4 - d.weekday()))


def _extract_emails(text: str) -> List[str]:
    # basic email extraction
    return list({m.group(0).lower() for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")})


def _extract_attendee_block_names(text: str) -> List[str]:
    """
    Extract names from lines that look like:
      Attendees: A, B, C
      Participants - A; B; C
      Present: ...
    """
    t = text or ""
    names: List[str] = []

    patterns = [
        r"(?im)^\s*(attendees|participants|present|in attendance)\s*[:\-]\s*(.+)$",
    ]
    for p in patterns:
        for m in re.finditer(p, t):
            chunk = m.group(2)
            # split by comma/semicolon/newline
            for part in re.split(r"[;,]|(?:\s{2,})|\n", chunk):
                part = _norm(part)
                if part:
                    names.append(part)

    # filter out obvious non-names (e.g., "all", "tbc")
    cleaned = []
    for n in names:
        if n.lower() in {"all", "tbc", "n/a"}:
            continue
        cleaned.append(n)
    return cleaned


def _extract_speaker_labels(text: str) -> List[str]:
    """
    Extract speaker labels like:
      Mia:
      Oliver G:
      OG:
    """
    t = text or ""
    labels = []
    for m in re.finditer(r"(?m)^\s*([A-Za-z][A-Za-z .'-]{0,40}?)\s*:\s+", t):
        label = _norm(m.group(1))
        # avoid common false positives
        if label.lower() in {"meeting", "notes", "actions", "agenda"}:
            continue
        labels.append(label)
    return list(dict.fromkeys(labels))  # preserve order, dedupe


def _initials_from_name(name: str) -> str:
    name = _norm(name)
    # If already looks like initials (2-4 letters)
    if re.fullmatch(r"[A-Za-z]{2,4}", name.replace(" ", "")):
        return name.replace(" ", "").upper()

    parts = [p for p in re.split(r"\s+", re.sub(r"[()]", "", name)) if p]
    if len(parts) == 1:
        return parts[0][:2].upper()
    # first + last initial; expand to 3 if needed
    ini = (parts[0][0] + parts[-1][0]).upper()
    if len(parts[0]) >= 2 and len(parts[-1]) >= 2:
        # allow 3 letters when last names collide; caller can adjust if needed
        pass
    return ini


def _titlecase_name(name: str) -> str:
    # Keep apostrophes/hyphens reasonably intact
    def tc(token: str) -> str:
        if not token:
            return token
        return token[0].upper() + token[1:].lower()

    parts = re.split(r"(\s+)", _norm(name))
    return "".join(tc(p) if p.strip() else p for p in parts)


def _build_participant_directory(client_config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    Optional but strongly recommended in client_config:

    client_config["participant_directory"] = {
        "OG": {"name": "Oliver Gough", "type": "internal"},
        "SW": {"name": "Sarah Williams", "type": "external"},
        # optionally:
        # "mia.deoliveira@plenitudeconsulting.com": {"name":"Mia de Oliveira","type":"internal","initials":"MDO"}
    }

    Returns normalized lookup map keyed by:
      - initials upper
      - email lower
    """
    directory = client_config.get("participant_directory") or {}
    out: Dict[str, Dict[str, str]] = {}

    if isinstance(directory, dict):
        for k, v in directory.items():
            if not isinstance(v, dict):
                continue
            key = _norm(str(k))
            if not key:
                continue
            out[key.upper()] = v
            out[key.lower()] = v
    return out


def _classify_person(
    raw: str,
    *,
    participant_dir: Dict[str, Dict[str, str]],
    internal_domains: List[str],
) -> Tuple[str, str, str]:
    """
    Returns (full_name, initials, bucket) where bucket is "internal" or "external".
    """
    r = _norm(raw)
    if not r:
        return ("", "", "internal")

    # If it's already "Full Name - (XX)"
    m = re.match(r"^(.*?)\s*-\s*\(([^)]+)\)\s*$", r)
    if m:
        full = _titlecase_name(m.group(1))
        ini = _norm(m.group(2)).upper()
        bucket = "internal" if ini in _INTERNAL_INITIALS else ("external" if ini in _EXTERNAL_INITIALS else "internal")
        return (full, ini, bucket)

    # Email?
    if "@" in r and re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r):
        email = r.lower()
        if email in participant_dir:
            v = participant_dir[email]
            full = _titlecase_name(v.get("name") or email)
            ini = (v.get("initials") or _initials_from_name(full)).upper()
            t = (v.get("type") or "").lower()
            bucket = "external" if t == "external" else "internal"
            return (full, ini, bucket)

        # domain-based classification
        domain = email.split("@")[-1]
        bucket = "internal" if any(domain.endswith(d.lower()) for d in internal_domains) else "external"
        full = email  # no name available
        ini = _initials_from_name(email.split("@")[0])
        return (full, ini, bucket)

    # Initials?
    if re.fullmatch(r"[A-Za-z]{2,4}", r.replace(" ", "")):
        ini = r.replace(" ", "").upper()
        if ini in participant_dir:
            v = participant_dir[ini]
            full = _titlecase_name(v.get("name") or ini)
            t = (v.get("type") or "").lower()
            bucket = "external" if t == "external" else "internal"
            return (full, ini, bucket)

        if ini in _INTERNAL_INITIALS:
            return (ini, ini, "internal")
        if ini in _EXTERNAL_INITIALS:
            return (ini, ini, "external")
        # unknown initials default internal (safer for your org), but configurable later
        return (ini, ini, "internal")

    # Full name
    full = _titlecase_name(r)
    ini = _initials_from_name(full)

    # If directory has a matching name, use its initials/type
    # (loose match)
    for v in participant_dir.values():
        if not isinstance(v, dict):
            continue
        if _norm(v.get("name", "")).lower() == full.lower():
            ini = (v.get("initials") or ini).upper()
            t = (v.get("type") or "").lower()
            bucket = "external" if t == "external" else "internal"
            return (full, ini, bucket)

    # default bucket internal unless config says otherwise
    return (full, ini, "internal")


def _format_attendee(full: str, ini: str) -> str:
    full = _norm(full)
    ini = _norm(ini).upper()
    if not full:
        full = ini or "Unknown"
    return f"{full} - ({ini})" if ini else f"{full} - (TBC)"


def _dedupe_attendees(attendees: List[str]) -> List[str]:
    seen = set()
    out = []
    for a in attendees:
        key = _norm(a).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _rebuild_attendees_if_needed(
    structured: Dict[str, Any],
    *,
    transcript_text: str,
    client_config: Dict[str, Any],
    flags: List[str],
) -> None:
    """
    Ensures attendees_table is populated and correctly mirrored into overview.attendees.
    """
    attendees_table = structured.get("attendees_table") or {}
    internal = attendees_table.get("internal") or []
    external = attendees_table.get("external") or []

    # If model produced something, still normalise formatting and mirror it
    produced_any = bool(internal or external)

    participant_dir = _build_participant_directory(client_config)
    internal_domains = client_config.get("internal_domains") or ["plenitudeconsulting.com"]
    if not isinstance(internal_domains, list):
        internal_domains = ["plenitudeconsulting.com"]

    if not produced_any:
        # Build from transcript heuristics
        candidates: List[str] = []
        candidates.extend(_extract_attendee_block_names(transcript_text))
        candidates.extend(_extract_speaker_labels(transcript_text))
        candidates.extend(_extract_emails(transcript_text))

        if not candidates:
            flags.append("T1: Attendees not detected from transcript; leaving attendees empty for manual confirmation.")
            structured["attendees_table"]["internal"] = []
            structured["attendees_table"]["external"] = []
            structured["overview"]["attendees"]["internal"] = []
            structured["overview"]["attendees"]["external"] = []
            return

        rebuilt_internal: List[str] = []
        rebuilt_external: List[str] = []
        for c in candidates:
            full, ini, bucket = _classify_person(c, participant_dir=participant_dir, internal_domains=internal_domains)
            if not ini:
                ini = "TBC"
            formatted = _format_attendee(full, ini)
            if bucket == "external":
                rebuilt_external.append(formatted)
            else:
                rebuilt_internal.append(formatted)

        rebuilt_internal = _dedupe_attendees(rebuilt_internal)
        rebuilt_external = _dedupe_attendees(rebuilt_external)

        structured["attendees_table"]["internal"] = rebuilt_internal
        structured["attendees_table"]["external"] = rebuilt_external
        flags.append("T1: Attendees rebuilt via deterministic extraction (speaker labels / attendee blocks / emails).")

    else:
        # Normalise model output attendee formatting
        fixed_internal: List[str] = []
        fixed_external: List[str] = []

        def fix_list(items: List[str], default_bucket: str) -> List[str]:
            out: List[str] = []
            for item in items or []:
                full, ini, bucket = _classify_person(item, participant_dir=participant_dir, internal_domains=internal_domains)
                if not ini:
                    ini = "TBC"
                out.append(_format_attendee(full, ini))
            return _dedupe_attendees(out)

        fixed_internal = fix_list(internal, "internal")
        fixed_external = fix_list(external, "external")

        structured["attendees_table"]["internal"] = fixed_internal
        structured["attendees_table"]["external"] = fixed_external

    # Mirror into overview.attendees (hard requirement)
    structured["overview"]["attendees"]["internal"] = structured["attendees_table"]["internal"]
    structured["overview"]["attendees"]["external"] = structured["attendees_table"]["external"]


def _extract_explicit_date_from_text(s: str) -> Optional[dt.date]:
    """
    Pulls explicit dates out of action title/detail (most common formats).
    """
    text = s or ""

    # YYYY-MM-DD
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(y, mo, d)
        except Exception:
            pass

    return None


def _derive_due_date(
    *,
    meeting_date: Optional[dt.date],
    title: str,
    detail: str,
    existing_due: str,
) -> str:
    """
    Applies your strict rules deterministically.
    - keep explicit date if present in existing_due or text
    - else compute only if meeting_date is known
    - else return "TBC"
    """
    existing = _norm(existing_due)

    # keep explicit date if present in existing_due
    d0 = _try_parse_meeting_date(existing)
    if d0:
        return d0.isoformat()

    # explicit date embedded in title/detail
    d1 = _extract_explicit_date_from_text(existing) or _extract_explicit_date_from_text(title) or _extract_explicit_date_from_text(detail)
    if d1:
        return d1.isoformat()

    if not meeting_date:
        return "TBC"

    text = f"{title} {detail} {existing}".lower()

    # relative conversions (only when meeting date known)
    if re.search(r"\b(eow|end of week|end-of-week)\b", text):
        return _friday_of_week(meeting_date).isoformat()

    if re.search(r"\b(next week)\b", text):
        next_week = meeting_date + dt.timedelta(days=7)
        return _friday_of_week(next_week).isoformat()

    if re.search(r"\b(tomorrow|next business day|next working day)\b", text):
        return _next_business_day(meeting_date).isoformat()

    # default strict rule when no date stated: Mon–Thu → next business day; Fri → following Monday
    return _next_business_day(meeting_date).isoformat()


def _normalise_owner_to_initials(owner: str, client_config: Dict[str, Any]) -> str:
    """
    Ensures owner is initials-only across output.
    Tries:
      - participant_directory lookup
      - already-initials patterns
      - derive initials from name
    """
    o = _norm(owner)
    if not o or o.lower() in {"tbc", "unassigned", "unknown"}:
        return "Unassigned"

    participant_dir = _build_participant_directory(client_config)

    # If already short initials
    if re.fullmatch(r"[A-Za-z]{2,4}", o.replace(" ", "")):
        return o.replace(" ", "").upper()

    # If owner contains email
    emails = _extract_emails(o)
    if emails:
        e = emails[0]
        if e in participant_dir:
            v = participant_dir[e]
            ini = (v.get("initials") or "").strip().upper()
            return ini or _initials_from_name(v.get("name") or e.split("@")[0])
        return _initials_from_name(e.split("@")[0])

    # If directory knows this name
    for v in participant_dir.values():
        if not isinstance(v, dict):
            continue
        if _norm(v.get("name", "")).lower() == o.lower():
            ini = (v.get("initials") or _initials_from_name(o)).upper()
            return ini

    return _initials_from_name(o)


def _post_process_structured_output(
    structured: Dict[str, Any],
    *,
    transcript_text: str,
    overrides: Dict[str, Any],
    client_config: Dict[str, Any],
    flags: List[str],
) -> Dict[str, Any]:
    """
    Fixes:
      - attendees capture & internal/external split
      - due date derivation (strict rules)
      - owner initials normalisation
      - mirrors attendees_table -> overview.attendees
    """
    # Ensure required containers exist (defensive)
    structured.setdefault("overview", {})
    structured["overview"].setdefault("attendees", {"internal": [], "external": []})
    structured.setdefault("attendees_table", {"internal": [], "external": []})
    structured.setdefault("new_actions", [])
    structured["overview"].setdefault("actions", [])

    # 1) Attendees
    _rebuild_attendees_if_needed(
        structured,
        transcript_text=transcript_text,
        client_config=client_config,
        flags=flags,
    )

    # 2) Due dates + owner initials on actions (new_actions is definitive; also keep overview.actions aligned)
    meeting_date = _try_parse_meeting_date(overrides.get("DATE", ""))

    def fix_actions(action_list: List[Dict[str, Any]], list_name: str) -> List[Dict[str, Any]]:
        fixed: List[Dict[str, Any]] = []
        for a in action_list or []:
            title = _norm(a.get("title", ""))
            detail = _norm(a.get("detail", ""))
            owner = _normalise_owner_to_initials(a.get("owner", ""), client_config)
            due = _derive_due_date(
                meeting_date=meeting_date,
                title=title,
                detail=detail,
                existing_due=str(a.get("due_date", "") or ""),
            )

            if due == "TBC" and meeting_date:
                # we had enough info to compute but couldn't match anything; default rule already applied,
                # so if it's still TBC, something is off
                pass

            fixed.append(
                {
                    "title": title or "TBC",
                    "detail": detail or "",
                    "owner": owner or "Unassigned",
                    "due_date": due or "TBC",
                }
            )

        if meeting_date:
            flags.append(f"T1: Due dates normalised for {list_name} using meeting date {meeting_date.isoformat()} (strict rules).")
        else:
            flags.append(f"T1: Meeting date not provided; due dates left as-is/TBC for {list_name}.")
        return fixed

    structured["new_actions"] = fix_actions(structured.get("new_actions", []), "new_actions")
    structured["overview"]["actions"] = fix_actions(structured["overview"].get("actions", []), "overview.actions")

    # 3) Ensure attendees mirrored (in case other code modified)
    structured["overview"]["attendees"]["internal"] = structured["attendees_table"]["internal"]
    structured["overview"]["attendees"]["external"] = structured["attendees_table"]["external"]

    return structured


# -----------------------------
# MAIN ENTRY
# -----------------------------
def analyse_transcript_with_agent_t1(
    text: str,
    overrides: Dict[str, Any],
    client_config: Dict[str, Any],
) -> AgentOutput:
    """
    Tier 1 Agent: strictest language + maximum detail + clean, decision-grade outputs.
    Enforces attendee formatting: "Full Name - (Initials)" and initials-only elsewhere.
    Also applies deterministic post-processing to fix attendee capture and due date rules.
    """
    cleaned = (text or "").strip()

    derived: Dict[str, Any] = {}
    flags: List[str] = []

    if not overrides.get("MEETING_NAME"):
        derived["MEETING_NAME"] = client_config.get("meeting_title") or "Project Meeting"
        flags.append("T1: Meeting name missing — defaulted. Confirm required.")

    if len(cleaned) < 50:
        flags.append("T1: Transcript/notes appear very short — output may be incomplete.")

    model = os.getenv("OPENAI_MODEL_T1", "gpt-4o-mini")

    system_instructions = """
You are NFR_T1_Strict_Agent for Plenitude Consulting’s ScopeSight Notes for Record (NFR) workflow.

Your task:
Analyse a meeting transcript or Teams AI notes and return a fully structured, high-precision Notes for Record (NFR) as JSON ONLY, matching the provided schema exactly.

Tier 1 must be:
- strict
- formal
- conservative (no invention)
- maximally detailed while remaining concise and client-ready

========================
NON-NEGOTIABLE OUTPUT RULES
========================
- Output JSON only (no markdown, no commentary).
- Must match the schema exactly. Do not add keys or omit required keys.
- Do not invent facts. If unclear, be conservative.
- If unknown:
  - due_date: "TBC"
  - owner: "Unassigned"
  - lists: []
- Never fabricate attendees, actions, decisions, dates, risks, approvals, or deliverables.

========================
T1 LANGUAGE STANDARD (STRICT + CLEAN)
========================
Tier 1 language must read like a formal project record.

Hard bans (do not use):
- “discussed”, “talked about”, “touched on”, “ongoing”, “reviewed”, “went through”, “covered”
unless followed by explicit outcome detail.

Every bullet must contain explicit information. Each bullet should include at least TWO of:
- confirmed outcome / decision
- rationale (why)
- delivery impact (what changes)
- risk / issue / blocker
- dependency / required input
- next step and responsible party (if known)

Rewrite weak statements into decision-grade statements:
❌ “Ongoing review of the fraud alert response scenario.”
✅ “Fraud alert response scenario remains under review; validation evidence is required before approval can be granted and the approach finalised.”

Be concise:
- Prefer 1–2 sentences, but do not sacrifice completeness.
- Avoid filler words, hedging, and meeting-chat tone.
- Use precise verbs: “confirmed”, “approved”, “rejected”, “blocked by”, “depends on”, “requires”, “signed off”, “escalated”.

========================
NFR STRUCTURE (MAP DIRECTLY TO JSON FIELDS)
========================

1) overview
- time:
  - Use stated meeting time if present.
  - Otherwise default "10:00".
- agenda:
  - 5–10 agenda items (more detailed than T2).
  - Each item should be a concrete topic or decision area.
- attendees:
  - Must mirror attendees_table exactly.
- discussion_points:
  - 10–18 bullets (T1 is more comprehensive).
  - Each bullet must capture a decision, risk, dependency, delivery impact, or explicit next step.
  - Avoid generic progress updates; always specify what changed or what is required.
- actions:
  - Include all actionable items found.
  - May overlap with new_actions but must not contradict them.

2) objectives_agenda
- 5–12 outcome-oriented bullets.
- Must state intended outcomes (e.g., “Confirm X approach”, “Agree Y timeline”, “Approve Z artefact”).

3) attendees_table
- Must mirror overview.attendees exactly.

4) key_discussion_points
- 6–12 headings (workstreams / decision areas).
- Under each heading include 3–10 bullets capturing:
  - decisions and rationale
  - risks/issues/blockers (and their impact)
  - dependencies and who owns them
  - approvals required and status
  - next steps and immediate implications

5) new_actions
- This is the definitive action list.
- Each action must include:
  - title: short, verb-based, specific
  - detail: expected output + acceptance criteria (what “done” means) where possible
  - owner: initials if known; else "Unassigned"
  - due_date: apply rules below or "TBC"
- Consolidate duplicates.
- Include implied actions (e.g., “need to confirm…”, “can you send…”, “we should review…”).
- Do not create micro-actions unless clearly separate deliverables.

========================
DUE DATE RULES (STRICT)
========================
- If a due date is explicitly stated, use it.
- If meeting date is known:
  - Mon–Thu → next business day
  - Fri → following Monday
- If meeting date unknown → "TBC"
- If transcript states “end of week”, “next week”, etc., convert to a specific date ONLY if the meeting date is provided; otherwise use "TBC".

========================
ATTENDEE CAPTURE + FORMATTING (T1 – MAX ACCURACY)
========================
- Output attendee strings as: "Full Name - (Initials)"
- Use initials ONLY throughout the rest of the JSON (discussion points, actions, bullets).

How to detect attendees:
1) Explicit attendee lists in the transcript/notes.
2) Speaker labels / name prefixes.
3) Teams AI notes attendee/participants metadata if present.
4) Phrases like “joined by…”, “present: …”, “attendees: …”.

Do NOT include:
- people only mentioned but not present
- distribution lists or generic email aliases unless clearly attending

Consistency requirement:
- If you list "Full Name - (XX)" in attendees_table, you must ONLY use "XX" elsewhere.

Return JSON only. Follow the schema exactly.
""".strip()

    user_payload = f"""
MEETING CONTEXT (if provided):
- Meeting name: {overrides.get("MEETING_NAME", "")}
- Date: {overrides.get("DATE", "")}
- Time: {overrides.get("TIME", "")}
- Location: {overrides.get("LOCATION", "")}
- Client: {overrides.get("CLIENT_NAME", "")} ({overrides.get("CLIENT_CODE", "")})
- Project: {overrides.get("PROJECT_NAME", "")} ({overrides.get("PROJECT_CODE", "")})

TRANSCRIPT / NOTES:
{cleaned}
""".strip()

    structured = _call_openai_structured(
        model=model,
        system_instructions=system_instructions,
        user_text=user_payload,
        temperature=0.10,
    )

    # Deterministic fixes for attendee capture + due date calculation
    structured = _post_process_structured_output(
        structured,
        transcript_text=cleaned,
        overrides={**overrides, **derived},  # include derived defaults for date logic if you later add them
        client_config=client_config or {},
        flags=flags,
    )

    return AgentOutput(
        structured_data=structured,
        derived_overrides=derived,
        flags=flags,
        cleaned_text=cleaned,
    )
