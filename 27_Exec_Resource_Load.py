# ============================================================
# 27_👥_Exec_Resource_Load.py — ScopeSight v3
# Executive Resource Load & Capacity Dashboard
# ============================================================

import streamlit as st
import pandas as pd

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# SETUP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

st.set_page_config(
    page_title="👥 Resource Load",
    page_icon="👥",
    layout="wide",
)

set_pmo_theme(page_title="👥 Resource Load & Capacity")
render_sidebar()

# ---------------------------------------------------------
# GLOBAL STYLES (Shared Admin Look)
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] {
    height:0 !important;
    visibility:hidden !important;
}

/* Section header band */
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.5rem 0 1rem 0;
}
.section-header h3 {
    margin: 0;
    color: white;
    font-size: 1.2rem;
    font-weight: 600;
}

/* Info box */
.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin-bottom: 1.25rem;
}

/* Scrollable table container */
.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e6f2ff;
}

h2 { text-align:center !important; margin-top:25px !important; }
h3 { text-align:center !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# LOAD USER
# ---------------------------------------------------------
email = st.session_state.get("email")
if not email:
    st.error("Unable to load your profile. Please log in again.")
    st.stop()

role = st.session_state.get("role")

# ---------------------------------------------------------
# PAGE INTRO
# ---------------------------------------------------------
st.markdown(
    """
<div style='text-align:center; max-width:850px; margin:auto;
font-size:1.05rem; line-height:1.55;'>
Resource utilisation, capacity risks and skill coverage across your assigned clients.
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------
# CLIENT SCOPE
# ---------------------------------------------------------
if role == "admin":
    clients_df = run_query(
        """
        SELECT id AS client_id, client_name
        FROM client_scaffold
        ORDER BY client_name
        """
    )
else:
    clients_df = run_query(
        """
        SELECT
            c.id AS client_id,
            c.client_name
        FROM user_client_permissions u
        JOIN client_scaffold c
          ON c.id = u.client_id
        WHERE LOWER(u.user_email) = :email
        ORDER BY c.client_name
        """,
        {"email": email.strip().lower()},
    )

if clients_df is None or clients_df.empty:
    if role == "admin":
        st.error("No clients exist in the system.")
    else:
        st.warning(
            "You are not assigned to any clients.\n\n"
            "If this is unexpected, ask an administrator to assign you."
        )
    st.stop()

client_ids = clients_df["client_id"].astype(int).tolist()

if not client_ids:
    st.stop()  # safety, should never hit due to earlier check

client_ids_sql = f"({','.join(str(cid) for cid in client_ids)})"

# ---------------------------------------------------------
# LOAD ALLOCATIONS (v3 ARCHITECTURE)
# ---------------------------------------------------------
alloc_df = run_query(
    f"""
    SELECT 
        rp.resource_id,
        rp.full_name,
        rp.role,
        rp.skillset,
        rp.department,

        ra.allocation_pct,
        ra.start_date,
        ra.end_date,

        p.project_name,
        c.client_name
    FROM resource_allocation ra
    JOIN resource_pool rp ON ra.resource_id = rp.resource_id
    JOIN projects p ON ra.project_id = p.project_id
    JOIN client_scaffold c ON ra.client_id = c.id
    WHERE ra.client_id IN {client_ids_sql}
    ORDER BY rp.full_name, p.project_name
"""
)

if alloc_df is None or alloc_df.empty:
    st.info("No resource allocations found for your assigned clients.")
    pmo_footer()
    st.stop()

# ---------------------------------------------------------
# UTILISATION CALCULATION (unchanged)
# ---------------------------------------------------------
util = (
    alloc_df.groupby(["resource_id", "full_name"])["allocation_pct"]
    .sum()
    .reset_index()
)
util.columns = ["resource_id", "Resource", "Total Allocation (%)"]
util["Availability (%)"] = 100 - util["Total Allocation (%)"]

availability = util[["Resource", "Total Allocation (%)", "Availability (%)"]]
availability = availability.sort_values("Availability (%)", ascending=True)

detail = alloc_df[
    [
        "full_name",
        "role",
        "department",
        "client_name",
        "project_name",
        "allocation_pct",
        "start_date",
        "end_date",
    ]
].rename(
    columns={
        "full_name": "Resource",
        "allocation_pct": "Allocation (%)",
    }
)

skill_df = (
    alloc_df["skillset"]
    .fillna("Unspecified")
    .value_counts()
)

# ---------------------------------------------------------
# TOP-LEVEL METRICS (unchanged logic)
# ---------------------------------------------------------
total_resources = util["resource_id"].nunique()
avg_utilisation = round(util["Total Allocation (%)"].mean(), 1)
overallocated = util[util["Total Allocation (%)"] > 100].shape[0]
underutilised = util[util["Total Allocation (%)"] < 40].shape[0]

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_overview, tab_util, tab_avail, tab_detail, tab_skills = st.tabs(
    [
        "📊 Overview",
        "📘 Utilisation Summary",
        "🟩 Availability",
        "📂 Detailed Allocations",
        "🧠 Skillset Distribution",
    ]
)

# ============================================================
# TAB 1 — OVERVIEW / KPIs
# ============================================================
with tab_overview:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📊 Top-Level Metrics</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong>How to use this view:</strong><br/>
            Quickly scan <b>overall utilisation</b>, <b>overallocated staff</b> and
            <b>underutilised capacity</b> across your assigned clients.
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Resources", total_resources)
    c2.metric("Average Utilisation", f"{avg_utilisation}%")
    c3.metric("Overallocated (>100%)", overallocated)
    c4.metric("Underutilised (<40%)", underutilised)

# ============================================================
# TAB 2 — RESOURCE UTILISATION SUMMARY
# ============================================================
with tab_util:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📘 Resource Utilisation Summary</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.dataframe(
        util.sort_values("Total Allocation (%)", ascending=False),
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.bar_chart(util.set_index("Resource")["Total Allocation (%)"])

# ============================================================
# TAB 3 — AVAILABILITY OVERVIEW
# ============================================================
with tab_avail:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🟩 Availability Overview</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.dataframe(availability, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# TAB 4 — DETAILED ALLOCATION TABLE
# ============================================================
with tab_detail:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📂 Detailed Resource Allocations</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.dataframe(detail, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# TAB 5 — SKILLSET DISTRIBUTION
# ============================================================
with tab_skills:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🧠 Skillset Distribution</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.bar_chart(skill_df)

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
