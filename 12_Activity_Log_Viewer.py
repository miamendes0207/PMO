# ============================================================
# 12_📜_Activity_Log_Viewer.py — ScopeSight v3.0 (Fixed)
# Admin Activity Log Viewer — Clients + Projects + System Events
# ============================================================

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

from modules.db import run_query
from auth.login import require_login

from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ============================================================
# BOOTSTRAP
# ============================================================
hide_streamlit_nav()
require_login()

query = st.query_params

if query.get("dev") == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True


st.set_page_config(
    page_title="📜 Activity Log Viewer",
    page_icon="📜",
    layout="wide",
)

set_pmo_theme(page_title="📜 Activity Logs")
render_sidebar()

st.markdown(
    """
<style>
header[data-testid="stHeader"] {
    height:0px !important;
    visibility:hidden !important;
}

/* Shared visual language (matching admin pages) */
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

/* Scrollable table container (for future use if needed) */
.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e6f2ff;
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# INTRO
# ============================================================

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#2f855a;'>💡 Tip</strong><br/>
    Use the filters to narrow down by user, client, project, action type or date range.
    The search box will also match against the raw JSON <code>details</code>.
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# LOAD LOG DATA
# ============================================================

logs_df = run_query(
    """
    SELECT 
        sal.log_id AS id,
        COALESCE(u.email, sal.user_email) AS user,
        sal.event_type AS action,
        sal.entity_type AS entity_type,
        sal.entity_id AS entity_id,
        sal.event_data AS details,
        sal.timestamp
    FROM system_activity_log sal
    LEFT JOIN users u 
        ON u.email = sal.user_email     -- << FIXED JOIN
    ORDER BY sal.timestamp DESC
"""
)

if logs_df is None or logs_df.empty:
    st.info("No activity has been recorded yet.")
    pmo_footer()
    st.stop()

logs_df["timestamp"] = pd.to_datetime(logs_df["timestamp"])


# ============================================================
# PARSE JSON DETAILS
# ============================================================

def safe_parse(detail):
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        try:
            return json.loads(detail)
        except:
            return {"raw": detail}
    return {}


logs_df["details"] = logs_df["details"].apply(safe_parse)


def extract(details, key):
    return details.get(key) if isinstance(details, dict) else None


logs_df["role"] = logs_df["details"].apply(lambda d: extract(d, "role") or "user")
logs_df["client"] = logs_df["details"].apply(
    lambda d: extract(d, "client") or extract(d, "client_name")
)
logs_df["client_id"] = logs_df["details"].apply(lambda d: extract(d, "client_id"))
logs_df["project"] = logs_df["details"].apply(
    lambda d: extract(d, "project") or extract(d, "project_name")
)
logs_df["project_id"] = logs_df["details"].apply(lambda d: extract(d, "project_id"))


# ============================================================
# FILTER PANEL
# ============================================================
with st.expander("🔍 Filter Activity", expanded=True):

    st.markdown(
        """
        <div class='section-header'>
            <h3>🔍 Filter Activity</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='step-header'>
            <h4>Filter Options</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    user_filter = col1.multiselect(
        "User", sorted(logs_df["user"].dropna().unique())
    )
    action_filter = col2.multiselect(
        "Action Type", sorted(logs_df["action"].unique())
    )
    client_filter = col3.multiselect(
        "Client", sorted(logs_df["client"].dropna().unique())
    )

    p1, p2 = st.columns(2)
    project_filter = p1.multiselect(
        "Project", sorted(logs_df["project"].dropna().unique())
    )

    d1, d2 = st.columns(2)
    start_date = d1.date_input("From Date", logs_df["timestamp"].min().date())
    end_date = d2.date_input("To Date", logs_df["timestamp"].max().date())

    search_query = st.text_input(
        "🔎 Search (matches user, client, project, or details)"
    )


# ============================================================
# APPLY FILTERS
# ============================================================
filtered = logs_df.copy()

if user_filter:
    filtered = filtered[filtered["user"].isin(user_filter)]

if action_filter:
    filtered = filtered[filtered["action"].isin(action_filter)]

if client_filter:
    filtered = filtered[filtered["client"].isin(client_filter)]

if project_filter:
    filtered = filtered[filtered["project"].isin(project_filter)]

filtered = filtered[
    (filtered["timestamp"].dt.date >= start_date)
    & (filtered["timestamp"].dt.date <= end_date)
]

if search_query.strip():
    q = search_query.lower()
    filtered = filtered[
        filtered.apply(
            lambda r: (
                q in str(r["user"]).lower()
                or q in str(r["client"]).lower()
                or q in str(r["project"]).lower()
                or q in str(r["action"]).lower()
                or q in json.dumps(r["details"], indent=2).lower()
            ),
            axis=1,
        )
    ]


# ============================================================
# RESULTS HEADER
# ============================================================
st.markdown(
    f"""
    <div class='section-header'>
        <h3>📌 Showing {len(filtered)} matching log entries</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<hr/>", unsafe_allow_html=True)


# ============================================================
# EXPORT OPTIONS
# ============================================================
st.markdown(
    """
    <div class='step-header'>
        <h4>⬇️ Export</h4>
    </div>
    """,
    unsafe_allow_html=True,
)

colA, colB = st.columns(2)

colA.download_button(
    "⬇️ Export as CSV",
    data=filtered.to_csv(index=False),
    file_name="activity_log_export.csv",
    mime="text/csv",
    use_container_width=True,
)

colB.download_button(
    "⬇️ Export as JSON",
    data=filtered.to_json(orient="records", indent=2),
    file_name="activity_log_export.json",
    mime="application/json",
    use_container_width=True,
)

st.markdown("<hr/>", unsafe_allow_html=True)


# ============================================================
# ACTION COLOUR MAP (v3 EVENTS)
# ============================================================
ACTION_COLOURS = {
    # ---------------------------
    # CLIENT EVENTS
    # ---------------------------
    "client_submitted": "#1E88E5",
    "client_approved": "#43A047",
    "client_rejected": "#E53935",
    # ---------------------------
    # PROJECT EVENTS
    # ---------------------------
    "project_submitted": "#8E24AA",
    "project_approved": "#6A1B9A",
    "project_rejected": "#AD1457",
    # ---------------------------
    # DOCUMENTS & NFRS
    # ---------------------------
    "generated_nfr": "#4CAF50",
    "generated_weekly_nfr": "#2E7D32",
    "document_generated": "#00ACC1",
    "daily_nfr_created": "#00897B",
    "generated_governance_pack": "#3949AB",
    # ---------------------------
    # RAIDS
    # ---------------------------
    "raids_update": "#FB8C00",
    "raid_audit": "#EF6C00",
    # ---------------------------
    # ACTIONS
    # ---------------------------
    "action_created": "#6D4C41",
    "action_updated": "#8D6E63",
    # ---------------------------
    # USER / AUTH
    # ---------------------------
    "login": "#00838F",
    "user_created": "#7CB342",
    "user_deleted": "#D32F2F",
}


def colour_for(action):
    return ACTION_COLOURS.get(action, "#546E7A")


# ============================================================
# DISPLAY LOG CARDS
# ============================================================
for _, row in filtered.iterrows():

    colour = colour_for(row["action"])
    details_json = json.dumps(row["details"], indent=2)

    st.markdown(
        f"""
    <div style="
        border-left: 6px solid {colour};
        padding: 14px;
        margin-bottom: 14px;
        background: #F9FAFB;
        border-radius: 8px;
        border: 1px solid #E1E5EB;
    ">
        <div><b>{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</b></div>
        <div><b>User:</b> {row['user']} ({row['role']})</div>
        <div><b>Action:</b> <span style="color:{colour}; font-weight:600;">{row['action']}</span></div>

        {"<b>Client:</b> " + str(row["client"]) if row["client"] else ""}
        <br/>
        {"<b>Project:</b> " + str(row["project"]) if row["project"] else ""}

        <details style="margin-top:8px;">
            <summary><b>Details</b></summary>
            <pre style="font-size:12px; margin-top:8px;">{details_json}</pre>
        </details>
    </div>
    """,
        unsafe_allow_html=True,
    )

st.markdown("<hr/>", unsafe_allow_html=True)
pmo_footer()
