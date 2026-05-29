# ============================================================
# 22_📈_CEO_Portfolio_Overview.py — ScopeSight v3.0
# CEO Portfolio Overview (Schema-Aligned)
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
def get_single_value(df, default=0):
    if df is None or df.empty:
        return default
    try:
        return df.iloc[0, 0] or default
    except Exception:
        return default


# ---------------------------------------------------------
# INIT
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

st.set_page_config(
    page_title="📈 CEO Portfolio Overview",
    page_icon="📈",
    layout="wide",
)

set_pmo_theme(page_title="📈 CEO Portfolio Overview")
render_sidebar()

# ---------------------------------------------------------
# CSS
# ---------------------------------------------------------
st.markdown("""
<style>
header[data-testid="stHeader"] {
    height: 0px !important;
    visibility: hidden !important;
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
    border-radius: 4px;
    margin-bottom:1.5rem;
}
.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e6f2ff;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# INTRO
# ---------------------------------------------------------
st.markdown("""
<div style='text-align:center; max-width:850px; margin:auto;
font-size:1.05rem; line-height:1.55;'>
High-level visibility of clients, projects, risks, KPIs,
and overall portfolio performance across the organisation.
</div>
""", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)


# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview",
    "🎯 RAG Distribution",
    "🧭 Client Performance",
    "🔥 Top Risks",
    "📝 Overdue Actions",
    "📘 NFR Reports"
])


# ============================================================
# ▶ TAB 1 — OVERVIEW & TOP METRICS
# ============================================================
with tab1:

    st.markdown("""
    <div class='section-header'><h3>📊 Portfolio at a Glance</h3></div>
    <div class='info-box'>
        <b>Quick tip:</b> Use this dashboard as a <b>portfolio health check</b> —
        watch green projects, overdue actions, and open risks.
    </div>
    """, unsafe_allow_html=True)

    total_clients = get_single_value(run_query("SELECT COUNT(*) FROM clients"))

    total_projects = get_single_value(run_query("SELECT COUNT(*) FROM projects"))

    active_projects = get_single_value(run_query("""
        SELECT COUNT(*)
        FROM projects
        WHERE status ILIKE 'open'
    """))

    green_projects = get_single_value(run_query("""
        SELECT COUNT(*)
        FROM projects
        WHERE health_score >= 75
    """))

    on_track_pct = round((green_projects / total_projects) * 100) if total_projects else 0

    avg_delivery_score = get_single_value(
        run_query("SELECT AVG(delivery_score) FROM client_kpis")
    )

    avg_budget_health = get_single_value(
        run_query("SELECT AVG(budget_health) FROM client_kpis")
    )

    open_risks = get_single_value(run_query("""
        SELECT COUNT(*)
        FROM raids
        WHERE status ILIKE 'open'
    """))

    overdue_actions = get_single_value(run_query("""
        SELECT COUNT(*)
        FROM actions
        WHERE due_date < CURRENT_DATE
          AND status NOT ILIKE 'closed'
    """))

    nfr_30 = get_single_value(run_query("""
        SELECT COUNT(*)
        FROM nfr_reports
        WHERE week_start >= CURRENT_DATE - INTERVAL '30 days'
    """))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clients", total_clients)
    c2.metric("Active Projects", active_projects)
    c3.metric("On Track (Green)", f"{on_track_pct}%")
    c4.metric("Open Risks", open_risks)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Avg Delivery Score", f"{round(avg_delivery_score or 0)}%")
    c6.metric("Avg Budget Health", f"{round(avg_budget_health or 0)}%")
    c7.metric("Overdue Actions", overdue_actions)
    c8.metric("NFRs (30 Days)", nfr_30)


# ============================================================
# ▶ TAB 2 — RAG DISTRIBUTION
# ============================================================
with tab2:

    st.markdown("<div class='section-header'><h3>🎯 Project RAG Status</h3></div>", unsafe_allow_html=True)

    rag_df = run_query("""
        SELECT
            CASE
                WHEN health_score >= 75 THEN 'Green'
                WHEN health_score >= 50 THEN 'Amber'
                ELSE 'Red'
            END AS rag_status,
            COUNT(*) AS count
        FROM projects
        GROUP BY 1
    """)

    if rag_df is not None and not rag_df.empty:
        rag_df = rag_df.set_index("rag_status")
        st.bar_chart(rag_df)
    else:
        st.info("No project health data available.")


# ============================================================
# ▶ TAB 3 — CLIENT PERFORMANCE
# ============================================================
with tab3:

    st.markdown("<div class='section-header'><h3>🧭 Client Performance Snapshot</h3></div>", unsafe_allow_html=True)

    client_perf_df = run_query("""
        SELECT
            c.client_name,
            k.delivery_score,
            k.risk_index,
            k.budget_health,
            k.velocity_score,
            k.period_start,
            k.period_end
        FROM client_kpis k
        JOIN clients c ON k.client_id = c.client_id
        ORDER BY k.period_end DESC
        LIMIT 50
    """)

    if client_perf_df is not None and not client_perf_df.empty:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(client_perf_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No client KPI data found.")


# ============================================================
# ▶ TAB 4 — TOP RISKS
# ============================================================
with tab4:

    st.markdown("<div class='section-header'><h3>🔥 Highest Portfolio Risks</h3></div>", unsafe_allow_html=True)

    risks_df = run_query("""
        SELECT
            c.client_name,
            r.raid_type,
            r.title,
            r.probability,
            r.severity,
            r.revised_score,
            r.owner_plen,
            r.owner_client,
            r.status
        FROM raids r
        LEFT JOIN clients c ON r.client_id = c.client_id
        WHERE r.status ILIKE 'open'
        ORDER BY r.revised_score DESC
        LIMIT 20
    """)

    if risks_df is not None and not risks_df.empty:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(risks_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No open risks found.")


# ============================================================
# ▶ TAB 5 — OVERDUE ACTIONS
# ============================================================
with tab5:

    st.markdown("<div class='section-header'><h3>📝 Overdue Actions</h3></div>", unsafe_allow_html=True)

    actions_df = run_query("""
        SELECT
            c.client_name,
            a.title,
            a.owner,
            a.priority,
            a.status,
            a.due_date
        FROM actions a
        LEFT JOIN clients c ON a.client_id = c.client_id
        WHERE a.due_date < CURRENT_DATE
          AND a.status NOT ILIKE 'closed'
        ORDER BY a.due_date ASC
    """)

    if actions_df is not None and not actions_df.empty:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(actions_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.success("No overdue actions — strong performance!")


# ============================================================
# ▶ TAB 6 — NFR ACTIVITY
# ============================================================
with tab6:

    st.markdown("<div class='section-header'><h3>📘 Recent NFR Activity</h3></div>", unsafe_allow_html=True)

    nfr_df = run_query("""
        SELECT
            c.client_name,
            n.week_start,
            n.week_end,
            LEFT(n.summary_text, 200) AS summary_preview
        FROM nfr_reports n
        LEFT JOIN clients c ON n.client_id = c.client_id
        ORDER BY n.week_start DESC
        LIMIT 20
    """)

    if nfr_df is not None and not nfr_df.empty:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(nfr_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No NFR reports yet.")


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
