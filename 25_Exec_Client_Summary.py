# ============================================================
# 25_📈_Exec_Client_Summary.py — ScopeSight v3.5 (FIXED)
#
# KEY FIXES vs v3.4:
#   ✅ exec_project_summary VIEW now used (created by 00_exec_project_summary_view.sql)
#   ✅ nfr_reports replaced with weekly_nfr + week_commencing (correct table/column)
#   ✅ raids queried with raid_id PK (not id)
#   ✅ actions queried with action_id PK (not id)
#   ✅ work_items model: uses wi.client_id directly (exists in schema)
#   ✅ RAG priority: override → snapshot → base (resolved in view)
# ============================================================

import streamlit as st
import json
import datetime as dt
import requests
import pandas as pd

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

st.set_page_config(
    page_title="📈 Executive Client Summary",
    page_icon="📈",
    layout="wide",
)

# ── Helpers ──────────────────────────────────────────────────
CLOSED_STATUSES = ("closed", "completed")


def safe(df):
    if df is None or getattr(df, "empty", True): return 0
    try:
        return list(df.iloc[0])[0] or 0
    except Exception:
        return 0


@st.cache_data(ttl=300, show_spinner=False)
def table_exists(schema: str, table: str) -> bool:
    df = run_query(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=:s AND table_name=:t LIMIT 1",
        {"s": schema, "t": table},
    )
    return df is not None and not df.empty


@st.cache_data(ttl=300, show_spinner=False)
def column_exists(schema: str, table: str, column: str) -> bool:
    df = run_query(
        "SELECT 1 FROM information_schema.columns WHERE table_schema=:s AND table_name=:t AND column_name=:c LIMIT 1",
        {"s": schema, "t": table, "c": column},
    )
    return df is not None and not df.empty


@st.cache_data(ttl=300, show_spinner=False)
def _has_work_items() -> bool:
    # work_items has client_id (confirmed in schema) so we can filter directly
    return (
            table_exists("public", "work_items")
            and column_exists("public", "work_items", "client_id")
            and column_exists("public", "work_items", "item_type")
    )


# ── Exec context loader ───────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_client_exec_context(client_id: int) -> dict:
    use_wi = _has_work_items()

    # Projects from exec view — probe optional columns defensively
    _vc = lambda col: column_exists("public", "exec_project_summary", col)
    _sel = lambda col, alias=None, typ="text": (
        f"{col}" + (f" AS {alias}" if alias else "")
        if _vc(col) else
        f"NULL::{typ}" + (f" AS {alias}" if alias else f" AS {col}")
    )
    proj_df = run_query(
        f"""
        SELECT
            project_id, project_name, rag_status,
            {_sel("rag_source")},
            health_score, status, project_manager, delivery_lead,
            budget_total, budget_spent, budget_rag,
            {_sel("total_allocation_pct", typ="integer")},
            {_sel("latest_summary")},
            {_sel("latest_risks")},
            {_sel("latest_actions")}
        FROM public.exec_project_summary
        WHERE client_id = :cid
        ORDER BY
            CASE rag_status WHEN 'Red' THEN 1 WHEN 'Amber' THEN 2 WHEN 'Green' THEN 3 ELSE 4 END,
            project_name
        """,
        {"cid": client_id},
    )

    # Risks
    if use_wi:
        risk_df = run_query(
            """
            SELECT title, description, NULL::text AS likelihood, NULL::text AS impact,
                   status, updated_at
            FROM public.work_items
            WHERE client_id = :cid
              AND LOWER(item_type) IN ('risk','issue','raid')
              AND LOWER(status) = 'open'
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 10
            """,
            {"cid": client_id},
        )
    else:
        risk_df = run_query(
            """
            SELECT title, description, likelihood, impact, status, updated_at
            FROM public.raids
            WHERE client_id = :cid AND LOWER(status) = 'open'
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 10
            """,
            {"cid": client_id},
        )

    # Actions — work_items has no owner column; get it via work_item_assignees → users
    if use_wi:
        actions_df = run_query(
            """
            SELECT
                wi.work_item_id, wi.title,
                COALESCE(u.email, wi.created_by::text) AS owner,
                wi.status, wi.due_date, wi.priority, wi.updated_at
            FROM public.work_items wi
            LEFT JOIN public.work_item_assignees wia
                ON wia.work_item_id = wi.work_item_id AND wia.role = 'owner'
            LEFT JOIN public.users u ON u.user_id = wia.user_id
            WHERE wi.client_id = :cid
              AND LOWER(wi.item_type) = 'action'
              AND LOWER(wi.status) NOT IN ('closed','completed')
            ORDER BY wi.due_date ASC NULLS LAST
            LIMIT 30
            """,
            {"cid": client_id},
        )
    else:
        actions_df = run_query(
            """
            SELECT title, owner, status, due_date, priority, updated_at
            FROM public.actions
            WHERE client_id = :cid
              AND LOWER(status) NOT IN ('closed','completed')
            ORDER BY due_date ASC NULLS LAST
            LIMIT 30
            """,
            {"cid": client_id},
        )

    # NFR: join via project too in case client_id is null on weekly_nfr rows
    nfr_meta = run_query(
        """
        SELECT COUNT(*) AS nfr_count_30d, MAX(week_commencing) AS last_week_start
        FROM public.weekly_nfr wn
        WHERE (
            wn.client_id = :cid
            OR wn.project_id IN (
                SELECT project_id FROM public.projects WHERE client_id = :cid
            )
        )
          AND wn.week_commencing >= CURRENT_DATE - INTERVAL '90 days'

        """,
        {"cid": client_id},
    )

    return {
        "client_id": client_id,
        "projects": [] if proj_df is None or proj_df.empty else proj_df.to_dict("records"),
        "risks": [] if risk_df is None or risk_df.empty else risk_df.to_dict("records"),
        "actions": [] if actions_df is None or actions_df.empty else actions_df.to_dict("records"),
        "nfr": {} if nfr_meta is None or nfr_meta.empty else nfr_meta.to_dict("records")[0],
        "generated_at_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
        "work_source": "work_items" if use_wi else "raids/actions tables",
    }


def _rule_based_summary(context: dict) -> str:
    projects = context.get("projects", [])
    risks = context.get("risks", [])
    actions = context.get("actions", [])
    nfr = context.get("nfr", {}) or {}

    total = len(projects)
    reds = [p for p in projects if (p.get("rag_status") or "").lower() == "red"]
    ambers = [p for p in projects if (p.get("rag_status") or "").lower() == "amber"]
    greens = [p for p in projects if (p.get("rag_status") or "").lower() == "green"]

    def _d(x):
        return "Not recorded" if x in (None, "", "nan") else str(x)

    if total == 0:
        delivery = "No projects are recorded for this client."
    else:
        delivery = (
            f"Portfolio health: {len(reds)} Red / {len(ambers)} Amber / {len(greens)} Green across {total} project(s). "
        )
        if reds:
            delivery += "Red items require executive recovery plans and unblocking of dependencies."
        elif ambers:
            delivery += "Amber items signal emerging pressure — intervene early to prevent Red deterioration."
        else:
            delivery += "Signals are stable; maintain cadence and proactive risk management."

    schedule = "\n".join(
        f"- {_d(p.get('project_name'))}: RAG={_d(p.get('rag_status'))} | "
        f"Status={_d(p.get('status'))} | PM={_d(p.get('project_manager'))} | "
        f"Latest: {_d(p.get('latest_summary'))}"
        for p in projects[:6]
    ) or "Not enough data."

    risk_text = "\n".join(
        f"- {r.get('title', '(untitled)')} (L/I: {r.get('likelihood', '?')}/{r.get('impact', '?')}) — "
        f"{r.get('description', '') or 'No description.'}"
        for r in risks[:5]
    ) if risks else "No open risks recorded.\n- Confirm RAID log is actively maintained."

    today = dt.date.today()
    overdue, upcoming = [], []
    for a in actions:
        if (a.get("status") or "").lower() in CLOSED_STATUSES:
            continue
        due = a.get("due_date")
        due_date = None
        if due is not None:
            try:
                due_date = due if isinstance(due, dt.date) else dt.date.fromisoformat(str(due)[:10])
            except Exception:
                pass
        (overdue if due_date and due_date < today else upcoming).append(a)

    action_lines = []
    if overdue:
        action_lines.append("Overdue:")
        action_lines += [
            f"- {a.get('title', '(untitled)')} | Owner: {a.get('owner', 'TBC')} | Due: {a.get('due_date')} | Priority: {a.get('priority', 'TBC')}"
            for a in overdue[:5]
        ]
    if upcoming:
        action_lines.append("Upcoming:")
        action_lines += [
            f"- {a.get('title', '(untitled)')} | Owner: {a.get('owner', 'TBC')} | Due: {a.get('due_date', 'No date')} | Priority: {a.get('priority', 'TBC')}"
            for a in upcoming[:5]
        ]
    action_text = "\n".join(
        action_lines) if action_lines else "No open actions recorded.\n- Confirm action tracking is in place."

    nfr_count = int(nfr.get("nfr_count_30d") or 0)
    last_week = nfr.get("last_week_start") or "N/A"
    governance = (
        f"Notes for Record activity (last 30 days): {nfr_count}. Latest week start: {last_week}. "
        "If delivery pressure is increasing, ensure decisions, risks, and actions are consistently captured with clear ownership."
    )

    return (
        f"DELIVERY\n{delivery}\n\n"
        f"SCHEDULE\n{schedule}\n\n"
        f"RISKS\n{risk_text}\n\n"
        f"ACTIONS\n{action_text}\n\n"
        f"GOVERNANCE & SIGNALS\n{governance}"
    )


def _openai_summary(context: dict, client_name: str) -> str:
    api_key = None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        pass
    if not api_key:
        return _rule_based_summary(context)

    compact = {
        "client_name": client_name,
        "projects": context.get("projects", [])[:12],
        "risks": context.get("risks", [])[:10],
        "actions": context.get("actions", [])[:15],
        "nfr": context.get("nfr", {}) or {},
        "work_source": context.get("work_source"),
        "generated_at_utc": context.get("generated_at_utc"),
    }

    prompt = f"""
You are a Senior Executive PMO Advisor preparing a board-ready client summary.
"NFR" = Notes for Record (governance documentation), NOT a delivery metric.
Client: {client_name}

Output format EXACTLY:

DELIVERY
2–4 strong sentences

SCHEDULE
3–6 bullets (each starts with "- ")

RISKS
3–5 bullets (each starts with "- ")

ACTIONS
3–6 bullets (each starts with "- ", overdue first)

GOVERNANCE & SIGNALS
2–4 sentences

Rules: Do NOT invent. If missing say "Not recorded". Be executive and concise.

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
        return (text or "").strip() or _rule_based_summary(context)
    except Exception:
        return _rule_based_summary(context)


def render_exec_summary_widget(client_id: int, client_name: str):
    st.markdown(
        f"""<div class="subsection-title">🧠 Executive Summary
        <span class="pill">{client_name}</span></div>""",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([6, 1])
    with c2:
        if st.button("🔄 Refresh", key=f"refresh_{client_id}", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    context = _load_client_exec_context(client_id)
    with st.spinner("Generating summary..."):
        summary = _openai_summary(context, client_name)

    st.markdown(
        f"""<div class="exec-box"><pre>{summary}</pre>
        <div class="exec-meta">Snapshot: {context.get("generated_at_utc", "")}
         | Source: {context.get("work_source", "")}</div></div>""",
        unsafe_allow_html=True,
    )


# ── Page setup ────────────────────────────────────────────────
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="📈 Executive Client Summary")
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

clients_df = run_query(
    """
    SELECT c.id AS client_id, c.client_name
    FROM public.user_client_permissions u
    JOIN public.client_scaffold c ON c.id = u.client_id
    WHERE LOWER(u.user_email) = :email
    ORDER BY c.client_name
    """,
    {"email": email},
)

if clients_df is None or clients_df.empty:
    st.warning("You have no assigned clients. Contact an administrator.")
    st.stop()

client_map = {row["client_name"]: row["client_id"] for _, row in clients_df.iterrows()}
sel_client = st.selectbox("Select Client", list(client_map.keys()))
client_id = client_map[sel_client]

st.markdown("<br/>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📁 Project Portfolio", "🔥 Top Risks", "📝 Actions"])

# ── Tab 1: KPIs + exec summary ────────────────────────────────
with tab1:
    st.markdown("<div class='section-header'><h3>📊 Client Overview</h3></div>", unsafe_allow_html=True)

    # All counts from correct tables
    total_projects = safe(run_query(
        "SELECT COUNT(*) FROM public.exec_project_summary WHERE client_id = :cid",
        {"cid": client_id},
    ))

    use_wi = _has_work_items()
    if use_wi:
        open_risks = safe(run_query(
            "SELECT COUNT(*) FROM public.work_items WHERE client_id=:cid AND LOWER(item_type) IN ('risk','issue','raid') AND LOWER(status)='open'",
            {"cid": client_id},
        ))
        overdue_actions = safe(run_query(
            "SELECT COUNT(*) FROM public.work_items WHERE client_id=:cid AND LOWER(item_type)='action' AND due_date < CURRENT_DATE AND LOWER(status) NOT IN ('closed','completed')",
            {"cid": client_id},
        ))
    else:
        open_risks = safe(run_query(
            "SELECT COUNT(*) FROM public.raids WHERE client_id=:cid AND LOWER(status)='open'",
            {"cid": client_id},
        ))
        overdue_actions = safe(run_query(
            "SELECT COUNT(*) FROM public.actions WHERE client_id=:cid AND due_date < CURRENT_DATE AND LOWER(status) NOT IN ('closed','completed')",
            {"cid": client_id},
        ))

    # NFR: also match via project_id in case client_id is null on weekly_nfr rows
    nfr_volume = safe(run_query(
        """SELECT COUNT(*) FROM public.weekly_nfr wn
        WHERE (wn.client_id = :cid OR wn.project_id IN (SELECT project_id FROM public.projects WHERE client_id = :cid))
          AND wn.week_commencing >= CURRENT_DATE - INTERVAL '90 days'""",
        {"cid": client_id},
    ))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projects", total_projects)
    c2.metric("Open Risks", open_risks)
    c3.metric("Overdue Actions", overdue_actions)
    c4.metric("Notes For Record (30d)", nfr_volume)
    st.caption(f"RAG source: exec_project_summary | Work source: {'work_items' if use_wi else 'raids/actions tables'}")

    st.markdown("<br/>", unsafe_allow_html=True)
    render_exec_summary_widget(client_id, sel_client)

# ── Tab 2: Portfolio ──────────────────────────────────────────
with tab2:
    st.markdown("<div class='section-header'><h3>📁 Project Portfolio</h3></div>", unsafe_allow_html=True)
    proj_df = run_query(
        """
        SELECT
            project_name,
            status,
            project_manager,
            rag_status
        FROM public.exec_project_summary
        WHERE client_id = :cid
        ORDER BY
            CASE rag_status WHEN 'Red' THEN 1 WHEN 'Amber' THEN 2 WHEN 'Green' THEN 3 ELSE 4 END,
            project_name
        """,
        {"cid": client_id},
    )
    if proj_df is None or proj_df.empty:
        st.info("No projects recorded for this client.")
    else:
        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(proj_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ── Tab 3: Risks ──────────────────────────────────────────────
with tab3:
    st.markdown("<div class='section-header'><h3>🔥 RAID Log</h3></div>", unsafe_allow_html=True)

    # Full RAID log for this client — mirrors the RAID log exactly across all live approved projects
    raid_df = run_query(
        """
        SELECT
            r.raid_id,
            p.project_name,
            r.raid_type         AS type,
            r.title,
            r.description,
            r.owner,
            r.status,
            r.likelihood,
            r.impact,
            r.probability,
            r.severity,
            r.score,
            r.revised_score,
            r.mitigation_plan,
            r.mitigation_status,
            r.date_raised,
            r.planned_close,
            r.date_closed,
            r.next_review,
            r.updated_at
        FROM public.raids r
        JOIN public.projects p ON p.project_id = r.project_id
        WHERE r.client_id = :cid
          AND LOWER(COALESCE(p.status, 'open')) NOT IN
              ('closed','completed','rejected','cancelled','canceled','archived')
        ORDER BY
            CASE LOWER(r.status) WHEN 'open' THEN 1 WHEN 'in progress' THEN 2 ELSE 3 END,
            COALESCE(r.score, 0) DESC,
            COALESCE(r.severity, 0) DESC,
            r.date_raised DESC NULLS LAST
        """,
        {"cid": client_id},
    )

    if raid_df is None or raid_df.empty:
        st.success("No RAIDs recorded for this client's live projects.")
    else:
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
        sel_status = st.selectbox("Filter by status", statuses, key="raid_status_filter_25")

        display_df = raid_df.copy()
        if sel_status != "All":
            display_df = display_df[display_df["status"].astype(str).str.title() == sel_status]

        display_df = display_df.dropna(axis=1, how="all")

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.caption(f"Showing {len(display_df)} of {total_raids} RAID entries across live projects")

# ── Tab 4: Actions ────────────────────────────────────────────
with tab4:
    st.markdown("<div class='section-header'><h3>📝 Overdue & Upcoming Actions</h3></div>", unsafe_allow_html=True)

    # Primary: actions table joined to live projects for this client
    actions_df = run_query(
        """
        SELECT
            a.action_id,
            p.project_name,
            a.title,
            a.owner,
            a.status,
            a.due_date,
            a.priority,
            a.updated_at
        FROM public.actions a
        JOIN public.projects p ON p.project_id = a.project_id
        WHERE a.client_id = :cid
          AND LOWER(a.status) NOT IN ('closed','completed')
          AND LOWER(COALESCE(p.status,'open')) NOT IN
              ('closed','completed','rejected','cancelled','canceled','archived')
        ORDER BY a.due_date ASC NULLS LAST
        """,
        {"cid": client_id},
    )

    # Fallback: actions without a project_id (client-level actions)
    if actions_df is None or actions_df.empty:
        actions_df = run_query(
            """
            SELECT action_id, NULL::text AS project_name, title, owner,
                   status, due_date, priority, updated_at
            FROM public.actions
            WHERE client_id = :cid
              AND LOWER(status) NOT IN ('closed','completed')
            ORDER BY due_date ASC NULLS LAST
            """,
            {"cid": client_id},
        )

    if actions_df is None or actions_df.empty:
        st.info("No open actions found for this client's live projects.")
    else:
        today = dt.date.today()
        actions_df["due_date"] = pd.to_datetime(actions_df["due_date"], errors="coerce").dt.date
        overdue_df = actions_df[actions_df["due_date"].notna() & (actions_df["due_date"] < today)]
        upcoming_df = actions_df[actions_df["due_date"].isna() | (actions_df["due_date"] >= today)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total open", len(actions_df))
        c2.metric("Overdue", len(overdue_df))
        c3.metric("Upcoming / No Date", len(upcoming_df))

        if not overdue_df.empty:
            st.markdown("<br/>**🔴 Overdue:**", unsafe_allow_html=True)
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            st.dataframe(overdue_df, use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)

        if not upcoming_df.empty:
            st.markdown("<br/>**📅 Upcoming / No Due Date:**", unsafe_allow_html=True)
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            st.dataframe(upcoming_df, use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)

pmo_footer()