# ============================================================
# 13_🧮_Project_Submission_Tracker.py — ScopeSight v2.1 (Formatted)
# Tracks all project submissions (pending / approved / rejected)
# and shows which ones have become live delivery projects.
# ============================================================

import os
import streamlit as st

from modules.ui_hide_nav import hide_streamlit_nav
from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.db import run_query

# ---------------------------------------------------------
# DEV MODE OVERRIDES
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
hide_streamlit_nav()

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="🧮 Project Submission Tracker",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded",
)

set_pmo_theme(page_title="🧮 Project Submission Tracker")
render_sidebar()

# ---------------------------------------------------------
# STYLES (match Weekly NFR look)
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Shared visual language */
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

# ---------------------------------------------------------
# INTRO
# ---------------------------------------------------------
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 Tip</strong><br/>
    Use the tabs to review each stage. Expand a record for the full JSON snapshot.
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================
# LOAD DATA
# ============================================================

# 1) Get scaffold submissions
scaffold_df = run_query("""
    SELECT
        ps.id,
        ps.client_id,
        cs.client_name,
        cs.client_code,
        ps.project_name,
        ps.project_code,
        ps.tier,
        ps.description,
        ps.submitted_by,
        ps.submitted_on,
        ps.status,
        ps.approved_by,
        ps.approved_on,
        ps.rejected_by,
        ps.rejected_on,
        ps.rejection_reason
    FROM project_scaffold ps
    LEFT JOIN client_scaffold cs
        ON cs.id = ps.client_id
    ORDER BY ps.submitted_on DESC NULLS LAST
""")

# 2) Get actual live projects
live_projects = run_query("""
    SELECT
        p.project_id,
        p.project_name,
        p.project_code,
        p.client_id,
        cs.client_name,
        cs.client_code,
        p.created_at
    FROM projects p
    LEFT JOIN client_scaffold cs
        ON cs.id = p.client_id
    ORDER BY p.created_at DESC NULLS LAST
""")

# ============================================================
# TABS
# ============================================================
tab_pending, tab_approved, tab_rejected = st.tabs([
    "⏳ Pending",
    "🟩 Approved + Live",
    "❌ Rejected"
])

# ============================================================
# TAB 1 — PENDING PROJECTS
# ============================================================
with tab_pending:
    st.markdown(
        """
<div class='section-header'>
    <h3>⏳ Pending Project Submissions</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    pending = scaffold_df[scaffold_df["status"] == "awaiting_approval"]

    if pending.empty:
        st.success("🎉 No pending project submissions.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>Snapshot</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            pending[
                [
                    "client_name",
                    "project_name",
                    "project_code",
                    "tier",
                    "submitted_by",
                    "submitted_on",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            """
<div class='step-header'>
    <h4>Details</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        for _, row in pending.iterrows():
            with st.expander(f"📁 {row['project_name']} ({row['project_code']}) — {row['client_name']}"):
                st.json(row.to_dict())

# ============================================================
# TAB 2 — APPROVED + LIVE PROJECTS
# ============================================================
with tab_approved:
    st.markdown(
        """
<div class='section-header'>
    <h3>🟩 Approved Submissions</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    approved = scaffold_df[scaffold_df["status"] == "approved"]

    if approved.empty:
        st.info("No approved submissions yet.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>Approved Snapshot</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            approved[
                [
                    "client_name",
                    "project_name",
                    "project_code",
                    "tier",
                    "submitted_by",
                    "submitted_on",
                    "approved_by",
                    "approved_on",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
<div class='section-header'>
    <h3>🚀 Live Projects</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='info-box'><strong style='color:#48bb78;'>Live Projects</strong><br/>"
        "These are projects created in the <code>projects</code> table.</div>",
        unsafe_allow_html=True,
    )

    if live_projects.empty:
        st.warning("No live projects found.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            live_projects[
                [
                    "client_name",
                    "project_name",
                    "project_code",
                    "created_at",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# TAB 3 — REJECTED PROJECTS
# ============================================================
with tab_rejected:
    st.markdown(
        """
<div class='section-header'>
    <h3>❌ Rejected Project Submissions</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    rejected = scaffold_df[scaffold_df["status"] == "rejected"]

    if rejected.empty:
        st.info("No rejected submissions recorded.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>Rejected Snapshot</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            rejected[
                [
                    "client_name",
                    "project_name",
                    "project_code",
                    "submitted_by",
                    "submitted_on",
                    "rejected_by",
                    "rejected_on",
                    "rejection_reason",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            """
<div class='step-header'>
    <h4>Details</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        for _, row in rejected.iterrows():
            with st.expander(f"🟥 {row['project_name']} ({row['project_code']}) — {row['client_name']}"):
                st.json(row.to_dict())

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
