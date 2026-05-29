# ================================================
# 4_📝_Action_Manager.py — ScopeSight v3.7
# + 🤖 Action AI Helper (shorthand → optional prefill)
# + 🔔 New Notifications System (db.notify + overlay)
# ================================================

import os
import datetime as dt

import pandas as pd
import streamlit as st
from modules.permissions import get_project_member_emails

# ------------------------------------------------------------
# PAGE CONFIG (must be the first Streamlit call)
# ------------------------------------------------------------
st.set_page_config(
    page_title="📝 Action Manager",
    page_icon="📝",
    layout="wide",
)

# ------------------------------------------------------------
# IMPORTS AFTER PAGE CONFIG
# ------------------------------------------------------------
from auth.login import require_login
from modules.ui_hide_nav import hide_streamlit_nav
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar

from modules.db import (
    run_query,
    add_action,
    update_action,
    notify,  # ✅ NEW
)

from modules.notifications_overlay import render_notifications_overlay  # ✅ NEW

from modules.log_utils import log_event
from modules.action_manager.action_config import STATUS_OPTIONS, PRIORITY_OPTIONS
from modules.raids.raids_config import BRAND_COLOURS

from modules.action_manager.action_ai import expand_action_shorthand


# ------------------------------------------------------------
# DEV OVERRIDES (robust query param handling)
# ------------------------------------------------------------
try:
    query = st.query_params
except AttributeError:
    query = st.experimental_get_query_params()

dev_flag = query.get("dev")
if isinstance(dev_flag, list):
    is_dev = "1" in dev_flag
else:
    is_dev = dev_flag == "1"

if is_dev:
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True

# ------------------------------------------------------------
# AUTH + THEME + NAV
# ------------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="📝 Action Manager")
render_sidebar()

user_email = (st.session_state.get("email", "system") or "system").strip().lower()
current_email = user_email

# ✅ Render notification overlay on this page
render_notifications_overlay(current_email or "")

# ------------------------------------------------------------
# STYLES
# ------------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

.nfr-card {
    background: white;
    border: 2px solid #4facfe;
    padding: 1.5rem;
    border-radius: 12px;
    margin: 1.5rem 0;
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.15);
}
.nfr-card h3 {
    color: #0077be;
    margin: 0 0 1rem 0;
    font-size: 1.3rem;
    font-weight: 600;
}
.info-row {
    background: #f0f9ff;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border-radius: 6px;
    border-left: 4px solid #4facfe;
}
.info-row strong { color: #0077be; }

.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.25rem 0 1rem 0;
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
    margin: 1.0rem 0 1rem 0;
}
.step-header h4 {
    color: #0077be;
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
}

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
}

.action-table-container {
    background: white;
    border: 2px solid #4facfe;
    border-radius: 12px;
    padding: 1rem;
    margin: 1.25rem 0;
    max-height: 550px;
    overflow-y: auto;
}

div.stButton > button,
div.stDownloadButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.05rem;
    font-weight: 600;
    padding: 0.65rem 1.5rem;
    border: none;
    border-radius: 8px;
    transition: all 0.2s ease;
}
div.stButton > button:hover,
div.stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 12px rgba(79, 172, 254, 0.35);
}

label { font-weight: 600 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# STATE RESET HELPERS
# ============================================================
def _clear_keys(prefixes: list[str]):
    """Delete any session_state keys that start with any of the given prefixes."""
    for k in list(st.session_state.keys()):
        if any(k.startswith(p) for p in prefixes):
            del st.session_state[k]


def _reset_new_form():
    _clear_keys(
        [
            "new_title",
            "new_detail",
            "new_comments",
            "new_owner_seed",
            "new_owner_",
            "new_status",
            "new_priority",
            "new_set_due",
            "new_due_date",
            "new_set_actual",
            "new_actual_date",
            "new_ai_nonce",
            "new_ai_shorthand_",
        ]
    )


def _reset_edit_form(action_id: int):
    p = f"edit_{action_id}"
    _clear_keys([f"{p}_"])


# ============================================================
# OWNER DROPDOWN DATA (project members)
# ============================================================
OWNER_MODE_OPTIONS = ["Select from project members", "Manual entry"]


def owner_picker(
    label: str,
    key_prefix: str,
    member_options: list[str],
    member_map: dict,
    current_owner: str | None = None,
) -> str:
    current_owner = (current_owner or "").strip()
    mode = st.radio(label, OWNER_MODE_OPTIONS, horizontal=True, key=f"{key_prefix}_mode")

    if mode == "Manual entry" or not member_options:
        return st.text_input("Owner (manual)", value=current_owner, key=f"{key_prefix}_manual")

    opts = ["— Select owner —"]
    if current_owner and current_owner.lower() not in [v.lower() for v in member_map.values()]:
        opts.append(f"Current: {current_owner}")
    opts.extend(member_options)

    default_index = 0
    if current_owner:
        for i, opt in enumerate(opts):
            if opt in member_map and member_map[opt].lower() == current_owner.lower():
                default_index = i
                break

    picked = st.selectbox("Owner (email)", opts, index=default_index, key=f"{key_prefix}_pick")

    if picked.startswith("Current: "):
        return current_owner
    if picked in member_map:
        return member_map[picked]
    return current_owner


# ============================================================
# AI APPLY HELPERS
# ============================================================
def apply_action_ai_to_state(prefix: str, parsed: dict):
    st.session_state[f"{prefix}_title"] = parsed.get("title") or ""
    st.session_state[f"{prefix}_detail"] = parsed.get("detail") or ""
    st.session_state[f"{prefix}_comments"] = parsed.get("comments") or ""

    if parsed.get("owner"):
        st.session_state[f"{prefix}_owner_seed"] = parsed["owner"]

    if parsed.get("status"):
        st.session_state[f"{prefix}_status"] = parsed["status"]

    if parsed.get("priority"):
        st.session_state[f"{prefix}_priority"] = parsed["priority"]

    due_dt = parsed.get("due_date_dt")
    if isinstance(due_dt, dt.date):
        st.session_state[f"{prefix}_set_due"] = True
        st.session_state[f"{prefix}_due_date"] = due_dt

    ac_dt = parsed.get("actual_close_date_dt")
    if isinstance(ac_dt, dt.date):
        st.session_state[f"{prefix}_set_actual"] = True
        st.session_state[f"{prefix}_actual_date"] = ac_dt


# ============================================================
# BUILD DISPLAY TABLE
# ============================================================
ACTIONS_HEADERS = [
    "No.",
    "Date Raised",
    "Subject",
    "Action Description",
    "Owner",
    "Target Close Date",
    "Actual Close Date",
    "Comments",
    "Status",
    "Priority",
    "Edit",
]


def build_display_df(source_df: pd.DataFrame) -> pd.DataFrame:
    if source_df.empty:
        return source_df

    df_disp = source_df.copy()
    df_disp["No."] = df_disp["action_id"]
    df_disp["Date Raised"] = pd.to_datetime(df_disp["date_raised"], errors="coerce").dt.date

    df_disp["Subject"] = df_disp["title"]
    df_disp["Action Description"] = df_disp["detail"]
    df_disp["Owner"] = df_disp["owner"]

    df_disp["Target Close Date"] = pd.to_datetime(df_disp["due_date"], errors="coerce").dt.date
    df_disp["Actual Close Date"] = pd.to_datetime(df_disp["actual_close_date"], errors="coerce").dt.date

    df_disp["Comments"] = df_disp.get("comments", "")
    df_disp["Status"] = df_disp.get("status", "")
    df_disp["Priority"] = df_disp.get("priority", "")
    df_disp["Edit"] = df_disp["action_id"]

    return df_disp[ACTIONS_HEADERS]


def style_table(dfi: pd.DataFrame):
    header_color = BRAND_COLOURS.get("header_blue", "#002060")
    return dfi.style.set_table_styles(
        [
            {
                "selector": "th",
                "props": [
                    ("background-color", header_color),
                    ("color", "white"),
                    ("font-weight", "bold"),
                ],
            }
        ]
    )


# ============================================================
# CLIENT & PROJECT SELECTION
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>🏢 Client & Project Selection</h3>
</div>
""",
    unsafe_allow_html=True,
)

clients_df = run_query(
    """
    SELECT 
        id AS client_id,
        client_name,
        client_code
    FROM client_scaffold
    WHERE status = 'approved'
    ORDER BY client_name
"""
)

if clients_df is None or clients_df.empty:
    st.error("⚠ No approved clients found.")
    pmo_footer()
    st.stop()

client_name = st.selectbox("Select Client", clients_df["client_name"], key="am_client")
client_row = clients_df[clients_df["client_name"] == client_name].iloc[0]
client_id = int(client_row["client_id"])
client_code = client_row.get("client_code")

projects_df = run_query(
    """
    SELECT project_id, project_name, project_code
    FROM projects
    WHERE client_id = :cid
      AND LOWER(status) = 'open'
    ORDER BY project_name
""",
    {"cid": client_id},
)

if projects_df is None or projects_df.empty:
    st.warning("⚠ This client has no open projects.")
    pmo_footer()
    st.stop()

project_name = st.selectbox("Select Project", projects_df["project_name"], key="am_project")
proj_row = projects_df[projects_df["project_name"] == project_name].iloc[0]
project_id = int(proj_row["project_id"])
project_code = proj_row.get("project_code")

# Owner options for this project
members = get_project_member_emails(project_id) or []
member_options = []
member_map = {}
for m in members:
    e = (m.get("user_email") or "").strip().lower()
    disp = (m.get("display_name") or e).strip()
    if not e:
        continue
    label = f"{disp} — {e}"
    member_options.append(label)
    member_map[label] = e
member_options = sorted(member_options)

# ============================================================
# LOAD ACTIONS FOR PROJECT
# ============================================================
actions_df = run_query(
    """
    SELECT *
    FROM actions
    WHERE project_id = :pid
    ORDER BY date_raised DESC NULLS LAST, created_at DESC NULLS LAST
""",
    {"pid": project_id},
)

if actions_df is None:
    actions_df = pd.DataFrame()

# ============================================================
# TABS
# ============================================================
tab_view, tab_edit, tab_add = st.tabs(["📋 View Actions", "✏️ Edit Action", "➕ Add Action"])

# ============================================================
# TAB: VIEW ACTIONS
# ============================================================
with tab_view:
    st.markdown(
        """
<div class='section-header'>
    <h3>📋 Current Actions</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if actions_df.empty:
        st.info("No actions found for this project.")
    else:
        filtered = actions_df.copy()
        today = dt.date.today()

        st.markdown(
            """
<div class='step-header'>
    <h4>Filters</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            status_filter = st.multiselect(
                "Status",
                STATUS_OPTIONS,
                default=["Open", "In Progress"] if "Open" in STATUS_OPTIONS else STATUS_OPTIONS,
                key="am_filter_status",
            )

        with c2:
            owners = sorted(filtered["owner"].dropna().astype(str).unique().tolist())
            owner_filter = st.multiselect("Owner", owners, key="am_filter_owner")

        with c3:
            priority_filter = st.multiselect("Priority", PRIORITY_OPTIONS, key="am_filter_priority")

        with c4:
            due_filter = st.selectbox("Target Close Date", ["All", "Due Today", "This Week", "Overdue"], key="am_filter_due")

        if status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]
        if owner_filter:
            filtered = filtered[filtered["owner"].isin(owner_filter)]
        if priority_filter:
            filtered = filtered[filtered["priority"].isin(priority_filter)]

        if due_filter != "All":
            dd = pd.to_datetime(filtered["due_date"], errors="coerce").dt.date
            if due_filter == "Due Today":
                filtered = filtered[dd == today]
            elif due_filter == "This Week":
                start = today - dt.timedelta(days=today.weekday())
                end = start + dt.timedelta(days=6)
                filtered = filtered[(dd >= start) & (dd <= end)]
            elif due_filter == "Overdue":
                filtered = filtered[(dd < today) & dd.notna()]

        display_df = build_display_df(filtered)

        st.markdown('<div class="action-table-container">', unsafe_allow_html=True)
        st.dataframe(
            style_table(display_df),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.download_button(
            "⬇️ Export Filtered Actions (CSV)",
            display_df.to_csv(index=False),
            file_name=f"{project_name}_actions.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ============================================================
# TAB: EDIT ACTION
# ============================================================
with tab_edit:
    st.markdown(
        """
<div class='section-header'>
    <h3>✏️ Edit Action</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if actions_df.empty:
        st.info("No actions to edit for this project.")
    else:
        # Build display labels while keeping action_id as the actual selected value
        def _fmt_closed_date(v):
            if v is None or pd.isna(v):
                return ""
            try:
                d = pd.to_datetime(v).date()
                return d.strftime("%d %b %Y")
            except Exception:
                return ""

        options = []
        for _, r in actions_df.iterrows():
            aid = r.get("action_id")
            status = (r.get("status") or "").strip() or "Open"
            status_clean = status.strip().lower()
            subject = (r.get("title") or "").strip() or "Untitled"

            # Optional: truncate long subjects so dropdown stays clean
            if len(subject) > 60:
                subject = subject[:60] + "..."

            closed_states = {"closed", "completed"}

            if status_clean in closed_states:
                closed_on = _fmt_closed_date(r.get("actual_close_date"))
                pretty_status = "Closed" if status_clean == "closed" else "Completed"
                label = f"{aid} — {subject} — {pretty_status}" + (f" — {closed_on}" if closed_on else "")
            else:
                label = f"{aid} — {subject} — {status or 'Open'}"

            options.append(
                {
                    "id": int(aid) if str(aid).isdigit() else aid,
                    "label": label,
                    "is_openish": status_clean not in closed_states,  # for sorting
                }
            )

        # Sort so open-ish items appear first, then by id
        options = sorted(
            options,
            key=lambda x: (0 if x.get("is_openish") else 1, int(x["id"]) if str(x["id"]).isdigit() else 9999999),
        )

        selected_edit = st.selectbox(
            "Select an Action to Edit",
            options=options,
            format_func=lambda o: o["label"],
            key="am_edit_action_id",
        )

        # ✅ ALWAYS use the int id for DB + state keys
        selected_edit_id = int(selected_edit["id"])
        editing = actions_df[actions_df["action_id"] == selected_edit_id].iloc[0]
        edit_prefix = f"edit_{selected_edit_id}"

        # ✅ Store/compare the previous selection using the INT id (not the dict)
        prev_id = st.session_state.get("am_prev_edit_id")
        if prev_id != selected_edit_id:
            if isinstance(prev_id, int):
                _reset_edit_form(prev_id)
            st.session_state["am_prev_edit_id"] = selected_edit_id

            st.session_state[f"{edit_prefix}_title"] = editing.get("title") or ""
            st.session_state[f"{edit_prefix}_detail"] = editing.get("detail") or ""
            st.session_state[f"{edit_prefix}_comments"] = editing.get("comments") or ""
            st.session_state[f"{edit_prefix}_status"] = (editing.get("status") or "")
            st.session_state[f"{edit_prefix}_priority"] = (editing.get("priority") or "")
            st.session_state[f"{edit_prefix}_owner_seed"] = (editing.get("owner") or "")

            def _safe_date(v):
                if v is None or pd.isna(v):
                    return None
                if isinstance(v, dt.date):
                    return v
                try:
                    return pd.to_datetime(v).date()
                except Exception:
                    return None

            due_seed = _safe_date(editing.get("due_date"))
            actual_seed = _safe_date(editing.get("actual_close_date"))

            st.session_state[f"{edit_prefix}_set_due"] = due_seed is not None
            st.session_state[f"{edit_prefix}_due_date"] = due_seed or dt.date.today()

            st.session_state[f"{edit_prefix}_set_actual"] = actual_seed is not None
            st.session_state[f"{edit_prefix}_actual_date"] = actual_seed or dt.date.today()

            st.session_state[f"{edit_prefix}_ai_nonce"] = 0

        with st.expander("🤖 AI Helper", expanded=False):
            nonce = int(st.session_state.get(f"{edit_prefix}_ai_nonce", 0))
            shorthand_key = f"{edit_prefix}_ai_shorthand_{nonce}"

            shorthand_e = st.text_area(
                "Shorthand",
                placeholder="e.g. Confirm access approvals; Owner: HT; due tomorrow; priority High; status In Progress",
                key=shorthand_key,
                height=120,
            )

            cA, cB = st.columns(2)
            with cA:
                if st.button("✨ Generate updates from shorthand", key=f"{edit_prefix}_ai_btn", use_container_width=True):
                    parsed = expand_action_shorthand(
                        shorthand=shorthand_e,
                        status_options=STATUS_OPTIONS,
                        priority_options=PRIORITY_OPTIONS,
                        history=[],
                    )
                    apply_action_ai_to_state(edit_prefix, parsed)

                    st.session_state[f"{edit_prefix}_ai_nonce"] = nonce + 1
                    st.success("Generated. Review/edit below, then save when ready.")
                    st.rerun()

            with cB:
                if st.button("🧽 Reset edit form", key=f"{edit_prefix}_reset_btn", use_container_width=True):
                    _reset_edit_form(selected_edit_id)
                    st.session_state["am_prev_edit_id"] = None
                    st.rerun()

        # capture old values to detect meaningful changes (status close)
        old_status = (editing.get("status") or "").strip()
        old_owner = (editing.get("owner") or "").strip()
        old_due = pd.to_datetime(editing.get("due_date"), errors="coerce")
        old_due_str = old_due.date().isoformat() if not pd.isna(old_due) else ""

        # ✅ form key must NOT include dicts
        with st.form(f"edit_action_form_{selected_edit_id}"):

            subject_e = st.text_input("Subject", key=f"{edit_prefix}_title")
            detail_e = st.text_area("Action Description", height=120, key=f"{edit_prefix}_detail")

            owner_seed = st.session_state.get(f"{edit_prefix}_owner_seed", "") or ""
            owner_e = owner_picker(
                "Owner",
                key_prefix=f"{edit_prefix}_owner",
                member_options=member_options,
                member_map=member_map,
                current_owner=owner_seed,
            )

            status_val = st.session_state.get(f"{edit_prefix}_status") or (editing.get("status") or "")
            if status_val not in STATUS_OPTIONS:
                status_val = STATUS_OPTIONS[0] if STATUS_OPTIONS else ""

            priority_val = st.session_state.get(f"{edit_prefix}_priority") or (editing.get("priority") or "")
            if priority_val not in PRIORITY_OPTIONS:
                priority_val = PRIORITY_OPTIONS[0] if PRIORITY_OPTIONS else ""

            status_e = st.selectbox(
                "Status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(status_val) if status_val in STATUS_OPTIONS else 0,
                key=f"{edit_prefix}_status",
            )
            priority_e = st.selectbox(
                "Priority",
                PRIORITY_OPTIONS,
                index=PRIORITY_OPTIONS.index(priority_val) if priority_val in PRIORITY_OPTIONS else 0,
                key=f"{edit_prefix}_priority",
            )

            set_due = st.checkbox(
                "Set Target Close Date",
                value=bool(st.session_state.get(f"{edit_prefix}_set_due", False)),
                key=f"{edit_prefix}_set_due",
            )
            due_e = st.date_input(
                "Target Close Date",
                value=st.session_state.get(f"{edit_prefix}_due_date", dt.date.today()),
                disabled=not set_due,
                key=f"{edit_prefix}_due_date",
            )

            set_actual = st.checkbox(
                "Set Actual Close Date",
                value=bool(st.session_state.get(f"{edit_prefix}_set_actual", False)),
                key=f"{edit_prefix}_set_actual",
            )
            actual_e = st.date_input(
                "Actual Close Date",
                value=st.session_state.get(f"{edit_prefix}_actual_date", dt.date.today()),
                disabled=not set_actual,
                key=f"{edit_prefix}_actual_date",
            )

            comments_e = st.text_area("Comments", height=120, key=f"{edit_prefix}_comments")

            submit_edit = st.form_submit_button("💾 Save Changes")

        if submit_edit:
            # ✅ DB update must receive an int id (not dict)
            update_action(
                action_id=selected_edit_id,
                title=subject_e,
                detail=detail_e,
                comments=comments_e,
                owner=owner_e,
                status=status_e,
                priority=priority_e,
                due_date=due_e if set_due else None,
                actual_close_date=actual_e if set_actual else None,
            )

            log_event(
                "action_updated",
                {
                    "user_email": user_email,
                    "entity_type": "action",
                    "entity_id": selected_edit_id,
                    "client": client_name,
                    "client_id": client_id,
                    "client_code": client_code,
                    "project": project_name,
                    "project_id": project_id,
                    "project_code": project_code,
                    "title": subject_e,
                },
            )

            # ✅ NEW NOTIFICATIONS (created/updated/closed)
            try:
                new_due_str = (due_e.isoformat() if (set_due and isinstance(due_e, dt.date)) else "")
                changed_owner = (owner_e or "").strip() != old_owner
                changed_due = new_due_str != old_due_str

                # Treat both "closed" and "completed" as closed-like if you want:
                old_s = (old_status or "").strip().lower()
                new_s = (status_e or "").strip().lower()
                closed_now = old_s not in {"closed", "completed"} and new_s in {"closed", "completed"}

                if closed_now:
                    notify(
                        event_type="action.closed",
                        title=f"✅ Action closed: {subject_e}",
                        body=f"Closed by {current_email}",
                        severity="info",
                        project_id=project_id,
                        client_id=client_id,
                        created_by=current_email,
                        meta={"entity_type": "action", "entity_id": selected_edit_id},
                    )
                else:
                    notify(
                        event_type="action.updated",
                        title=f"✏️ Action updated: {subject_e}",
                        body=(
                            f"Owner: {owner_e or 'Unassigned'}"
                            + (f" | Due: {due_e.isoformat()}" if (set_due and due_e) else "")
                            + (f" | Status: {status_e}" if status_e else "")
                            + (f" | Priority: {priority_e}" if priority_e else "")
                        ),
                        severity="info",
                        project_id=project_id,
                        client_id=client_id,
                        created_by=current_email,
                        meta={
                            "entity_type": "action",
                            "entity_id": selected_edit_id,
                            "changed_owner": bool(changed_owner),
                            "changed_due": bool(changed_due),
                        },
                    )
            except Exception:
                pass

            _reset_edit_form(selected_edit_id)
            st.session_state["am_prev_edit_id"] = None

            st.success("Action updated successfully!")
            st.rerun()

# ============================================================
# TAB: ADD NEW ACTION
# ============================================================
with tab_add:
    st.markdown(
        """
<div class='section-header'>
    <h3>➕ Add New Action</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    _, right_btn = st.columns([6, 2])
    with right_btn:
        if st.button("🧽 Reset new form", key="am_new_reset", use_container_width=True):
            _reset_new_form()
            st.rerun()

    with st.expander("🤖 AI Helper", expanded=False):
        st.markdown(
            """
            <div class='info-box'>
                <strong style='color:#48bb78;'>Tip</strong><br/>
                Paste shorthand like: <i>"Owner: HT; due 12/02/2026; priority High; status Open"</i>.
                We’ll prefill fields — you can then review and adjust before saving.
            </div>
            """,
            unsafe_allow_html=True,
        )

        nonce = int(st.session_state.get("new_ai_nonce", 0))
        shorthand_key = f"new_ai_shorthand_{nonce}"

        shorthand = st.text_area(
            "Shorthand",
            placeholder="e.g. Chase vendor for final SOW; Owner: HT; due 12/02/2026; priority High; status Open",
            key=shorthand_key,
            height=120,
        )

        if st.button("✨ Generate fields from shorthand", use_container_width=True, key="new_ai_btn"):
            parsed = expand_action_shorthand(
                shorthand=shorthand,
                status_options=STATUS_OPTIONS,
                priority_options=PRIORITY_OPTIONS,
                history=[],
            )
            apply_action_ai_to_state("new", parsed)

            st.session_state["new_ai_nonce"] = nonce + 1
            st.success("Generated. Review/edit below, then save when ready.")
            st.rerun()

    with st.form("add_action_form"):
        today = dt.date.today()
        st.markdown(
            f"<div style='font-size:0.9rem; color:#666;'>📅 Date Raised: <b>{today}</b></div>",
            unsafe_allow_html=True,
        )

        subject = st.text_input("Subject *", key="new_title")
        detail = st.text_area("Action Description *", height=120, key="new_detail")

        col1, col2 = st.columns(2)
        with col1:
            owner_seed = st.session_state.get("new_owner_seed", "") or ""
            owner = owner_picker(
                "Owner",
                key_prefix="new_owner",
                member_options=member_options,
                member_map=member_map,
                current_owner=owner_seed,
            )
        with col2:
            status_default = st.session_state.get("new_status") or (
                "Open" if "Open" in STATUS_OPTIONS else (STATUS_OPTIONS[0] if STATUS_OPTIONS else "")
            )
            status = st.selectbox(
                "Status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(status_default) if status_default in STATUS_OPTIONS else 0,
                key="new_status",
            )

        col3, col4, col5 = st.columns(3)

        with col3:
            priority_default = st.session_state.get("new_priority") or (
                PRIORITY_OPTIONS[1] if len(PRIORITY_OPTIONS) > 1 else (PRIORITY_OPTIONS[0] if PRIORITY_OPTIONS else "")
            )
            priority = st.selectbox(
                "Priority",
                PRIORITY_OPTIONS,
                index=PRIORITY_OPTIONS.index(priority_default) if priority_default in PRIORITY_OPTIONS else 0,
                key="new_priority",
            )

        with col4:
            set_due = st.checkbox(
                "Set Target Close Date",
                value=bool(st.session_state.get("new_set_due", False)),
                key="new_set_due",
            )
            due_date = st.date_input(
                "Target Close Date",
                value=st.session_state.get("new_due_date", today),
                disabled=not set_due,
                key="new_due_date",
            )

        with col5:
            set_actual = st.checkbox(
                "Set Actual Close Date",
                value=bool(st.session_state.get("new_set_actual", False)),
                key="new_set_actual",
            )
            actual_close_date = st.date_input(
                "Actual Close Date",
                value=st.session_state.get("new_actual_date", today),
                disabled=not set_actual,
                key="new_actual_date",
            )

        comments = st.text_area("Comments", height=120, key="new_comments")
        submitted = st.form_submit_button("💾 Save Action")

    if submitted:
        if not (subject or "").strip() or not (detail or "").strip():
            st.warning("Please provide both a Subject and Description.")
        else:
            new_action_id = add_action(
                client_id=client_id,
                project_id=project_id,
                title=subject,
                detail=detail,
                comments=comments,
                owner=owner,
                status=status,
                priority=priority,
                due_date=due_date if set_due else None,
                actual_close_date=actual_close_date if set_actual else None,
                date_raised=today,
            )

            log_event(
                "action_created",
                {
                    "user_email": user_email,
                    "client": client_name,
                    "client_id": client_id,
                    "client_code": client_code,
                    "project": project_name,
                    "project_id": project_id,
                    "project_code": project_code,
                    "title": subject,
                },
            )

            # NEW NOTIFICATION: action created
            try:
                notify(
                    event_type="action.created",
                    title=f"🆕 New action added: {subject}",
                    body=(
                        f"Owner: {owner or 'Unassigned'}"
                        + (f" | Due: {due_date.isoformat()}" if (set_due and due_date) else "")
                        + (f" | Priority: {priority}" if priority else "")
                        + (f" | Status: {status}" if status else "")
                    ),
                    severity="info",
                    project_id=project_id,
                    client_id=client_id,
                    created_by=current_email,
                    meta={"entity_type": "action", "entity_id": int(new_action_id) if new_action_id else None},
                )
            except Exception:
                pass

            _reset_new_form()
            st.success(f"Action '{subject}' created successfully!")
            st.rerun()

# ============================================================
# FOOTER
# ============================================================
pmo_footer()