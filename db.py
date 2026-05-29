# ============================================================
# db.py — ScopeSight 1.0
# Central database access layer (Supabase PostgreSQL)
# ============================================================
from __future__ import annotations
import streamlit as st
import pandas as pd
import sqlalchemy as sa
import bcrypt
import json
import numpy as np
import datetime as dt


# ============================================================
# DATABASE CONNECTION
# ============================================================

engine = sa.create_engine(
    st.secrets["db_url"],
    pool_pre_ping=True,
    pool_recycle=3600,
)

# ============================================================
# PARAM SANITISER  (Fixes np.int64 / np.bool_ issues)
# ============================================================

def _sanitize_params(params: dict | None) -> dict:
    """Convert NumPy → native Python for psycopg2/sqlalchemy."""
    if not params:
        return {}

    clean: dict = {}
    for k, v in params.items():

        # np scalar types
        if isinstance(v, (np.integer, np.floating)):
            clean[k] = v.item()

        # np bool
        elif isinstance(v, np.bool_):
            clean[k] = bool(v)

        # other numpy objects (arrays etc.)
        elif hasattr(v, "item"):
            try:
                clean[k] = v.item()
            except Exception:
                clean[k] = v
        else:
            clean[k] = v

    return clean


# ============================================================
# GENERIC QUERY FUNCTIONS
# ============================================================

def run_query(sql, params=None):
    try:
        if params is None:
            params = {}

        if not isinstance(params, dict):
            raise TypeError("run_query params must be a dict of named parameters")

        with engine.connect() as conn:
            return pd.read_sql(
                sa.text(sql),
                conn,
                params=params,
            )

    except Exception as e:
        st.error(f"❌ Database query failed: {e}")
        return pd.DataFrame()


def run_execute(sql: str, params: dict | tuple | None = None):
    """
    Run INSERT/UPDATE/DELETE with safety + sanitisation.

    IMPORTANT:
    - Recommended: use named params → :name in SQL, pass dict {"name": value}
    - Tuple/positional mode is only safe if the SQL is written for it.

    If the SQL contains a RETURNING clause, this will return the first row
    as a dict OR the single value if only 1 column is returned.
    Otherwise returns None.
    """
    try:
        is_returning = "returning" in sql.lower()

        # Positional mode
        if isinstance(params, tuple):
            with engine.begin() as conn:
                result = conn.execute(sa.text(sql), params)

        # Named parameters mode
        else:
            params = _sanitize_params(params)
            with engine.begin() as conn:
                result = conn.execute(sa.text(sql), params or {})

        if is_returning:
            row = result.mappings().first()
            if row is None:
                raise Exception("INSERT failed — no row returned from RETURNING")

            if len(row) == 1:
                return list(row.values())[0]

            return dict(row)

        return None

    except Exception as e:
        st.error(f"❌ Database update failed: {e}")
        raise


# ============================================================
# USER AUTHENTICATION — public.users (SQLAlchemy)
# ============================================================

def get_user_by_email(email: str):
    email_norm = (email or "").strip().lower()

    df = run_query(
        """
        SELECT
            user_id,
            email,
            full_name,
            role,
            password_hash,
            is_active
        FROM public.users
        WHERE LOWER(email) = :email
        LIMIT 1
        """,
        {"email": email_norm},
    )

    if df is None or df.empty:
        return None

    row = df.iloc[0].to_dict()

    return {
        "user_id": int(row.get("user_id")) if row.get("user_id") is not None else None,
        "email": (row.get("email") or "").strip().lower(),
        "full_name": row.get("full_name"),
        "role": (row.get("role") or "user").strip().lower(),
        "password_hash": row.get("password_hash"),
        "is_active": bool(row.get("is_active")) if row.get("is_active") is not None else True,
    }


def validate_user(email: str, password: str):
    email_norm = (email or "").strip().lower()
    password_raw = password or ""

    record = get_user_by_email(email_norm)
    if not record:
        return None

    if record.get("is_active") is False:
        return None

    stored_hash = record.get("password_hash")
    if not stored_hash or not isinstance(stored_hash, str):
        return None

    stored_hash = stored_hash.strip()

    # bcrypt guard
    if not stored_hash.startswith("$2"):
        return None

    try:
        if bcrypt.checkpw(
            password_raw.encode("utf-8"),
            stored_hash.encode("utf-8"),
        ):
            return record
    except Exception:
        return None

    return None


def create_user(email: str, password: str, role: str = "user"):
    email_norm = (email or "").strip().lower()
    password_raw = password or ""

    hashed = bcrypt.hashpw(
        password_raw.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    run_execute(
        """
        INSERT INTO public.users (email, password_hash, role, is_active)
        VALUES (:email, :password_hash, :role, TRUE)
        """,
        {
            "email": email_norm,
            "password_hash": hashed,
            "role": role,
        },
    )


def get_user_id(email: str):
    email_norm = (email or "").strip().lower()

    df = run_query(
        """
        SELECT user_id
        FROM public.users
        WHERE LOWER(email) = :email
        LIMIT 1
        """,
        {"email": email_norm},
    )

    return int(df.iloc[0]["user_id"]) if not df.empty else None


def reset_user_password(email: str, new_password: str):
    email_norm = (email or "").strip().lower()
    new_password = new_password or ""

    new_hash = bcrypt.hashpw(
        new_password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    run_execute(
        """
        UPDATE public.users
        SET password_hash = :password_hash
        WHERE LOWER(email) = :email
        """,
        {"password_hash": new_hash, "email": email_norm},
    )


# ============================================================
# CLIENTS
# ============================================================

def get_clients():
    return run_query("""
        SELECT id AS client_id, client_name
        FROM client_scaffold
        ORDER BY client_name
    """)


def get_client_id(client_name: str):
    row = run_query("""
        SELECT client_id 
        FROM clients
        WHERE client_name = :name
    """, {"name": client_name})

    if row is None or row.empty:
        raise ValueError(f"Client '{client_name}' not found in clients table.")

    return int(row.iloc[0]["client_id"])


def create_client(client_name: str):
    run_execute(
        """
        INSERT INTO clients (client_name)
        VALUES (:name)
        ON CONFLICT (client_name) DO NOTHING
        """,
        {"name": client_name},
    )

    df = run_query(
        """
        SELECT client_id 
        FROM clients 
        WHERE client_name = :name
        """,
        {"name": client_name},
    )
    return df.iloc[0]["client_id"] if not df.empty else None


# ============================================================
# PROJECTS
# ============================================================

def get_projects_for_client(client_id: int):
    return run_query(
        """
        SELECT 
            project_id,
            project_name,
            project_code,
            description,
            status,
            created_at
        FROM projects
        WHERE client_id = :cid
        ORDER BY project_name
        """,
        {"cid": client_id},
    )


def get_project_id(project_name: str, client_id: int):
    df = run_query(
        """
        SELECT project_id
        FROM projects
        WHERE project_name = :pname
          AND client_id = :cid
        """,
        {"pname": project_name, "cid": client_id},
    )
    return df.iloc[0]["project_id"] if not df.empty else None


def create_project(
    client_id: int,
    project_name: str,
    project_code: str | None = None,
    description: str | None = None,
):
    new_id = run_execute(
        """
        INSERT INTO projects (client_id, project_name, project_code, description)
        VALUES (:cid, :name, :code, :desc)
        RETURNING project_id
        """,
        {
            "cid": client_id,
            "name": project_name,
            "code": project_code,
            "desc": description,
        },
    )
    return int(new_id) if new_id is not None else None


# ============================================================
# USER–CLIENT PERMISSIONS
# ============================================================

def set_user_permission(email: str, client_name: str, level: str):
    email_norm = (email or "").strip().lower()
    user_id = get_user_id(email_norm)
    client_id = get_client_id(client_name)

    if not user_id or not client_id:
        return

    run_execute(
        """
        INSERT INTO public.user_client_permissions (
            user_id,
            user_email,
            client_id,
            role
        )
        VALUES (
            :uid,
            :email,
            :cid,
            :lvl
        )
        ON CONFLICT (user_id, client_id)
        DO UPDATE SET
            role = EXCLUDED.role,
            user_email   = EXCLUDED.user_email
        """,
        {
            "uid": user_id,
            "email": email_norm,
            "cid": client_id,
            "lvl": level,
        },
    )


def get_user_permissions(email: str):
    user_id = get_user_id(email)
    if not user_id:
        return pd.DataFrame()

    return run_query(
        """
        SELECT 
            c.client_name, 
            p.role
        FROM user_client_permissions p
        JOIN clients c ON p.client_id = c.client_id
        WHERE p.user_id = :uid
        ORDER BY c.client_name
        """,
        {"uid": user_id},
    )


# ============================================================
# ACTIONS MANAGER  (UPDATED: triggers RAG snapshot on writes)
# ============================================================

import json



def get_actions(client_id: int):
    return run_query(
        """
        SELECT *
        FROM actions
        WHERE client_id = :cid
        ORDER BY due_date NULLS LAST, action_id
        """,
        {"cid": client_id},
    )


def _trigger_rag_recalc_for_project(project_id: int, user_email: str | None = None):
    """
    Recompute + snapshot project RAG after a health-contributing change.
    Safe to call even if the RAG engine or tables are not fully wired yet.
    """
    try:
        from modules.project_health import compute_and_snapshot
        compute_and_snapshot(
            project_id,
            run_query,
            run_execute,
            computed_by=(user_email or "system"),
            only_if_changed=True,
        )
    except Exception:
        # Intentionally swallow errors here so a RAG failure never blocks core writes.

        pass


def add_action(
    client_id: int,
    project_id: int,
    title: str,
    detail: str,
    comments: str | None,
    owner: str | None,
    status: str,
    priority: str,
    due_date,
    actual_close_date,
    date_raised,
    *,
    user_email: str | None = None,   # <-- NEW
):
    row = run_execute(
        """
        INSERT INTO actions (
            client_id, project_id,
            title, detail, comments,
            owner, status, priority,
            due_date, actual_close_date, date_raised,
            created_at, updated_at
        )
        VALUES (
            :client_id, :project_id,
            :title, :detail, :comments,
            :owner, :status, :priority,
            :due_date, :actual_close_date, :date_raised,
            NOW(), NOW()
        )
        RETURNING action_id
        """,
        {
            "client_id": client_id,
            "project_id": project_id,
            "title": title,
            "detail": detail,
            "comments": comments,
            "owner": owner,
            "status": status,
            "priority": priority,
            "due_date": due_date,
            "actual_close_date": actual_close_date,
            "date_raised": date_raised,
        },
    )

    # NEW: recompute project RAG after write
    _trigger_rag_recalc_for_project(project_id, user_email=user_email)

    return row


def update_action(
    action_id: int,
    title: str | None = None,
    detail: str | None = None,
    comments: str | None = None,
    owner: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date=None,
    actual_close_date=None,
    *,
    user_email: str | None = None,   # <-- NEW
):
    # Get project_id for this action so we can trigger RAG
    proj = run_query(
        "SELECT project_id FROM actions WHERE action_id = :aid LIMIT 1",
        {"aid": action_id},
    )
    project_id = None
    if proj is not None and not proj.empty:
        try:
            project_id = int(proj.iloc[0]["project_id"])
        except Exception:
            project_id = None

    row = run_execute(
        """
        UPDATE actions SET
            title             = COALESCE(:title, title),
            detail            = COALESCE(:detail, detail),
            comments          = COALESCE(:comments, comments),
            owner             = COALESCE(:owner, owner),
            status            = COALESCE(:status, status),
            priority          = COALESCE(:priority, priority),
            due_date          = COALESCE(:due_date, due_date),
            actual_close_date = COALESCE(:actual_close_date, actual_close_date),
            updated_at        = NOW()
        WHERE action_id = :action_id
        """,
        {
            "action_id": action_id,
            "title": title,
            "detail": detail,
            "comments": comments,
            "owner": owner,
            "status": status,
            "priority": priority,
            "due_date": due_date,
            "actual_close_date": actual_close_date,
        },
    )

    # NEW: recompute project RAG after write
    if project_id is not None:
        _trigger_rag_recalc_for_project(project_id, user_email=user_email)

    return row


def get_actions_for_project(project_id: int):
    return run_query(
        """
        SELECT *
        FROM actions
        WHERE project_id = :pid
        ORDER BY due_date NULLS LAST, action_id
        """,
        {"pid": project_id},
    )


# ============================================================
# RAIDS  (UPDATED: triggers RAG snapshot on writes)
# ============================================================

def get_raids_for_project(project_id: int):
    return run_query(
        """
        SELECT *
        FROM raids
        WHERE project_id = :pid
        ORDER BY created_at DESC
        """,
        {"pid": project_id},
    )


def add_raid_entry(record: dict, *, user_email: str | None = None) -> int | None:
    record = dict(record or {})

    # --- load table columns + nullability (helps diagnose NOT NULL)
    meta = run_query("""
        SELECT column_name, is_nullable, data_type
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='raids'
        ORDER BY ordinal_position
    """)
    if meta is None or meta.empty:
        raise RuntimeError("Could not read raids table schema from information_schema")

    table_cols = meta["column_name"].astype(str).tolist()
    table_set = set(table_cols)

    # --- core requirements (spine)
    core_required = ["client_id", "project_id", "raid_type", "type", "title", "status", "modified_by"]
    missing_core = [k for k in core_required if record.get(k) in (None, "", [])]
    if missing_core:
        raise ValueError(f"Missing required core fields: {missing_core}")

    # --- normalize a couple of common types
    # Dates: allow dt.date / dt.datetime; leave as-is, psycopg2 handles them.
    # custom_fields: if dict, serialize to JSON string (safe across drivers)
    if "custom_fields" in record and isinstance(record["custom_fields"], dict):
        record["custom_fields"] = json.dumps(record["custom_fields"])

    # --- only insert keys that exist in table
    insert_record = {k: v for k, v in record.items() if k in table_set}

    # Ensure we still have something to insert besides timestamps
    if not insert_record:
        raise ValueError(
            "Insert record became empty after filtering to raids table columns. "
            f"Record keys: {sorted(record.keys())}, Table cols sample: {table_cols[:25]}"
        )

    include_created = "created_at" in table_set
    include_updated = "updated_at" in table_set

    cols = list(insert_record.keys())
    vals = [f":{c}" for c in cols]

    if include_created:
        cols.append("created_at")
        vals.append("NOW()")
    if include_updated:
        cols.append("updated_at")
        vals.append("NOW()")

    sql = f"INSERT INTO raids ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING raid_id"

    # --- run + catch to show actionable diagnostics
    try:
        row = run_execute(sql, insert_record)
    except Exception as e:
        # Build a *really* useful error message
        not_nullable = meta[meta["is_nullable"] == "NO"]["column_name"].astype(str).tolist()
        nulls_in_not_nullable = [c for c in not_nullable if c in insert_record and insert_record.get(c) in (None, "")]
        raise RuntimeError(
            "RAID INSERT FAILED.\n"
            f"Error: {e}\n\n"
            f"SQL: {sql}\n\n"
            f"Insert keys: {sorted(insert_record.keys())}\n"
            f"Likely NOT NULL violations (present but null): {nulls_in_not_nullable}\n\n"
            f"Note: if a NOT NULL column is missing entirely from insert, it will also fail unless it has a DEFAULT."
        ) from e

    if row is None:
        return None

    # --- keep your RAG recalc
    try:
        pid = int(record.get("project_id")) if record.get("project_id") is not None else None
    except Exception:
        pid = None
    if pid is not None:
        _trigger_rag_recalc_for_project(pid, user_email=user_email or record.get("modified_by"))

    if isinstance(row, dict):
        return int(row["raid_id"])
    return int(row)


# ============================================================
# RAID FILES + AUDIT (unchanged)
# ============================================================

def save_raid_file(raid_id: int, file_name: str, file_bytes: bytes):
    run_execute(
        """
        INSERT INTO raids_files (raid_id, file_name, file_bytes)
        VALUES (:rid, :name, :bytes)
        """,
        {"rid": raid_id, "name": file_name, "bytes": file_bytes},
    )


def log_raid_audit(raid_id, client_id, user_email, action, details):
    run_execute(
        """
        INSERT INTO raids_audit_log (raid_id, client_id, user_email, action, details)
        VALUES (:rid, :cid, :email, :action, :details)
        """,
        {
            "rid": raid_id,
            "cid": client_id,
            "email": user_email,
            "action": action,
            "details": json.dumps(details),
        },
    )


def get_raid_audit(client_id: int):
    return run_query(
        """
        SELECT *
        FROM raids_audit_log
        WHERE client_id = :cid
        ORDER BY timestamp DESC
        """,
        {"cid": client_id},
    )

# ============================================================
# WEEKLY NFR STORAGE
# ============================================================

def insert_weekly_nfr(record: dict) -> int:
    new_id = run_execute(
        """
        INSERT INTO weekly_nfr (
            client_id, project_id, week_commencing, date_range, meeting_title,
            project_client, objectives, attendees_internal, attendees_external,
            discussion_sections, actions, file_name, generated_by, raw_json
        )
        VALUES (
            :client_id, :project_id, :week_commencing, :date_range, :meeting_title,
            :project_client, :objectives, :attendees_internal, :attendees_external,
            :discussion_sections, :actions, :file_name, :generated_by, :raw_json
        )
        RETURNING id;
        """,
        record,
    )

    if new_id is None:
        raise Exception("Weekly NFR insert failed — no ID returned.")

    return int(new_id)


def save_weekly_nfr_file(weekly_nfr_id: int, file_bytes: bytes):
    run_execute(
        """
        INSERT INTO weekly_nfr_files (weekly_nfr_id, file_bytes)
        VALUES (:wid, :bytes)
        """,
        {"wid": weekly_nfr_id, "bytes": file_bytes},
    )


# ============================================================
# CLIENT SETTINGS
# ============================================================

def get_client_setting(client_id: int, key: str):
    df = run_query(
        """
        SELECT setting_value
        FROM client_settings
        WHERE client_id = :cid AND setting_key = :key
        """,
        {"cid": client_id, "key": key},
    )
    return df.iloc[0]["setting_value"] if not df.empty else None


def set_client_setting(client_id: int, key: str, value):
    run_execute(
        """
        INSERT INTO client_settings (client_id, setting_key, setting_value)
        VALUES (:cid, :key, :val)
        ON CONFLICT (client_id, setting_key)
        DO UPDATE SET setting_value = EXCLUDED.setting_value
        """,
        {"cid": client_id, "key": key, "val": value},
    )


# ============================================================
# PROJECT SETTINGS
# ============================================================

def get_project_setting(project_id: int, key: str):
    df = run_query(
        """
        SELECT setting_value
        FROM project_settings
        WHERE project_id = :pid AND setting_key = :key
        """,
        {"pid": project_id, "key": key},
    )
    return df.iloc[0]["setting_value"] if not df.empty else None


def set_project_setting(project_id: int, key: str, value):
    if value is None:
        json_val = None
    else:
        if isinstance(value, (dict, list, int, float, bool)):
            json_val = json.dumps(value)
        elif isinstance(value, str):
            try:
                json.loads(value)
                json_val = value
            except Exception:
                json_val = json.dumps(value)
        else:
            json_val = json.dumps(value)

    run_execute(
        """
        INSERT INTO project_settings (project_id, setting_key, setting_value)
        VALUES (:pid, :key, :val)
        ON CONFLICT (project_id, setting_key)
        DO UPDATE SET setting_value = EXCLUDED.setting_value
        """,
        {"pid": project_id, "key": key, "val": json_val},
    )


# ============================================================
# SYSTEM ACTIVITY LOG (NEW MODEL)
# ============================================================

def log_system_event(
    event_type: str,
    event_data: dict | None = None,
    user_id: int | None = None,
    performed_by: str | None = None,
    client_id: int | None = None,
    project_id: int | None = None,
):
    payload = {
        "event_type": event_type,
        "event_data": json.dumps(event_data or {}),
        "user_id": user_id,
        "performed_by": performed_by,
        "client_id": client_id,
        "project_id": project_id,
    }

    run_execute(
        """
        INSERT INTO system_activity_log (
            event_type, event_data, user_id, performed_by, client_id, project_id
        )
        VALUES (
            :event_type, :event_data, :user_id, :performed_by, :client_id, :project_id
        )
        """,
        payload,
    )


def get_system_activity(limit: int = 500):
    return run_query(
        """
        SELECT 
            sal.log_id AS id,
            COALESCE(u.email, sal.performed_by) AS user,
            sal.event_type AS action,
            sal.event_data AS details,
            sal.client_id,
            sal.project_id,
            sal.timestamp
        FROM system_activity_log sal
        LEFT JOIN users u ON sal.user_id = u.user_id
        ORDER BY sal.timestamp DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )


def get_user_client_permissions(user_id):
    return run_query("""
        SELECT ucp.client_id, c.client_name, ucp.role
        FROM user_client_permissions ucp
        JOIN clients c ON c.client_id = ucp.client_id
        WHERE ucp.user_id = :uid
        ORDER BY c.client_name
    """, {"uid": user_id})


def get_user_project_permissions(user_id):
    return run_query(
        """
        SELECT
            upp.project_id,
            p.project_name,
            p.project_code,
            c.client_name,
            c.client_id
        FROM user_project_permissions upp
        JOIN projects p ON p.project_id = upp.project_id
        JOIN clients c ON c.client_id = p.client_id
        WHERE upp.user_id = :uid
        ORDER BY c.client_name, p.project_name
        """,
        {"uid": user_id},
    )


# ============================================================
# GANTT / WORKSTREAMS / TASKS
# ============================================================

def get_workstreams(project_id: int):
    return run_query(
        """
        SELECT workstream_id, project_id, name, description, sort_order
        FROM workstreams
        WHERE project_id = :pid
        ORDER BY sort_order, name
        """,
        {"pid": project_id},
    )


def add_workstream(project_id: int, name: str, description: str | None = None, sort_order: int = 0):
    return run_execute(
        """
        INSERT INTO workstreams (project_id, name, description, sort_order)
        VALUES (:pid, :name, :desc, :sort)
        RETURNING workstream_id
        """,
        {"pid": project_id, "name": name, "desc": description, "sort": sort_order},
    )


def update_workstream(workstream_id: int, name: str | None, description: str | None, sort_order: int | None):
    ws_df = run_query(
        """
        SELECT project_id, name AS current_name
        FROM workstreams
        WHERE workstream_id = :wid
        """,
        {"wid": workstream_id},
    )
    if ws_df is None or ws_df.empty:
        raise ValueError("Workstream not found.")

    project_id = int(ws_df.iloc[0]["project_id"])
    current_name = (ws_df.iloc[0]["current_name"] or "").strip()

    new_name = (name or "").strip() or current_name

    dup_df = run_query(
        """
        SELECT workstream_id
        FROM workstreams
        WHERE project_id = :pid
          AND LOWER(name) = LOWER(:nm)
          AND workstream_id <> :wid
        LIMIT 1
        """,
        {"pid": project_id, "nm": new_name, "wid": workstream_id},
    )

    if dup_df is not None and not dup_df.empty:
        raise ValueError(f"A workstream called '{new_name}' already exists for this project.")

    run_execute(
        """
        UPDATE workstreams
        SET
            name = COALESCE(:name, name),
            description = COALESCE(:desc, description),
            sort_order = COALESCE(:sort, sort_order)
        WHERE workstream_id = :wid
        """,
        {"wid": workstream_id, "name": new_name, "desc": description, "sort": sort_order},
    )


def delete_workstream(workstream_id: int):
    run_execute(
        """
        DELETE FROM workstreams
        WHERE workstream_id = :wid
        """,
        {"wid": workstream_id},
    )


def get_project_tasks(project_id: int):
    return run_query(
        """
        SELECT
            t.task_id,
            t.project_id,
            t.workstream_id,
            ws.name AS workstream_name,
            t.title,
            t.description,
            t.start_date,
            t.end_date,
            t.status,
            t.percent_complete,
            t.priority
        FROM tasks t
        JOIN workstreams ws ON ws.workstream_id = t.workstream_id
        WHERE t.project_id = :pid
        ORDER BY t.start_date, t.end_date, ws.sort_order, t.title
        """,
        {"pid": project_id},
    )


def add_task(
    project_id: int,
    workstream_id: int,
    title: str,
    description: str | None,
    start_date,
    end_date,
    status: str = "not_started",
    percent_complete: int = 0,
    priority: str = "medium",
    created_by: str | None = None,
):
    return run_execute(
        """
        INSERT INTO tasks (
            project_id, workstream_id,
            title, description,
            start_date, end_date,
            status, percent_complete, priority,
            created_by
        )
        VALUES (
            :pid, :wid,
            :title, :desc,
            :start, :end,
            :status, :pct, :prio,
            :created_by
        )
        RETURNING task_id
        """,
        {
            "pid": project_id,
            "wid": workstream_id,
            "title": title,
            "desc": description,
            "start": start_date,
            "end": end_date,
            "status": status,
            "pct": percent_complete,
            "prio": priority,
            "created_by": created_by,
        },
    )


def update_task(task_id: int, updates: dict):
    payload = dict(updates or {})
    payload["tid"] = task_id

    run_execute(
        """
        UPDATE tasks SET
            title            = COALESCE(:title, title),
            description      = COALESCE(:description, description),
            start_date       = COALESCE(:start_date, start_date),
            end_date         = COALESCE(:end_date, end_date),
            status           = COALESCE(:status, status),
            percent_complete = COALESCE(:percent_complete, percent_complete),
            priority         = COALESCE(:priority, priority),
            updated_by       = COALESCE(:updated_by, updated_by)
        WHERE task_id = :tid
        """,
        payload,
    )


def delete_task(task_id: int):
    run_execute(
        """
        DELETE FROM tasks
        WHERE task_id = :tid
        """,
        {"tid": task_id},
    )


def get_task_assignments(task_id: int):
    return run_query(
        """
        SELECT
            a.assignment_id,
            a.task_id,
            a.resource_id,
            r.full_name,
            a.allocation_pct,
            a.planned_hours,
            a.role_on_task,
            a.notes,
            a.assignment_status
        FROM task_assignments a
        JOIN resource_pool r ON r.resource_id = a.resource_id
        WHERE a.task_id = :tid
        ORDER BY r.full_name
        """,
        {"tid": task_id},
    )


def upsert_task_assignment(
    task_id: int,
    resource_id: int,
    allocation_pct: int = 100,
    planned_hours: float | None = None,
    role_on_task: str | None = None,
    notes: str | None = None,
    assignment_status: str = "proposed",
):
    run_execute(
        """
        INSERT INTO task_assignments (
            task_id, resource_id,
            allocation_pct, planned_hours,
            role_on_task, notes, assignment_status
        )
        VALUES (
            :tid, :rid,
            :pct, :hours,
            :role, :notes, :status
        )
        ON CONFLICT (task_id, resource_id)
        DO UPDATE SET
            allocation_pct     = EXCLUDED.allocation_pct,
            planned_hours      = EXCLUDED.planned_hours,
            role_on_task       = EXCLUDED.role_on_task,
            notes              = EXCLUDED.notes,
            assignment_status  = EXCLUDED.assignment_status,
            updated_at         = NOW()
        """,
        {
            "tid": task_id,
            "rid": resource_id,
            "pct": allocation_pct,
            "hours": planned_hours,
            "role": role_on_task,
            "notes": notes,
            "status": assignment_status,
        },
    )


def delete_task_assignment(assignment_id: int):
    run_execute(
        """
        DELETE FROM task_assignments
        WHERE assignment_id = :aid
        """,
        {"aid": assignment_id},
    )


def get_active_resources():
    return run_query(
        """
        SELECT
            resource_id,
            full_name,
            role,
            department,
            skillset
        FROM public.resource_pool
        WHERE is_active = TRUE
        ORDER BY full_name
        """
    )


def get_resource_id_for_user(user_id: int):
    if not user_id:
        return None

    df = run_query(
        """
        SELECT resource_id
        FROM resource_pool
        WHERE user_id = :uid
          AND is_active = TRUE
        LIMIT 1
        """,
        {"uid": user_id},
    )
    if df is None or df.empty:
        return None

    return int(df.iloc[0]["resource_id"])


def get_tasks_assigned_to_resource(resource_id: int):
    if resource_id is None:
        return pd.DataFrame()

    try:
        df = run_query(
            """
            SELECT
                ta.assignment_id,
                ta.assignment_status,
                ta.allocation_pct,
                ta.planned_hours,
                ta.role_on_task,

                t.task_id,
                t.project_id,
                t.workstream_id,
                t.title,
                t.description,
                t.start_date,
                t.end_date,
                t.status,
                t.percent_complete,
                t.priority,

                ws.name AS workstream_name,
                p.project_name,
                p.project_code,
                cs.client_name
            FROM public.task_assignments ta
            JOIN public.tasks t ON t.task_id = ta.task_id
            JOIN public.workstreams ws ON ws.workstream_id = t.workstream_id
            JOIN public.projects p ON p.project_id = t.project_id
            LEFT JOIN public.client_scaffold cs ON cs.id = p.client_id
            WHERE ta.resource_id = :rid
              AND ta.assignment_status IN ('proposed', 'approved')
            ORDER BY t.start_date, t.end_date, cs.client_name, p.project_name, ws.name, t.title
            """,
            {"rid": int(resource_id)},
        )

        return df if df is not None and not df.empty else pd.DataFrame()

    except Exception as e:
        st.error(f"Error loading tasks for resource {resource_id}: {e}")
        return pd.DataFrame()


# ============================================================
# PIPELINE (unchanged)
# ============================================================

def get_pipeline_items(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    params = {}
    where_sql = ""

    if start and end:
        where_sql = """
        WHERE (
          plot_start IS NOT NULL
          AND plot_start <= :end
          AND plot_end   >= :start
        )
        """
        params["start"] = start
        params["end"] = end

    sql = f"""
        WITH x AS (
            SELECT
                p.*,
                COALESCE(p.est_start_date, p.start_date, p.target_close_date) AS plot_start,
                COALESCE(
                    p.est_end_date,
                    p.end_date,
                    COALESCE(p.est_start_date, p.start_date, p.target_close_date)
                ) AS plot_end
            FROM public.portfolio_pipeline p
        )
        SELECT
            pipeline_id,
            client_id,
            COALESCE(client_name, '') AS client_name,
            item_name,
            service_line,
            stage,
            probability,
            est_value,
            start_date,
            end_date,
            target_close_date,
            proposal_deadline,
            est_start_date,
            est_end_date,
            owner_email,
            status,
            notes,
            created_at,
            updated_at
        FROM x
        {where_sql}
        ORDER BY
            COALESCE(est_start_date, start_date, target_close_date, end_date) NULLS LAST,
            item_name
    """

    df = run_query(sql, params if params else None)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def add_pipeline_item(payload: dict):
    payload = dict(payload or {})

    sql = """
        INSERT INTO public.portfolio_pipeline
        (client_id, client_name, item_name, service_line, stage, probability, est_value,
         start_date, end_date, target_close_date,
         proposal_deadline, est_start_date, est_end_date,
         owner_email, status, notes)
        VALUES
        (:client_id, :client_name, :item_name, :service_line, :stage, :probability, :est_value,
         :start_date, :end_date, :target_close_date,
         :proposal_deadline, :est_start_date, :est_end_date,
         :owner_email, :status, :notes)
    """

    payload.setdefault("proposal_deadline", None)
    payload.setdefault("est_start_date", None)
    payload.setdefault("est_end_date", None)

    run_execute(sql, payload)


def update_pipeline_item(pipeline_id: int, payload: dict):
    payload = dict(payload or {})
    payload["pipeline_id"] = pipeline_id

    payload.setdefault("proposal_deadline", None)
    payload.setdefault("est_start_date", None)
    payload.setdefault("est_end_date", None)

    sql = """
        UPDATE public.portfolio_pipeline
        SET
            client_id = :client_id,
            client_name = :client_name,
            item_name = :item_name,
            service_line = :service_line,
            stage = :stage,
            probability = :probability,
            est_value = :est_value,
            start_date = :start_date,
            end_date = :end_date,
            target_close_date = :target_close_date,
            proposal_deadline = :proposal_deadline,
            est_start_date = :est_start_date,
            est_end_date = :est_end_date,
            owner_email = :owner_email,
            status = :status,
            notes = :notes,
            updated_at = NOW()
        WHERE pipeline_id = :pipeline_id
    """
    run_execute(sql, payload)


def delete_pipeline_item(pipeline_id: int):
    run_execute(
        "DELETE FROM public.portfolio_pipeline WHERE pipeline_id = :id",
        {"id": pipeline_id},
    )


# ============================================================
# NOTIFICATIONS — Preferences + Events + Deliveries (UPDATED)
# ============================================================

def get_user_assigned_projects(user_email: str) -> pd.DataFrame:
    """
    Canonical assigned-projects lookup for notifications.
    Uses user_project_permissions → projects.
    """
    user_id = get_user_id(user_email)
    if not user_id:
        return pd.DataFrame(columns=["project_id", "project_name", "project_code"])

    df = get_user_project_permissions(user_id)
    if df is None or df.empty:
        return pd.DataFrame(columns=["project_id", "project_name", "project_code"])

    out = pd.DataFrame()
    out["project_id"] = df["project_id"].astype(int)
    out["project_name"] = df["project_name"].astype(str)
    out["project_code"] = df.get("project_code", pd.Series([""] * len(df))).fillna("").astype(str)

    return out.sort_values(["project_name"])


def get_notification_prefs(user_email: str) -> pd.DataFrame:
    return run_query(
        """
        SELECT
            user_email,
            project_id,
            event_type,
            channel_in_app,
            channel_email,
            enabled,
            digest_mode,
            updated_at
        FROM public.user_notification_prefs
        WHERE LOWER(user_email) = LOWER(:email)
        ORDER BY project_id NULLS FIRST, event_type
        """,
        {"email": user_email},
    )


def upsert_notification_pref(
    user_email: str,
    project_id,
    event_type: str,
    in_app: bool,
    email: bool,
    enabled: bool,
    digest_mode: str,
):
    run_execute(
        """
        INSERT INTO public.user_notification_prefs
            (user_email, project_id, event_type, channel_in_app, channel_email, enabled, digest_mode, updated_at)
        VALUES
            (:email, :pid, :etype, :in_app, :email_ch, :enabled, :digest, NOW())
        ON CONFLICT (user_email, project_id, event_type)
        DO UPDATE SET
            channel_in_app = EXCLUDED.channel_in_app,
            channel_email  = EXCLUDED.channel_email,
            enabled        = EXCLUDED.enabled,
            digest_mode    = EXCLUDED.digest_mode,
            updated_at     = NOW()
        """,
        {
            "email": (user_email or "").strip().lower(),
            "pid": project_id,          # None -> NULL (global)
            "etype": (event_type or "").strip().lower(),
            "in_app": bool(in_app),
            "email_ch": bool(email),
            "enabled": bool(enabled),
            "digest": str(digest_mode or "realtime"),
        },
    )


def clear_notification_prefs_for_scope(user_email: str, project_id):
    run_execute(
        """
        DELETE FROM public.user_notification_prefs
        WHERE LOWER(user_email) = LOWER(:email)
          AND (
                (:pid IS NULL AND project_id IS NULL)
                OR project_id = :pid
              )
        """,
        {"email": (user_email or "").strip().lower(), "pid": project_id},
    )


# ----------------------------
# Events
# ----------------------------

def create_notification_event(
    event_type: str,
    title: str,
    body: str,
    severity: str = "info",
    project_id: int | None = None,
    client_id: int | None = None,
    created_by: str | None = None,
    meta: dict | None = None,
) -> int | None:
    """
    Creates a notification event row and returns event_id.

    Expected table: public.notification_events
      - id (serial/bigserial PK)
      - project_id (int null)
      - client_id (int null)   (optional but supported here)
      - event_type (text)
      - title (text)
      - body (text)
      - severity (text)
      - meta (jsonb)           (optional)
      - created_by (text)      (optional)
      - created_at (timestamp default now)
    """
    payload = {
        "project_id": project_id,
        "client_id": client_id,
        "event_type": (event_type or "").strip().lower(),
        "title": (title or "").strip(),
        "body": (body or "").strip(),
        "severity": (severity or "info").strip().lower(),
        "meta": json.dumps(meta or {}),
        "created_by": (created_by or "").strip().lower() or None,
    }

    try:
        event_id = run_execute(
            """
            INSERT INTO public.notification_events
                (project_id, client_id, event_type, title, body, severity, meta, created_by, created_at)
            VALUES
                (:project_id, :client_id, :event_type, :title, :body, :severity, :meta, :created_by, NOW())
            RETURNING id
            """,
            payload,
        )
        return int(event_id) if event_id is not None else None
    except Exception:
        # error already surfaced by run_execute
        return None


# ----------------------------
# Recipient resolution + delivery
# ----------------------------

def _get_project_user_emails(project_id: int) -> list[str]:
    """
    Returns user emails assigned to a project via user_project_permissions.
    """
    if not project_id:
        return []

    df = run_query(
        """
        SELECT DISTINCT u.email
        FROM public.user_project_permissions upp
        JOIN public.users u ON u.user_id = upp.user_id
        WHERE upp.project_id = :pid
          AND COALESCE(u.is_active, TRUE) = TRUE
          AND u.email IS NOT NULL
        """,
        {"pid": int(project_id)},
    )
    if df is None or df.empty:
        return []
    return [str(x).strip().lower() for x in df["email"].tolist() if str(x).strip()]


def _get_all_user_emails_for_client(client_id: int) -> list[str]:
    """
    Fallback scope: users with client permission (user_client_permissions).
    """
    if not client_id:
        return []

    df = run_query(
        """
        SELECT DISTINCT u.email
        FROM public.user_client_permissions ucp
        JOIN public.users u ON u.user_id = ucp.user_id
        WHERE ucp.client_id = :cid
          AND COALESCE(u.is_active, TRUE) = TRUE
          AND u.email IS NOT NULL
        """,
        {"cid": int(client_id)},
    )
    if df is None or df.empty:
        return []
    return [str(x).strip().lower() for x in df["email"].tolist() if str(x).strip()]


def _load_matching_prefs(event_type: str, project_id: int | None, user_emails: list[str] | None) -> pd.DataFrame:
    """
    Pulls prefs that match either:
      - exact project scope (project_id = :pid)
      - global scope (project_id IS NULL)
    for the event_type, limited to a set of users if provided.
    """
    et = (event_type or "").strip().lower()

    # FIX: previously the WHERE clause used unconditional OR branches that
    # collapsed into "always match global prefs", meaning a user with a
    # disabled global pref for e.g. 'raid.reopened' would be silently
    # skipped even if they had an enabled project-scoped pref for it.
    #
    # The corrected logic:
    #   - If project_id is given: return rows scoped to that project OR global (NULL)
    #   - If project_id is None:  return only global (NULL) rows
    # This ensures fanout's scope_rank override (project beats global) works correctly.

    if user_emails:
        if project_id is not None:
            return run_query(
                """
                SELECT
                    user_email,
                    project_id,
                    event_type,
                    channel_in_app,
                    channel_email,
                    enabled,
                    digest_mode
                FROM public.user_notification_prefs
                WHERE LOWER(event_type) = :etype
                  AND (project_id = :pid OR project_id IS NULL)
                  AND LOWER(user_email) = ANY(:emails)
                """,
                {
                    "etype": et,
                    "pid": project_id,
                    "emails": [e.strip().lower() for e in user_emails],
                },
            )
        else:
            return run_query(
                """
                SELECT
                    user_email,
                    project_id,
                    event_type,
                    channel_in_app,
                    channel_email,
                    enabled,
                    digest_mode
                FROM public.user_notification_prefs
                WHERE LOWER(event_type) = :etype
                  AND project_id IS NULL
                  AND LOWER(user_email) = ANY(:emails)
                """,
                {
                    "etype": et,
                    "emails": [e.strip().lower() for e in user_emails],
                },
            )

    if project_id is not None:
        return run_query(
            """
            SELECT
                user_email,
                project_id,
                event_type,
                channel_in_app,
                channel_email,
                enabled,
                digest_mode
            FROM public.user_notification_prefs
            WHERE LOWER(event_type) = :etype
              AND (project_id = :pid OR project_id IS NULL)
            """,
            {"etype": et, "pid": project_id},
        )
    else:
        return run_query(
            """
            SELECT
                user_email,
                project_id,
                event_type,
                channel_in_app,
                channel_email,
                enabled,
                digest_mode
            FROM public.user_notification_prefs
            WHERE LOWER(event_type) = :etype
              AND project_id IS NULL
            """,
            {"etype": et},
        )


def deliver_notification(
    event_id: int,
    user_email: str,
    channel: str = "in_app",
) -> int | None:
    """
    Create a delivery row for one user+channel. Returns delivery_id (id) if RETURNING works.

    Expected table: public.notification_deliveries
      - id (serial/bigserial PK)
      - event_id (fk)
      - user_email (text)
      - channel (text)  ('in_app'|'email')
      - delivered_at (timestamp default now)
      - read_at (timestamp null)
      - dismissed (bool default false)

    Strongly recommended unique index:
      UNIQUE(event_id, user_email, channel)
    """
    if not event_id or not user_email:
        return None

    ch = (channel or "in_app").strip().lower()
    email_norm = (user_email or "").strip().lower()

    try:
        delivery_id = run_execute(
            """
            INSERT INTO public.notification_deliveries
                (event_id, user_email, channel, delivered_at, dismissed)
            VALUES
                (:eid, :email, :ch, NOW(), FALSE)
            ON CONFLICT (event_id, user_email, channel)
            DO NOTHING
            RETURNING id
            """,
            {"eid": int(event_id), "email": email_norm, "ch": ch},
        )
        return int(delivery_id) if delivery_id is not None else None
    except Exception:
        # If your table doesn't have the ON CONFLICT constraint yet,
        # you'll see the error here (and in Streamlit).
        return None


def fanout_notification_event(
    event_id: int,
    event_type: str,
    project_id: int | None = None,
    client_id: int | None = None,
    explicit_recipients: list[str] | None = None,
) -> dict:
    """
    Computes recipients and creates notification_deliveries based on preferences.

    Rules:
    - If explicit_recipients provided: only those users are considered.
    - Else if project_id: recipients = users assigned to project via user_project_permissions.
    - Else if client_id: recipients = users assigned to client via user_client_permissions.
    - Else: no recipients (safe default).

    Preference matching:
    - exact project scope (project_id = pid) OR global (project_id IS NULL)
    - enabled = true
    - channel flags control which deliveries are created

    Returns a small stats dict you can log.
    """
    if not event_id:
        return {"event_id": event_id, "delivered": 0, "in_app": 0, "email": 0, "skipped": 0}

    # 1) candidate users
    if explicit_recipients:
        candidates = [e.strip().lower() for e in explicit_recipients if (e or "").strip()]
    elif project_id:
        candidates = _get_project_user_emails(int(project_id))
    elif client_id:
        candidates = _get_all_user_emails_for_client(int(client_id))
    else:
        candidates = []

    if not candidates:
        return {"event_id": event_id, "delivered": 0, "in_app": 0, "email": 0, "skipped": 0}

    # 2) prefs for these users (global + project)
    prefs_df = _load_matching_prefs(event_type, project_id, candidates)
    prefs_df = prefs_df if isinstance(prefs_df, pd.DataFrame) else pd.DataFrame()

    # 3) build an effective prefs map:
    #    project-specific overrides global.
    eff = {}
    if not prefs_df.empty:
        prefs_df["user_email"] = prefs_df["user_email"].astype(str).str.strip().str.lower()
        prefs_df["scope_rank"] = prefs_df["project_id"].apply(lambda x: 1 if pd.notna(x) else 0)
        prefs_df = prefs_df.sort_values(["user_email", "scope_rank"], ascending=[True, False])
        for _, r in prefs_df.iterrows():
            ue = r["user_email"]
            if ue not in eff:
                eff[ue] = {
                    "enabled": bool(r.get("enabled", True)),
                    "in_app": bool(r.get("channel_in_app", True)),
                    "email": bool(r.get("channel_email", False)),
                    "digest_mode": (r.get("digest_mode") or "realtime"),
                }

    delivered_total = 0
    delivered_in_app = 0
    delivered_email = 0
    skipped = 0

    # 4) deliver
    for ue in candidates:
        p = eff.get(ue, None)

        # Default behavior if no pref row exists:
        # - in_app ON, email OFF, enabled ON
        enabled = True if p is None else bool(p["enabled"])
        in_app_on = True if p is None else bool(p["in_app"])
        email_on = False if p is None else bool(p["email"])

        if not enabled:
            skipped += 1
            continue

        if in_app_on:
            did = deliver_notification(event_id, ue, "in_app")
            if did is not None:
                delivered_total += 1
                delivered_in_app += 1

        if email_on:
            did = deliver_notification(event_id, ue, "email")
            if did is not None:
                delivered_total += 1
                delivered_email += 1

    return {
        "event_id": int(event_id),
        "delivered": int(delivered_total),
        "in_app": int(delivered_in_app),
        "email": int(delivered_email),
        "skipped": int(skipped),
        "candidate_users": len(candidates),
    }


def notify(
    event_type: str,
    title: str,
    body: str,
    severity: str = "info",
    project_id: int | None = None,
    client_id: int | None = None,
    created_by: str | None = None,
    meta: dict | None = None,
    recipients: list[str] | None = None,
) -> dict:
    """
    One-call helper:
      1) create event
      2) fanout deliveries

    Returns: {"event_id": ..., "delivered": ..., ...}
    """
    eid = create_notification_event(
        event_type=event_type,
        title=title,
        body=body,
        severity=severity,
        project_id=project_id,
        client_id=client_id,
        created_by=created_by,
        meta=meta,
    )
    if not eid:
        return {"event_id": None, "delivered": 0, "in_app": 0, "email": 0, "skipped": 0}

    stats = fanout_notification_event(
        event_id=int(eid),
        event_type=event_type,
        project_id=project_id,
        client_id=client_id,
        explicit_recipients=recipients,
    )
    return stats


# ----------------------------
# In-app inbox helpers (overlay + page)
# ----------------------------

def get_inapp_notifications(user_email: str, limit: int = 6, _tick: int | None = None):
    return run_query(
        """
        SELECT
            d.id AS delivery_id,
            d.event_id,
            d.read_at,
            d.dismissed,
            d.delivered_at,
            e.project_id,
            e.client_id,
            e.event_type,
            e.title,
            e.body,
            e.severity,
            e.created_at
        FROM public.notification_deliveries d
        JOIN public.notification_events e
          ON e.id = d.event_id
        WHERE LOWER(d.user_email) = LOWER(:email)
          AND d.channel = 'in_app'
          AND COALESCE(d.dismissed, FALSE) = FALSE
        ORDER BY COALESCE(e.created_at, d.delivered_at) DESC
        LIMIT :limit
        """,
        {"email": (user_email or "").strip().lower(), "limit": int(limit)},
    )



def get_inapp_unread_count(user_email: str) -> int:
    df = run_query(
        """
        SELECT COUNT(*)::int AS n
        FROM public.notification_deliveries d
        WHERE LOWER(d.user_email) = LOWER(:email)
          AND d.channel = 'in_app'
          AND COALESCE(d.dismissed, FALSE) = FALSE
          AND d.read_at IS NULL
        """,
        {"email": (user_email or "").strip().lower()},
    )
    if df is None or df.empty:
        return 0
    return int(df.iloc[0]["n"])


def mark_notification_read(delivery_id: int, user_email: str):
    run_execute(
        """
        UPDATE public.notification_deliveries
        SET read_at = COALESCE(read_at, NOW())
        WHERE id = :did
          AND LOWER(user_email) = LOWER(:email)
        """,
        {"did": int(delivery_id), "email": (user_email or "").strip().lower()},
    )


def dismiss_notification(delivery_id: int, user_email: str):
    run_execute(
        """
        UPDATE public.notification_deliveries
        SET dismissed = TRUE,
            read_at = COALESCE(read_at, NOW())
        WHERE id = :did
          AND LOWER(user_email) = LOWER(:email)
        """,
        {"did": int(delivery_id), "email": (user_email or "").strip().lower()},
    )


def dismiss_all_notifications(user_email: str):
    run_execute(
        """
        UPDATE public.notification_deliveries
        SET dismissed = TRUE,
            read_at = COALESCE(read_at, NOW())
        WHERE LOWER(user_email) = LOWER(:email)
          AND channel = 'in_app'
          AND COALESCE(dismissed, FALSE) = FALSE
        """,
        {"email": (user_email or "").strip().lower()},
    )
