# ============================================================
# 11_🪪_Project_Setup_Approval.py — ScopeSight v3.6
# Project Setup & Administration
#
# FIXES vs v3.5:
# - On approval, the projects table settings column is now populated with
#   a full settings block (tier + branding + raids_config).  This is the
#   primary read path used by load_raids_config_for_project() in the
#   RAIDs log, which checks projects.settings first.
# - raids_config is also stored in project_settings table (set_project_setting)
#   for the secondary read path (projects.raids_config column fallback).
# - _coerce_json now correctly merges branding from scaffold settings so
#   the nested raids_config is preserved inside the settings block written
#   to projects.settings.
# ============================================================

import os
import json
from datetime import datetime

import streamlit as st
import bcrypt

from modules.db import run_query, run_execute, set_project_setting
from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.log_utils import log_event
from modules.notifications_utils import send_notification
from modules.ui_hide_nav import hide_streamlit_nav
from modules.project_filesystem import ensure_project_folder, delete_project_folder

# ---------------------------------------------------------
# DEV MODE
# ---------------------------------------------------------
query = st.query_params

if "dev" in query and query.get("dev") == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True

require_login()
hide_streamlit_nav()

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
set_pmo_theme(page_title="🪪 Project Setup & Administration")

st.markdown("""
<style>
header[data-testid="stHeader"] {
    height: 0px !important;
    visibility: hidden !important;
}

.page-title {
    font-size: 2rem;
    font-weight: 800;
    color: #0f172a;
    margin: 0 0 0.5rem 0;
}

.page-subtitle {
    color: #64748b;
    font-size: 1rem;
    margin-bottom: 2rem;
}

.section-header {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #94a3b8;
    margin: 2rem 0 1rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

.info-box {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-left: 4px solid #0ea5e9;
    padding: 1rem 1.25rem;
    border-radius: 10px;
    margin: 1rem 0 2rem 0;
}

.info-box-text {
    color: #334155;
    font-size: 0.9rem;
    line-height: 1.5;
}

.project-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.project-card-header {
    font-size: 1.1rem;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid #f1f5f9;
}

.subsection-header {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #64748b;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #f1f5f9;
}

.detail-row {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}

.detail-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #64748b;
    min-width: 120px;
}

.detail-value {
    font-size: 0.85rem;
    color: #334155;
}

.status-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-pending  { background: #fef3c7; color: #92400e; }
.status-open     { background: #dcfce7; color: #166534; }
.status-closed   { background: #f1f5f9; color: #475569; }

.warning-box {
    background: linear-gradient(135deg, #fef2f2 0%, #ffffff 100%);
    border: 1px solid #fecaca;
    border-left: 4px solid #dc2626;
    padding: 1rem 1.25rem;
    border-radius: 10px;
    margin: 1rem 0;
}

.warning-title {
    font-weight: 700;
    color: #991b1b;
    font-size: 0.95rem;
    margin-bottom: 0.5rem;
}

.warning-text {
    color: #334155;
    font-size: 0.85rem;
    line-height: 1.5;
}

.table-container {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1rem;
    margin: 1rem 0;
}

.access-item {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
}

div.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

div.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
}

.streamlit-expanderHeader {
    font-weight: 600 !important;
    background: #f8fafc !important;
    border-radius: 8px !important;
}

label {
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}
</style>
""", unsafe_allow_html=True)

render_sidebar()

# ---------------------------------------------------------
# ROLE GUARD
# ---------------------------------------------------------
role = st.session_state.get("role", "user")
if role != "admin":
    st.error("🚫 Only administrators can access Project Setup & Administration.")
    pmo_footer()
    st.stop()

# ---------------------------------------------------------
# SERVICE LINE OPTIONS
# ---------------------------------------------------------
SERVICE_LINES = [
    "Fraud",
    "Tech & Data",
    "Advisory & Transformation",
    "Other",
]


def normalise_service_line(choice: str, other_text: str) -> str | None:
    choice = (choice or "").strip()
    other_text = (other_text or "").strip()
    if not choice:
        return None
    if choice.lower() == "other":
        return other_text if other_text else None
    return choice


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def verify_admin_password(pwd: str) -> bool:
    email = st.session_state.get("email")
    row = run_query(
        "SELECT password_hash FROM users WHERE email = :email",
        {"email": email},
    )

    if row is None or row.empty:
        st.error("User not found.")
        return False

    correct_hash = row.iloc[0]["password_hash"].encode()

    if not pwd:
        st.error("Please enter your password.")
        return False

    if not bcrypt.checkpw(pwd.encode(), correct_hash):
        st.error("❌ Incorrect password.")
        return False

    return True


def ensure_admin_for_delete() -> bool:
    if st.session_state.get("role") != "admin":
        st.error("Only administrators can delete projects.")
        return False
    return True


def _coerce_json(value, default):
    """Ensure scaffold fields are safe JSON objects."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def _build_live_settings_block(scaffold_row: dict, service_line_value: str) -> dict:
    """
    Build the full settings JSON that will be written to projects.settings.
    This is what load_raids_config_for_project() reads on the RAIDs log page
    (primary read path: projects.settings -> settings.raids_config).
    """
    base_settings = _coerce_json(scaffold_row.get("settings"), {})
    raids_value   = _coerce_json(scaffold_row.get("raids_config"), {})
    branding      = base_settings.get("branding") or {}
    tier          = base_settings.get("tier") or scaffold_row.get("tier") or "tier_2"

    return {
        "tier": tier,
        "branding": branding,
        "service_line": service_line_value,
        # This is the canonical key the RAIDs log reads:
        "raids_config": raids_value,
    }


def load_pending_projects():
    df = run_query("""
        SELECT 
            p.id AS project_id,
            p.client_id AS scaffold_client_id,
            p.project_name,
            p.project_code,
            p.client_name,
            p.description,
            p.tier,
            p.settings,
            p.project_start_date,
            p.expected_end_date,
            p.project_manager,
            p.access_list,
            p.raids_config,
            p.actions_config,
            p.nfr_config,
            p.submitted_by,
            p.submitted_on,
            p.status
        FROM project_scaffold p
        WHERE p.status IN ('pending', 'awaiting_approval')
        ORDER BY p.submitted_on NULLS LAST
    """)
    return df.to_dict("records") if df is not None and not df.empty else []


def load_live_projects():
    df = run_query("""
        SELECT 
            p.project_id,
            p.project_name,
            p.project_code,
            p.client_id,
            p.status,
            p.service_line,
            cs.client_name,
            cs.client_code
        FROM projects p
        LEFT JOIN client_scaffold cs ON p.client_id = cs.id
        WHERE LOWER(p.status) = 'open'
        ORDER BY cs.client_name, p.project_name
    """)
    return df if df is not None and not df.empty else None


def load_closed_projects():
    df = run_query("""
        SELECT 
            p.project_id,
            p.project_name,
            p.project_code,
            p.client_id,
            p.status,
            p.service_line,
            cs.client_name,
            cs.client_code
        FROM projects p
        LEFT JOIN client_scaffold cs ON p.client_id = cs.id
        WHERE LOWER(p.status) = 'closed'
        ORDER BY cs.client_name, p.project_name
    """)
    return df if df is not None and not df.empty else None


# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_pending, tab_live, tab_closed = st.tabs([
    f"🧱 Pending ({len(load_pending_projects())})",
    "✅ Live Projects",
    "📦 Closed Projects"
])

# =========================================================
# TAB 1 — PENDING PROJECT SETUP
# =========================================================
with tab_pending:
    st.markdown("<div class='section-header'>Pending Project Approvals</div>", unsafe_allow_html=True)

    pending_projects = load_pending_projects()

    if not pending_projects:
        st.info("🎉 No projects awaiting approval.")
    else:
        for row in pending_projects:
            project_id = row["project_id"]
            scaffold_client_id = row.get("scaffold_client_id")
            project_name = row["project_name"]
            project_code = row["project_code"]
            client_name = row["client_name"]

            with st.expander(f"📁 {project_name} — {client_name}", expanded=False):
                st.markdown("<div class='project-card'>", unsafe_allow_html=True)

                st.markdown("<div class='subsection-header'>📋 Project Details</div>", unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div class='detail-row'>
                        <span class='detail-label'>Client:</span>
                        <span class='detail-value'>{client_name}</span>
                    </div>
                    <div class='detail-row'>
                        <span class='detail-label'>Project Name:</span>
                        <span class='detail-value'>{project_name}</span>
                    </div>
                    <div class='detail-row'>
                        <span class='detail-label'>Project Code:</span>
                        <span class='detail-value'><code>{project_code}</code></span>
                    </div>
                    """, unsafe_allow_html=True)

                with col2:
                    st.markdown(f"""
                    <div class='detail-row'>
                        <span class='detail-label'>Submitted By:</span>
                        <span class='detail-value'>{row['submitted_by']}</span>
                    </div>
                    <div class='detail-row'>
                        <span class='detail-label'>Submitted On:</span>
                        <span class='detail-value'>{row['submitted_on']}</span>
                    </div>
                    <div class='detail-row'>
                        <span class='detail-label'>Status:</span>
                        <span class='status-badge status-pending'>Pending Approval</span>
                    </div>
                    """, unsafe_allow_html=True)

                if row.get('description'):
                    st.markdown(f"""
                    <div class='detail-row' style='margin-top: 1rem;'>
                        <span class='detail-label'>Description:</span>
                        <span class='detail-value'>{row['description']}</span>
                    </div>
                    """, unsafe_allow_html=True)

                # ── Show RAIDs config summary ──────────────────────────
                raids_preview = _coerce_json(row.get("raids_config"), {})
                if raids_preview:
                    enabled = raids_preview.get("enabled_optional_fields") or []
                    custom  = raids_preview.get("custom_fields") or []
                    st.markdown("<div class='subsection-header'>📌 RAIDs Log Design</div>", unsafe_allow_html=True)
                    st.caption(
                        f"Optional fields: {', '.join(enabled) or 'defaults'} · "
                        f"Custom fields: {len(custom)}"
                    )

                st.markdown("</div>", unsafe_allow_html=True)

                # Editable fields
                st.markdown("<div class='subsection-header'>⚙️ Project Configuration</div>", unsafe_allow_html=True)

                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    project_start_edit = st.date_input(
                        "Project Start Date",
                        value=row.get("project_start_date"),
                        key=f"start_{project_id}",
                    )
                with col_date2:
                    expected_end_edit = st.date_input(
                        "Expected End Date",
                        value=row.get("expected_end_date"),
                        key=f"end_{project_id}",
                    )

                project_manager_edit = st.text_input(
                    "Project Manager",
                    value=row.get("project_manager") or "",
                    key=f"pm_{project_id}",
                )

                st.markdown("<div class='subsection-header'>🏷️ Service Line</div>", unsafe_allow_html=True)

                sl_pick = st.selectbox(
                    "Service Line",
                    SERVICE_LINES,
                    index=0,
                    key=f"sl_pick_{project_id}",
                )
                sl_other = ""
                if sl_pick == "Other":
                    sl_other = st.text_input(
                        "Specify Service Line",
                        key=f"sl_other_{project_id}",
                        placeholder="Enter custom service line"
                    )

                # Access list
                st.markdown("<div class='subsection-header'>👥 Project Access</div>", unsafe_allow_html=True)

                raw_access = row.get("access_list") or "[]"
                try:
                    access_list = (
                        json.loads(raw_access)
                        if isinstance(raw_access, str)
                        else (raw_access or [])
                    )
                except Exception:
                    access_list = []

                if not isinstance(access_list, list):
                    access_list = []

                key_prefix = f"access_edit_{project_id}"
                if key_prefix not in st.session_state:
                    st.session_state[key_prefix] = access_list.copy()

                edit_rows = st.session_state[key_prefix]
                remove_queue = []

                for i, entry in enumerate(edit_rows):
                    c1, c2, c3 = st.columns([4, 3, 1])
                    with c1:
                        entry["email"] = st.text_input(
                            "Email",
                            value=entry.get("email", ""),
                            key=f"{key_prefix}_email_{i}",
                            label_visibility="collapsed",
                            placeholder="user@example.com"
                        )
                    with c2:
                        role_val = entry.get("role", "user")
                        role_options = ["ceo", "exec", "user", "viewer"]
                        if role_val not in role_options:
                            role_val = "user"
                        entry["role"] = st.selectbox(
                            "Role",
                            role_options,
                            index=role_options.index(role_val),
                            key=f"{key_prefix}_role_{i}",
                            label_visibility="collapsed"
                        )
                    with c3:
                        if st.button("🗑️", key=f"{key_prefix}_remove_{i}"):
                            remove_queue.append(i)

                for idx in sorted(remove_queue, reverse=True):
                    del edit_rows[idx]

                if st.button("➕ Add User", key=f"{key_prefix}_add", use_container_width=True):
                    edit_rows.append({"email": "", "role": "viewer"})

                final_access_list = [r for r in edit_rows if r.get("email", "").strip()]

                # Action buttons
                st.markdown("<div class='subsection-header'>✅ Approval Actions</div>", unsafe_allow_html=True)

                reason = st.text_input(
                    "Rejection reason (optional)",
                    key=f"reject_reason_{project_id}",
                    placeholder="Why is this project being rejected?"
                )

                col_approve, col_reject, col_delete = st.columns(3)

                approve = col_approve.button(
                    "✅ Approve Project",
                    key=f"approve_{project_id}",
                    use_container_width=True,
                    type="primary"
                )
                reject = col_reject.button(
                    "❌ Reject",
                    key=f"reject_{project_id}",
                    use_container_width=True,
                )
                delete = col_delete.button(
                    "🗑️ Delete",
                    key=f"delete_scaffold_{project_id}",
                    use_container_width=True,
                )

                # ── Approval logic ─────────────────────────────────────
                if approve:
                    approver = st.session_state.get("email")

                    service_line_value = normalise_service_line(sl_pick, sl_other)
                    if sl_pick == "Other" and not service_line_value:
                        st.error("❌ Please enter a value for 'Other' service line.")
                        st.stop()

                    # Update scaffold status
                    run_execute("""
                        UPDATE project_scaffold
                        SET 
                            status = 'approved',
                            approved_by = (SELECT user_id FROM users WHERE email = :by_email),
                            approved_on = NOW(),
                            project_start_date = :ps,
                            expected_end_date = :ee,
                            project_manager = :pm,
                            access_list = CAST(:al AS jsonb)
                        WHERE id = :id
                    """, {
                        "by_email": approver,
                        "ps": project_start_edit,
                        "ee": expected_end_edit,
                        "pm": project_manager_edit,
                        "al": json.dumps(final_access_list),
                        "id": project_id,
                    })

                    # Get client details
                    cs_row = run_query(
                        "SELECT client_name, client_code FROM client_scaffold WHERE id = :id",
                        {"id": scaffold_client_id},
                    )

                    if cs_row is not None and not cs_row.empty:
                        client_name_resolved = cs_row.iloc[0]["client_name"]
                        client_code_resolved  = cs_row.iloc[0]["client_code"]
                    else:
                        client_name_resolved  = client_name
                        client_code_resolved  = "".join(
                            (c.lower() if c.isalnum() else "_")
                            for c in client_name
                        ).strip("_")

                    # Build the full settings block for the live project.
                    # This populates projects.settings so load_raids_config_for_project()
                    # can find raids_config via the primary read path.
                    live_settings = _build_live_settings_block(row, service_line_value)

                    # Create the live project row — write settings column immediately
                    result = run_execute("""
                        INSERT INTO projects (
                            project_name, project_code, client_id, client_name,
                            service_line, status, settings
                        )
                        VALUES (:name, :code, :cid, :client_name, :service_line, 'open',
                                CAST(:settings AS jsonb))
                        RETURNING project_id
                    """, {
                        "name": project_name,
                        "code": project_code,
                        "cid": scaffold_client_id,
                        "client_name": client_name_resolved,
                        "service_line": service_line_value,
                        "settings": json.dumps(live_settings),
                    })

                    live_project_id = int(result)

                    # Parse sub-configs
                    raids_value   = _coerce_json(row.get("raids_config"), {})
                    actions_value = _coerce_json(row.get("actions_config"), {})
                    nfr_value     = _coerce_json(row.get("nfr_config"), {})

                    # Also write to project_settings table (secondary / fallback read path)
                    set_project_setting(live_project_id, "settings",            live_settings)
                    set_project_setting(live_project_id, "tier",                live_settings.get("tier", "tier_2"))
                    set_project_setting(live_project_id, "description",         row.get("description") or "")
                    set_project_setting(live_project_id, "project_start_date",  str(project_start_edit) if project_start_edit else None)
                    set_project_setting(live_project_id, "expected_end_date",   str(expected_end_edit) if expected_end_edit else None)
                    set_project_setting(live_project_id, "project_manager",     project_manager_edit or "")
                    set_project_setting(live_project_id, "service_line",        service_line_value)
                    set_project_setting(live_project_id, "access_list",         final_access_list)
                    set_project_setting(live_project_id, "raids_config",        raids_value)
                    set_project_setting(live_project_id, "actions_config",      actions_value)
                    set_project_setting(live_project_id, "nfr_config",          nfr_value)

                    # Create filesystem folder
                    metadata = {
                        "project_id":   live_project_id,
                        "project_name": project_name,
                        "project_code": project_code,
                        "client_name":  client_name_resolved,
                        "client_code":  client_code_resolved,
                        "service_line": service_line_value,
                        "approved_on":  datetime.utcnow().isoformat(),
                        "approved_by":  approver,
                    }

                    settings_payload = {
                        "tier":               live_settings.get("tier", "tier_2"),
                        "description":        row.get("description") or "",
                        "project_start_date": str(project_start_edit) if project_start_edit else None,
                        "expected_end_date":  str(expected_end_edit) if expected_end_edit else None,
                        "project_manager":    project_manager_edit or "",
                        "service_line":       service_line_value,
                        "settings":           live_settings,
                        "access_list":        final_access_list,
                        "raids_config":       raids_value,
                        "actions_config":     actions_value,
                        "nfr_config":         nfr_value,
                    }

                    ensure_project_folder(
                        client_code=client_code_resolved,
                        project_code=project_code,
                        metadata=metadata,
                        settings=settings_payload,
                    )

                    log_event("project_approved", {
                        "project_name":  project_name,
                        "project_code":  project_code,
                        "client":        client_name_resolved,
                        "client_code":   client_code_resolved,
                        "project_id":    live_project_id,
                        "service_line":  service_line_value,
                        "approved_by":   approver,
                    })

                    send_notification("project_approved", {
                        "project_name":  project_name,
                        "client_name":   client_name_resolved,
                        "project_code":  project_code,
                        "submitted_by":  row["submitted_by"],
                        "approved_by":   approver,
                        "service_line":  service_line_value,
                    })

                    st.success(f"✅ Project '{project_name}' approved successfully!")
                    st.rerun()

                # ── Rejection logic ────────────────────────────────────
                if reject:
                    rejector = st.session_state.get("email")

                    run_execute("""
                        UPDATE project_scaffold
                        SET 
                            status = 'rejected',
                            rejected_by = (SELECT user_id FROM users WHERE email = :by_email),
                            rejected_on = NOW(),
                            rejection_reason = :reason
                        WHERE id = :id
                    """, {
                        "by_email": rejector,
                        "reason":   reason or "Not specified",
                        "id":       project_id,
                    })

                    log_event("project_rejected", {
                        "project_name": project_name,
                        "project_code": project_code,
                        "client":       client_name,
                        "rejected_by":  rejector,
                        "reason":       reason or "Not specified",
                    })

                    send_notification("project_rejected", {
                        "project_name":  project_name,
                        "client_name":   client_name,
                        "submitted_by":  row["submitted_by"],
                        "rejected_by":   rejector,
                        "reason":        reason or "Not specified",
                    })

                    st.warning(f"❌ Project '{project_name}' has been rejected.")
                    st.rerun()

                # ── Delete logic ───────────────────────────────────────
                if f"delete_scaffold_confirm_{project_id}" not in st.session_state:
                    st.session_state[f"delete_scaffold_confirm_{project_id}"] = False

                if delete:
                    st.session_state[f"delete_scaffold_confirm_{project_id}"] = True

                if st.session_state.get(f"delete_scaffold_confirm_{project_id}"):
                    st.markdown("""
                    <div class='warning-box'>
                        <div class='warning-title'>⚠️ Permanent Deletion Warning</div>
                        <div class='warning-text'>
                            This will permanently delete the scaffold record. This action cannot be undone.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    pwd = st.text_input("Enter your password", type="password", key=f"pwd_scaffold_{project_id}")
                    confirm_word = st.text_input("Type DELETE to confirm", key=f"word_scaffold_{project_id}")

                    col_confirm, col_cancel = st.columns(2)

                    if col_confirm.button("🔥 Confirm Delete", key=f"confirm_delete_scaffold_{project_id}",
                                          use_container_width=True):
                        if not verify_admin_password(pwd):
                            st.stop()

                        if confirm_word.strip().upper() != "DELETE":
                            st.error("❌ You must type DELETE to confirm.")
                            st.stop()

                        run_execute("DELETE FROM project_scaffold WHERE id = :id", {"id": project_id})

                        log_event("project_scaffold_deleted", {
                            "project_id":   project_id,
                            "project_name": project_name,
                            "client":       client_name,
                            "deleted_by":   st.session_state.get("email"),
                        })

                        st.success(f"🗑️ Scaffold for '{project_name}' permanently deleted.")
                        st.session_state[f"delete_scaffold_confirm_{project_id}"] = False
                        st.rerun()

                    if col_cancel.button("Cancel", key=f"cancel_delete_scaffold_{project_id}",
                                         use_container_width=True):
                        st.session_state[f"delete_scaffold_confirm_{project_id}"] = False
                        st.rerun()

# =========================================================
# TAB 2 — LIVE PROJECTS
# =========================================================
with tab_live:
    st.markdown("<div class='section-header'>Live Projects</div>", unsafe_allow_html=True)

    live_df = load_live_projects()

    if live_df is None:
        st.info("No live projects found.")
    else:
        display_live = live_df.copy()
        display_live["client_name"]  = display_live["client_name"].fillna("Unknown")
        display_live["service_line"] = display_live["service_line"].fillna("Unassigned")

        st.dataframe(
            display_live[["project_id", "project_name", "project_code", "client_name", "service_line"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "project_id":    "ID",
                "project_name":  "Project Name",
                "project_code":  "Code",
                "client_name":   "Client",
                "service_line":  "Service Line"
            }
        )

        st.markdown("<div class='subsection-header'>Manage Project</div>", unsafe_allow_html=True)

        lookup = {
            f"{(row['client_name'] or 'Unknown')} — {row['project_name']} ({row['project_code']})": row["project_id"]
            for _, row in live_df.iterrows()
        }

        selected_label = st.selectbox("Select a project", list(lookup.keys()), label_visibility="collapsed")
        selected_id    = lookup[selected_label]
        row            = live_df[live_df["project_id"] == selected_id].iloc[0]

        with st.container():
            st.markdown("<div class='project-card'>", unsafe_allow_html=True)

            st.markdown(f"**{row['project_name']}** <span class='status-badge status-open'>● Live</span>",
                        unsafe_allow_html=True)
            st.caption(f"Client: {row['client_name'] or 'Unknown'} · Code: `{row['project_code']}`")

            st.markdown("<div class='subsection-header'>🏷️ Service Line</div>", unsafe_allow_html=True)

            cur_sl      = (row.get("service_line") or "").strip()
            default_idx = SERVICE_LINES.index(cur_sl) if cur_sl in SERVICE_LINES else SERVICE_LINES.index(
                "Other") if cur_sl else 0

            col_sl1, col_sl2 = st.columns([2, 1])

            with col_sl1:
                edit_sl_pick = st.selectbox("Service Line", SERVICE_LINES, index=default_idx,
                                            key=f"live_sl_pick_{selected_id}")
                edit_sl_other = ""
                if edit_sl_pick == "Other":
                    edit_sl_other = st.text_input("Specify", value=cur_sl if cur_sl not in SERVICE_LINES else "",
                                                  key=f"live_sl_other_{selected_id}")

            with col_sl2:
                st.markdown("<div style='height: 1.65rem'></div>", unsafe_allow_html=True)
                if st.button("💾 Save", use_container_width=True, key=f"save_sl_live_{selected_id}"):
                    new_sl = normalise_service_line(edit_sl_pick, edit_sl_other)
                    if edit_sl_pick == "Other" and not new_sl:
                        st.error("❌ Please specify service line.")
                    else:
                        run_execute("UPDATE projects SET service_line = :sl WHERE project_id = :pid",
                                    {"sl": new_sl, "pid": selected_id})
                        set_project_setting(selected_id, "service_line", new_sl)
                        # Keep projects.settings in sync too
                        settings_df = run_query(
                            "SELECT settings FROM projects WHERE project_id = :pid LIMIT 1",
                            {"pid": selected_id},
                        )
                        if settings_df is not None and not settings_df.empty:
                            s = _coerce_json(settings_df.iloc[0].get("settings"), {})
                            s["service_line"] = new_sl
                            run_execute(
                                "UPDATE projects SET settings = CAST(:s AS jsonb) WHERE project_id = :pid",
                                {"s": json.dumps(s), "pid": selected_id},
                            )
                        st.success("✅ Service line updated.")
                        st.rerun()

            st.markdown("<div class='subsection-header'>⚙️ Project Actions</div>", unsafe_allow_html=True)

            col1, col2 = st.columns(2)

            if col1.button("📦 Close Project", use_container_width=True, key=f"close_{selected_id}"):
                run_execute("UPDATE projects SET status = 'closed' WHERE project_id = :pid", {"pid": selected_id})
                log_event("project_closed", {
                    "project_id":   selected_id,
                    "project_name": row["project_name"],
                    "client":       row["client_name"],
                    "closed_by":    st.session_state.get("email"),
                })
                send_notification("project_closed", {
                    "project_name": row["project_name"],
                    "client_name":  row["client_name"],
                    "closed_by":    st.session_state.get("email"),
                })
                st.success("📦 Project closed.")
                st.rerun()

            if col2.button("🗑️ Delete Project", use_container_width=True, key=f"delete_live_{selected_id}"):
                st.session_state[f"delete_live_confirm_{selected_id}"] = True

            st.markdown("</div>", unsafe_allow_html=True)

        if f"delete_live_confirm_{selected_id}" not in st.session_state:
            st.session_state[f"delete_live_confirm_{selected_id}"] = False

        if st.session_state.get(f"delete_live_confirm_{selected_id}"):
            st.markdown("""
            <div class='warning-box'>
                <div class='warning-title'>⚠️ Permanent Deletion Warning</div>
                <div class='warning-text'>This will permanently delete the project and all associated data.</div>
            </div>
            """, unsafe_allow_html=True)

            pwd_live         = st.text_input("Password", type="password", key=f"pwd_live_{selected_id}")
            confirm_word_live = st.text_input("Type DELETE", key=f"word_live_{selected_id}")

            col_c1, col_c2 = st.columns(2)

            if col_c1.button("🔥 Confirm Delete", key=f"confirm_delete_live_{selected_id}", use_container_width=True):
                if not verify_admin_password(pwd_live) or confirm_word_live.strip().upper() != "DELETE":
                    st.error("❌ Invalid confirmation.")
                    st.stop()

                client_code = row.get("client_code")
                if client_code:
                    delete_project_folder(client_code, row["project_code"])

                run_execute("DELETE FROM projects WHERE project_id = :pid", {"pid": selected_id})
                log_event("project_deleted", {
                    "project_id":   selected_id,
                    "project_name": row["project_name"],
                    "deleted_by":   st.session_state.get("email"),
                })
                st.success("🗑️ Project deleted.")
                st.session_state[f"delete_live_confirm_{selected_id}"] = False
                st.rerun()

            if col_c2.button("Cancel", key=f"cancel_delete_live_{selected_id}", use_container_width=True):
                st.session_state[f"delete_live_confirm_{selected_id}"] = False
                st.rerun()

# =========================================================
# TAB 3 — CLOSED PROJECTS
# =========================================================
with tab_closed:
    st.markdown("<div class='section-header'>Closed Projects</div>", unsafe_allow_html=True)

    closed_df = load_closed_projects()

    if closed_df is None:
        st.info("No closed projects found.")
    else:
        display_closed = closed_df.copy()
        display_closed["client_name"]  = display_closed["client_name"].fillna("Unknown")
        display_closed["service_line"] = display_closed["service_line"].fillna("Unassigned")

        st.dataframe(
            display_closed[["project_id", "project_name", "project_code", "client_name", "service_line"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "project_id":   "ID",
                "project_name": "Project Name",
                "project_code": "Code",
                "client_name":  "Client",
                "service_line": "Service Line"
            }
        )

        st.markdown("<div class='subsection-header'>Manage Closed Project</div>", unsafe_allow_html=True)

        lookup_closed = {
            f"{(row['client_name'] or 'Unknown')} — {row['project_name']} ({row['project_code']})": row["project_id"]
            for _, row in closed_df.iterrows()
        }

        selected_closed_label = st.selectbox(
            "Select a project", list(lookup_closed.keys()), label_visibility="collapsed"
        )
        closed_id = lookup_closed[selected_closed_label]
        row_c     = closed_df[closed_df["project_id"] == closed_id].iloc[0]

        with st.container():
            st.markdown("<div class='project-card'>", unsafe_allow_html=True)

            st.markdown(f"**{row_c['project_name']}** <span class='status-badge status-closed'>● Closed</span>",
                        unsafe_allow_html=True)
            st.caption(f"Client: {row_c['client_name']} · Code: `{row_c['project_code']}`")

            st.markdown("<div class='subsection-header'>🏷️ Service Line</div>", unsafe_allow_html=True)

            cur_sl_c      = (row_c.get("service_line") or "").strip()
            default_idx_c = SERVICE_LINES.index(cur_sl_c) if cur_sl_c in SERVICE_LINES else SERVICE_LINES.index(
                "Other") if cur_sl_c else 0

            col_slc1, col_slc2 = st.columns([2, 1])

            with col_slc1:
                edit_sl_pick_c = st.selectbox("Service Line", SERVICE_LINES, index=default_idx_c,
                                              key=f"closed_sl_pick_{closed_id}")
                edit_sl_other_c = ""
                if edit_sl_pick_c == "Other":
                    edit_sl_other_c = st.text_input("Specify", value=cur_sl_c if cur_sl_c not in SERVICE_LINES else "",
                                                    key=f"closed_sl_other_{closed_id}")

            with col_slc2:
                st.markdown("<div style='height: 1.65rem'></div>", unsafe_allow_html=True)
                if st.button("💾 Save", use_container_width=True, key=f"save_sl_closed_{closed_id}"):
                    new_sl_c = normalise_service_line(edit_sl_pick_c, edit_sl_other_c)
                    if edit_sl_pick_c == "Other" and not new_sl_c:
                        st.error("❌ Please specify service line.")
                    else:
                        run_execute("UPDATE projects SET service_line = :sl WHERE project_id = :pid",
                                    {"sl": new_sl_c, "pid": closed_id})
                        set_project_setting(closed_id, "service_line", new_sl_c)
                        settings_df = run_query(
                            "SELECT settings FROM projects WHERE project_id = :pid LIMIT 1",
                            {"pid": closed_id},
                        )
                        if settings_df is not None and not settings_df.empty:
                            s = _coerce_json(settings_df.iloc[0].get("settings"), {})
                            s["service_line"] = new_sl_c
                            run_execute(
                                "UPDATE projects SET settings = CAST(:s AS jsonb) WHERE project_id = :pid",
                                {"s": json.dumps(s), "pid": closed_id},
                            )
                        st.success("✅ Service line updated.")
                        st.rerun()

            st.markdown("<div class='subsection-header'>⚙️ Project Actions</div>", unsafe_allow_html=True)

            col_c1, col_c2 = st.columns(2)

            if col_c1.button("🔄 Reopen Project", use_container_width=True, key=f"reopen_{closed_id}"):
                run_execute("UPDATE projects SET status = 'open' WHERE project_id = :pid", {"pid": closed_id})
                log_event("project_reopened", {
                    "project_id":   closed_id,
                    "project_name": row_c["project_name"],
                    "reopened_by":  st.session_state.get("email"),
                })
                st.success("🔄 Project reopened.")
                st.rerun()

            if col_c2.button("🗑️ Delete Project", use_container_width=True, key=f"delete_closed_{closed_id}"):
                st.session_state[f"delete_closed_confirm_{closed_id}"] = True

            st.markdown("</div>", unsafe_allow_html=True)

        if f"delete_closed_confirm_{closed_id}" not in st.session_state:
            st.session_state[f"delete_closed_confirm_{closed_id}"] = False

        if st.session_state.get(f"delete_closed_confirm_{closed_id}"):
            st.markdown("""
            <div class='warning-box'>
                <div class='warning-title'>⚠️ Permanent Deletion Warning</div>
                <div class='warning-text'>This will permanently delete the closed project.</div>
            </div>
            """, unsafe_allow_html=True)

            pwd_closed         = st.text_input("Password", type="password", key=f"pwd_closed_{closed_id}")
            confirm_word_closed = st.text_input("Type DELETE", key=f"word_closed_{closed_id}")

            col_cc1, col_cc2 = st.columns(2)

            if col_cc1.button("🔥 Confirm Delete", key=f"confirm_delete_closed_{closed_id}", use_container_width=True):
                if not verify_admin_password(pwd_closed) or confirm_word_closed.strip().upper() != "DELETE":
                    st.error("❌ Invalid confirmation.")
                    st.stop()

                client_code = row_c.get("client_code")
                if client_code:
                    delete_project_folder(client_code, row_c["project_code"])

                run_execute("DELETE FROM projects WHERE project_id = :pid", {"pid": closed_id})
                log_event("project_deleted", {
                    "project_id":   closed_id,
                    "project_name": row_c["project_name"],
                    "deleted_by":   st.session_state.get("email"),
                })
                st.success("🗑️ Project deleted.")
                st.session_state[f"delete_closed_confirm_{closed_id}"] = False
                st.rerun()

            if col_cc2.button("Cancel", key=f"cancel_delete_closed_{closed_id}", use_container_width=True):
                st.session_state[f"delete_closed_confirm_{closed_id}"] = False
                st.rerun()

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<div style='margin-top: 4rem;'></div>", unsafe_allow_html=True)
pmo_footer()