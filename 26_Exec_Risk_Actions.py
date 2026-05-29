# ============================================================
# 26_⚠️_Exec_Risk_Actions.py — ScopeSight v3.1 (FINAL FIX)
# Executive Risks & Actions Overview (Client-Level)
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
    page_title="⚠️ Risks & Actions Overview",
    page_icon="⚠️",
    layout="wide",
)

set_pmo_theme(page_title="⚠️ Risks & Actions")
render_sidebar()


# ---------------------------------------------------------
# STYLES (match Project Submission Tracker / Weekly NFR look)
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
# HEADER (Tracker-style header + green divider + tip)
# ---------------------------------------------------------
st.markdown(
    """
<div style='text-align: center; padding: 2rem 0;'>
    <p style='color: #666; font-size: 1.1rem;'>
        Escalated risks, overdue actions and delivery blockers across your assigned clients.
    </p>
</div>
<hr style='border: none; height: 2px; background-color: #2ECC71; margin: 0 0 2rem 0;' />
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 Tip</strong><br/>
    Open each section below to review KPIs, the risk register, actions, and project health snapshot.
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# LOAD & NORMALISE USER
# ---------------------------------------------------------
email = (st.session_state.get("email") or "").strip().lower()
role = (st.session_state.get("role") or "").strip().lower()

if not email:
    st.error("Unable to load your profile. Please log in again.")
    st.stop()


# ---------------------------------------------------------
# SAFE DF HELPER
# ---------------------------------------------------------
def safe(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if df is not None and not df.empty else pd.DataFrame()


# ---------------------------------------------------------
# GET EXEC-ASSIGNED CLIENTS (CANONICAL)
# ---------------------------------------------------------
st.markdown(
    """
<div class='section-header'>
    <h3>📁 Client Selection</h3>
</div>
""",
    unsafe_allow_html=True,
)

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
    st.warning(
        "You are not assigned to any clients.\n\n"
        "If this is unexpected, ask an administrator to assign you to a client."
    )
    st.stop()

client_map = dict(zip(clients_df["client_name"], clients_df["client_id"]))

sel_client = st.selectbox(
    "Select Client",
    options=list(client_map.keys()),
)

client_id = client_map[sel_client]

st.markdown("<br/>", unsafe_allow_html=True)


# ============================================================
# KPI METRICS
# ============================================================
with st.expander("📊 KPI Summary", expanded=True):

    open_risks = safe(run_query(
        """
        SELECT COUNT(*) AS c
        FROM public.raids
        WHERE client_id = :cid
          AND LOWER(status) = 'open'
        """,
        {"cid": client_id},
    ))

    critical_risks = safe(run_query(
        """
        SELECT COUNT(*) AS c
        FROM public.raids
        WHERE client_id = :cid
          AND LOWER(status) = 'open'
          AND probability >= 4
          AND severity >= 4
        """,
        {"cid": client_id},
    ))

    open_actions = safe(run_query(
        """
        SELECT COUNT(*) AS c
        FROM public.actions
        WHERE client_id = :cid
          AND LOWER(status) NOT IN ('closed', 'complete', 'done')
        """,
        {"cid": client_id},
    ))

    overdue_actions = safe(run_query(
        """
        SELECT COUNT(*) AS c
        FROM public.actions
        WHERE client_id = :cid
          AND due_date < CURRENT_DATE
          AND LOWER(status) NOT IN ('closed', 'complete', 'done')
        """,
        {"cid": client_id},
    ))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open Risks", int(open_risks.iloc[0, 0]) if not open_risks.empty else 0)
    c2.metric("Critical Risks (≥4×4)", int(critical_risks.iloc[0, 0]) if not critical_risks.empty else 0)
    c3.metric("Open Actions", int(open_actions.iloc[0, 0]) if not open_actions.empty else 0)
    c4.metric("Overdue Actions", int(overdue_actions.iloc[0, 0]) if not overdue_actions.empty else 0)


# ============================================================
# RISK REGISTER
# ============================================================
with st.expander("🔥 Risk Register Overview", expanded=False):

    risks_df = run_query(
        """
        SELECT
            raid_type,
            title,
            description,
            probability,
            severity,
            revised_score,
            owner_plen,
            owner_client,
            status,
            updated_at
        FROM public.raids
        WHERE client_id = :cid
        ORDER BY
            revised_score DESC NULLS LAST,
            severity DESC,
            probability DESC,
            updated_at DESC
        """,
        {"cid": client_id},
    )

    if risks_df.empty:
        st.success("No open risks recorded — excellent position for this client.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(risks_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ACTION SUMMARY
# ============================================================
with st.expander("📝 Actions Overview", expanded=False):

    actions_df = run_query(
        """
        SELECT
            title,
            owner,
            priority,
            status,
            due_date,
            updated_at
        FROM public.actions
        WHERE client_id = :cid
        ORDER BY
            CASE
                WHEN due_date < CURRENT_DATE
                 AND LOWER(status) NOT IN ('closed','complete','done')
                THEN 0 ELSE 1
            END,
            due_date ASC NULLS LAST
        """,
        {"cid": client_id},
    )

    if actions_df.empty:
        st.success("No actions recorded — all clear.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(actions_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PROJECT HEALTH SNAPSHOT
# ============================================================
with st.expander("📁 Project Health Snapshot", expanded=False):

    proj_df = run_query(
        """
        SELECT
            project_name,
            rag_status,
            health_score,
            project_start_date AS start_date,
            expected_end_date  AS end_date,
            project_manager
        FROM public.projects
        WHERE client_id = :cid
        ORDER BY
            CASE rag_status
                WHEN 'Red' THEN 1
                WHEN 'Amber' THEN 2
                WHEN 'Green' THEN 3
                ELSE 4
            END,
            project_name
        """,
        {"cid": client_id},
    )

    if proj_df.empty:
        st.info("No active projects found for this client.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(proj_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# AI INSIGHT PLACEHOLDER
# ============================================================
with st.expander("🤖 Executive Insight (AI-Generated)", expanded=False):
    st.success("Leni will soon summarise key risk themes and action bottlenecks automatically.")


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)
pmo_footer()
