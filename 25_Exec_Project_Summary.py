# ============================================================
# 25_📈_Exec_Project_Summary.py — ScopeSight v3.0
# Executive Project Summary Dashboard
# ============================================================

import streamlit as st

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# SAFE VALUE HELPER
# ---------------------------------------------------------
def safe(df):
    """Return first value from query or 0."""
    if df is None or df.empty:
        return 0
    try:
        return list(df.iloc[0])[0] or 0
    except:
        return 0


# ---------------------------------------------------------
# SETUP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

st.set_page_config(
    page_title="📊 Executive Project Summary",
    page_icon="📊",
    layout="wide",
)

set_pmo_theme(page_title="📊 Executive Project Summary")
render_sidebar()


# ---------------------------------------------------------
# GLOBAL STYLE (Matches Submission Tracker Formatting)
# ---------------------------------------------------------
st.markdown("""
<style>
header[data-testid="stHeader"] {
    height:0 !important;
    visibility:hidden !important;
}
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.5rem 0 1rem 0;
}
.section-header h3 { margin:0; color:white; }
.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin-bottom: 1.25rem;
}
.table-container {
    max-height: 520px;
    overflow-y: auto;
    border: 1px solid #e6f2ff;
    border-radius: 10px;
}
h2 { text-align:center !important; margin-top:25px !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# LOAD PROFILE
# ---------------------------------------------------------
email = st.session_state.get("email")
if not email:
    st.error("Unable to load your profile. Please log in again.")
    st.stop()


# ---------------------------------------------------------
# INTRO
# ---------------------------------------------------------
st.markdown("""
<div style='text-align:center; max-width:850px; margin:auto;
font-size:1.05rem; line-height:1.55;'>
Delivery health, risk exposure and key actions across your assigned clients.
</div>
""", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)


# ---------------------------------------------------------
# LOAD ASSIGNED CLIENTS (v3 architecture)
# ---------------------------------------------------------
clients_df = run_query(
    """
    SELECT
        c.id AS client_id,
        c.client_name
    FROM public.user_client_permissions u
    JOIN public.client_scaffold c
      ON c.id = u.client_id
    WHERE LOWER(u.user_email) = :email
    ORDER BY c.client_name
    """,
    {"email": email.strip().lower()},
)

if clients_df.empty:
    st.warning("You have no assigned clients. Contact an administrator.")
    st.stop()

client_map = {
    row["client_name"]: row["client_id"]
    for _, row in clients_df.iterrows()
}

sel_client = st.selectbox("Select Client", list(client_map.keys()))
client_id = client_map[sel_client]

st.markdown("<br/>", unsafe_allow_html=True)


# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Overview",
    "📁 Project Portfolio",
    "🔥 Top Risks",
    "📝 Actions"
])


# ============================================================
# ▶ TAB 1 — KPIs & SUMMARY
# ============================================================
with tab1:

    st.markdown("""
    <div class='section-header'><h3>📊 Client Overview</h3></div>
    """, unsafe_allow_html=True)

    total_projects = safe(run_query("""
        SELECT COUNT(*) 
        FROM projects 
        WHERE client_id = :cid
    """, {"cid": client_id}))

    open_risks = safe(run_query("""
        SELECT COUNT(*)
        FROM raids
        WHERE client_id = :cid
          AND status ILIKE 'open'
    """, {"cid": client_id}))

    overdue_actions = safe(run_query("""
        SELECT COUNT(*)
        FROM actions
        WHERE client_id = :cid
          AND due_date < CURRENT_DATE
          AND status NOT ILIKE 'closed'
    """, {"cid": client_id}))

    nfr_volume = safe(run_query("""
        SELECT COUNT(*)
        FROM nfr_reports
        WHERE client_id = :cid
          AND week_start >= CURRENT_DATE - INTERVAL '30 days'
    """, {"cid": client_id}))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projects", total_projects)
    c2.metric("Open Risks", open_risks)
    c3.metric("Overdue Actions", overdue_actions)
    c4.metric("NFRs (30 Days)", nfr_volume)


# ============================================================
# ▶ TAB 2 — PROJECT PORTFOLIO
# ============================================================
with tab2:

    st.markdown("""
    <div class='section-header'><h3>📁 Project Portfolio</h3></div>
    """, unsafe_allow_html=True)

    proj_df = run_query(
        """
        SELECT
            p.project_name,
            p.rag_status,
            p.health_score,
            p.status,
            p.project_start_date AS start_date,
            p.expected_end_date AS end_date,
            p.project_manager
        FROM public.projects p
        WHERE p.client_id = :cid
        ORDER BY
            CASE p.rag_status
                WHEN 'Red' THEN 1
                WHEN 'Amber' THEN 2
                WHEN 'Green' THEN 3
                ELSE 4
            END,
            p.project_name
        """,
        {"cid": client_id},
    )

    if proj_df.empty:
        st.info("No projects recorded for this client.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(proj_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ▶ TAB 3 — RISK SUMMARY
# ============================================================
with tab3:

    st.markdown("""
    <div class='section-header'><h3>🔥 Top Risks</h3></div>
    """, unsafe_allow_html=True)

    risk_df = run_query("""
        SELECT 
            title,
            description,
            likelihood,
            impact,
            status,
            updated_at
        FROM raids
        WHERE client_id = :cid
          AND status ILIKE 'open'
        ORDER BY updated_at DESC
        LIMIT 10
    """, {"cid": client_id})

    if risk_df.empty:
        st.success("No open risks — strong risk control.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(risk_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ▶ TAB 4 — ACTION SUMMARY
# ============================================================
with tab4:

    st.markdown("""
    <div class='section-header'><h3>📝 Overdue & Upcoming Actions</h3></div>
    """, unsafe_allow_html=True)

    actions_df = run_query("""
        SELECT
            title,
            owner,
            status,
            due_date,
            priority,
            updated_at
        FROM actions
        WHERE client_id = :cid
        ORDER BY 
            CASE WHEN due_date < CURRENT_DATE AND status NOT ILIKE 'closed' THEN 0 ELSE 1 END,
            due_date ASC
    """, {"cid": client_id})

    if actions_df.empty:
        st.info("No actions found for this client.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(actions_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
