# ============================================================
# 26_📈_Exec_Project_Summary.py — ScopeSight v3.3 (FIXED)
#
# KEY FIXES vs v3.2:
#   ✅ Project context loaded via exec_project_summary VIEW for consistent RAG
#   ✅ raids queried with correct PK: raid_id (not id)
#   ✅ actions queried with correct PK: action_id (not id)
#   ✅ nfr count from weekly_nfr / week_commencing (not nfr_reports.week_start)
#   ✅ project_scaffold join uses project_code OR project_name (no 'id' column)
# ============================================================

import streamlit as st
import json
import datetime as dt
import requests
import re

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

st.set_page_config(
    page_title="📊 Executive Project Summary",
    page_icon="📊",
    layout="wide",
)


def safe(df):
    if df is None or getattr(df, "empty", True): return 0
    try:
        return list(df.iloc[0])[0] or 0
    except Exception:
        return 0


def _normalize_exec_summary(text: str) -> str:
    if not text: return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    headings = ["DELIVERY", "SCHEDULE", "RISKS", "ACTIONS", "GOVERNANCE & SIGNALS"]
    for h in headings:
        t = re.sub(rf"(?m)^{re.escape(h)}\s+(?=\S)", f"{h}\n\n", t)
        t = re.sub(rf"(?m)^{re.escape(h)}\n(?!\n)", f"{h}\n\n", t)
    t = re.sub(r"(?<=\d)\s*\n\s*(?=\d)", "", t)
    t = re.sub(r"(?m)^[ \t]*[•–—]\s*", "- ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


# ── Project exec context ──────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_project_exec_context(project_id: int) -> dict:
    """
    Loads project data preferring exec_project_summary view for RAG/health.
    Falls back to raw projects table if view not yet created.
    """

    # Try exec view first (correct RAG) — probe optional columns defensively
    def _evc(col):
        from modules.db import run_query as _rq
        df = _rq(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='exec_project_summary' AND column_name=:c LIMIT 1",
            {"c": col},
        )
        return df is not None and not df.empty

    _s = lambda col, alias=None, typ="text": (
        (f"{col}" + (f" AS {alias}" if alias else ""))
        if _evc(col) else
        (f"NULL::{typ}" + (f" AS {alias}" if alias else f" AS {col}"))
    )

    proj_df = run_query(
        f"""
        SELECT
            project_id, client_id, client_name, project_name, project_code,
            rag_status, {_s("rag_source")}, health_score, status,
            project_start_date AS start_date,
            expected_end_date  AS end_date,
            project_manager, delivery_lead,
            {_s("latest_summary")},
            {_s("last_status_update_at", alias="updated_at")}
        FROM public.exec_project_summary
        WHERE project_id = :pid
        LIMIT 1
        """,
        {"pid": project_id},
    )

    # Fallback to raw projects + scaffold join
    if proj_df is None or proj_df.empty:
        proj_df = run_query(
            """
            SELECT
                p.project_id, p.client_id, c.client_name,
                p.project_name, p.project_code,
                p.rag_status, 'base' AS rag_source,
                p.health_score, p.status,
                COALESCE(p.project_start_date, ps.project_start_date) AS start_date,
                COALESCE(p.expected_end_date,  ps.expected_end_date)  AS end_date,
                COALESCE(p.project_manager,    ps.project_manager)    AS project_manager,
                p.delivery_lead, NULL::text AS latest_summary, p.updated_at
            FROM public.projects p
            LEFT JOIN public.project_scaffold ps
              ON ps.client_id = p.client_id
             AND (ps.project_code = p.project_code OR ps.project_name = p.project_name)
            LEFT JOIN public.client_scaffold c ON c.id = p.client_id
            WHERE p.project_id = :pid
            LIMIT 1
            """,
            {"pid": project_id},
        )

    project = {} if proj_df is None or proj_df.empty else proj_df.to_dict("records")[0]

    # RAID snapshot for exec summary context (top open items by score)
    risk_df = run_query(
        """
        SELECT
            raid_id, raid_type AS type, title, description,
            likelihood, impact, probability, severity,
            COALESCE(revised_score, score) AS effective_score,
            status, owner, mitigation_plan, date_raised, planned_close
        FROM public.raids
        WHERE project_id = :pid
          AND LOWER(status) NOT IN ('closed', 'completed')
        ORDER BY COALESCE(revised_score, score, 0) DESC, severity DESC NULLS LAST
        LIMIT 10
        """,
        {"pid": project_id},
    )

    # Actions — FIX: use action_id not id
    actions_df = run_query(
        """
        SELECT action_id, title, owner, status, due_date, priority, updated_at
        FROM public.actions
        WHERE project_id = :pid
          AND LOWER(status) NOT IN ('closed', 'completed')
        ORDER BY due_date ASC NULLS LAST
        LIMIT 30
        """,
        {"pid": project_id},
    )

    # NFR: extended window + daily_nfr fallback if weekly_nfr has no rows
    nfr_meta = run_query(
        """
        SELECT COUNT(*) AS nfr_count_30d, MAX(week_commencing) AS last_week_start
        FROM public.weekly_nfr
        WHERE project_id = :pid
          AND week_commencing >= CURRENT_DATE - INTERVAL '90 days'

        """,
        {"pid": project_id},
    )

    return {
        "project_id": project_id,
        "project": project,
        "risks": [] if risk_df is None or risk_df.empty else risk_df.to_dict("records"),
        "actions": [] if actions_df is None or actions_df.empty else actions_df.to_dict("records"),
        "nfr": {} if nfr_meta is None or nfr_meta.empty else nfr_meta.to_dict("records")[0],
        "generated_at_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
    }


def _rule_based_detailed_summary(context: dict) -> str:
    project = context.get("project", {}) or {}
    risks = context.get("risks", []) or []
    actions = context.get("actions", []) or []
    nfr = context.get("nfr", {}) or {}

    def _d(x):
        return "Not recorded" if x in (None, "", "nan") else str(x)

    rag = _d(project.get("rag_status"))
    hs = _d(project.get("health_score"))
    status = _d(project.get("status"))
    pm = _d(project.get("project_manager"))
    proj = _d(project.get("project_name"))
    rag_src = project.get("rag_source", "base")
    dates = f"{_d(project.get('start_date'))} → {_d(project.get('end_date'))}"

    delivery = (
        f"Project health: RAG={rag} (source: {rag_src}) | Health Score={hs} | Status={status}. PM={pm}. "
    )
    if rag.lower() == "red":
        delivery += "Material delivery risk present; confirm recovery plan, blockers, and exec decisions required."
    elif rag.lower() == "amber":
        delivery += "Emerging pressure — intervene early on schedule/resourcing/dependencies."
    elif rag.lower() == "green":
        delivery += "Signals stable; maintain cadence and proactive risk/action control."
    else:
        delivery += "RAG not recorded — enforce health reporting cadence."

    schedule = (
        f"- Project: {proj}\n- Dates: {dates}\n- Status: {status}\n- PM: {pm}"
    )

    risk_text = "\n".join(
        f"- {r.get('title', '(untitled)')} (L/I: {r.get('likelihood', '?')}/{r.get('impact', '?')}) — "
        f"{r.get('description', '') or 'No description.'}"
        for r in risks[:5]
    ) if risks else "No open risks recorded.\n- Confirm RAID log is actively maintained."

    today = dt.date.today()
    overdue, upcoming = [], []
    for a in actions:
        if (a.get("status") or "").lower() in ("closed", "completed"): continue
        due = a.get("due_date")
        due_date = None
        try:
            due_date = due if isinstance(due, dt.date) else dt.date.fromisoformat(str(due)[:10])
        except Exception:
            pass
        (overdue if due_date and due_date < today else upcoming).append(a)

    action_lines = []
    for label, lst in (("Overdue:", overdue[:5]), ("Upcoming:", upcoming[:5])):
        if lst:
            action_lines.append(label)
            action_lines += [
                f"- {a.get('title', '(untitled)')} | Owner: {a.get('owner', 'TBC')} | Due: {a.get('due_date', 'No date')} | Priority: {a.get('priority', 'TBC')}"
                for a in lst
            ]
    action_text = "\n".join(action_lines) if action_lines else "No open actions recorded."

    nfr_count = int(nfr.get("nfr_count_30d") or 0)
    governance = (
        f"Notes for Record activity (last 30d): {nfr_count}. Latest week: {nfr.get('last_week_start', 'N/A')}. "
        "Ensure decisions, risks, and actions are consistently captured with clear ownership."
    )

    return _normalize_exec_summary(
        f"DELIVERY\n{delivery}\n\nSCHEDULE\n{schedule}\n\nRISKS\n{risk_text}\n\nACTIONS\n{action_text}\n\nGOVERNANCE & SIGNALS\n{governance}"
    )


def _openai_detailed_summary(context: dict, project_name: str, client_name: str) -> str:
    api_key = None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        pass
    if not api_key:
        return _rule_based_detailed_summary(context)

    compact = {
        "client_name": client_name,
        "project_name": project_name,
        "project": context.get("project", {}),
        "risks": context.get("risks", [])[:10],
        "actions": context.get("actions", [])[:15],
        "nfr": context.get("nfr", {}),
        "generated_at_utc": context.get("generated_at_utc"),
    }

    prompt = f"""
You are a Senior Executive PMO Advisor preparing a board-ready PROJECT summary.
"NFR" = Notes for Record (governance documentation).
Client: {client_name} | Project: {project_name}

Output format EXACTLY:

DELIVERY
2–4 sentences: health/RAG/confidence, biggest risk driver.

SCHEDULE
3–6 bullets ("- " each): milestones, slippage risk, critical path.

RISKS
3–5 bullets ("- " each): title, why it matters, L/I, next action.

ACTIONS
3–6 bullets ("- " each): overdue first, owner + due date, consequence.

GOVERNANCE & SIGNALS
2–4 sentences: NFR cadence, governance recommendation.

Rules: Do NOT invent. "Not recorded" if missing. Executive tone.

DATA (json):
{json.dumps(compact, default=str)}
""".strip()

    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4.1-mini", "input": prompt},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        text = None
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    text = c["text"]
                    break
            if text: break
        return _normalize_exec_summary((text or "").strip()) or _rule_based_detailed_summary(context)
    except Exception:
        return _rule_based_detailed_summary(context)


def render_project_exec_summary(project_id: int, project_name: str, client_name: str):
    st.markdown(
        f"""<div class="subsection-title">🧠 Executive Summary
        <span class="pill">{client_name} • {project_name}</span></div>""",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([6, 1])
    with c2:
        if st.button("🔄 Refresh", key=f"refresh_{project_id}", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    context = _load_project_exec_context(project_id)
    with st.spinner("Generating summary..."):
        summary = _openai_detailed_summary(context, project_name, client_name)

    rag_src = context.get("project", {}).get("rag_source", "")
    st.markdown(
        f"""<div class="exec-box"><pre>{summary}</pre>
        <div class="exec-meta">Snapshot: {context.get("generated_at_utc", "")}
         | RAG source: {rag_src}</div></div>""",
        unsafe_allow_html=True,
    )


# ── Page setup ────────────────────────────────────────────────
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="📊 Executive Project Summary")
render_sidebar()

st.markdown("""
<style>
header[data-testid="stHeader"] { height:0 !important; visibility:hidden !important; }
.section-header { background:linear-gradient(90deg,#4facfe 0%,#00f2fe 100%);
    padding:1rem 1.5rem; border-radius:8px; margin:1.5rem 0 1rem 0; }
.section-header h3 { margin:0; color:white; }
.table-container { max-height:520px; overflow-y:auto;
    border:1px solid #e6f2ff; border-radius:10px; }
.subsection-title { font-weight:700; font-size:1.05rem; margin:0.25rem 0 0.75rem 0;
    color:#102a43; display:flex; align-items:center; justify-content:center; gap:0.5rem; }
.subsection-title .pill { font-size:.8rem; font-weight:700; padding:.2rem .55rem;
    border-radius:999px; background:#ebf8ff; border:1px solid #bee3f8; color:#2b6cb0; }
.exec-box { background:#ffffff; border:1px solid #e6f2ff; border-radius:10px;
    padding:1rem 1.1rem; margin-bottom:1.25rem; }
.exec-box pre { margin:0; white-space:pre-wrap; font-family:inherit;
    font-size:0.95rem; line-height:1.55; }
.exec-meta { opacity:.65; font-size:.8rem; margin-top:.75rem; text-align:right; }
</style>
""", unsafe_allow_html=True)

email = (st.session_state.get("email") or "").strip().lower()
if not email:
    st.error("Unable to load your profile. Please log in again.")
    st.stop()

user_df = run_query(
    "SELECT user_id FROM public.users WHERE LOWER(email) = :email LIMIT 1",
    {"email": email},
)
if user_df is None or user_df.empty:
    st.error("User profile not found. Contact an administrator.")
    st.stop()

user_id = int(user_df.iloc[0]["user_id"])

projects_df = run_query(
    """
    SELECT
        p.project_id,
        p.project_name,
        p.client_id,
        c.client_name,
        upp.access_level
    FROM public.user_project_permissions upp
    JOIN public.projects p ON p.project_id = upp.project_id
    LEFT JOIN public.client_scaffold c ON c.id = p.client_id
    WHERE upp.user_id = :uid
    ORDER BY c.client_name, p.project_name
    """,
    {"uid": user_id},
)

if projects_df is None or projects_df.empty:
    st.warning("You have no assigned projects. Contact an administrator.")
    st.stop()

projects_df["label"] = projects_df.apply(
    lambda r: f"{r.get('client_name', '(No client)')} • {r.get('project_name', '(Unnamed)')}", axis=1
)
project_map = {row["label"]: int(row["project_id"]) for _, row in projects_df.iterrows()}

sel_label = st.selectbox("Select Project", list(project_map.keys()))
project_id = project_map[sel_label]
sel_row = projects_df[projects_df["project_id"] == project_id].iloc[0]
proj_name = sel_row.get("project_name", "Project")
cli_name = sel_row.get("client_name", "Client")

st.markdown("<br/>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📁 Project", "🔥 Top Risks", "📝 Actions"])

# ── Tab 1 ────────────────────────────────────────────────────
with tab1:
    st.markdown("<div class='section-header'><h3>📊 Project Overview</h3></div>", unsafe_allow_html=True)

    open_risks = safe(run_query(
        "SELECT COUNT(*) FROM public.raids WHERE project_id=:pid AND LOWER(status)='open'",
        {"pid": project_id},
    ))
    overdue_actions = safe(run_query(
        "SELECT COUNT(*) FROM public.actions WHERE project_id=:pid AND due_date < CURRENT_DATE AND LOWER(status) NOT IN ('closed','completed')",
        {"pid": project_id},
    ))
    # NFR count: 90-day window to avoid missing recent records
    nfr_volume = safe(run_query(
        """SELECT COUNT(*) FROM public.weekly_nfr WHERE project_id=:pid AND week_commencing >= CURRENT_DATE - INTERVAL '90 days'""",
        {"pid": project_id},
    ))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Project", 1)
    c2.metric("Open Risks", open_risks)
    c3.metric("Overdue Actions", overdue_actions)
    c4.metric("Notes For Record (30d)", nfr_volume)

    st.markdown("<br/>", unsafe_allow_html=True)
    render_project_exec_summary(project_id, proj_name, cli_name)

# ── Tab 2 ────────────────────────────────────────────────────
with tab2:
    st.markdown("<div class='section-header'><h3>📁 Project Snapshot</h3></div>", unsafe_allow_html=True)

    # Try exec view first (correct RAG + scaffold PM/date fallback)
    proj_detail = run_query(
        """
        SELECT
            project_name,
            project_code,
            status,
            project_start_date,
            expected_end_date,
            project_manager,
            rag_status
        FROM public.exec_project_summary
        WHERE project_id = :pid
        LIMIT 1
        """,
        {"pid": project_id},
    )

    # Fallback: raw projects + scaffold join
    if proj_detail is None or proj_detail.empty:
        proj_detail = run_query(
            """
            SELECT
                p.project_name,
                p.project_code,
                p.status,
                COALESCE(p.project_start_date, ps.project_start_date) AS project_start_date,
                COALESCE(p.expected_end_date,  ps.expected_end_date)  AS expected_end_date,
                COALESCE(p.project_manager,    ps.project_manager)    AS project_manager,
                p.rag_status
            FROM public.projects p
            LEFT JOIN public.project_scaffold ps
              ON ps.client_id = p.client_id
             AND (ps.project_code = p.project_code OR ps.project_name = p.project_name)
            WHERE p.project_id = :pid
            LIMIT 1
            """,
            {"pid": project_id},
        )

    if proj_detail is None or proj_detail.empty:
        st.info("No project data found.")
    else:
        # Display as clean key-value cards rather than a 1-row table
        row = proj_detail.iloc[0]


        def _fv(v):
            return str(v) if v is not None and str(v) not in ("None", "nan", "") else "—"


        rag_val = _fv(row.get("rag_status"))
        rag_colour = {"Red": "#fee2e2", "Amber": "#fef3c7", "Green": "#dcfce7"}.get(rag_val, "#f1f5f9")
        rag_text = {"Red": "#991b1b", "Amber": "#92400e", "Green": "#166534"}.get(rag_val, "#334155")

        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:.75rem;margin-bottom:.75rem">
          <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8">Project</div>
            <div style="font-size:1.1rem;font-weight:800;color:#0f172a;margin-top:.2rem">{_fv(row.get("project_name"))}</div>
          </div>
          <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8">Code</div>
            <div style="font-size:1.1rem;font-weight:800;color:#0f172a;margin-top:.2rem">{_fv(row.get("project_code"))}</div>
          </div>
          <div style="background:{rag_colour};border:1px solid {rag_colour};border-radius:10px;padding:.9rem 1rem">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:{rag_text}">RAG Status</div>
            <div style="font-size:1.1rem;font-weight:800;color:{rag_text};margin-top:.2rem">{rag_val}</div>
          </div>
          <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8">Status</div>
            <div style="font-size:1.1rem;font-weight:800;color:#0f172a;margin-top:.2rem">{_fv(row.get("status"))}</div>
          </div>
          <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8">Start Date</div>
            <div style="font-size:1.1rem;font-weight:800;color:#0f172a;margin-top:.2rem">{_fv(row.get("project_start_date"))}</div>
          </div>
          <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8">End Date</div>
            <div style="font-size:1.1rem;font-weight:800;color:#0f172a;margin-top:.2rem">{_fv(row.get("expected_end_date"))}</div>
          </div>
          <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem;grid-column:span 3">
            <div style="font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.8px;color:#94a3b8">Project Manager</div>
            <div style="font-size:1.1rem;font-weight:800;color:#0f172a;margin-top:.2rem">{_fv(row.get("project_manager"))}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

# ── Tab 3 ────────────────────────────────────────────────────
with tab3:
    st.markdown("<div class='section-header'><h3>📋 RAID Log Snapshot</h3></div>", unsafe_allow_html=True)

    # Full RAID log snapshot — mirrors the RAID log exactly, all types & statuses
    raid_df = run_query(
        """
        SELECT
            raid_id,
            raid_type       AS type,
            title,
            description,
            owner,
            status,
            likelihood,
            impact,
            probability,
            severity,
            score,
            revised_score,
            mitigation_plan,
            mitigation_status,
            date_raised,
            planned_close,
            date_closed,
            next_review,
            updated_at
        FROM public.raids
        WHERE project_id = :pid
        ORDER BY
            CASE LOWER(status) WHEN 'open' THEN 1 WHEN 'in progress' THEN 2 ELSE 3 END,
            COALESCE(score, 0) DESC,
            COALESCE(severity, 0) DESC,
            date_raised DESC NULLS LAST
        """,
        {"pid": project_id},
    )

    if raid_df is None or raid_df.empty:
        st.success("No RAIDs recorded for this project.")
    else:
        import pandas as pd

        # Summary metrics
        total_raids = len(raid_df)
        open_raids = int(
            (raid_df["status"].astype(str).str.lower() == "open").sum()) if "status" in raid_df.columns else 0
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=30)
        raid_df["updated_at"] = pd.to_datetime(raid_df["updated_at"], errors="coerce")
        stale_count = int((raid_df["updated_at"] < cutoff).sum())

        c1, c2, c3 = st.columns(3)
        c1.metric("Total RAIDs", total_raids)
        c2.metric("Open", open_raids)
        c3.metric("Stale (30+ days, no update)", stale_count)

        statuses = ["All"] + sorted(raid_df["status"].dropna().astype(str).str.title().unique().tolist())
        sel_status = st.selectbox("Filter by status", statuses, key="raid_status_filter_26")

        display_df = raid_df.copy()
        if sel_status != "All":
            display_df = display_df[display_df["status"].astype(str).str.title() == sel_status]
        display_df = display_df.dropna(axis=1, how="all")

        # First 15 always visible
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(display_df.head(15), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if len(display_df) > 15:
            with st.expander(f"🔍 View all {len(display_df)} rows", expanded=False):
                st.markdown('<div class="table-container">', unsafe_allow_html=True)
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)

        st.caption(
            f"Showing {min(15, len(display_df))} of {len(display_df)} entries (filtered from {total_raids} total)")

# ── Tab 4 ────────────────────────────────────────────────────
with tab4:
    st.markdown("<div class='section-header'><h3>📝 Overdue & Upcoming Actions</h3></div>", unsafe_allow_html=True)

    # FIX: action_id not id
    actions_df = run_query(
        """
        SELECT action_id, title, owner, status, due_date, priority, updated_at
        FROM public.actions
        WHERE project_id = :pid
          AND LOWER(status) NOT IN ('closed','completed')
        ORDER BY due_date ASC NULLS LAST
        """,
        {"pid": project_id},
    )

    if actions_df is None or actions_df.empty:
        st.info("No open actions found for this project.")
    else:
        import pandas as pd

        today = dt.date.today()
        actions_df["due_date"] = pd.to_datetime(actions_df["due_date"], errors="coerce").dt.date
        overdue_df = actions_df[actions_df["due_date"].notna() & (actions_df["due_date"] < today)]
        upcoming_df = actions_df[actions_df["due_date"].isna() | (actions_df["due_date"] >= today)]
        c1, c2 = st.columns(2)
        c1.metric("Overdue", len(overdue_df))
        c2.metric("Upcoming / No Date", len(upcoming_df))
        st.markdown("<br/>**Overdue:**", unsafe_allow_html=True)
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(overdue_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<br/>**Upcoming:**", unsafe_allow_html=True)
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(upcoming_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

pmo_footer()