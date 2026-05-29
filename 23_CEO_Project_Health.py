# ============================================================
# 23_💡_CEO_Project_Health.py — ScopeSight v3.0
# CEO Portfolio Delivery Health Dashboard (RUN_QUERY SAFE)
# ============================================================

import streamlit as st
from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# INIT
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

st.set_page_config(
    page_title="💡 Portfolio Project Health",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
)

set_pmo_theme(page_title="💡 Portfolio Health Overview")
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
# INTRO (Tracker-style header + green divider + tip)
# ---------------------------------------------------------
st.markdown(
    """
<div style='text-align: center; padding: 2rem 0;'>
    <p style='color: #666; font-size: 1.1rem;'>
        Portfolio-wide summary of delivery confidence and overall project health.
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
    RAG metrics give a quick portfolio read. The table highlights off-track projects first, and the trend shows average health over time when available.
</div>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# SESSION CONTEXT
# ---------------------------------------------------------
role = st.session_state.get("role")
client_id = st.session_state.get("client_id")


# ---------------------------------------------------------
# CLIENT SCOPE LOGIC
# ---------------------------------------------------------
project_where = ""
trend_where = ""

if role != "ceo":
    if not client_id:
        st.error("No client context available.")
        st.stop()

    project_where = f"WHERE p.client_id = {int(client_id)}"
    trend_where = f"WHERE client_id = {int(client_id)}"


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def single_value(df, default=0):
    if df is None or df.empty:
        return default
    return df.iloc[0, 0] or default


def get_table_columns(table_name: str) -> set[str]:
    df = run_query(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = '{table_name}'
    """)
    if df is None or df.empty:
        return set()
    return set(df["column_name"].tolist())


def first_existing(colset: set[str], candidates: list[str]):
    for c in candidates:
        if c in colset:
            return c
    return None


# ---------------------------------------------------------
# SCHEMA DISCOVERY
# ---------------------------------------------------------
projects_cols = get_table_columns("projects")
trend_cols = get_table_columns("exec_project_health_trend")

health_score_col = "health_score" if "health_score" in projects_cols else None
project_name_col = first_existing(projects_cols, ["project_name", "name", "title"])
status_col = "status" if "status" in projects_cols else None
pm_col = first_existing(projects_cols, ["project_manager", "owner"])
start_col = first_existing(projects_cols, ["start_date", "created_at"])
end_col = first_existing(projects_cols, ["expected_end_date", "end_date", "due_date"])

trend_date_col = first_existing(
    trend_cols,
    ["updated_at", "created_at", "snapshot_date", "recorded_on", "date"]
)

if not project_name_col or not health_score_col:
    st.error("Required project fields missing (project_name / health_score).")
    st.stop()


# ============================================================
# PORTFOLIO RAG METRICS
# ============================================================
def rag_count(condition: str):
    sql = f"""
        SELECT COUNT(*)
        FROM projects p
        {project_where}
        {"AND" if project_where else "WHERE"} {condition}
    """
    return single_value(run_query(sql))


st.markdown(
    """
<div class='section-header'>
    <h3>🧭 Portfolio RAG Overview</h3>
</div>
""",
    unsafe_allow_html=True,
)

green = rag_count(f"{health_score_col} >= 75")
amber = rag_count(f"{health_score_col} BETWEEN 50 AND 74")
red = rag_count(f"{health_score_col} < 50")

col1, col2, col3 = st.columns(3)
col1.metric("🟢 On Track", green)
col2.metric("🟠 At Risk", amber)
col3.metric("🔴 Off Track", red)


# ============================================================
# PROJECT HEALTH TABLE
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>📋 Project Health Summary</h3>
</div>
""",
    unsafe_allow_html=True,
)

select_cols = [
    f"p.{project_name_col} AS project_name",
    "c.client_name",
    f"p.{health_score_col} AS health_score",
    f"""
        CASE
            WHEN p.{health_score_col} >= 75 THEN 'Green'
            WHEN p.{health_score_col} >= 50 THEN 'Amber'
            ELSE 'Red'
        END AS health_rag
    """
]

if status_col:
    select_cols.append(f"p.{status_col} AS status")
if start_col:
    select_cols.append(f"p.{start_col} AS start_date")
if end_col:
    select_cols.append(f"p.{end_col} AS end_date")
if pm_col:
    select_cols.append(f"p.{pm_col} AS project_manager")

projects_df = run_query(f"""
    SELECT {", ".join(select_cols)}
    FROM projects p
    JOIN clients c ON p.client_id = c.client_id
    {project_where}
    ORDER BY
        CASE
            WHEN p.{health_score_col} < 50 THEN 1
            WHEN p.{health_score_col} < 75 THEN 2
            ELSE 3
        END,
        project_name
""")

if projects_df is not None and not projects_df.empty:
    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.dataframe(projects_df, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("No projects found.")


# ============================================================
# PORTFOLIO HEALTH TREND (OPTIONAL)
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>📈 Portfolio Delivery Health Trend</h3>
</div>
""",
    unsafe_allow_html=True,
)

if trend_date_col and "health_score" in trend_cols:
    trend_df = run_query(f"""
        SELECT
            {trend_date_col}::date AS date,
            AVG(health_score) AS avg_health
        FROM exec_project_health_trend
        {trend_where}
        GROUP BY {trend_date_col}::date
        ORDER BY date ASC
    """)

    if trend_df is not None and not trend_df.empty:
        st.markdown(
            """
<div class='step-header'>
    <h4>Average Health Score Over Time</h4>
</div>
""",
            unsafe_allow_html=True,
        )
        trend_df = trend_df.set_index("date")
        st.line_chart(trend_df)
    else:
        st.info("No historical health trend data available yet.")
else:
    st.info("Health trend unavailable (no date column in trend table).")


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)
pmo_footer()
