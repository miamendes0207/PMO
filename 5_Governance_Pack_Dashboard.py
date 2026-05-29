# ============================================================
# 5_📊_Governance_Pack_Dashboard.py — ScopeSight v3.7
# FIXES:
# ✅ Exec/RAID/Actions summaries render properly (no lost newlines/bullets)
# ✅ Prefer project-scoped RAIDs / Actions / Weekly NFR when a project is selected
#    (falls back gracefully if DB tables don’t have project_id)
# ============================================================

import streamlit as st
import os
import datetime as dt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# ---------------------------------------------------------
# PAGE CONFIG  (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="📊 Governance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# IMPORTS AFTER CONFIG
# ---------------------------------------------------------
from modules.ui_hide_nav import hide_streamlit_nav
from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar

from modules.db import run_query, get_project_tasks
from modules.gov_builder.gov_config import default_reporting_period

from modules.gov_builder.gov_ai import (
    GovBrief,
    filter_records_for_period,
    ExecSummaryAgent,
    DeliverySummaryAgent,
    RisksIssuesAgent,
    ActionsSummaryAgent,
)

# ---------------------------------------------------------
# AUTH + DEV OVERRIDES
# ---------------------------------------------------------
hide_streamlit_nav()
require_login()

try:
    query = st.query_params
except AttributeError:
    query = st.experimental_get_query_params()

if query.get("dev") == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True

# ---------------------------------------------------------
# THEME + SIDEBAR
# ---------------------------------------------------------
set_pmo_theme(page_title="📊 Governance Dashboard")
render_sidebar()

# ---------------------------------------------------------
# ENHANCED GLOBAL STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Main header styling */
.main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2rem 2rem;
    border-radius: 12px;
    margin-bottom: 2rem;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
}
.main-header h1 {
    color: white;
    margin: 0;
    font-size: 2rem;
    font-weight: 700;
}
.main-header p {
    color: rgba(255, 255, 255, 0.9);
    margin: 0.5rem 0 0 0;
    font-size: 1.1rem;
}

/* Section headers */
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 0.75rem 1.25rem;
    border-radius: 10px;
    margin: 1.5rem 0 1rem 0;
    box-shadow: 0 2px 8px rgba(79, 172, 254, 0.2);
}
.section-header h3 {
    color: white;
    margin: 0;
    font-size: 1.1rem;
    font-weight: 700;
}

/* KPI Cards */
.kpi-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
}
.kpi-card {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border-radius: 12px;
    padding: 1.25rem;
    border: 2px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    border-color: #4facfe;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
}
.kpi-icon { font-size: 1.5rem; margin-bottom: 0.5rem; }
.kpi-label {
    font-size: 0.85rem;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.kpi-value {
    font-size: 2.25rem;
    color: #0f172a;
    font-weight: 800;
    margin: 0.5rem 0;
    line-height: 1;
}
.kpi-sub { font-size: 0.8rem; color: #94a3b8; margin-top: 0.5rem; }

/* Selection area */
.selection-area {
    background: #f9fafb;
    padding: 1.5rem;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    margin-bottom: 1.5rem;
}

/* Empty state */
.empty-state {
    text-align: center;
    padding: 3rem 2rem;
    background: #f9fafb;
    border-radius: 10px;
    border: 2px dashed #cbd5e1;
}
.empty-state-icon { font-size: 3rem; margin-bottom: 1rem; opacity: 0.5; }
.empty-state-text { color: #64748b; font-size: 1rem; }

/* Period indicator */
.period-indicator {
    background: #eff6ff;
    border-left: 4px solid #3b82f6;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1rem 0;
    font-size: 0.9rem;
    color: #1e40af;
}

/* AI cards (HTML) */
.ai-card {
    background: #ffffff;
    border-radius: 10px;
    padding: 1.25rem;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    margin: 0.75rem 0;
}
.ai-card p { margin: 0 0 0.75rem 0; color: #0f172a; }
.ai-card ul { margin: 0.25rem 0 0.75rem 1.25rem; }
.ai-card li { margin: 0.25rem 0; color: #0f172a; }
.ai-card b { color: #0f172a; }

/* Improved buttons */
div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 0.95rem;
    font-weight: 600;
    padding: 0.625rem 1.5rem;
    border: none;
    border-radius: 8px;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(79, 172, 254, 0.2);
}
div.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.35);
}

/* Tab styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: #f8fafc;
    padding: 0.5rem;
    border-radius: 10px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 0.625rem 1.25rem;
    font-weight: 600;
}

/* Spinner */
.stSpinner > div { border-color: #4facfe !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# AI RENDERING HELPERS (fixes bullets/newlines getting “flattened”)
# ============================================================

def _escape_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def _basic_md_to_html(md: str) -> str:
    """
    Minimal, safe Markdown-ish to HTML for our summaries:
    - **bold** -> <b>
    - lines starting with "* " -> <ul><li>
    - preserves paragraphs / line breaks
    This avoids Streamlit’s markdown being broken by injecting raw HTML wrappers.
    """
    text = _escape_html(md or "").strip()
    if not text:
        return ""

    # bold **x**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    lines = text.splitlines()

    out = []
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.strip()
        if not line:
            close_ul()
            out.append("<br>")
            continue

        if line.startswith("* "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{line[2:].strip()}</li>")
        else:
            close_ul()
            out.append(f"<p>{line}</p>")

    close_ul()
    return "\n".join(out)

def render_ai_card(md_text: str):
    html = _basic_md_to_html(md_text)
    if not html:
        st.info("No content available.")
        return
    st.markdown(f"<div class='ai-card'>{html}</div>", unsafe_allow_html=True)

# ============================================================
# DATA LOADERS
# ============================================================

def load_clients():
    return run_query(
        """
        SELECT id AS client_id, client_name, client_code
        FROM client_scaffold
        WHERE status = 'approved'
        ORDER BY client_name
        """
    )

def load_projects_for_client(client_id: int):
    return run_query(
        """
        SELECT
            project_id,
            project_name,
            project_code,
            project_start_date,
            expected_end_date
        FROM projects
        WHERE client_id = :cid
          AND status = 'open'
        ORDER BY project_name
        """,
        {"cid": client_id},
    )

def load_raid_data(client_id: int, project_id: int | None):
    """
    Prefer project-scoped raids when project_id is supplied.
    Falls back gracefully if raids table doesn't have project_id.
    """
    if project_id is not None:
        try:
            return run_query(
                """
                SELECT *
                FROM raids
                WHERE client_id = :cid
                  AND project_id = :pid
                ORDER BY created_at DESC NULLS LAST
                LIMIT 400
                """,
                {"cid": client_id, "pid": project_id},
            )
        except Exception:
            pass

    return run_query(
        """
        SELECT *
        FROM raids
        WHERE client_id = :cid
        ORDER BY created_at DESC NULLS LAST
        LIMIT 400
        """,
        {"cid": client_id},
    )

def load_action_data(client_id: int, project_id: int | None):
    """
    Prefer project-scoped actions when project_id is supplied.
    Falls back gracefully if actions table doesn't have project_id.
    """
    if project_id is not None:
        try:
            return run_query(
                """
                SELECT *
                FROM actions
                WHERE client_id = :cid
                  AND project_id = :pid
                ORDER BY due_date NULLS LAST, created_at DESC
                LIMIT 800
                """,
                {"cid": client_id, "pid": project_id},
            )
        except Exception:
            pass

    return run_query(
        """
        SELECT *
        FROM actions
        WHERE client_id = :cid
        ORDER BY due_date NULLS LAST, created_at DESC
        LIMIT 800
        """,
        {"cid": client_id},
    )

def load_weekly_nfr(client_id: int, project_id: int | None, period_start: dt.date, period_end: dt.date):
    """
    Prefer project-scoped weekly NFRs when project_id is supplied.
    Falls back gracefully if weekly_nfr table doesn't have project_id.
    """
    if project_id is not None:
        try:
            return run_query(
                """
                SELECT *
                FROM weekly_nfr
                WHERE client_id = :cid
                  AND project_id = :pid
                  AND week_commencing >= :start
                  AND week_commencing <= :end
                ORDER BY week_commencing DESC
                """,
                {"cid": client_id, "pid": project_id, "start": period_start, "end": period_end},
            )
        except Exception:
            pass

    return run_query(
        """
        SELECT *
        FROM weekly_nfr
        WHERE client_id = :cid
          AND week_commencing >= :start
          AND week_commencing <= :end
        ORDER BY week_commencing DESC
        """,
        {"cid": client_id, "start": period_start, "end": period_end},
    )

# ============================================================
# RECORD SANITIZER
# ============================================================

def _safe_str(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            import json
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    return str(v)

def sanitize_records(records):
    clean = []
    for r in records or []:
        rr = {}
        for k, v in (r or {}).items():
            rr[k] = _safe_str(v) if isinstance(v, (dict, list)) else v
        clean.append(rr)
    return clean

# ============================================================
# KPI HELPERS
# ============================================================

def compute_kpis(raid_df, actions_df):
    open_raids = 0
    high_risk_raids = 0
    open_actions = 0
    overdue_actions = 0

    if raid_df is not None and not raid_df.empty:
        if "status" in raid_df.columns:
            s = raid_df["status"].astype(str).str.lower()
            open_raids = (s.isin(["open", "in progress", "active"])).sum()

        score_col = "revised_score" if "revised_score" in raid_df.columns else "score"
        if score_col in raid_df.columns:
            high_risk_raids = (pd.to_numeric(raid_df[score_col], errors="coerce").fillna(0) >= 12).sum()

    if actions_df is not None and not actions_df.empty:
        s = actions_df["status"].astype(str).str.lower() if "status" in actions_df.columns else pd.Series([], dtype=str)
        open_mask = ~s.isin(["closed", "done", "completed"])
        open_actions = int(open_mask.sum()) if len(open_mask) else 0

        if "due_date" in actions_df.columns and len(open_mask):
            due = pd.to_datetime(actions_df["due_date"], errors="coerce")
            overdue_actions = int((open_mask & due.notna() & (due.dt.date < dt.date.today())).sum())

    return {
        "open_raids": int(open_raids),
        "high_risk": int(high_risk_raids),
        "open_actions": int(open_actions),
        "overdue_actions": int(overdue_actions),
    }

def render_kpi_cards(kpis: dict):
    html = f"""
    <div class="kpi-container">
        <div class="kpi-card">
            <div class="kpi-icon">⚠️</div>
            <div class="kpi-label">Open RAIDs</div>
            <div class="kpi-value">{kpis['open_raids']}</div>
            <div class="kpi-sub">Active risks, issues & dependencies</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-icon">🔴</div>
            <div class="kpi-label">High-Risk Items</div>
            <div class="kpi-value">{kpis['high_risk']}</div>
            <div class="kpi-sub">Score ≥ 12 requiring attention</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-icon">📋</div>
            <div class="kpi-label">Open Actions</div>
            <div class="kpi-value">{kpis['open_actions']}</div>
            <div class="kpi-sub">Pending completion</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-icon">⏰</div>
            <div class="kpi-label">Overdue Actions</div>
            <div class="kpi-value">{kpis['overdue_actions']}</div>
            <div class="kpi-sub">Past due date - needs attention</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# GANTT HELPERS
# ============================================================

def _safe_date(v):
    if v is None or pd.isna(v):
        return None
    if isinstance(v, dt.date):
        return v
    return pd.to_datetime(v).date()

def render_gantt_from_tasks(tasks_df: pd.DataFrame, project_name: str):
    if tasks_df is None or tasks_df.empty:
        st.markdown(
            """
        <div class="empty-state">
            <div class="empty-state-icon">📊</div>
            <div class="empty-state-text">No tasks found for this project's Gantt plan.</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        return

    df = tasks_df.copy()
    df["Start"] = df["start_date"].apply(_safe_date)
    df["Finish"] = df["end_date"].apply(_safe_date)

    df = df[df["Start"].notna() & df["Finish"].notna()]
    if df.empty:
        st.info("No tasks with valid start/end dates to show.")
        return

    def _bar_text(row):
        title = (row.get("title") or "").strip()
        pct = int(row.get("percent_complete") or 0)
        short = (title[:25] + "…") if len(title) > 26 else title
        return f"{short} ({pct}%)"

    df["BarText"] = df.apply(_bar_text, axis=1)

    ws_order = (
        df.groupby("workstream_name", dropna=False)["Start"]
        .min()
        .sort_values()
        .index.tolist()
    )

    colors = px.colors.qualitative.Set3

    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="workstream_name",
        color="workstream_name",
        text="BarText",
        hover_data={
            "workstream_name": True,
            "title": True,
            "priority": True,
            "status": True,
            "percent_complete": True,
            "Start": True,
            "Finish": True,
        },
        category_orders={"workstream_name": ws_order},
        color_discrete_sequence=colors,
    )

    fig.update_traces(
        textposition="inside",
        insidetextanchor="middle",
        cliponaxis=False,
        marker=dict(line=dict(width=0.5, color="rgba(0,0,0,0.2)")),
    )

    fig.update_yaxes(showticklabels=True, title=None)

    today = dt.date.today()
    today_dt = dt.datetime.combine(today, dt.time())

    fig.add_shape(
        type="line",
        x0=today_dt,
        x1=today_dt,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line=dict(color="#ef4444", width=2.5, dash="dash"),
    )

    fig.add_annotation(
        x=today_dt,
        y=1.02,
        xref="x",
        yref="paper",
        text="📍 Today",
        showarrow=False,
        xanchor="center",
        yanchor="bottom",
        font=dict(size=11, color="#ef4444"),
        bgcolor="rgba(255, 255, 255, 0.9)",
        bordercolor="#ef4444",
        borderwidth=1,
        borderpad=4,
    )

    fig.update_layout(
        height=max(500, 70 + 40 * len(ws_order)),
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(248, 250, 252, 0.5)",
        paper_bgcolor="white",
        title=dict(text=f"<b>Delivery Timeline</b> — {project_name}", x=0.5, xanchor="center"),
    )

    st.plotly_chart(fig, use_container_width=True)

def render_upcoming_milestones(tasks_df: pd.DataFrame):
    if tasks_df is None or tasks_df.empty:
        st.markdown(
            """
        <div class="empty-state">
            <div class="empty-state-icon">📅</div>
            <div class="empty-state-text">No plan data available to derive upcoming milestones.</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        return

    df = tasks_df.copy()
    df["start_dt"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_dt"] = pd.to_datetime(df["end_date"], errors="coerce")

    if "status" in df.columns:
        s = df["status"].astype(str).str.lower()
        df = df[~s.isin(["done", "completed"])]

    if df.empty:
        st.info("No open tasks available for upcoming milestones.")
        return

    today = dt.date.today()
    next_week = today + dt.timedelta(days=7)

    start_in_window = df["start_dt"].dt.date.between(today, next_week)
    end_in_window = df["end_dt"].dt.date.between(today, next_week)
    window_df = df[start_in_window | end_in_window]

    if window_df.empty:
        st.info("✅ No key milestones starting or ending in the next 7 days.")
        return

    st.markdown(
        f"""
    <div class="period-indicator">
        📌 <b>{len(window_df)}</b> upcoming milestone(s) in the next 7 days
    </div>
    """,
        unsafe_allow_html=True,
    )

    cols = [c for c in ["workstream_name", "title", "start_date", "end_date", "status", "percent_complete", "priority"]
            if c in window_df.columns]
    window_df = window_df[cols].copy()

    if "start_date" in window_df.columns:
        window_df = window_df.sort_values("start_date")

    window_df = window_df.head(20)
    st.dataframe(window_df, use_container_width=True, hide_index=True)

# ============================================================
# MAIN DASHBOARD
# ============================================================

def main():
    # ---------------------------
    # SELECTION AREA
    # ---------------------------
    with st.container():
        st.markdown(
            """
        <div class='section-header'>
            <h3>🎯 Select Context</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='selection-area'>", unsafe_allow_html=True)

        clients_df = load_clients()
        if clients_df is None or clients_df.empty:
            st.error("❌ No approved clients found. Please contact your administrator.")
            pmo_footer()
            return

        col1, col2 = st.columns(2)
        with col1:
            client_name = st.selectbox("📁 Client", clients_df["client_name"], help="Select the client for governance reporting")
            row = clients_df[clients_df["client_name"] == client_name].iloc[0]
            client_id = int(row["client_id"])

        with col2:
            projects_df = load_projects_for_client(client_id)
            selected_project_row = None
            project_name = None
            project_id = None

            if projects_df is not None and not projects_df.empty:
                project_name = st.selectbox("📊 Project (for Gantt)", projects_df["project_name"], help="Select a project to scope the summary + view timeline")
                selected_project_row = projects_df[projects_df["project_name"] == project_name].iloc[0]
                project_id = int(selected_project_row.get("project_id"))
            else:
                st.info("ℹ️ No open projects found for this client")

        st.markdown("---")

        st.markdown("**📅 Reporting Period**")
        default_start, default_end = default_reporting_period()

        col3, col4 = st.columns(2)
        with col3:
            period_start = st.date_input("Start Date", default_start)
        with col4:
            period_end = st.date_input("End Date", default_end)

        if period_end < period_start:
            st.error("⚠️ End date cannot be before start date.")
            st.stop()

        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------
    # LOAD DATA
    # ---------------------------
    with st.spinner("🔄 Loading governance data..."):
        raids_df = load_raid_data(client_id, project_id)
        actions_df = load_action_data(client_id, project_id)
        weekly_df = load_weekly_nfr(client_id, project_id, period_start, period_end)

        tasks_df = None
        if project_id is not None:
            tasks_df = get_project_tasks(project_id)

    # Sanitize records
    raid_records_all = sanitize_records(raids_df.to_dict("records")) if raids_df is not None and not raids_df.empty else []
    action_records_all = sanitize_records(actions_df.to_dict("records")) if actions_df is not None and not actions_df.empty else []
    weekly_records_all = sanitize_records(weekly_df.to_dict("records")) if weekly_df is not None and not weekly_df.empty else []
    task_records_all = sanitize_records(tasks_df.to_dict("records")) if tasks_df is not None and not tasks_df.empty else []

    # Filter for period
    weekly_records = filter_records_for_period(weekly_records_all, period_start, period_end, kind="weekly_nfr")
    raid_records = filter_records_for_period(raid_records_all, period_start, period_end, kind="raids")
    action_records = filter_records_for_period(action_records_all, period_start, period_end, kind="actions")
    task_records = filter_records_for_period(task_records_all, period_start, period_end, kind="tasks")

    # Compute KPIs (already scoped to project if project_id exists + DB supports it)
    kpis = compute_kpis(
        raids_df if raids_df is not None else pd.DataFrame(),
        actions_df if actions_df is not None else pd.DataFrame(),
    )

    # Build governance brief
    brief = GovBrief(
        client_name=client_name,
        project_name=project_name,
        period_start=period_start,
        period_end=period_end,
        weekly_nfr=weekly_records,
        raids=raid_records,
        actions=action_records,
        tasks=task_records,
        kpis=kpis,
    )

    # ========================================================
    # TABS LAYOUT
    # ========================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Overview",
        "📅 Timeline & Gantt",
        "⚠️ RAIDs",
        "✅ Actions"
    ])

    # ---------------------------
    # TAB 1: OVERVIEW
    # ---------------------------
    with tab1:
        st.markdown(
            """
        <div class='section-header'>
            <h3>📊 Key Metrics</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        render_kpi_cards(kpis)

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            f"""
        <div class="period-indicator">
            📅 Reporting Period: <b>{period_start.strftime('%d %b %Y')}</b> → <b>{period_end.strftime('%d %b %Y')}</b>
            {"<br>📌 Scoped to: <b>" + project_name + "</b>" if project_name else "<br>📌 Scope: <b>Client-level (no project selected)</b>"}
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
        <div class='section-header'>
            <h3>🤖 AI-Powered Insights</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        with st.spinner("🧠 Generating governance insights..."):
            exec_sum = ExecSummaryAgent().run(brief)
            delivery_sum = DeliverySummaryAgent().run(brief)
            risk_sum = RisksIssuesAgent().run(brief)
            actions_sum = ActionsSummaryAgent().run(brief)

        # Executive Summary
        with st.expander("⭐ **Executive Summary**", expanded=True):
            render_ai_card(exec_sum)

        col_left, col_right = st.columns(2)
        with col_left:
            with st.expander("🚚 **Delivery Summary**", expanded=True):
                render_ai_card(delivery_sum)

        with col_right:
            with st.expander("⚠️ **Risks & Issues Summary**", expanded=True):
                render_ai_card(risk_sum)

        with st.expander("📝 **Actions Summary**", expanded=True):
            render_ai_card(actions_sum)

    # ---------------------------
    # TAB 2: TIMELINE & GANTT
    # ---------------------------
    with tab2:
        st.markdown(
            """
        <div class='section-header'>
            <h3>📅 Project Delivery Timeline</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        if selected_project_row is None or tasks_df is None:
            st.markdown(
                """
            <div class="empty-state">
                <div class="empty-state-icon">📊</div>
                <div class="empty-state-text">
                    Select an open project above to view the Gantt chart.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
        else:
            render_gantt_from_tasks(tasks_df, project_name or "Project")

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            """
        <div class='section-header'>
            <h3>📌 Upcoming Milestones</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        render_upcoming_milestones(tasks_df)

    # ---------------------------
    # TAB 3: RAIDS SNAPSHOT
    # ---------------------------
    with tab3:
        st.markdown(
            """
        <div class='section-header'>
            <h3>⚠️ RAIDs Snapshot</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        if raids_df is None or raids_df.empty:
            st.markdown(
                """
            <div class="empty-state">
                <div class="empty-state-icon">✅</div>
                <div class="empty-state-text">No RAIDs found for this scope.</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
        else:
            col1, col2, col3, col4 = st.columns(4)

            total_raids = len(raids_df)
            open_count = kpis["open_raids"]
            high_risk_count = kpis["high_risk"]

            with col1:
                st.metric("Total RAIDs", total_raids)
            with col2:
                st.metric("Open", open_count)
            with col3:
                st.metric("High Risk", high_risk_count, delta=None if high_risk_count == 0 else "Attention needed")
            with col4:
                closed_count = total_raids - open_count
                st.metric("Closed", closed_count)

            st.markdown("<br>", unsafe_allow_html=True)

            snapshot = raids_df.copy()
            sort_cols = []
            if "revised_score" in snapshot.columns:
                sort_cols.append(("revised_score", False))
            elif "score" in snapshot.columns:
                sort_cols.append(("score", False))
            if "created_at" in snapshot.columns:
                sort_cols.append(("created_at", False))

            if sort_cols:
                by = [c[0] for c in sort_cols]
                asc = [c[1] for c in sort_cols]
                snapshot = snapshot.sort_values(by=by, ascending=asc)

            snapshot = snapshot.head(50)
            st.caption(f"Showing top {len(snapshot)} RAIDs (sorted by risk score and date)")
            st.dataframe(snapshot, use_container_width=True, height=400)

    # ---------------------------
    # TAB 4: ACTIONS SNAPSHOT
    # ---------------------------
    with tab4:
        st.markdown(
            """
        <div class='section-header'>
            <h3>✅ Actions Snapshot</h3>
        </div>
        """,
            unsafe_allow_html=True,
        )

        if actions_df is None or actions_df.empty:
            st.markdown(
                """
            <div class="empty-state">
                <div class="empty-state-icon">✅</div>
                <div class="empty-state-text">No actions found for this scope.</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
        else:
            col1, col2, col3, col4 = st.columns(4)

            total_actions = len(actions_df)
            open_count = kpis["open_actions"]
            overdue_count = kpis["overdue_actions"]

            with col1:
                st.metric("Total Actions", total_actions)
            with col2:
                st.metric("Open", open_count)
            with col3:
                st.metric("Overdue", overdue_count, delta=None if overdue_count == 0 else "Urgent")
            with col4:
                completed_count = total_actions - open_count
                st.metric("Completed", completed_count)

            st.markdown("<br>", unsafe_allow_html=True)

            snapshot = actions_df.copy()

            if "due_date" in snapshot.columns:
                due = pd.to_datetime(snapshot["due_date"], errors="coerce")
                snapshot["__due"] = due
                if "status" in snapshot.columns:
                    s = snapshot["status"].astype(str).str.lower()
                    open_mask = ~s.isin(["closed", "done", "completed"])
                    snapshot["__open_flag"] = open_mask.astype(int)
                    snapshot = snapshot.sort_values(by=["__open_flag", "__due"], ascending=[False, True])
                else:
                    snapshot = snapshot.sort_values(by="__due", ascending=True)

            snapshot = snapshot.head(50)
            snapshot = snapshot.drop(columns=[c for c in ["__due", "__open_flag"] if c in snapshot.columns])

            st.caption(f"Showing top {len(snapshot)} actions (open items prioritised, sorted by due date)")
            st.dataframe(snapshot, use_container_width=True, height=400)

    pmo_footer()


if __name__ == "__main__":
    main()
