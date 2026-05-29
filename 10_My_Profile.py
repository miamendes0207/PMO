# ============================================================
# 10_👤_My_Profile.py — ScopeSight v3.7
# ============================================================

import os
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
)

# UI
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# client_code generation
from modules.client_filesystem import safe_fs_name



# ---------------------------------------------------------
# DEV MODE SUPPORT
# ---------------------------------------------------------
query = st.query_params

if query.get("dev") == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True


# ---------------------------------------------------------
# LOGIN REQUIRED + UI SETUP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="👤 My Profile")
render_sidebar()


# ---------------------------------------------------------
# STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

.nfr-card {
    background: white;
    border: 2px solid #4facfe;
    padding: 1.25rem 1.25rem;
    border-radius: 12px;
    margin: 1rem 0;
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.12);
}
.nfr-card h3 {
    color: #0077be;
    margin: 0 0 0.75rem 0;
    font-size: 1.15rem;
    font-weight: 800;
}

.info-row {
    background: #f0f9ff;
    padding: 0.7rem 0.95rem;
    margin: 0.45rem 0;
    border-radius: 8px;
    border-left: 4px solid #4facfe;
}
.info-row strong { color: #0077be; }

.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 0.9rem 1.25rem;
    border-radius: 10px;
    margin: 0.75rem 0 0.75rem 0;
}
.section-header h3 {
    color: white;
    margin: 0;
    font-size: 1.15rem;
    font-weight: 800;
}

.step-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.7rem 0.95rem;
    border-radius: 8px;
    margin: 1.05rem 0 0.65rem 0;
}
.step-header h4 {
    color: #0077be;
    margin: 0;
    font-size: 1.02rem;
    font-weight: 800;
}

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 0.95rem 1rem;
    border-radius: 8px;
    margin: 0.85rem 0;
}

.permission-pill {
    display: inline-block;
    padding: 0.23rem 0.62rem;
    border-radius: 999px;
    background: #eef6ff;
    border: 1px solid #bcdcff;
    color: #0b5394;
    font-weight: 800;
    font-size: 0.9rem;
}

.small-muted {
    color: #5b6b7a;
    font-size: 0.92rem;
}

div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.02rem;
    font-weight: 800;
    padding: 0.62rem 1.25rem;
    border: none;
    border-radius: 10px;
    transition: all 0.2s ease;
}
div.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 12px rgba(79, 172, 254, 0.30);
}

label { font-weight: 650 !important; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def clear_keys(*keys: str):
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]


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


def _first_existing(colset: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colset:
            return c
    return None


def _select_existing(table: str, candidates: list[str]) -> list[str]:
    cols = _table_columns(table)
    return [c for c in candidates if c in cols]


def _insert_requester_client_access(user_id: int, email: str, client_id: int, role_value: str):
    cols = _table_columns("user_client_permissions")
    role_col = _first_existing(cols, ["role", "access_level"]) or "role"

    email_col = None
    if "user_email" in cols:
        email_col = "user_email"
    elif "email" in cols:
        email_col = "email"

    if email_col:
        run_execute(
            f"""
            INSERT INTO public.user_client_permissions (user_id, {email_col}, client_id, {role_col})
            VALUES (:uid, :uem, :cid, :role)
            ON CONFLICT DO NOTHING
            """,
            {"uid": int(user_id), "uem": email, "cid": int(client_id), "role": role_value},
        )
    else:
        run_execute(
            f"""
            INSERT INTO public.user_client_permissions (user_id, client_id, {role_col})
            VALUES (:uid, :cid, :role)
            ON CONFLICT DO NOTHING
            """,
            {"uid": int(user_id), "cid": int(client_id), "role": role_value},
        )


def _nice_dt(v):
    try:
        if pd.isna(v):
            return ""
        return pd.to_datetime(v).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return v


def _norm_str(x) -> str:
    return ("" if x is None else str(x)).strip()



# ---------------------------------------------------------
# One-time reset
# ---------------------------------------------------------
if "profile_page_loaded" not in st.session_state:
    st.session_state["profile_page_loaded"] = True
    clear_keys(
        "req_client_reason", "req_project_reason", "req_role_reason",
        "req_new_client_name", "req_new_client_code", "req_new_client_desc", "req_new_client_notes",
        "profile_new_skill_name", "profile_new_skill_category", "profile_new_skill_rating",
        "pw_old", "pw_new", "pw_confirm",
    )


# ---------------------------------------------------------
# LOAD USER RECORD
# ---------------------------------------------------------
email = (st.session_state.get("email") or "").strip().lower()
record = get_user_by_email(email)

if not record:
    st.error("❌ Unable to load your profile. Contact an administrator.")
    pmo_footer()
    st.stop()

global_role = (record.get("role") or "user").strip().lower()
stored_hash = record.get("password_hash")
current_role = (st.session_state.get("role") or global_role or "user").strip().lower()

user_row = run_query(
    """
    SELECT user_id, full_name
    FROM public.users
    WHERE LOWER(email) = :email
    """,
    {"email": email},
)

if user_row is None or user_row.empty:
    st.error("❌ Could not resolve your user ID. Contact an administrator.")
    pmo_footer()
    st.stop()

user_id = int(user_row.iloc[0]["user_id"])
user_full_name = user_row.iloc[0].get("full_name") or email


# ============================================================
# TABS
# ============================================================
tab_account, tab_access, tab_request, tab_skills, tab_password = st.tabs(
    ["👤 Account", "🔐 Access & Permissions", "📨 Request Access", "🧩 My Skills", "🔑 Change Password"]
)


# ============================================================
# TAB 1: ACCOUNT DETAILS (no metrics)
# ============================================================
with tab_account:
    st.markdown(
        """
        <div class='section-header'>
            <h3>👤 Account Details</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class='nfr-card'>
            <h3>✓ Signed In</h3>
            <div class='info-row'><strong>Name:</strong> {_norm_str(user_full_name)}</div>
            <div class='info-row'><strong>Email:</strong> <code>{email}</code></div>
            <div class='info-row'><strong>Global Role:</strong> <span class='permission-pill'>{global_role}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("What do the roles mean?", expanded=False):
        st.markdown(
            """
- **viewer**: read-only access  
- **user**: standard delivery access (create/update items where permitted)  
- **exec**: broader reporting + governance features  
- **ceo**: portfolio-level views (clients + executive summaries)
            """.strip()
        )


# ============================================================
# TAB 2: ACCESS & PERMISSIONS
# ============================================================
with tab_access:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🔐 Access & Permissions</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>Tip</strong><br/>
            If something is missing here, ask an administrator to update your client/project assignments.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # CLIENT ACCESS
    st.markdown(
        """
        <div class='step-header'>
            <h4>🔐 Client Access</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ucp_cols = _table_columns("user_client_permissions")
    ucp_role_col = _first_existing(ucp_cols, ["role", "access_level"]) or "role"

    client_search = st.text_input("Search clients", placeholder="Type to filter…", key="perm_client_search")

    client_perms = run_query(
        f"""
        SELECT
            cs.client_name,
            ucp.{ucp_role_col} AS role
        FROM public.user_client_permissions ucp
        JOIN public.client_scaffold cs
          ON cs.id = ucp.client_id
        WHERE ucp.user_id = :uid
        ORDER BY cs.client_name
        """,
        {"uid": user_id},
    )

    if client_perms is None or client_perms.empty:
        st.info("No client access assigned.")
    else:
        df = client_perms.copy()
        if client_search.strip():
            df = df[df["client_name"].astype(str).str.lower().str.contains(client_search.strip().lower())]
        st.dataframe(df, use_container_width=True, hide_index=True)

    # PROJECT ACCESS
    st.markdown(
        """
        <div class='step-header'>
            <h4>📁 Project Access</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    upp_cols = _table_columns("user_project_permissions")
    upp_role_col = _first_existing(upp_cols, ["role", "access_level"])

    project_search = st.text_input("Search projects", placeholder="Type to filter…", key="perm_project_search")

    if not upp_role_col:
        st.error("user_project_permissions is missing both 'role' and 'access_level'.")
    else:
        project_perms = run_query(
            f"""
            SELECT
                p.project_name,
                cs.client_name,
                upp.{upp_role_col} AS role
            FROM public.user_project_permissions upp
            JOIN public.projects p
              ON p.project_id = upp.project_id
            JOIN public.client_scaffold cs
              ON cs.id = p.client_id
            WHERE upp.user_id = :uid
            ORDER BY cs.client_name, p.project_name
            """,
            {"uid": user_id},
        )

        if project_perms is None or project_perms.empty:
            st.info("No project-level access assigned.")
        else:
            dfp = project_perms.copy()
            if project_search.strip():
                q = project_search.strip().lower()
                dfp = dfp[
                    dfp["project_name"].astype(str).str.lower().str.contains(q)
                    | dfp["client_name"].astype(str).str.lower().str.contains(q)
                ]
            st.dataframe(dfp, use_container_width=True, hide_index=True)


# ============================================================
# TAB 3: REQUEST ACCESS (consistent subtitle style)
# ============================================================
with tab_request:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📨 Request Access</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            Request access to clients/projects you can’t currently see, or ask to change your global role.
            Requests are sent to admins via the <strong>User Access Manager</strong>.
            <br/><br/>
            <strong>CEO/Exec:</strong> You can also submit a <em>New Client</em> request — it is created as
            <strong>Pending</strong> and only visible to you (and admins) until approved.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not _table_exists("access_requests"):
        st.warning(
            "Access request logging is not enabled yet (missing table: access_requests). "
            "Ask an admin to run the access request table migration."
        )
    else:
        # existing access (to remove from request lists)
        existing_client_ids = set()
        tmp = run_query("SELECT client_id FROM public.user_client_permissions WHERE user_id = :uid", {"uid": user_id})
        if tmp is not None and not tmp.empty and "client_id" in tmp.columns:
            existing_client_ids = set(tmp["client_id"].astype(int).tolist())

        existing_project_ids = set()
        tmp = run_query("SELECT project_id FROM public.user_project_permissions WHERE user_id = :uid", {"uid": user_id})
        if tmp is not None and not tmp.empty and "project_id" in tmp.columns:
            existing_project_ids = set(tmp["project_id"].astype(int).tolist())

        req_options = ["Client access", "Project access", "Change my global role"]
        if current_role in ("exec", "ceo"):
            req_options.append("Add a new client")

        req_type = st.radio(
            "What do you want to request?",
            req_options,
            horizontal=True,
            key="req_type_radio",
        )
        st.markdown("<hr/>", unsafe_allow_html=True)

        all_clients = run_query(
            """
            SELECT id AS client_id, client_name
            FROM public.client_scaffold
            WHERE status = 'approved'
            ORDER BY client_name
            """
        )
        all_projects = run_query(
            """
            SELECT p.project_id, p.project_name, cs.client_name, p.client_id
            FROM public.projects p
            JOIN public.client_scaffold cs ON cs.id = p.client_id
            WHERE p.status IN ('open','active','in_progress','live','delivery')
               OR p.status IS NULL
            ORDER BY cs.client_name, p.project_name
            """
        )

        # ---------- CLIENT ACCESS ----------
        if req_type == "Client access":
            st.markdown(
                """
                <div class='step-header'>
                    <h4>🔐 Request Client Access</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if all_clients is None or all_clients.empty:
                st.info("No clients available to request.")
            else:
                req_clients = all_clients.copy()
                req_clients["client_id"] = req_clients["client_id"].astype(int)
                req_clients = req_clients[~req_clients["client_id"].isin(existing_client_ids)]

                if req_clients.empty:
                    st.success("You already have access to all approved clients.")
                else:
                    search = st.text_input("Filter list", placeholder="Type a client name…", key="req_client_filter")
                    show_df = req_clients.copy()
                    if search.strip():
                        show_df = show_df[show_df["client_name"].astype(str).str.lower().str.contains(search.strip().lower())]

                    if show_df.empty:
                        st.info("No matches for that filter.")
                    else:
                        client_label = show_df.apply(lambda r: f"{r['client_name']} (ID {int(r['client_id'])})", axis=1)
                        selected = st.selectbox("Select a client", client_label.tolist(), key="req_client_select")

                        desired_role = st.selectbox(
                            "Requested role",
                            ["viewer", "user", "exec", "ceo"],
                            index=0,
                            key="req_client_role",
                        )
                        reason = st.text_area(
                            "Reason",
                            placeholder="e.g. I’m supporting delivery reporting for this client…",
                            key="req_client_reason",
                        )

                        if st.button("Submit client request", use_container_width=True, key="req_client_submit"):
                            chosen_row = show_df.iloc[client_label.tolist().index(selected)]
                            run_execute(
                                """
                                INSERT INTO public.access_requests
                                    (user_id, user_email, request_type, target_type, target_id, target_label, requested_role, reason)
                                VALUES
                                    (:uid, :email, 'client_access', 'client', :tid, :tlabel, :rrole, :reason)
                                """,
                                {
                                    "uid": user_id,
                                    "email": email,
                                    "tid": int(chosen_row["client_id"]),
                                    "tlabel": str(chosen_row["client_name"]),
                                    "rrole": str(desired_role),
                                    "reason": (reason or "").strip(),
                                },
                            )
                            st.success("✅ Client access request submitted.")
                            clear_keys("req_client_reason")
                            st.rerun()

        # ---------- PROJECT ACCESS ----------
        elif req_type == "Project access":
            st.markdown(
                """
                <div class='step-header'>
                    <h4>📁 Request Project Access</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if all_projects is None or all_projects.empty:
                st.info("No projects available to request.")
            else:
                req_projects = all_projects.copy()
                req_projects["project_id"] = req_projects["project_id"].astype(int)
                req_projects = req_projects[~req_projects["project_id"].isin(existing_project_ids)]

                if req_projects.empty:
                    st.success("You already have access to all available projects.")
                else:
                    search = st.text_input("Filter list", placeholder="Type client or project name…", key="req_project_filter")
                    show_df = req_projects.copy()
                    if search.strip():
                        q = search.strip().lower()
                        show_df = show_df[
                            show_df["client_name"].astype(str).str.lower().str.contains(q)
                            | show_df["project_name"].astype(str).str.lower().str.contains(q)
                        ]

                    if show_df.empty:
                        st.info("No matches for that filter.")
                    else:
                        project_label = show_df.apply(
                            lambda r: f"{r['client_name']} → {r['project_name']} (Project ID {int(r['project_id'])})",
                            axis=1,
                        )
                        selected = st.selectbox("Select a project", project_label.tolist(), key="req_project_select")

                        desired_role = st.selectbox(
                            "Requested role",
                            ["viewer", "user", "exec", "ceo"],
                            index=0,
                            key="req_project_role",
                        )
                        reason = st.text_area(
                            "Reason",
                            placeholder="e.g. I need access to manage RAID and reporting…",
                            key="req_project_reason",
                        )

                        if st.button("Submit project request", use_container_width=True, key="req_project_submit"):
                            chosen_row = show_df.iloc[project_label.tolist().index(selected)]
                            run_execute(
                                """
                                INSERT INTO public.access_requests
                                    (user_id, user_email, request_type, target_type, target_id, target_label, requested_role, reason)
                                VALUES
                                    (:uid, :email, 'project_access', 'project', :tid, :tlabel, :rrole, :reason)
                                """,
                                {
                                    "uid": user_id,
                                    "email": email,
                                    "tid": int(chosen_row["project_id"]),
                                    "tlabel": f"{chosen_row['client_name']} → {chosen_row['project_name']}",
                                    "rrole": str(desired_role),
                                    "reason": (reason or "").strip(),
                                },
                            )
                            st.success("✅ Project access request submitted.")
                            clear_keys("req_project_reason")
                            st.rerun()

        # ---------- NEW CLIENT ----------
        elif req_type == "Add a new client":
            st.markdown(
                """
                <div class='step-header'>
                    <h4>➕ Request a New Client (Pending)</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                """
                <div class='info-box'>
                    This creates a <strong>Pending</strong> client record visible only to you (and admins) until approved.
                    <br/><br/>
                    <strong>Important:</strong> A valid <code>client_code</code> is required — if you leave it blank we will generate one from the client name.
                </div>
                """,
                unsafe_allow_html=True,
            )

            new_client_name = st.text_input("Client name", placeholder="e.g. N Brown", key="req_new_client_name")
            new_client_code = st.text_input("Client code", placeholder="e.g. n_brown", key="req_new_client_code")
            new_client_desc = st.text_area("Description (optional)", placeholder="What is this client / what work is expected?", key="req_new_client_desc")
            new_client_notes = st.text_area("Additional notes (optional)", placeholder="Anything admin needs to know (billing entity, region, contacts, etc.)", key="req_new_client_notes")

            if st.button("Submit new client request", use_container_width=True, key="req_new_client_submit"):
                if not (new_client_name or "").strip():
                    st.error("Please enter a client name.")
                    st.stop()

                raw_code = (new_client_code or "").strip()
                final_code = safe_fs_name(raw_code) if raw_code else safe_fs_name(new_client_name.strip())

                if not final_code:
                    st.error("❌ Could not generate a valid client code. Please enter a simpler client name or code.")
                    st.stop()

                dupe = run_query(
                    "SELECT 1 FROM public.client_scaffold WHERE LOWER(client_code)=LOWER(:c) LIMIT 1",
                    {"c": final_code},
                )
                if dupe is not None and not dupe.empty:
                    st.error(f"❌ Client code '{final_code}' already exists. Please enter a different code.")
                    st.stop()

                run_execute(
                    """
                    INSERT INTO public.client_scaffold
                        (client_name, client_code, settings, status, submitted_by, submitted_on)
                    VALUES
                        (:name, :code, '{}'::jsonb, 'pending', :uid, NOW())
                    """,
                    {
                        "name": new_client_name.strip(),
                        "code": final_code,
                        "uid": str(user_id),
                    },
                )

                new_row = run_query(
                    """
                    SELECT id
                    FROM public.client_scaffold
                    WHERE LOWER(client_code) = LOWER(:code)
                    ORDER BY submitted_on DESC
                    LIMIT 1
                    """,
                    {"code": final_code},
                )
                if new_row is None or new_row.empty:
                    st.error("❌ Created client, but could not resolve its ID. Contact an admin.")
                    st.stop()

                new_client_id = int(new_row.iloc[0]["id"])

                requester_role = "exec" if current_role in ("exec", "ceo") else "viewer"
                _insert_requester_client_access(
                    user_id=user_id,
                    email=email,
                    client_id=new_client_id,
                    role_value=requester_role,
                )

                details = f"""
Client Code: {final_code}
Description: {_norm_str(new_client_desc) or 'N/A'}
Notes: {_norm_str(new_client_notes) or 'N/A'}
client_id: {new_client_id}
""".strip()

                run_execute(
                    """
                    INSERT INTO public.access_requests
                        (user_id, user_email, request_type, target_type, target_id, target_label, requested_role, reason)
                    VALUES
                        (:uid, :email, 'new_client', 'client_new', :tid, :tlabel, NULL, :reason)
                    """,
                    {
                        "uid": user_id,
                        "email": email,
                        "tid": new_client_id,
                        "tlabel": new_client_name.strip(),
                        "reason": details,
                    },
                )

                st.success(f"✅ New client submitted as PENDING (code: {final_code}).")
                clear_keys("req_new_client_name", "req_new_client_code", "req_new_client_desc", "req_new_client_notes")
                st.rerun()

            st.markdown(
                """
                <div class='step-header'>
                    <h4>🕒 My Pending Client Submissions</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            pending = run_query(
                """
                SELECT id, client_name, client_code, status, submitted_on, approved_on, rejected_on, rejection_reason
                FROM public.client_scaffold
                WHERE NULLIF(submitted_by::text,'') = :uid_txt
                  AND status IN ('pending','awaiting_approval','rejected','withdrawn')
                ORDER BY submitted_on DESC
                """,
                {"uid_txt": str(user_id)},
            )

            if pending is None or pending.empty:
                st.info("No pending/rejected client submissions yet.")
            else:
                dfp = pending.copy()
                for col in ["submitted_on", "approved_on", "rejected_on"]:
                    if col in dfp.columns:
                        dfp[col] = dfp[col].apply(_nice_dt)
                st.dataframe(dfp, use_container_width=True, hide_index=True)

        # ---------- ROLE CHANGE ----------
        else:
            st.markdown(
                """
                <div class='step-header'>
                    <h4>🧑‍⚖️ Request a Global Role Change</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class='info-row'>
                    <strong>Current global role:</strong>
                    &nbsp;<span class='permission-pill'>{global_role}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            requested_global_role = st.selectbox("Requested global role", ["viewer", "user", "exec", "ceo"], index=0, key="req_role_select")
            reason = st.text_area("Reason", placeholder="Explain why this role change is needed…", key="req_role_reason")

            if st.button("Submit role change request", use_container_width=True, key="req_role_submit"):
                if not (reason or "").strip():
                    st.error("Please add a reason for the role change request.")
                    st.stop()

                run_execute(
                    """
                    INSERT INTO public.access_requests
                        (user_id, user_email, request_type, target_type, target_id, target_label, requested_role, reason)
                    VALUES
                        (:uid, :email, 'role_change', 'global_role', NULL, 'Global Role', :rrole, :reason)
                    """,
                    {"uid": user_id, "email": email, "rrole": str(requested_global_role), "reason": (reason or "").strip()},
                )
                st.success("✅ Role change request submitted.")
                clear_keys("req_role_reason")
                st.rerun()

        # Recent requests (always same subtitle style)
        st.markdown(
            """
            <div class='step-header'>
                <h4>📌 My Recent Requests</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        my_reqs = run_query(
            """
            SELECT request_type, target_label, requested_role, status, created_at, reviewed_on, review_notes
            FROM public.access_requests
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT 25
            """,
            {"uid": user_id},
        )

        if my_reqs is None or my_reqs.empty:
            st.info("No requests submitted yet.")
        else:
            dfr = my_reqs.copy()
            for col in ["created_at", "reviewed_on"]:
                if col in dfr.columns:
                    dfr[col] = dfr[col].apply(_nice_dt)
            st.dataframe(dfr, use_container_width=True, hide_index=True)


# ============================================================
# TAB 4: MY SKILLS (clean + structured)
# ============================================================
with tab_skills:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🧩 My Skills & Expertise</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            Skills and ratings (0–5) are stored in the central resource pool and used for allocation and reporting.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not (_table_exists("skills") and _table_exists("resource_skills")):
        st.warning(
            "Skills data is not available yet (missing tables: skills/resource_skills). "
            "Ask an admin to run the Skills Matrix import."
        )
    else:
        # Resolve resource_id (schema safe)
        rp_cols = _table_columns("resource_pool")
        has_user_id_col = "user_id" in rp_cols
        has_email_col = "email" in rp_cols

        rp_select = _select_existing("resource_pool", ["resource_id", "full_name", "email", "user_id", "role", "department"])
        if "resource_id" not in rp_select:
            st.error("resource_pool is missing required column: resource_id")
        else:
            resource_row = None

            if has_email_col:
                resource_row = run_query(
                    f"SELECT {', '.join(rp_select)} FROM public.resource_pool WHERE LOWER(email)=:email LIMIT 1",
                    {"email": email},
                )

            if (resource_row is None or resource_row.empty) and has_user_id_col:
                resource_row = run_query(
                    f"SELECT {', '.join(rp_select)} FROM public.resource_pool WHERE user_id=:uid LIMIT 1",
                    {"uid": user_id},
                )

            if resource_row is None or resource_row.empty:
                insert_cols, insert_vals, params = [], [], {}

                if "full_name" in rp_cols:
                    insert_cols.append("full_name"); insert_vals.append(":full_name"); params["full_name"] = user_full_name
                if has_email_col:
                    insert_cols.append("email"); insert_vals.append(":email"); params["email"] = email
                if has_user_id_col:
                    insert_cols.append("user_id"); insert_vals.append(":uid"); params["uid"] = user_id
                if "role" in rp_cols:
                    insert_cols.append("role"); insert_vals.append(":role"); params["role"] = global_role
                if "department" in rp_cols:
                    insert_cols.append("department"); insert_vals.append(":dept"); params["dept"] = ""

                if insert_cols:
                    run_execute(
                        f"INSERT INTO public.resource_pool ({', '.join(insert_cols)}) VALUES ({', '.join(insert_vals)})",
                        params,
                    )

                # re-fetch
                if has_email_col:
                    resource_row = run_query(
                        f"SELECT {', '.join(rp_select)} FROM public.resource_pool WHERE LOWER(email)=:email LIMIT 1",
                        {"email": email},
                    )
                else:
                    resource_row = run_query(
                        f"SELECT {', '.join(rp_select)} FROM public.resource_pool WHERE user_id=:uid LIMIT 1",
                        {"uid": user_id},
                    )

            if resource_row is None or resource_row.empty:
                st.error("❌ Could not resolve your resource record in resource_pool. Contact an administrator.")
            else:
                resource_id = int(resource_row.iloc[0]["resource_id"])

                # Controls row
                c1, c2, c3 = st.columns([1, 1, 2])
                with c1:
                    show_only_rated = st.toggle("Rated only (>0)", value=True, key="skills_only_rated")
                with c2:
                    group_view = st.selectbox("View", ["Table", "By Category"], index=0, key="skills_view_mode")
                with c3:
                    skill_search = st.text_input("Search", placeholder="Filter skills…", key="skills_search")

                skills_df = run_query(
                    """
                    SELECT
                        s.skill_name,
                        COALESCE(NULLIF(s.category,''), 'General') AS category,
                        rs.rating
                    FROM public.resource_skills rs
                    JOIN public.skills s
                      ON s.skill_id = rs.skill_id
                    WHERE rs.resource_id = :rid
                      AND (:only_rated = FALSE OR rs.rating > 0)
                    ORDER BY rs.rating DESC, s.skill_name
                    """,
                    {"rid": resource_id, "only_rated": bool(show_only_rated)},
                )

                # Apply search filter
                if skills_df is not None and not skills_df.empty and skill_search.strip():
                    q = skill_search.strip().lower()
                    skills_df = skills_df[
                        skills_df["skill_name"].astype(str).str.lower().str.contains(q)
                        | skills_df["category"].astype(str).str.lower().str.contains(q)
                    ]

                # Display
                st.markdown(
                    """
                    <div class='step-header'>
                        <h4>✅ My Skills</h4>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if skills_df is None or skills_df.empty:
                    st.info("No skills found yet for your profile.")
                else:
                    if group_view == "By Category":
                        # grouped category view - cleaner than one long table
                        cats = sorted(skills_df["category"].astype(str).unique().tolist())
                        for cat in cats:
                            block = skills_df[skills_df["category"].astype(str) == cat].copy()
                            block = block.sort_values(["rating", "skill_name"], ascending=[False, True])
                            st.markdown(f"**{cat}**")
                            st.dataframe(block[["skill_name", "rating"]], use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(skills_df, use_container_width=True, hide_index=True)

                # Edit rating
                st.markdown(
                    """
                    <div class='step-header'>
                        <h4>✏️ Update a Rating</h4>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                base_for_edit = run_query(
                    """
                    SELECT s.skill_name, rs.rating
                    FROM public.resource_skills rs
                    JOIN public.skills s ON s.skill_id = rs.skill_id
                    WHERE rs.resource_id = :rid
                    ORDER BY s.skill_name
                    """,
                    {"rid": resource_id},
                )

                if base_for_edit is None or base_for_edit.empty:
                    st.info("Once skills exist for your profile, you can update ratings here.")
                else:
                    skill_options = base_for_edit["skill_name"].astype(str).tolist()
                    col1, col2, col3 = st.columns([2, 1, 1])

                    with col1:
                        selected_skill = st.selectbox("Skill", skill_options, index=0, key="edit_skill_select")
                    with col2:
                        cur = base_for_edit.loc[base_for_edit["skill_name"] == selected_skill]
                        cur_rating = int(cur.iloc[0]["rating"]) if not cur.empty else 0
                        new_rating = st.select_slider("Rating", options=[0, 1, 2, 3, 4, 5], value=cur_rating, key="edit_skill_rating")
                    with col3:
                        st.write(""); st.write("")
                        save_existing = st.button("Save rating", use_container_width=True, key="edit_skill_save")

                    if save_existing:
                        sid_df = run_query("SELECT skill_id FROM public.skills WHERE skill_name = :sn LIMIT 1", {"sn": selected_skill})
                        if sid_df is None or sid_df.empty:
                            st.error("Could not resolve skill ID. Contact an admin.")
                            st.stop()

                        skill_id = int(sid_df.iloc[0]["skill_id"])

                        run_execute(
                            """
                            INSERT INTO public.resource_skills (resource_id, skill_id, rating)
                            VALUES (:rid, :sid, :rt)
                            ON CONFLICT (resource_id, skill_id)
                            DO UPDATE SET rating = EXCLUDED.rating, updated_at = NOW()
                            """,
                            {"rid": resource_id, "sid": skill_id, "rt": int(new_rating)},
                        )
                        st.success(f"✅ Updated: {selected_skill} = {int(new_rating)}")
                        st.rerun()

                # Add new skill
                st.markdown(
                    """
                    <div class='step-header'>
                        <h4>➕ Add a New Skill</h4>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.form("add_new_skill_form"):
                    new_skill_name = st.text_input("New skill name", placeholder="e.g. Power BI, Scrum, Data Modelling", key="profile_new_skill_name")
                    new_skill_category = st.text_input("Category (optional)", placeholder="e.g. Delivery, Data, PMO, Tooling", key="profile_new_skill_category")
                    new_skill_rating = st.select_slider("Initial rating", options=[0, 1, 2, 3, 4, 5], value=3, key="profile_new_skill_rating")

                    add_submit = st.form_submit_button("Add skill")

                    if add_submit:
                        if not (new_skill_name or "").strip():
                            st.error("Please enter a skill name.")
                            st.stop()

                        run_execute(
                            """
                            INSERT INTO public.skills (skill_name, category)
                            VALUES (:sn, :cat)
                            ON CONFLICT (skill_name)
                            DO UPDATE SET category = EXCLUDED.category
                            """,
                            {"sn": new_skill_name.strip(), "cat": (new_skill_category or "").strip()},
                        )

                        sid_df = run_query("SELECT skill_id FROM public.skills WHERE skill_name = :sn LIMIT 1", {"sn": new_skill_name.strip()})
                        if sid_df is None or sid_df.empty:
                            st.error("Could not resolve the new skill after insert. Contact an admin.")
                            st.stop()

                        skill_id = int(sid_df.iloc[0]["skill_id"])

                        run_execute(
                            """
                            INSERT INTO public.resource_skills (resource_id, skill_id, rating)
                            VALUES (:rid, :sid, :rt)
                            ON CONFLICT (resource_id, skill_id)
                            DO UPDATE SET rating = EXCLUDED.rating, updated_at = NOW()
                            """,
                            {"rid": resource_id, "sid": skill_id, "rt": int(new_skill_rating)},
                        )

                        st.success(f"✅ Added: {new_skill_name.strip()} ({int(new_skill_rating)})")
                        clear_keys("profile_new_skill_name", "profile_new_skill_category", "profile_new_skill_rating")
                        st.rerun()


# ============================================================
# TAB 5: PASSWORD CHANGE (no dropdown/expander)
# ============================================================
with tab_password:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🔑 Change Password</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>Security</strong><br/>
            Use a strong password (length + mix of characters). Your new password takes effect immediately.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='step-header'>
            <h4>🔑 Update Password</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    old_pw = st.text_input("Current password", type="password", key="pw_old")
    new_pw = st.text_input("New password", type="password", key="pw_new")
    confirm_pw = st.text_input("Confirm new password", type="password", key="pw_confirm")

    if new_pw:
        valid_strength, msg = validate_password_strength(new_pw)
        color = "#4CAF50" if valid_strength else "#E74C3C"
        label = "Strong password ✔️" if valid_strength else f"Weak password ✖️ — {msg}"

        st.markdown(
            f"""
            <div style='padding:10px; background:{color}; color:white;
                        text-align:center; border-radius:10px; margin-bottom:10px; font-weight:900;'>
                {label}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.button("Update Password", use_container_width=True, key="pw_update_btn"):
        if not old_pw or not new_pw or not confirm_pw:
            st.error("⚠ Please fill in all fields.")
            st.stop()

        if new_pw != confirm_pw:
            st.error("❌ New passwords do not match.")
            st.stop()

        valid, msg = validate_password_strength(new_pw)
        if not valid:
            st.error(f"❌ {msg}")
            st.stop()

        if not stored_hash or not bcrypt.checkpw(old_pw.encode(), stored_hash.encode()):
            st.error("❌ Incorrect current password.")
            st.stop()

        if bcrypt.checkpw(new_pw.encode(), stored_hash.encode()):
            st.error("⚠ New password cannot be identical to the old one.")
            st.stop()

        new_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()

        run_execute(
            """
            UPDATE public.users
            SET password_hash = :pw
            WHERE LOWER(email) = :email
            """,
            {"pw": new_hash, "email": email},
        )

        st.success("✅ Password updated successfully.")
        st.info("Your new password takes effect immediately.")
        clear_keys("pw_old", "pw_new", "pw_confirm")
        st.rerun()

pmo_footer()
