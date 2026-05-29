# modules/nfr/nfr_weekly_agent_T1.py
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()  # uses OPENAI_API_KEY env var by default


@dataclass
class WeeklyAgentOutput:
    structured_data: Dict[str, Any]
    flags: List[str]
    cleaned_inputs: Optional[Dict[str, Any]] = None


def _weekly_json_schema() -> Dict[str, Any]:
    """
    JSON Schema for Weekly Structured Outputs.
    Strict schema is critical because the UI + doc builder consume this directly.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["overview", "objectives", "attendees_internal", "attendees_external", "discussion", "actions"],
        "properties": {
            "overview": {
                "type": "object",
                "additionalProperties": False,
                "required": ["week_commencing", "date_range", "meeting_title", "project_client"],
                "properties": {
                    "week_commencing": {"type": "string"},
                    "date_range": {"type": "string"},
                    "meeting_title": {"type": "string"},
                    "project_client": {"type": "string"},
                },
            },
            "objectives": {"type": "string"},
            "attendees_internal": {"type": "array", "items": {"type": "string"}},
            "attendees_external": {"type": "array", "items": {"type": "string"}},
            "discussion": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["subhead", "bullets"],
                    "properties": {
                        "subhead": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["Title", "Detail", "Owner", "Due Date"],
                    "properties": {
                        "Title": {"type": "string"},
                        "Detail": {"type": "string"},
                        "Owner": {"type": "string"},
                        "Due Date": {"type": "string"},
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
    """
    Calls OpenAI with Structured Outputs (JSON Schema) to guarantee shape.
    """
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "weekly_nfr_structured_output",
            "schema": _weekly_json_schema(),
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
            logger.exception("Weekly T1 agent call failed (attempt %s/%s)", attempt + 1, max_retries + 1)

    raise RuntimeError(f"Weekly T1 agent call failed after retries: {last_err}")


# -------------------------------------------------------------------
# Tier 1 Weekly Consolidation Instructions (STRICT + CLEAN + DETAILED)
# -------------------------------------------------------------------
DEFAULT_WEEKLY_T1_INSTRUCTIONS = """
You are NFR_WEEKLY_T1_CONSOLIDATION_AGENT for Plenitude Consulting’s ScopeSight.

Your task:
Combine multiple Daily NFRs (and optionally a Monday transcript/notes) into ONE coherent Weekly Notes for Record.
You must deduplicate, sense-check, and rewrite into a strict, decision-grade weekly record.

========================
NON-NEGOTIABLE OUTPUT RULES
========================
- Output JSON only. No markdown. No commentary. No prose outside JSON.
- The JSON MUST match the provided schema exactly. Do not add keys. Do not omit required keys.
- Do not invent facts. If uncertain, be conservative.
- If unknown:
  - Owner = "Unassigned"
  - Due Date = "TBC"
  - Lists = []
- Use UK English spelling.
- Avoid generic time references (e.g., "today", "tomorrow"). Use explicit dates if provided; otherwise keep wording date-neutral.

========================
T1 QUALITY BAR (STRICT)
========================
Tier 1 must read like a formal weekly client record.

Hard bans unless immediately followed by explicit outcomes and implications:
- “discussed”, “talked about”, “touched on”, “covered”, “reviewed”, “ongoing”, “in progress”

Every discussion bullet must include AT LEAST TWO of:
- decision/outcome
- rationale (why)
- delivery impact (what changes)
- risk/issue/blocker + impact
- dependency + owner/next step

Use precise verbs:
- “confirmed”, “approved”, “rejected”, “blocked by”, “depends on”, “requires”, “agreed”, “deferred”, “escalated”.

Do NOT claim agreement/approval unless explicitly stated.

========================
INPUTS YOU MAY RECEIVE
========================
You may receive:
1) overview metadata (week commencing, date range, meeting title, project/client)
2) Monday transcript/notes (optional)
3) daily NFR structured inputs (optional)
4) extracted actions list (often present)
5) optional attendees provided by the user

Treat user-provided attendees as authoritative.

========================
CONSOLIDATION RULES (STRICT SENSE-CHECK)
========================
1) Deduplicate aggressively
- Merge duplicates across the week:
  - discussion bullets that refer to the same topic
  - action items with the same intent
- Prefer the most complete and explicit wording.
- Do not repeat the same point under multiple sections unless strictly necessary.

2) Conflict handling (critical)
- If two inputs conflict (e.g., “approved” vs “not approved”):
  - do NOT choose a side unless one is clearly later and explicitly confirms the final status
  - rewrite conservatively:
    “Approval status remains unconfirmed; confirmation required before downstream work proceeds.”
- If owner differs:
  - prefer explicit named/initial owner stated alongside the action
  - otherwise set owner = "Unassigned" and include the dependency/assignment gap in Detail.
- If due dates differ:
  - prefer explicit written dates
  - else prefer earliest credible date
  - if unclear → "TBC" and explain in Detail.

3) Weekly-level language
- Convert daily “status chat” into weekly outcomes:
  - what changed, what was decided, what is blocked, what depends on what, what must happen next
- Ensure all bullets are standalone and understandable without the source notes.

========================
ATTENDEE NORMALISATION
========================
- If attendees are provided as "Full Name - (XX)", keep that format in attendee lists.
- In discussion/actions, refer to people by initials only where possible.
- If attendees are names without initials, keep names as-is (do not guess initials unless clearly derivable and non-ambiguous).
- De-duplicate attendees; keep a stable ordering (do not randomise).

========================
STRUCTURE REQUIREMENTS (MATCH SCHEMA)
========================
overview:
- week_commencing, date_range, meeting_title, project_client:
  - Use provided values.
  - Do not invent.

objectives:
- 4–8 sentences, outcome-driven.
- Express the week’s intent, decisions required, and focus areas.
- Avoid “we discussed”; instead state outcomes and planned results.

attendees_internal / attendees_external:
- Unique lists, de-duplicated, stable ordering.
- Prefer user-provided attendees; otherwise infer from inputs.

discussion:
- 6–12 sections (workstreams/decision areas).
- Each section includes 4–10 bullets where content supports it.
- Include explicit:
  - decisions + rationale (if present)
  - risks/issues + delivery impact
  - dependencies + owners
  - approvals required
  - clear next steps

actions:
- 0–25 items.
- Must be the definitive weekly action list.
- Merge duplicates.
- Each action must include:
  - Title: verb-based, specific
  - Detail: expected output + acceptance criteria implied (what “done” means) + dependencies/constraints
  - Owner: initials/name if explicitly stated; else "Unassigned"
  - Due Date: explicit date if given; else "TBC"

Return JSON only. Follow schema exactly.
"""


def consolidate_week_with_agent_t1(
    *,
    overview: Dict[str, str],
    monday_text: str = "",
    daily_structured_inputs: Optional[List[Dict[str, Any]]] = None,
    extracted_actions: Optional[List[Dict[str, str]]] = None,
    provided_attendees_internal: Optional[List[str]] = None,
    provided_attendees_external: Optional[List[str]] = None,
) -> WeeklyAgentOutput:
    """
    Tier 1 Weekly consolidation agent.

    Inputs:
      - overview: required dict with keys:
          week_commencing, date_range, meeting_title, project_client
      - monday_text: optional transcript/notes
      - daily_structured_inputs: optional list of daily NFR structured outputs (agent/generator payloads)
      - extracted_actions: optional list of action dicts from uploaded NFR doc tables
      - provided_attendees_internal/external: optional authoritative attendees
    """

    payload = {
        "overview": overview or {},
        "monday_transcript_or_notes": monday_text or "",
        "provided_attendees_internal": provided_attendees_internal or [],
        "provided_attendees_external": provided_attendees_external or [],
        "daily_nfr_structured_inputs": daily_structured_inputs or [],
        "extracted_actions_from_docs": extracted_actions or [],
    }

    # Allow ENV override for instructions (optional)
    system_instructions = os.getenv("WEEKLY_AGENT_T1_INSTRUCTIONS") or DEFAULT_WEEKLY_T1_INSTRUCTIONS
    model = os.getenv("OPENAI_MODEL_WEEKLY_T1", "gpt-4o-mini")

    structured = _call_openai_structured(
        model=model,
        system_instructions=system_instructions,
        user_text=json.dumps(payload, ensure_ascii=False),
        temperature=0.10,  # stricter/less variance for T1
    )

    flags: List[str] = []
    if not structured.get("discussion"):
        flags.append("Weekly T1 agent produced no discussion sections.")
    if structured.get("actions") is None:
        flags.append("Weekly T1 agent produced no actions list (actions key missing).")

    # Basic sanity: ensure overview fields exist (schema enforces, but keep flags helpful)
    ov = structured.get("overview", {}) or {}
    for k in ("week_commencing", "date_range", "meeting_title", "project_client"):
        if not ov.get(k):
            flags.append(f"Weekly T1: overview.{k} is missing or blank.")

    return WeeklyAgentOutput(
        structured_data=structured,
        flags=flags,
        cleaned_inputs=payload,
    )
