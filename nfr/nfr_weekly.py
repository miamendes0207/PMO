# modules/nfr/nfr_weekly.py
import json
from datetime import datetime, date
from typing import Any, Dict, Optional

from modules.db import run_execute
from modules.log_utils import log_event


def _normalise_week_start(week_start) -> date:
    """
    Accept:
      - date
      - datetime
      - "YYYY-MM-DD"
      - "DD/MM/YYYY"
    Return: date (defaults to today if None)
    """
    ws = week_start

    if isinstance(ws, date) and not isinstance(ws, datetime):
        return ws
    if isinstance(ws, datetime):
        return ws.date()

    if isinstance(ws, str) and ws.strip():
        s = ws.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
        # If it’s some other string, fail loudly
        raise ValueError(f"Unrecognised week_start date format: {ws}")

    return date.today()


def _coerce_weekly_engine_output(engine_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise multiple possible payload shapes into ONE canonical weekly structure:

    canonical = {
      "objectives": str,
      "attendees_internal": [str],
      "attendees_external": [str],
      "discussion_sections": [(subhead, [bullets])]  # list of tuples OR list-of-dicts supported
      "actions": [ {Title, Detail, Owner, Due Date} ],
      "overview": {... optional ...}
    }
    """
    eo = engine_output or {}

    # ---- Case A: "new weekly agent output" style ----
    # {
    #   overview: {...},
    #   objectives: "...",
    #   attendees_internal: [...],
    #   attendees_external: [...],
    #   discussion: [{subhead, bullets}, ...],
    #   actions: [{Title, Detail, Owner, Due Date}, ...]
    # }
    if "objectives" in eo or "attendees_internal" in eo or "discussion" in eo:
        discussion_sections = eo.get("discussion", [])
        # Allow both list-of-dicts and list-of-tuples
        if discussion_sections and isinstance(discussion_sections[0], dict):
            discussion_sections = [
                (d.get("subhead", ""), d.get("bullets", []) or [])
                for d in discussion_sections
            ]

        return {
            "overview": eo.get("overview", {}) or {},
            "objectives": eo.get("objectives", "") or "",
            "attendees_internal": eo.get("attendees_internal", []) or [],
            "attendees_external": eo.get("attendees_external", []) or [],
            "discussion_sections": discussion_sections or [],
            "actions": eo.get("actions", []) or [],
        }

    # ---- Case B: "old weekly payload" style ----
    # keys like OBJECTIVES, ATTENDEES_INTERNAL, DISCUSSION_SECTIONS, ACTIONS_LIST
    return {
        "overview": eo.get("OVERVIEW", {}) or {},
        "objectives": eo.get("OBJECTIVES", "") or "",
        "attendees_internal": eo.get("ATTENDEES_INTERNAL", []) or [],
        "attendees_external": eo.get("ATTENDEES_EXTERNAL", []) or [],
        "discussion_sections": eo.get("DISCUSSION_SECTIONS", []) or [],
        "actions": eo.get("ACTIONS_LIST", []) or [],
    }


def save_weekly_nfr(
    client_id: int,
    project_id: int,
    week_start,
    engine_output: Dict[str, Any],
    generated_by: str,
    file_name: str,
    client_name: Optional[str] = None,
    project_name: Optional[str] = None,
) -> int:
    """
    Save a weekly NFR into weekly_nfr table:
      - week_start -> DATE
      - data       -> JSONB

    engine_output can be:
      - old-style weekly dict (OBJECTIVES/ATTENDEES_INTERNAL/...)
      - new weekly agent output (objectives/attendees_internal/discussion/actions)
      - any dict that at least contains those components
    """

    print("🔥 ENTERING save_weekly_nfr()")

    ws = _normalise_week_start(week_start)
    print("📌 week_start normalized:", ws)

    canonical = _coerce_weekly_engine_output(engine_output)

    # Store both canonical (for rendering) + raw (for audit)
    data = {
        # Canonical keys used by weekly UI/doc builders
        "overview": canonical.get("overview", {}) or {},
        "objectives": canonical.get("objectives", "") or "",
        "attendees_internal": canonical.get("attendees_internal", []) or [],
        "attendees_external": canonical.get("attendees_external", []) or [],
        "discussion_sections": canonical.get("discussion_sections", []) or [],
        "actions": canonical.get("actions", []) or [],

        # Metadata
        "file_name": file_name,
        "generated_by": generated_by,

        # Raw snapshot (useful for debugging / future re-renders)
        "raw": engine_output or {},
    }

    print("📌 Final JSON payload (preview):", json.dumps(data, ensure_ascii=False)[:250] + "...")

    sql = """
        INSERT INTO weekly_nfr (
            client_id,
            project_id,
            week_start,
            data,
            created_at
        )
        VALUES (
            :client_id,
            :project_id,
            :week_start,
            CAST(:data AS jsonb),
            NOW()
        )
        RETURNING id
    """

    params = {
        "client_id": client_id,
        "project_id": project_id,
        "week_start": ws,
        "data": json.dumps(data, ensure_ascii=False),
    }

    print("🔥 Running INSERT into weekly_nfr...")
    new_id = run_execute(sql, params)
    print("🎉 WEEKLY NFR SAVED WITH ID:", new_id)

    # -----------------------
    # LOG EVENT (ACTIVITY LOG)
    # -----------------------
    try:
        log_event(
            "weekly_nfr_created",
            {
                "user_email": generated_by,
                "entity_type": "weekly_nfr",
                "entity_id": new_id,
                "client": client_name,
                "client_id": client_id,
                "project": project_name,
                "project_id": project_id,
                "week_start": str(ws),
                "file_name": file_name,
            }
        )
        print("📌 Logged weekly_nfr_created event")
    except Exception as e:
        # Don’t fail the save just because logging failed
        print("⚠️ Failed to log weekly_nfr_created event:", e)

    return int(new_id)
