# modules/nfr/nfr_weekly_agent_T2.py
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
    JSON Schema for Weekly Structured Outputs (T2).
    Keep identical to T1 for downstream compatibility.
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
            logger.exception("Weekly T2 agent call failed (attempt %s/%s)", attempt + 1, max_retries + 1)

    raise RuntimeError(f"Weekly T2 agent call failed after retries: {last_err}")


# -------------------------------------------------------------------
# Tier 2 Weekly Consolidation Instructions (DETAILED, SLIGHTLY RELAXED)
# -------------------------------------------------------------------
DEFAULT_WEEKLY_T2_INSTRUCTIONS = """
You are NFR_WEEKLY_T2_CONSOLIDATION_AGENT for Plenitude Consulting’s ScopeSight.

Your task:
Combine multiple Daily NFRs (and optionally a Monday transcript/notes) into ONE coherent Weekly Notes for Record.
You must deduplicate, sense-check, and standardise wording.
Your output is consumed directly by an application that renders a preview and generates a Word document.

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
- Avoid relative dates like “today/tomorrow” unless the date is explicitly stated.

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
OUTPUT GOAL
========================
Produce a single weekly record that:
- reflects what changed, what was decided, what is blocked, what depends on what, and what needs doing next
- removes duplicates and consolidates similar items
- is readable without referencing daily notes

========================
CONSOLIDATION RULES (SENSE-CHECK)
========================
1) Deduplication
- Merge duplicates across the week:
  - discussion bullets that are the same topic
  - action items with same intent
- Prefer the most complete wording.
- Keep 1 combined bullet rather than multiple partial bullets.

2) Conflict handling (important)
- If two daily notes conflict (e.g., “approved” vs “not approved”):
  - do NOT choose a side unless one is clearly later and explicit
  - rewrite conservatively:
    “Approval status remains unconfirmed; confirmation required.”
- If owner differs across duplicates:
  - prefer explicit named/initial owner
  - otherwise set owner = "Unassigned" and note dependency in Detail.
- If due dates differ:
  - prefer explicit written dates
  - else prefer earliest
  - if unclear → "TBC"

3) Weekly-level wording
- Replace daily “status chat” with weekly outcomes:
  - decision, impact, risk, dependency, next step
- Avoid vague bullets like “Discussed X”.
  Every bullet must contain at least ONE of:
  - decision/outcome
  - risk/issue/blocker + impact
  - dependency
  - next step

========================
ATTENDEE NORMALISATION
========================
- If attendees appear as "Full Name - (XX)", keep that format in attendee lists.
- In discussion/actions, refer to people by initials only (if provided).
- If attendees are names without initials, keep names as-is (do not guess initials unless clearly derivable and non-ambiguous).
- De-duplicate attendees; keep a stable ordering.

========================
STRUCTURE REQUIREMENTS (MATCH SCHEMA)
========================
overview:
- week_commencing, date_range, meeting_title, project_client:
  - Use provided values.

objectives:
- A short paragraph (2–6 sentences) capturing intended outcomes for the week.
- Use outcome language: confirm/agree/approve/resolve/deliver.

attendees_internal / attendees_external:
- Unique lists, de-duplicated, stable ordering.

discussion:
- 4–10 sections.
- Each section has:
  - subhead: a clear workstream/decision area title
  - bullets: 3–8 bullets that are decision-grade
- Bullets should be concise (1–2 sentences) and complete.

actions:
- 0–25 items.
- Each action has Title, Detail, Owner, Due Date.
- Title must be verb-based and specific.
- Detail must include context + expected output.

Return JSON only. Follow schema exactly.
"""


def consolidate_week_with_agent_t2(
    *,
    overview: Dict[str, str],
    monday_text: str = "",
    daily_structured_inputs: Optional[List[Dict[str, Any]]] = None,
    extracted_actions: Optional[List[Dict[str, str]]] = None,
    provided_attendees_internal: Optional[List[str]] = None,
    provided_attendees_external: Optional[List[str]] = None,
) -> WeeklyAgentOutput:
    """
    Tier 2 Weekly consolidation agent.

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
    system_instructions = os.getenv("WEEKLY_AGENT_T2_INSTRUCTIONS") or DEFAULT_WEEKLY_T2_INSTRUCTIONS
    model = os.getenv("OPENAI_MODEL_WEEKLY_T2", "gpt-4o-mini")

    structured = _call_openai_structured(
        model=model,
        system_instructions=system_instructions,
        user_text=json.dumps(payload, ensure_ascii=False),
        temperature=0.15,  # slightly more flexible than T1
    )

    flags: List[str] = []
    if not structured.get("discussion"):
        flags.append("Weekly T2 agent produced no discussion sections.")
    if structured.get("actions") is None:
        flags.append("Weekly T2 agent produced no actions list (actions key missing).")

    ov = structured.get("overview", {}) or {}
    for k in ("week_commencing", "date_range", "meeting_title", "project_client"):
        if not ov.get(k):
            flags.append(f"Weekly T2: overview.{k} is missing or blank.")

    return WeeklyAgentOutput(
        structured_data=structured,
        flags=flags,
        cleaned_inputs=payload,
    )
