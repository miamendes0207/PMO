# ================================================
# log_utils.py — ScopeSight Activity Logging Engine
# ================================================

import os
import json
import datetime
from pathlib import Path
import streamlit as st
import numpy as np
import pandas as pd

from modules.db import run_execute  # 🔹 DB logging support

def json_safe(obj):
    """Recursively convert objects into JSON-serialisable types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    return obj

# Path to the log file
LOG_DIR = Path("modules/logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "activity_log.json"


def _load_logs():
    """Load log file safely."""
    if not LOG_FILE.exists():
        return []

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_logs(logs):
    """Save logs back to file."""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4)


def log_event(event_type: str, details: dict | None = None):
    """
    Universal event logger.
    Writes to BOTH the local JSON log AND PostgreSQL system_activity_log.
    """

    # -----------------------------------------------
    # 1) Prepare common fields
    # -----------------------------------------------
    user_email = st.session_state.get("email", "unknown@user")
    role = st.session_state.get("role", "user")

    details = details or {}
    clean_details = json_safe(details)

    timestamp_utc = datetime.datetime.utcnow().isoformat()

    # -----------------------------------------------
    # 2) Write to local JSON file (dev mode)
    # -----------------------------------------------
    logs = _load_logs()
    json_entry = {
        "timestamp": timestamp_utc,
        "user": user_email,
        "role": role,
        "event_type": event_type,
        "details": clean_details,
    }
    logs.append(json_safe(json_entry))
    _save_logs(logs)

    # -----------------------------------------------
    # 3) Write to PostgreSQL (main activity log)
    # -----------------------------------------------
    try:
        run_execute("""
            INSERT INTO system_activity_log (
                user_email,
                event_type,
                entity_type,
                entity_id,
                event_data,
                timestamp
            )
            VALUES (
                :user_email,
                :event_type,
                :entity_type,
                :entity_id,
                CAST(:event_data AS jsonb),
                NOW()
            )
        """, {
            "user_email": user_email,
            "event_type": event_type,

            # Optional context (safe defaults)
            "entity_type": details.get("entity_type"),
            "entity_id": details.get("entity_id"),

            "event_data": json.dumps({
                "event_type": event_type,
                "details": clean_details,
                "user_email": user_email,
                "timestamp_utc": timestamp_utc,
            }),
        })

    except Exception as e:
        # Write DB failures to local JSON log for debugging
        logs = _load_logs()
        logs.append({
            "timestamp": timestamp_utc,
            "event_type": "system_activity_log_db_error",
            "error": str(e),
            "failed_event": event_type,
        })
        _save_logs(logs)


def log_document(
    client_name: str,
    doc_type: str,
    file_name: str,
    generated_by: str,
    source: str,
    status: str | None = None,
    error_message: str | None = None,
    event_type: str | None = None,
):
    """
    Log that a document was generated or failed.
    Allows overriding event_type (e.g., 'generated_weekly_nfr').
    """

    # Default behaviour unless overridden
    if event_type is None:
        event_type = "document_failed" if status else "document_generated"

    payload = {
        "client": client_name,
        "doc_type": doc_type,
        "file_name": file_name,
        "generated_by": generated_by,
        "source": source,
    }

    if status:
        payload["status"] = status

    if error_message:
        payload["error"] = error_message

    log_event(event_type, payload)

# ============================================================
# RAID-SPECIFIC AUDIT LOGGER — JSON + DATABASE
# ============================================================
def log_raid_audit(
    raid_id: int,
    client_id: int,
    project_id: int,
    action: str,
    details: dict,
    modified_by: str
):
    """
    Logs RAID audit actions into:
      1) Local JSON log (activity_log.json)
      2) system_activity_log table in PostgreSQL

    Expected to match usage in 3_RAID_Log_Assistant.py:

        log_raid_audit(
            raid_id=rid,
            client_id=client_id,
            project_id=project_id,
            action="created",
            details={"title": title, "raid_type": raid_type},
            modified_by=user_email
        )
    """

    # --------------------------------------------------------
    # 1) Write to JSON activity_log (for dev/local inspection)
    # --------------------------------------------------------
    logs = _load_logs()

    json_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event_type": "raid_audit",
        "raid_id": raid_id,
        "client_id": client_id,
        "project_id": project_id,
        "action": action,
        "details": details,
        "modified_by": modified_by,
    }

    logs.append(json_safe(json_entry))
    _save_logs(json_safe(logs))

    # --------------------------------------------------------
    # 2) Write to system_activity_log (PostgreSQL)
    # --------------------------------------------------------
    try:
        # Payload for the JSONB event_data column
        event_payload = {
            "raid_id": raid_id,
            "client_id": client_id,
            "project_id": project_id,
            "action": action,
            "details": details,
            "modified_by": modified_by,
            "source": "raid_assistant",
            "ts_utc": datetime.datetime.utcnow().isoformat(),
        }

        run_execute(
            """
            INSERT INTO system_activity_log (
                user_email,
                event_type,
                entity_type,
                entity_id,
                event_data,
                timestamp
            )
            VALUES (
                :user_email,
                :event_type,
                :entity_type,
                :entity_id,
                CAST(:event_data AS jsonb),
                NOW()
            )
            """,
            {
                "user_email": modified_by,
                "event_type": "raid_audit",
                "entity_type": "raid",
                "entity_id": raid_id,
                "event_data": json.dumps(event_payload),
            },
        )

    except Exception as e:
        # Fail gracefully: record DB logging failure into JSON log
        logs = _load_logs()
        logs.append(json_safe({
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": "raid_audit_db_error",
            "error": str(e),
            "raid_id": raid_id,
            "client_id": client_id,
            "project_id": project_id,
            "modified_by": modified_by,
        }))
        _save_logs(json_safe(logs))

        # Optionally show a warning in the UI during dev:
        # st.warning("RAID audit DB logging failed. Check logs for details.")
