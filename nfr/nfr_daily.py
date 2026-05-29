# ============================================================
# nfr_daily.py — Save Pipeline for DAILY NFRs
# ScopeSight v3.2 — Daily NFR Storage Logic
# ============================================================

import json
from modules.db import run_execute


def _safe_json(value):
    """Always returns a JSON string, never None."""
    if value is None:
        return "[]"
    return json.dumps(value)


def save_daily_nfr(
    client_id: int,
    project_id: int,
    meeting_title: str,
    engine_output: dict,
    generated_by: str,
):
    """
    Saves a DAILY NFR into the `daily_nfr` table.
    engine_output = result.structured_data from the NFR engine.
    """

    sql = """
        INSERT INTO daily_nfr (
            client_id,
            project_id,
            objectives,
            attendees_internal,
            attendees_external,
            discussion_sections,
            actions,
            issues,
            risks,
            generated_by,
            generated_on,
            raw_json
        )
        VALUES (
        :client_id,
        :project_id,
        :objectives,
        :attendees_internal,
        :attendees_external,
        :discussion_sections,
        :actions,
        :issues,
        :risks,
        :generated_by,
        NOW(),
        :raw_json
    )
    RETURNING id;
    """

    # Safely collect DB parameters
    params = {
        "client_id": client_id,
        "project_id": project_id,
        "objectives": engine_output.get("objectives", ""),
        "attendees_internal": _safe_json(engine_output.get("attendees_internal")),
        "attendees_external": _safe_json(engine_output.get("attendees_external")),
        "discussion_sections": _safe_json(engine_output.get("discussion_sections")),
        "actions": _safe_json(engine_output.get("actions")),
        "issues": _safe_json(engine_output.get("issues")),
        "risks": _safe_json(engine_output.get("risks")),
        "generated_by": generated_by,
        "raw_json": json.dumps(engine_output),
    }

    try:
        result = run_execute(sql, params)
        if isinstance(result, int):
            return result
    except Exception as e:
        print("❌ ERROR saving daily NFR:", e)
        print("SQL:", sql)
        print("PARAMS:", params)

    log_event(
        "daily_nfr_created",
        {
            "user_email": generated_by,
            "entity_type": "daily_nfr",
            "entity_id": daily_nfr_id,

            "client": client_name,
            "client_id": client_id,
            "project": project_name,
            "project_id": project_id,
            "date": str(date),
            "file_name": filename
        }
    )

    return None
