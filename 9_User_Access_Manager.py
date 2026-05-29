# ============================================================
# 9_🔐_User_Access_Manager.py — ScopeSight v3.6 (UPDATED)
# Unified User, Client & Project Access Management + Access Requests Workflow
#
# - Approve / Reject requests
# - Approve applies changes:
#       - role_change  -> updates public.users.role
#       - client_access -> upserts user_client_permissions + derives project access
#       - project_access -> upserts user_project_permissions
# - Enforces request role options: user / viewer / exec / ceo (for requests)
# - Requires reason to approve (reason is mandatory)
# - Schema-safe column mapping for access_requests (won’t crash if columns differ)
# ============================================================

import os
import random
import string
import streamlit as st
import bcrypt
import pandas as pd

from auth.login import (
    require_login,
    validate_password_strength,
)

from modules.db import (
    run_query,
    run_execute,
    get_user_by_email,
    create_user,
    get_user_id,
)

# ---------------------------------------------------------
# DEV MODE OVERRIDE
# ---------------------------------------------------------
query = st.query_params

if query.get("dev") == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True

require_login()

# ---------------------------------------------------------
# UI IMPORTS
# ---------------------------------------------------------
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

hide_streamlit_nav()
set_pmo_theme(page_title="🔐 User Access Manager")
render_sidebar()

# ---------------------------------------------------------
# STYLES — Match Project Submission Tracker Formatting
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] {
    height: 0px !important;
    visibility: hidden !important;
}
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 2rem 0 1rem 0;
}
.section-header h3 {
    color: white;
    margin: 0;
    font-size: 1.2rem;
    font-weight: 600;
}
.step-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1.25rem 0 1rem 0;
}
.step-header h4 {
    color: #0077be;
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
}
.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0 1.5rem 0;
}
.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e6f2ff;
}
.debug-box {
    background: #fff3cd;
    border: 2px solid #ffc107;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# RBAC CONSTANTS
# ---------------------------------------------------------
CLIENT_ROLES = ["ceo", "exec", "admin", "user", "viewer"]  # lowercase for DB
PROJECT_ACCESS_LEVELS = ["ADMIN", "USER", "VIEWER"]  # UPPERCASE for DB
NO_ACCESS = "(no access)"

# Mapping: client role (lowercase) → project access (UPPERCASE)
CLIENT_ROLE_TO_PROJECT_ACCESS = {
    "ceo": "VIEWER",
    "exec": "VIEWER",
    "admin": "ADMIN",
    "user": "USER",
    "viewer": "VIEWER",
}

# Global system roles (admin can set these in Add/Edit)
GLOBAL_ROLES = ["user", "admin", "viewer", "exec", "ceo"]

# Request allowed roles (from My Profile request rules)
REQUEST_ALLOWED_ROLES = ["user", "viewer", "exec", "ceo"]


def safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if df is not None and not df.empty else pd.DataFrame()


def to_db_role(val: str) -> str:
    """Client role stored in DB (lowercase)"""
    return (val or "").strip().lower()


def to_db_access(val: str) -> str:
    """Project access stored in DB (UPPERCASE)"""
    return (val or "").strip().upper()


def to_ui_lower(val: str) -> str:
    return (val or "").strip().lower()


def user_exists(email_addr: str) -> bool:
    return get_user_by_email(email_addr) is not None


# ---------------------------------------------------------
# SCHEMA HELPERS (for access_requests + safety)
# ---------------------------------------------------------
def _table_exists(table_name: str) -> bool:
    df = run_query(
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = :t
        LIMIT 1
        """,
        {"t": table_name},
    )
    return df is not None and not df.empty


def _table_columns(table_name: str) -> set[str]:
    df = run_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :t
        """,
        {"t": table_name},
    )
    if df is None or df.empty:
        return set()
    return set(df["column_name"].astype(str).tolist())


def _first_existing(colset: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colset:
            return c
    return None


# ---------------------------------------------------------
# INTRO
# ---------------------------------------------------------
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#2f855a;'>💡 Tip</strong><br/>
    Use the Overview tab to audit access, then use Add / Edit User to
    update client roles. Project access is derived automatically from client roles.<br/>
    The Access Requests tab allows admins to approve/reject requests from <strong>My Profile</strong>.
</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# LOAD USERS + CLIENTS + PROJECTS
# ---------------------------------------------------------
users_df = safe_df(
    run_query(
        """
        SELECT user_id, email, role, created_at
        FROM public.users
        ORDER BY email
        """
    )
)

clients_df = safe_df(
    run_query(
        """
        SELECT id AS client_id,
               client_name,
               client_code
        FROM public.client_scaffold
        WHERE status = 'approved'
        ORDER BY client_name
        """
    )
)

client_id_to_name = (
    dict(zip(clients_df["client_id"], clients_df["client_name"])) if not clients_df.empty else {}
)

projects_df = safe_df(
    run_query(
        """
        SELECT
            p.project_id,
            p.project_name,
            p.project_code,
            p.client_id,
            cs.client_name
        FROM public.projects p
        LEFT JOIN public.client_scaffold cs
            ON cs.id = p.client_id
        ORDER BY cs.client_name, p.project_name
        """
    )
)

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_overview, tab_requests, tab_existing, tab_add_edit, tab_delete = st.tabs(
    [
        "🔎 User Access Overview",
        "📨 Access Requests",
        "👥 Existing Users",
        "✏️ Add / Edit User",
        "🗑️ Delete User",
    ]
)

# =========================================================
# TAB 1 — USER ACCESS OVERVIEW MATRIX
# =========================================================
with tab_overview:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🔎 User Access Overview</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not users_df.empty:
        access_rows = []

        for _, user in users_df.iterrows():
            uid = int(user["user_id"])

            client_perms = safe_df(
                run_query(
                    """
                    SELECT
                        ucp.client_id,
                        cs.client_name,
                        ucp.role
                    FROM public.user_client_permissions ucp
                    JOIN public.client_scaffold cs
                      ON cs.id = ucp.client_id
                    WHERE ucp.user_id = :uid
                    ORDER BY cs.client_name
                    """,
                    {"uid": uid},
                )
            )

            project_perms = safe_df(
                run_query(
                    """
                    SELECT
                        upp.project_id,
                        p.project_name,
                        upp.access_level,
                        cs.client_name
                    FROM public.user_project_permissions upp
                    JOIN public.projects p
                      ON p.project_id = upp.project_id
                    JOIN public.client_scaffold cs
                      ON cs.id = p.client_id
                    WHERE upp.user_id = :uid
                    ORDER BY cs.client_name, p.project_name
                    """,
                    {"uid": uid},
                )
            )

            clients_str = (
                ", ".join(
                    f"{row['client_name']} ({to_ui_lower(str(row['role']))})"
                    for _, row in client_perms.iterrows()
                )
                if not client_perms.empty
                else "—"
            )

            projects_str = (
                ", ".join(
                    f"{row['client_name']} → {row['project_name']} ({to_ui_lower(str(row['access_level']))})"
                    for _, row in project_perms.iterrows()
                )
                if not project_perms.empty
                else "—"
            )

            access_rows.append(
                {
                    "Email": user["email"],
                    "Global Role": user["role"],
                    "Clients": clients_str,
                    "Projects": projects_str,
                }
            )

        overview_df = pd.DataFrame(access_rows)

        st.markdown(
            """
            <div class='step-header'>
                <h4>Filters</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        role_options = ["All"] + sorted(overview_df["Global Role"].dropna().unique().tolist())
        selected_role = st.selectbox("Filter by global role", role_options, index=0)

        email_filter = st.text_input("Search by email (contains)", "")
        scope_filter = st.text_input("Filter by client/project name (contains)", "")

        filtered_df = overview_df.copy()

        if selected_role != "All":
            filtered_df = filtered_df[filtered_df["Global Role"] == selected_role]

        if email_filter:
            s = email_filter.lower()
            filtered_df = filtered_df[filtered_df["Email"].str.lower().str.contains(s, na=False)]

        if scope_filter:
            s2 = scope_filter.lower()
            mask = (
                filtered_df["Clients"].str.lower().str.contains(s2, na=False)
                | filtered_df["Projects"].str.lower().str.contains(s2, na=False)
            )
            filtered_df = filtered_df[mask]

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No users found yet.")

# =========================================================
# TAB 2 — ACCESS REQUESTS (from My Profile)
# =========================================================
with tab_requests:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📨 Access Requests</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            Review access requests submitted by users from <strong>My Profile → Request Access</strong>.<br/>
            ✅ Approve applies the change automatically. ❌ Reject records the decision.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not _table_exists("access_requests"):
        st.warning("No access_requests table found. Add it to enable request workflow.")
    else:
        ar_cols = _table_columns("access_requests")

        # Column mapping (schema-safe)
        c_request_id = _first_existing(ar_cols, ["request_id", "id"])
        c_user_id = _first_existing(ar_cols, ["user_id", "requested_by", "requester_user_id"])
        c_user_email = _first_existing(ar_cols, ["user_email", "email"])
        c_request_type = _first_existing(ar_cols, ["request_type", "type", "request_kind"])
        c_target_type = _first_existing(ar_cols, ["target_type", "scope", "entity_type"])
        c_target_id = _first_existing(ar_cols, ["target_id", "entity_id"])
        c_target_label = _first_existing(ar_cols, ["target_label", "target_name", "target"])
        c_requested_role = _first_existing(ar_cols, ["requested_role", "role_requested", "new_role"])
        c_reason = _first_existing(ar_cols, ["reason", "justification", "notes"])
        c_status = _first_existing(ar_cols, ["status", "request_status"])
        c_created_at = _first_existing(ar_cols, ["created_at", "submitted_on", "requested_on"])
        c_reviewed_by = _first_existing(ar_cols, ["reviewed_by", "approved_by", "decided_by"])
        c_reviewed_on = _first_existing(ar_cols, ["reviewed_on", "approved_on", "decided_on"])
        c_review_notes = _first_existing(ar_cols, ["review_notes", "decision_notes", "admin_notes"])

        # Minimum needed
        if not all([c_request_id, c_status, c_requested_role, c_reason]):
            st.error(
                "access_requests table exists but is missing required columns for the workflow.\n"
                "Minimum required columns:\n"
                "- request_id (or id)\n"
                "- status\n"
                "- requested_role (or new_role)\n"
                "- reason (or notes)\n"
            )
        else:
            st.markdown(
                """
                <div class='step-header'>
                    <h4>Filters</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            status_filter = st.selectbox(
                "Show status",
                ["pending", "approved", "rejected", "cancelled", "all"],
                index=0,
            )

            where = ""
            params = {}
            if status_filter != "all":
                where = f"WHERE {c_status} = :st"
                params = {"st": status_filter}

            order_col = c_created_at or c_request_id
            reqs_df = safe_df(
                run_query(
                    f"""
                    SELECT *
                    FROM public.access_requests
                    {where}
                    ORDER BY {order_col} DESC
                    LIMIT 250
                    """,
                    params if params else None,
                )
            )

            if reqs_df.empty:
                st.info("No requests found for the selected filter.")
            else:
                st.markdown("#### Requests (latest 250)")
                st.markdown('<div class="table-container">', unsafe_allow_html=True)
                st.dataframe(reqs_df, use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<hr/>", unsafe_allow_html=True)
                st.markdown(
                    """
                    <div class='step-header'>
                        <h4>✅ Review a Request</h4>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                def _label(r: pd.Series) -> str:
                    rid = r.get(c_request_id)
                    who = r.get(c_user_email) or r.get(c_user_id) or "user"
                    typ = r.get(c_request_type) or "request"
                    tgt = r.get(c_target_label) or r.get(c_target_id) or ""
                    role_req = r.get(c_requested_role) or ""
                    stt = r.get(c_status) or ""
                    return f"#{rid} • {who} • {typ} • {tgt} • role={role_req} • {stt}"

                options = reqs_df.apply(_label, axis=1).tolist()
                selected_label = st.selectbox("Select request", options, index=0)
                selected_row = reqs_df.iloc[options.index(selected_label)].to_dict()

                req_id = selected_row.get(c_request_id)
                req_status = (selected_row.get(c_status) or "").strip().lower()
                req_type = (selected_row.get(c_request_type) or "").strip().lower()
                target_type = (selected_row.get(c_target_type) or "").strip().lower()
                target_id = selected_row.get(c_target_id)
                target_label = selected_row.get(c_target_label)
                requested_role = (selected_row.get(c_requested_role) or "").strip().lower()
                reason_txt = (selected_row.get(c_reason) or "").strip()

                st.markdown(
                    f"""
                    <div class='debug-box'>
                        <strong>Reason (required):</strong><br/>{reason_txt if reason_txt else "<em>Missing</em>"}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if requested_role and requested_role not in REQUEST_ALLOWED_ROLES:
                    st.error(
                        f"Requested role '{requested_role}' is not allowed for requests. "
                        f"Allowed: {', '.join(REQUEST_ALLOWED_ROLES)}"
                    )

                review_notes = st.text_area(
                    "Admin notes (optional)",
                    placeholder="Add a short decision note…",
                )

                colA, colB, colC = st.columns(3)
                with colA:
                    approve = st.button("✅ Approve", use_container_width=True, disabled=(req_status != "pending"))
                with colB:
                    reject = st.button("❌ Reject", use_container_width=True, disabled=(req_status != "pending"))
                with colC:
                    st.write("")
                    st.caption("Only pending requests can be actioned.")

                def _get_admin_user_id() -> int | None:
                    admin_email = (st.session_state.get("email") or "").strip().lower()
                    df = run_query(
                        "SELECT user_id FROM public.users WHERE LOWER(email)=:e LIMIT 1",
                        {"e": admin_email},
                    )
                    if df is None or df.empty:
                        return None
                    return int(df.iloc[0]["user_id"])

                def _update_request(new_status: str):
                    admin_uid = _get_admin_user_id()

                    sets = [f"{c_status} = :st"]
                    params2 = {"st": new_status, "rid": req_id}

                    if c_reviewed_on:
                        sets.append(f"{c_reviewed_on} = NOW()")
                    if c_reviewed_by and admin_uid is not None:
                        sets.append(f"{c_reviewed_by} = :rb")
                        params2["rb"] = admin_uid
                    if c_review_notes:
                        sets.append(f"{c_review_notes} = :rn")
                        params2["rn"] = (review_notes or "").strip()

                    run_execute(
                        f"""
                        UPDATE public.access_requests
                        SET {", ".join(sets)}
                        WHERE {c_request_id} = :rid
                        """,
                        params2,
                    )

                def _resolve_requester_user_id() -> int | None:
                    # Prefer stored user_id
                    if c_user_id and selected_row.get(c_user_id) is not None:
                        try:
                            return int(selected_row.get(c_user_id))
                        except Exception:
                            pass

                    # Fallback by email
                    if c_user_email and selected_row.get(c_user_email):
                        e = str(selected_row.get(c_user_email)).strip().lower()
                        df = run_query(
                            "SELECT user_id FROM public.users WHERE LOWER(email)=:e LIMIT 1",
                            {"e": e},
                        )
                        if df is not None and not df.empty:
                            return int(df.iloc[0]["user_id"])
                    return None

                def _apply_approved() -> bool:
                    requester_uid = _resolve_requester_user_id()
                    if requester_uid is None:
                        st.error("Could not resolve requester user_id to apply changes.")
                        return False

                    # If request type column is missing, infer by target_type when possible
                    # Accepted request types:
                    # - role_change (target_type global_role)
                    # - client_access (target_type client)
                    # - project_access (target_type project)
                    rt = req_type
                    if not rt and target_type:
                        rt = target_type

                    # --- ROLE CHANGE ---
                    if rt in ("role_change", "global_role") or target_type in ("global_role", "global"):
                        if requested_role not in REQUEST_ALLOWED_ROLES:
                            st.error("Cannot apply: requested role is not allowed.")
                            return False
                        run_execute(
                            "UPDATE public.users SET role = :r WHERE user_id = :uid",
                            {"r": requested_role, "uid": requester_uid},
                        )
                        return True

                    # --- CLIENT ACCESS ---
                    if rt in ("client_access", "client") or target_type == "client":
                        if target_id is None:
                            st.error("Missing target_id (client_id) on request.")
                            return False

                        cid = int(target_id)

                        # For requests, we only expect user/viewer/exec/ceo.
                        # If you ever allow admin via request later, extend REQUEST_ALLOWED_ROLES.
                        if requested_role not in REQUEST_ALLOWED_ROLES:
                            st.error("Cannot apply: requested role is not allowed for client access requests.")
                            return False

                        requester_email = ""
                        if c_user_email and selected_row.get(c_user_email):
                            requester_email = str(selected_row.get(c_user_email)).strip().lower()

                        run_execute(
                            """
                            INSERT INTO public.user_client_permissions (user_id, user_email, client_id, role)
                            VALUES (:uid, :email, :cid, :role)
                            ON CONFLICT (user_id, client_id)
                            DO UPDATE SET role = EXCLUDED.role, user_email = EXCLUDED.user_email
                            """,
                            {"uid": requester_uid, "email": requester_email, "cid": cid, "role": requested_role},
                        )

                        access_upper = CLIENT_ROLE_TO_PROJECT_ACCESS.get(requested_role, "VIEWER")
                        if access_upper not in PROJECT_ACCESS_LEVELS:
                            st.error(f"Invalid derived project access: {access_upper}")
                            return False

                        run_execute(
                            """
                            INSERT INTO public.user_project_permissions (user_id, project_id, access_level)
                            SELECT :uid, p.project_id, :access
                            FROM public.projects p
                            WHERE p.client_id = :cid
                            ON CONFLICT (user_id, project_id)
                            DO UPDATE SET access_level = EXCLUDED.access_level
                            """,
                            {"uid": requester_uid, "cid": cid, "access": access_upper},
                        )
                        return True

                    # --- PROJECT ACCESS ---
                    if rt in ("project_access", "project") or target_type == "project":
                        if target_id is None:
                            st.error("Missing target_id (project_id) on request.")
                            return False

                        pid = int(target_id)

                        # Simple mapping for requests:
                        # - user -> USER
                        # - viewer/exec/ceo -> VIEWER
                        access_upper = "USER" if requested_role == "user" else "VIEWER"
                        if access_upper not in PROJECT_ACCESS_LEVELS:
                            st.error(f"Invalid derived project access: {access_upper}")
                            return False

                        run_execute(
                            """
                            INSERT INTO public.user_project_permissions (user_id, project_id, access_level)
                            VALUES (:uid, :pid, :acc)
                            ON CONFLICT (user_id, project_id)
                            DO UPDATE SET access_level = EXCLUDED.access_level
                            """,
                            {"uid": requester_uid, "pid": pid, "acc": access_upper},
                        )
                        return True

                    st.error("Request type not recognised — cannot apply automatically.")
                    return False

                if approve:
                    if not reason_txt:
                        st.error("Cannot approve: request has no reason (reason is required).")
                    elif requested_role and requested_role not in REQUEST_ALLOWED_ROLES:
                        st.error("Cannot approve: requested role is not allowed.")
                    else:
                        ok = _apply_approved()
                        if ok:
                            _update_request("approved")
                            st.success("✅ Approved and applied.")
                            st.rerun()

                if reject:
                    _update_request("rejected")
                    st.success("❌ Rejected.")
                    st.rerun()

# =========================================================
# TAB 3 — EXISTING USERS
# =========================================================
with tab_existing:
    st.markdown(
        """
        <div class='section-header'>
            <h3>👥 Existing Users</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not users_df.empty:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(users_df, use_container_width=True, height=350)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No users created yet.")

# =========================================================
# TAB 4 — ADD / EDIT USER
# =========================================================
with tab_add_edit:
    st.markdown(
        """
        <div class='section-header'>
            <h3>✏️ Add / Edit User</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------------------------------------
    # USER DETAILS
    # ---------------------------------------------------------
    st.markdown(
        """
        <div class='step-header'>
            <h4>👤 User Details</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    email = (st.text_input("User email (login username)") or "").strip().lower()

    # ✅ Define full_name (prevents NameError, used for resource_pool)
    full_name = (st.text_input("Full name (for Resource Pool)", value="") or "").strip()

    # Load existing user (if any)
    existing_client_roles: dict[int, str] = {}  # client_id -> role (lowercase)
    existing_role = None
    uid = None
    mode = None  # "new" | "edit"

    can_continue = True

    if not email:
        st.caption("Enter an email address to begin.")
        can_continue = False
    elif "@" not in email:
        st.error("Invalid email.")
        can_continue = False
    else:
        user_row = get_user_by_email(email)
        mode = "edit" if user_row is not None else "new"

        if mode == "edit":
            existing_role = to_ui_lower(user_row.get("role"))
            uid = user_row.get("user_id")

            client_perm_df = safe_df(
                run_query(
                    """
                    SELECT
                        ucp.client_id,
                        cs.client_name,
                        ucp.role
                    FROM public.user_client_permissions ucp
                    JOIN public.client_scaffold cs
                      ON cs.id = ucp.client_id
                    WHERE ucp.user_id = :uid
                    ORDER BY cs.client_name
                    """,
                    {"uid": uid},
                )
            )

            existing_client_roles = {
                int(row["client_id"]): to_ui_lower(str(row["role"]))
                for _, row in client_perm_df.iterrows()
            }

        st.info("✅ Editing existing user" if mode == "edit" else "🆕 Creating new user")

    if not can_continue:
        st.divider()
        st.caption("Fill in the email above to unlock role, security and client governance settings.")
    else:
        # ---------------------------------------------------------
        # SYSTEM ACCESS
        # ---------------------------------------------------------
        st.markdown(
            """
            <div class='step-header'>
                <h4>🔑 System Access</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        role = st.selectbox(
            "Global role (system-level)",
            GLOBAL_ROLES,
            index=GLOBAL_ROLES.index(existing_role) if existing_role in GLOBAL_ROLES else 0,
        )

        st.markdown("<br/>", unsafe_allow_html=True)

        # ---------------------------------------------------------
        # SECURITY
        # ---------------------------------------------------------
        st.markdown(
            """
            <div class='step-header'>
                <h4>🔐 Security</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption(
            "A password is required for new users."
            if mode == "new"
            else "Leave blank to keep the existing password."
        )

        col_pw1, col_pw2 = st.columns([3, 1])

        with col_pw1:
            password = st.text_input(
                "Password",
                type="password",
                value=st.session_state.get("generated_pw", ""),
            )

        with col_pw2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("🔐 Generate Strong Password", use_container_width=True):
                g = (
                    random.choice(string.ascii_uppercase)
                    + random.choice(string.ascii_lowercase)
                    + random.choice(string.digits)
                    + random.choice("!@#$%^&*")
                    + "".join(random.choices(string.ascii_letters + string.digits, k=8))
                )
                st.session_state.generated_pw = g
                st.rerun()

        if password:
            valid, msg = validate_password_strength(password)
            color = "#A3C73E" if valid else "#E74C3C"
            st.markdown(
                f"""
                <div style='background:{color}; padding:6px; color:white;
                             text-align:center; border-radius:6px; margin-bottom:0.5rem;'>
                    {'Strong password ✔️' if valid else f'Weak password ✖ — {msg}'}
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<br/>", unsafe_allow_html=True)

        # ---------------------------------------------------------
        # CLIENT GOVERNANCE
        # ---------------------------------------------------------
        st.markdown(
            """
            <div class='step-header'>
                <h4>🏢 Client Governance</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("Assign a role per client. Project access is derived automatically.")

        client_roles: dict[int, str] = {}  # client_id -> role (lowercase)

        with st.expander("Client role assignments", expanded=True):
            if not clients_df.empty:
                for _, row in clients_df.iterrows():
                    cid = int(row["client_id"])
                    cname = row["client_name"]

                    current_role = existing_client_roles.get(cid)
                    options = [NO_ACCESS] + CLIENT_ROLES
                    default_idx = options.index(current_role) if current_role in options else 0

                    selected = st.selectbox(
                        f"Client: {cname}",
                        options,
                        index=default_idx,
                        key=f"client_role_{cid}",
                    )

                    if selected != NO_ACCESS:
                        client_roles[cid] = selected.strip().lower()
            else:
                st.caption("No approved clients configured yet.")

        st.markdown("<br/>", unsafe_allow_html=True)

        # ---------------------------------------------------------
        # PROJECT ACCESS OVERVIEW
        # ---------------------------------------------------------
        st.markdown(
            """
            <div class='step-header'>
                <h4>📁 Project Access Overview</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not client_roles:
            st.info("No client roles assigned — project access will not be created.")
        else:
            preview_rows = []
            for cid, crole in client_roles.items():
                preview_rows.append(
                    {
                        "Client": client_id_to_name.get(cid, str(cid)),
                        "Client Role": crole,
                        "Derived Project Access": CLIENT_ROLE_TO_PROJECT_ACCESS.get(crole, "VIEWER"),
                    }
                )
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br/>", unsafe_allow_html=True)

        show_debug = st.toggle("Show debug details", value=False)

        save_label = "Create user" if mode == "new" else "Save changes"

        if st.button(f"💾 {save_label}", use_container_width=True):

            # Optional debug
            if show_debug:
                st.markdown('<div class="debug-box">', unsafe_allow_html=True)
                st.write("### 🐛 Debug Information")
                st.write("**Client Roles Dictionary:**")
                st.json(client_roles)
                st.write("**Role Mapping:**")
                st.json(CLIENT_ROLE_TO_PROJECT_ACCESS)
                st.markdown("</div>", unsafe_allow_html=True)

            # Basic validation
            if not email:
                st.error("Email is required.")
                st.stop()

            if "@" not in email:
                st.error("Invalid email.")
                st.stop()

            # Password rules
            if mode == "new" and not password:
                st.error("Password required for new users.")
                st.stop()

            if password:
                valid, msg = validate_password_strength(password)
                if not valid:
                    st.error(f"Weak password — {msg}")
                    st.stop()

            # Create/update user
            if not user_exists(email):
                create_user(email, password, role)
                st.success(f"User '{email}' created.")
            else:
                run_execute(
                    "UPDATE public.users SET role = :role WHERE LOWER(email) = :email",
                    {"email": email, "role": role},
                )
                st.success("Global role updated.")

                if password:
                    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                    run_execute(
                        "UPDATE public.users SET password_hash = :pw WHERE LOWER(email) = :email",
                        {"email": email, "pw": hashed},
                    )
                    st.success("Password updated.")

            uid = get_user_id(email)
            if not uid:
                st.error("Could not resolve user_id after save. Check users table.")
                st.stop()

            email_norm = email.strip().lower()

            # ✅ Ensure this user exists in resource_pool (inactive by default)
            run_execute(
                """
                INSERT INTO public.resource_pool (full_name, role, skillset, department, is_active, user_id)
                SELECT :full_name, NULL, NULL, NULL, FALSE, :uid
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.resource_pool WHERE user_id = :uid
                )
                """,
                {
                    "full_name": (full_name or email_norm).strip(),
                    "uid": int(uid),
                },
            )

            # ---------------- CLIENT ROLES (DB stores lowercase) ----------------
            run_execute(
                "DELETE FROM public.user_client_permissions WHERE user_id = :uid",
                {"uid": int(uid)},
            )

            for cid, crole in client_roles.items():
                crole_lower = to_db_role(crole)

                if show_debug:
                    st.write(f"**Saving client {cid}:** role = '{crole_lower}'")

                if crole_lower not in CLIENT_ROLES:
                    st.error(f"Invalid client role: '{crole_lower}' (original: '{crole}')")
                    st.stop()

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
                        :role
                    )
                    ON CONFLICT (user_id, client_id)
                    DO UPDATE SET
                        role       = EXCLUDED.role,
                        user_email = EXCLUDED.user_email
                    """,
                    {
                        "uid": int(uid),
                        "email": email_norm,
                        "cid": int(cid),
                        "role": crole_lower,
                    },
                )

            # ---------------- PROJECT ACCESS (DB expects UPPERCASE) ----------------
            run_execute(
                "DELETE FROM public.user_project_permissions WHERE user_id = :uid",
                {"uid": int(uid)},
            )

            for cid, crole in client_roles.items():
                crole_lower = crole.strip().lower()
                access_upper = CLIENT_ROLE_TO_PROJECT_ACCESS.get(crole_lower, "VIEWER")

                if show_debug:
                    st.write(f"**Processing client {cid}:** '{crole_lower}' → '{access_upper}'")

                if access_upper not in PROJECT_ACCESS_LEVELS:
                    st.error(f"Invalid project access level: '{access_upper}' (from role: '{crole_lower}')")
                    st.stop()

                run_execute(
                    """
                    INSERT INTO public.user_project_permissions (user_id, project_id, access_level)
                    SELECT :uid, p.project_id, :access
                    FROM public.projects p
                    WHERE p.client_id = :cid
                    ON CONFLICT (user_id, project_id)
                    DO UPDATE SET access_level = EXCLUDED.access_level
                    """,
                    {
                        "uid": int(uid),
                        "cid": int(cid),
                        "access": access_upper,
                    },
                )

            st.success("✅ User client roles & derived project access updated successfully!")
            st.session_state.generated_pw = ""
            st.balloons()
            st.rerun()

# =========================================================
# TAB 5 — DELETE USER
# =========================================================
with tab_delete:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🗑️ Delete User</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    delete_email = st.selectbox(
        "Select user to delete",
        ["(none)"] + (users_df["email"].tolist() if not users_df.empty else []),
    )

    if delete_email != "(none)":
        if delete_email == st.session_state.get("email"):
            st.error("You cannot delete the account you're logged into.")
        else:
            if st.button("🗑️ Confirm Delete", use_container_width=True):
                run_execute(
                    "DELETE FROM public.users WHERE LOWER(email) = LOWER(:email)",
                    {"email": delete_email},
                )
                st.warning(f"User '{delete_email}' deleted.")
                st.rerun()

pmo_footer()
