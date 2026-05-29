# modules/nfr/nfr_agent_T2.py
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


@dataclass
class AgentOutput:
    structured_data: Dict[str, Any]
    derived_overrides: Dict[str, Any]
    flags: List[str]
    cleaned_text: Optional[str] = None


def _nfr_json_schema() -> Dict[str, Any]:
    """
    JSON Schema for Structured Outputs. Keep this aligned with what your generator expects.
    Structured Outputs with strict:true will constrain model output to this schema.
    """
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


# =============================
# Deterministic post-processing
# (kept aligned with T1 fixes)
# =============================
_INTERNAL_INITIALS = {"OG", "DM", "HT", "MDO", "CB", "TJ", "MH", "NC", "AW", "TN"}
_EXTERNAL_INITIALS = {"SW", "CH", "AH"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _try_parse_date(date_str: str) -> Optional[dt.date]:
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
    if d.weekday() <= 3:  # Mon-Thu
        return d + dt.timedelta(days=1)
    if d.weekday() == 4:  # Fri
        return d + dt.timedelta(days=3)
    if d.weekday() == 5:  # Sat
        return d + dt.timedelta(days=2)
    return d + dt.timedelta(days=1)  # Sun -> Mon


def _friday_of_week(d: dt.date) -> dt.date:
    return d + dt.timedelta(days=(4 - d.weekday()))


def _extract_emails(text: str) -> List[str]:
    return list({m.group(0).lower() for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")})


def _extract_attendee_block_names(text: str) -> List[str]:
    t = text or ""
    names: List[str] = []
    for m in re.finditer(r"(?im)^\s*(attendees|participants|present|in attendance)\s*[:\-]\s*(.+)$", t):
        chunk = m.group(2)
        for part in re.split(r"[;,]|(?:\s{2,})|\n", chunk):
            part = _norm(part)
            if part and part.lower() not in {"all", "tbc", "n/a"}:
                names.append(part)
    return names


def _extract_speaker_labels(text: str) -> List[str]:
    t = text or ""
    labels: List[str] = []
    for m in re.finditer(r"(?m)^\s*([A-Za-z][A-Za-z .'-]{0,40}?)\s*:\s+", t):
        label = _norm(m.group(1))
        if label.lower() in {"meeting", "notes", "actions", "agenda"}:
            continue
        labels.append(label)
    # preserve order while deduping
    return list(dict.fromkeys(labels))


def _initials_from_name(name: str) -> str:
    name = _norm(name)
    if re.fullmatch(r"[A-Za-z]{2,4}", name.replace(" ", "")):
        return name.replace(" ", "").upper()
    parts = [p for p in re.split(r"\s+", re.sub(r"[()]", "", name)) if p]
    if not parts:
        return "TBC"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _titlecase_name(name: str) -> str:
    def tc(token: str) -> str:
        if not token:
            return token
        return token[0].upper() + token[1:].lower()

    parts = re.split(r"(\s+)", _norm(name))
    return "".join(tc(p) if p.strip() else p for p in parts)


def _build_participant_directory(client_config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
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
    r = _norm(raw)
    if not r:
        return ("", "", "internal")

    # "Full Name - (XX)"
    m = re.match(r"^(.*?)\s*-\s*\(([^)]+)\)\s*$", r)
    if m:
        full = _titlecase_name(m.group(1))
        ini = _norm(m.group(2)).upper()
        bucket = "internal" if ini in _INTERNAL_INITIALS else ("external" if ini in _EXTERNAL_INITIALS else "internal")
        return (full, ini, bucket)

    # email
    if "@" in r and re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r):
        email = r.lower()
        if email in participant_dir:
            v = participant_dir[email]
            full = _titlecase_name(v.get("name") or email)
            ini = (v.get("initials") or _initials_from_name(full)).upper()
            t = (v.get("type") or "").lower()
            bucket = "external" if t == "external" else "internal"
            return (full, ini, bucket)

        domain = email.split("@")[-1]
        bucket = "internal" if any(domain.endswith(d.lower()) for d in internal_domains) else "external"
        full = email
        ini = _initials_from_name(email.split("@")[0])
        return (full, ini, bucket)

    # initials
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
        return (ini, ini, "internal")

    # full name
    full = _titlecase_name(r)
    ini = _initials_from_name(full)

    # directory match by exact name
    for v in participant_dir.values():
        if not isinstance(v, dict):
            continue
        if _norm(v.get("name", "")).lower() == full.lower():
            ini = (v.get("initials") or ini).upper()
            t = (v.get("type") or "").lower()
            bucket = "external" if t == "external" else "internal"
            return (full, ini, bucket)

    return (full, ini, "internal")


def _format_attendee(full: str, ini: str) -> str:
    full = _norm(full) or "Unknown"
    ini = _norm(ini).upper() or "TBC"
    return f"{full} - ({ini})"


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
    attendees_table = structured.get("attendees_table") or {}
    internal = attendees_table.get("internal") or []
    external = attendees_table.get("external") or []
    produced_any = bool(internal or external)

    participant_dir = _build_participant_directory(client_config)
    internal_domains = client_config.get("internal_domains") or ["plenitudeconsulting.com"]
    if not isinstance(internal_domains, list):
        internal_domains = ["plenitudeconsulting.com"]

    if not produced_any:
        candidates: List[str] = []
        candidates.extend(_extract_attendee_block_names(transcript_text))
        candidates.extend(_extract_speaker_labels(transcript_text))
        candidates.extend(_extract_emails(transcript_text))

        if not candidates:
            flags.append("T2: Attendees not detected; leaving attendees empty for manual confirmation.")
            structured["attendees_table"]["internal"] = []
            structured["attendees_table"]["external"] = []
            structured["overview"]["attendees"]["internal"] = []
            structured["overview"]["attendees"]["external"] = []
            return

        rebuilt_internal: List[str] = []
        rebuilt_external: List[str] = []
        for c in candidates:
            full, ini, bucket = _classify_person(c, participant_dir=participant_dir, internal_domains=internal_domains)
            formatted = _format_attendee(full, ini)
            if bucket == "external":
                rebuilt_external.append(formatted)
            else:
                rebuilt_internal.append(formatted)

        structured["attendees_table"]["internal"] = _dedupe_attendees(rebuilt_internal)
        structured["attendees_table"]["external"] = _dedupe_attendees(rebuilt_external)
        flags.append("T2: Attendees rebuilt via deterministic extraction (speaker labels / attendee blocks / emails).")
    else:
        def fix_list(items: List[str]) -> List[str]:
            out: List[str] = []
            for item in items or []:
                full, ini, _bucket = _classify_person(item, participant_dir=participant_dir, internal_domains=internal_domains)
                out.append(_format_attendee(full, ini))
            return _dedupe_attendees(out)

        structured["attendees_table"]["internal"] = fix_list(internal)
        structured["attendees_table"]["external"] = fix_list(external)

    # mirror to overview.attendees
    structured["overview"]["attendees"]["internal"] = structured["attendees_table"]["internal"]
    structured["overview"]["attendees"]["external"] = structured["attendees_table"]["external"]


def _extract_explicit_date_from_text(s: str) -> Optional[dt.date]:
    text = s or ""
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
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
    existing = _norm(existing_due)

    d0 = _try_parse_date(existing)
    if d0:
        return d0.isoformat()

    d1 = (
        _extract_explicit_date_from_text(existing)
        or _extract_explicit_date_from_text(title)
        or _extract_explicit_date_from_text(detail)
    )
    if d1:
        return d1.isoformat()

    if not meeting_date:
        return "TBC"

    text = f"{title} {detail} {existing}".lower()

    if re.search(r"\b(eow|end of week|end-of-week)\b", text):
        return _friday_of_week(meeting_date).isoformat()

    if re.search(r"\b(next week)\b", text):
        return _friday_of_week(meeting_date + dt.timedelta(days=7)).isoformat()

    if re.search(r"\b(tomorrow|next business day|next working day)\b", text):
        return _next_business_day(meeting_date).isoformat()

    # default strict rule when no date stated
    return _next_business_day(meeting_date).isoformat()


def _normalise_owner_to_initials(owner: str, client_config: Dict[str, Any]) -> str:
    o = _norm(owner)
    if not o or o.lower() in {"tbc", "unassigned", "unknown"}:
        return "Unassigned"

    participant_dir = _build_participant_directory(client_config)

    if re.fullmatch(r"[A-Za-z]{2,4}", o.replace(" ", "")):
        return o.replace(" ", "").upper()

    emails = _extract_emails(o)
    if emails:
        e = emails[0]
        if e in participant_dir:
            v = participant_dir[e]
            ini = (v.get("initials") or "").strip().upper()
            return ini or _initials_from_name(v.get("name") or e.split("@")[0])
        return _initials_from_name(e.split("@")[0])

    for v in participant_dir.values():
        if not isinstance(v, dict):
            continue
        if _norm(v.get("name", "")).lower() == o.lower():
            return (v.get("initials") or _initials_from_name(o)).upper()

    return _initials_from_name(o)


def _post_process_structured_output(
    structured: Dict[str, Any],
    *,
    transcript_text: str,
    overrides: Dict[str, Any],
    client_config: Dict[str, Any],
    flags: List[str],
) -> Dict[str, Any]:
    structured.setdefault("overview", {})
    structured["overview"].setdefault("attendees", {"internal": [], "external": []})
    structured.setdefault("attendees_table", {"internal": [], "external": []})
    structured.setdefault("new_actions", [])
    structured["overview"].setdefault("actions", [])

    # attendees
    _rebuild_attendees_if_needed(
        structured,
        transcript_text=transcript_text,
        client_config=client_config,
        flags=flags,
    )

    # due dates + owner normalisation
    meeting_date = _try_parse_date(overrides.get("DATE", ""))

    def fix_actions(action_list: List[Dict[str, Any]], list_name: str) -> List[Dict[str, Any]]:
        fixed: List[Dict[str, Any]] = []
        for a in action_list or []:
            title = _norm(a.get("title", "")) or "TBC"
            detail = _norm(a.get("detail", ""))
            owner = _normalise_owner_to_initials(a.get("owner", ""), client_config)
            due = _derive_due_date(
                meeting_date=meeting_date,
                title=title,
                detail=detail,
                existing_due=str(a.get("due_date", "") or ""),
            )
            fixed.append({"title": title, "detail": detail, "owner": owner, "due_date": due})
        if meeting_date:
            flags.append(f"T2: Due dates normalised for {list_name} using meeting date {meeting_date.isoformat()} (strict rules).")
        else:
            flags.append(f"T2: Meeting date not provided; due dates left as-is/TBC for {list_name}.")
        return fixed

    structured["new_actions"] = fix_actions(structured.get("new_actions", []), "new_actions")
    structured["overview"]["actions"] = fix_actions(structured["overview"].get("actions", []), "overview.actions")

    # mirror attendees again (hard requirement)
    structured["overview"]["attendees"]["internal"] = structured["attendees_table"]["internal"]
    structured["overview"]["attendees"]["external"] = structured["attendees_table"]["external"]

    return structured


def analyse_transcript_with_agent_t2(
    text: str,
    overrides: Dict[str, Any],
    client_config: Dict[str, Any],
) -> AgentOutput:
    """
    Tier 2 Agent: detailed, client-ready, slightly less rigid than Tier 1.
    Enforces attendee formatting: "Full Name - (Initials)" and initials-only elsewhere.
    Applies deterministic post-processing to fix attendee capture and due date rules.
    """
    cleaned = (text or "").strip()

    derived: Dict[str, Any] = {}
    flags: List[str] = []

    if not overrides.get("MEETING_NAME"):
        derived["MEETING_NAME"] = client_config.get("meeting_title") or "Project Meeting"
        flags.append("Meeting name missing — defaulted (T2).")

    model = os.getenv("OPENAI_MODEL_T2", "gpt-4o-mini")

    system_instructions = """
You are NFR_T2_Agent for Plenitude Consulting’s ScopeSight Notes for Record (NFR) workflow.

Your task:
Analyse a meeting transcript or Teams AI notes and return a structured Notes for Record (NFR) as JSON ONLY, matching the provided schema exactly.

You must be professional, clear, and detailed. Tier 2 is slightly more relaxed than Tier 1, but still must be high quality and client-ready.

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

========================
T2 LANGUAGE QUALITY (TIGHTENED)
========================
Write in an information-dense, client-ready style.

Avoid vague status language. Do NOT write bullets like:
- “Discussed X”
- “Ongoing review”
unless you add the missing context.

Every discussion bullet must communicate at least ONE of:
- a decision made
- a concrete next step
- a risk / issue / blocker
- a dependency
- a delivery impact

If the transcript only implies a next step (e.g., “we should”, “can you”, “let’s”), convert it into an action item.

Rewrite weak bullets into crisp statements:
❌ “Ongoing review of the fraud alert response scenario.”
✅ “Fraud alert response scenario remains under review; additional validation is required before sign-off can be confirmed.”

Be concise:
- Prefer 1–2 sentences per bullet, but ensure the bullet is complete.
- Avoid filler words and meeting-chat phrasing.
- Use specific nouns and verbs (“confirmed”, “agreed”, “blocked by”, “depends on”, “requires approval”).

========================
NFR STRUCTURE (IN THIS ORDER)
========================

1) overview
- time:
  - Use meeting time if stated, else default "10:00".
- agenda:
  - 3–8 agenda items (short, specific).
- attendees:
  - Must mirror attendees_table exactly.
- discussion_points:
  - 6–12 bullets summarising key outcomes, decisions, risks, and next steps.
  - Must be understandable without the transcript.
- actions:
  - Include actionable items found in the transcript.
  - May overlap with new_actions but must not contradict them.

2) objectives_agenda
- 3–8 bullets describing intended outcomes (not “what we talked about”).
- Use outcome language: “Confirm…”, “Agree…”, “Review…”, “Decide…”.

3) attendees_table
- Must mirror overview.attendees exactly.

4) key_discussion_points
- 4–8 headings (major topics/workstreams).
- Under each heading include 2–6 bullets capturing:
  - decisions and rationale (if present)
  - risks/issues/blockers
  - dependencies
  - next steps

5) new_actions
- This is the definitive action list.
- Each action must include:
  - title: verb-based, specific (e.g., “Confirm X approach”, “Send Y pack”)
  - detail: context + expected outcome
  - owner: initials if stated; else "Unassigned"
  - due_date: apply rules below or "TBC"
- Consolidate duplicates and avoid micro-actions.

========================
DUE DATE RULES
========================
- If a due date is explicitly stated, use it.
- If meeting date is known:
  - Mon–Thu → next business day
  - Fri → following Monday
- If meeting date unknown → "TBC"

========================
ATTENDEE CAPTURE + FORMATTING (T2 – STRICTER)
========================
- Output attendee names as: "Full Name - (Initials)"
- Use initials ONLY throughout the rest of the JSON (discussion points, actions, bullets).

Detect attendees via:
1) Explicit attendee lists
2) Speaker labels
3) Teams notes participant metadata (if present)
4) “joined by…”, “present: …” cues

Do NOT include people only mentioned but not present.

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
        temperature=0.15,
    )

    structured = _post_process_structured_output(
        structured,
        transcript_text=cleaned,
        overrides={**overrides, **derived},
        client_config=client_config or {},
        flags=flags,
    )

    return AgentOutput(
        structured_data=structured,
        derived_overrides=derived,
        flags=flags,
        cleaned_text=cleaned,
    )
