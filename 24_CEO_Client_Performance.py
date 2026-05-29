# ============================================================
# 24_🏢_CEO_Client_Performance.py — ScopeSight v4.5 (FIXED)
#
# KEY FIXES vs v4.4:
#   ✅ All RAG now read from exec_project_summary VIEW (override→snapshot→base)
#   ✅ raids queried with correct PK column (raid_id, not id)
#   ✅ actions queried with correct PK column (action_id, not id)
#   ✅ resources load from resource_allocation → resource_pool join (correct schema)
#   ✅ nfr counts from weekly_nfr using week_commencing (not nfr_reports.week_start)
#   ✅ load_raids_for_client removed non-existent 'id' column alias
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import pandas as pd
import streamlit as st
import requests

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# ============================================================
# CONFIG
# ============================================================
LIVE_EXCLUDED_STATUSES = ("closed", "completed", "rejected", "cancelled", "canceled", "archived")
TODAY = dt.date.today()

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="🏢 CEO Client Performance",
    page_icon="🏢",
    layout="wide",
)

require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🏢 CEO Client Performance")
render_sidebar()

# ============================================================
# STYLES
# ============================================================
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height:0 !important; visibility:hidden !important; }
.page-title { font-size:2.15rem; font-weight:950; color:#0f172a; margin:0 0 .25rem 0; }
.page-sub { color:#64748b; font-weight:650; margin:0 0 1.25rem 0; }
.panel { background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:1.2rem; }
.kpi { background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:1.1rem;
       min-height:120px; display:flex; flex-direction:column; justify-content:center; }
.kpi .label { font-size:.78rem; font-weight:900; text-transform:uppercase; letter-spacing:.85px; color:#94a3b8; }
.kpi .value { font-size:2.05rem; font-weight:950; color:#0f172a; margin-top:.2rem; line-height:1.1; }
.kpi .sub { margin-top:.35rem; font-size:.92rem; font-weight:750; color:#475569; }
.pill { display:inline-block; padding:.22rem .62rem; border-radius:999px; font-weight:900;
        font-size:.78rem; border:1px solid transparent; }
.pill.green { background:#dcfce7; color:#166534; border-color:#bbf7d0; }
.pill.amber { background:#fef3c7; color:#92400e; border-color:#fde68a; }
.pill.red   { background:#fee2e2; color:#991b1b; border-color:#fecaca; }
.pill.gray  { background:#f1f5f9; color:#334155; border-color:#e2e8f0; }
.table-wrap { border:1px solid #e2e8f0; border-radius:14px; overflow:hidden; }
.exec-box { background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; padding:1rem 1.1rem; }
.exec-box pre { margin:0; white-space:pre-wrap; font-family:inherit; font-size:0.95rem; line-height:1.55; }
.exec-meta { opacity:.65; font-size:.8rem; margin-top:.6rem; text-align:right; }
.small-note { color:#94a3b8; font-size:.85rem; font-weight:750; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# HELPERS
# ============================================================
def safe_df(df) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def table_exists(schema: str, table: str) -> bool:
    df = run_query(
        """SELECT 1 FROM information_schema.tables
           WHERE table_schema=:s AND table_name=:t LIMIT 1""",
        {"s": schema, "t": table},
    )
    return df is not None and not df.empty


@st.cache_data(ttl=600, show_spinner=False)
def column_exists(schema: str, table: str, col: str) -> bool:
    df = run_query(
        """SELECT 1 FROM information_schema.columns
           WHERE table_schema=:s AND table_name=:t AND column_name=:c LIMIT 1""",
        {"s": schema, "t": table, "c": col},
    )
    return df is not None and not df.empty


def norm_rag(x) -> str | None:
    if x is None:
        return None
    s = str(x).strip().lower()
    return s if s in ("green", "amber", "red") else None


def rag_pill(rag: str | None) -> str:
    r = norm_rag(rag)
    if r == "green": return "<span class='pill green'>Green</span>"
    if r == "amber": return "<span class='pill amber'>Amber</span>"
    if r == "red":   return "<span class='pill red'>Red</span>"
    return "<span class='pill gray'>Not set</span>"


def worst_rag(g: int, a: int, r: int) -> str | None:
    if r > 0: return "red"
    if a > 0: return "amber"
    if g > 0: return "green"
    return None


def to_date(x):
    try:
        if pd.isna(x): return None
        if isinstance(x, dt.date): return x
        return pd.to_datetime(x).date()
    except Exception:
        return None


# ============================================================
# LOADERS — all now use exec_project_summary for RAG/project data
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def load_clients() -> pd.DataFrame:
    return safe_df(run_query(
        "SELECT id AS client_id, client_name FROM public.client_scaffold ORDER BY client_name"
    ))


@st.cache_data(ttl=300, show_spinner=False)
def load_live_projects_for_client(client_id: int) -> pd.DataFrame:
    """
    Uses exec_project_summary VIEW which already:
      - Applies RAG priority (override → snapshot → base)
      - Excludes closed/archived projects
      - Joins allocation, status updates, PM fallback
    Falls back to public.projects if view doesn't exist yet.
    """
    if table_exists("public", "exec_project_summary"):
        # Probe which optional columns the current view version exposes
        has_rag_source   = column_exists("public", "exec_project_summary", "rag_source")
        has_alloc        = column_exists("public", "exec_project_summary", "total_allocation_pct")
        has_latest_sum   = column_exists("public", "exec_project_summary", "latest_summary")
        has_last_status  = column_exists("public", "exec_project_summary", "last_status_update_at")

        rag_src_sel  = "rag_source,"          if has_rag_source  else "NULL::text AS rag_source,"
        alloc_sel    = "total_allocation_pct," if has_alloc       else "NULL::integer AS total_allocation_pct,"
        sum_sel      = "latest_summary,"       if has_latest_sum  else "NULL::text AS latest_summary,"
        status_sel   = "last_status_update_at" if has_last_status else "updated_at AS last_status_update_at"

        df = run_query(
            f"""
            SELECT
                project_id,
                project_name,
                client_id,
                status,
                rag_status          AS effective_rag,
                {rag_src_sel}
                health_score,
                budget_rag,
                budget_total,
                budget_spent,
                project_start_date  AS start_date,
                expected_end_date   AS end_date,
                project_manager,
                delivery_lead,
                {alloc_sel}
                {sum_sel}
                {status_sel}
            FROM public.exec_project_summary
            WHERE client_id = :cid
            ORDER BY
                CASE rag_status WHEN 'Red' THEN 1 WHEN 'Amber' THEN 2 WHEN 'Green' THEN 3 ELSE 4 END,
                project_name
            """,
            {"cid": client_id},
        )
    else:
        # Fallback: raw projects table (RAG less reliable)
        df = run_query(
            """
            SELECT
                project_id, project_name, client_id, status,
                rag_status AS effective_rag, NULL AS rag_source,
                health_score, budget_rag, budget_total, budget_spent,
                project_start_date AS start_date,
                expected_end_date  AS end_date,
                project_manager, delivery_lead,
                NULL::integer AS total_allocation_pct,
                NULL::text AS latest_summary,
                updated_at AS last_status_update_at
            FROM public.projects
            WHERE client_id = :cid
              AND LOWER(COALESCE(status,'open')) NOT IN
                  ('closed','completed','rejected','cancelled','canceled','archived')
            ORDER BY project_name
            """,
            {"cid": client_id},
        )
        if df is not None:
            st.warning(
                "⚠️ exec_project_summary view not found — using raw projects table. "
                "Run `00_exec_project_summary_view.sql` in your database to enable full RAG logic.",
                icon="⚠️",
            )

    df = safe_df(df)
    if not df.empty:
        for c in ("start_date", "end_date"):
            if c in df.columns:
                df[c] = df[c].apply(to_date)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_raids_for_client(client_id: int) -> pd.DataFrame:
    """Full RAID snapshot for the client — all statuses, all key columns, sorted by risk score."""
    if not table_exists("public", "raids"):
        return pd.DataFrame()
    return safe_df(run_query(
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
        LEFT JOIN public.projects p ON p.project_id = r.project_id
        WHERE r.client_id = :cid
          AND LOWER(COALESCE(p.status, 'open')) NOT IN
              ('closed','completed','rejected','cancelled','canceled','archived')
        ORDER BY
            CASE LOWER(r.status) WHEN 'open' THEN 1 WHEN 'in progress' THEN 2 ELSE 3 END,
            COALESCE(r.revised_score, r.score, 0) DESC,
            COALESCE(r.severity, 0) DESC,
            r.date_raised DESC NULLS LAST
        """,
        {"cid": client_id},
    ))


@st.cache_data(ttl=300, show_spinner=False)
def load_actions_for_client(client_id: int) -> pd.DataFrame:
    """
    FIX: uses correct PK column action_id (not id).
    """
    if not table_exists("public", "actions"):
        return pd.DataFrame()
    df = safe_df(run_query(
        """
        SELECT
            action_id,
            title,
            owner,
            status,
            due_date,
            priority,
            updated_at
        FROM public.actions
        WHERE client_id = :cid
          AND LOWER(status) NOT IN ('closed','completed')
        ORDER BY due_date ASC NULLS LAST, updated_at DESC NULLS LAST
        LIMIT 80
        """,
        {"cid": client_id},
    ))
    if not df.empty and "due_date" in df.columns:
        df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce").dt.date
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_resources_for_client(client_id: int, projects_df: pd.DataFrame) -> pd.DataFrame:
    """
    FIX: correct join path is resource_allocation → resource_pool (not a flat resource_allocation table).
    Schema: resource_allocation(resource_id, project_id, client_id, allocation_pct)
            resource_pool(resource_id, full_name, role, user_email)
    """
    if table_exists("public", "resource_allocation") and table_exists("public", "resource_pool"):
        df = safe_df(run_query(
            """
            SELECT
                p.project_id,
                p.project_name,
                rp.full_name        AS resource,
                COALESCE(rp.user_email, rp.email) AS resource_email,
                rp.role AS role,
                ra.allocation_pct
            FROM public.projects p
            JOIN public.resource_allocation ra ON ra.project_id = p.project_id
            JOIN public.resource_pool rp       ON rp.resource_id = ra.resource_id
            WHERE p.client_id = :cid
              AND LOWER(COALESCE(p.status,'open')) NOT IN
                  ('closed','completed','rejected','cancelled','canceled','archived')
              AND ra.allocation_pct > 0
            ORDER BY p.project_name, rp.full_name
            """,
            {"cid": client_id},
        ))
        if not df.empty:
            df["resource_id"] = (
                df["resource_email"].fillna("").astype(str).str.strip().str.lower()
                .where(
                    df["resource_email"].fillna("").astype(str).str.strip() != "",
                    df["resource"].fillna("").astype(str).str.strip().str.lower()
                )
            )
            df = df[df["resource_id"].fillna("").astype(str).str.strip() != ""]
            return df

    # Fallback: PM / delivery lead from projects
    rows = []
    if projects_df is not None and not projects_df.empty:
        for _, r in projects_df.iterrows():
            pname = r.get("project_name")
            for person, role in (
                (r.get("project_manager"), "Project Manager"),
                (r.get("delivery_lead"),   "Delivery Lead"),
            ):
                if isinstance(person, str) and person.strip():
                    rows.append({"project_name": pname, "resource": person.strip(), "role": role})

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["resource_id"] = out["resource"].fillna("").astype(str).str.strip().str.lower()
    return out[out["resource_id"] != ""]


@st.cache_data(ttl=300, show_spinner=False)
def load_nfr_count_for_client(client_id: int) -> int:
    """
    FIX: uses weekly_nfr with week_commencing (correct column name).
    nfr_reports.week_start does not exist in this schema.
    """
    df = safe_df(run_query(
        """
        SELECT COUNT(*) AS cnt
        FROM public.weekly_nfr wn
        WHERE (
            wn.client_id = :cid
            OR wn.project_id IN (SELECT project_id FROM public.projects WHERE client_id = :cid)
        )
          AND wn.week_commencing >= CURRENT_DATE - INTERVAL '90 days'
        """,
        {"cid": client_id},
    ))
    if df.empty: return 0
    try: return int(df.iloc[0]["cnt"])
    except Exception: return 0


# ============================================================
# EXEC SUMMARY
# ============================================================
def _rule_based_exec_summary(
    *,
    client_name: str,
    projects_df: pd.DataFrame,
    resources_df: pd.DataFrame,
    rag_counts: dict,
    raids_df: pd.DataFrame,
    actions_df: pd.DataFrame,
    nfr_count: int,
) -> str:
    total = rag_counts.get("total", 0)
    g = rag_counts.get("green", 0)
    a = rag_counts.get("amber", 0)
    r = rag_counts.get("red", 0)

    res_count = (
        int(resources_df["resource_id"].nunique())
        if (resources_df is not None and not resources_df.empty and "resource_id" in resources_df.columns)
        else 0
    )

    overdue_actions = 0
    if actions_df is not None and not actions_df.empty and "due_date" in actions_df.columns:
        stt = actions_df["status"].astype(str).str.lower() if "status" in actions_df.columns else pd.Series([], dtype=str)
        dd = pd.to_datetime(actions_df["due_date"], errors="coerce").dt.date
        overdue_actions = int(((dd < TODAY) & (~stt.isin(["closed", "completed"])) & dd.notna()).sum())

    stale_risks = 0
    if raids_df is not None and not raids_df.empty and "updated_at" in raids_df.columns:
        upd = pd.to_datetime(raids_df["updated_at"], errors="coerce")
        is_closed = raids_df["status"].astype(str).str.lower().isin(["closed", "completed"]) if "status" in raids_df.columns else pd.Series(False, index=raids_df.index)
        stale_risks = int(((upd < (dt.datetime.utcnow() - dt.timedelta(days=30))) & ~is_closed).sum())

    worst = "Red" if r > 0 else ("Amber" if a > 0 else ("Green" if g > 0 else "Not recorded"))

    reds, ambers = [], []
    if projects_df is not None and not projects_df.empty and "effective_rag" in projects_df.columns:
        s = projects_df["effective_rag"].astype(str).str.lower()
        reds   = projects_df[s == "red"]["project_name"].astype(str).tolist()[:6]
        ambers = projects_df[s == "amber"]["project_name"].astype(str).tolist()[:6]

    lines = [
        f"Client: {client_name}", "",
        f"Live portfolio: {total} project(s). Effective RAG: G {g} / A {a} / R {r} (Overall: {worst}).",
        f"Assigned resources: {res_count}.",
        f"Open RAIDs: {0 if raids_df is None else len(raids_df)}; stale (30+ days): {stale_risks}.",
        f"Open actions: {0 if actions_df is None else len(actions_df)}; overdue: {overdue_actions}.",
        f"Notes for Record (last 30d): {nfr_count}.",
        "",
    ]

    if r > 0 and reds:
        lines += ["Red projects (exec attention):"] + [f"- {p}" for p in reds] + [""]
    if a > 0 and ambers:
        lines += ["Amber projects (monitor / unblock):"] + [f"- {p}" for p in ambers] + [""]

    # Latest status signals from exec_project_summary
    if projects_df is not None and not projects_df.empty and "latest_summary" in projects_df.columns:
        sigs = projects_df[["project_name", "latest_summary"]].copy()
        sigs["latest_summary"] = sigs["latest_summary"].fillna("").astype(str).str.strip()
        sigs = sigs[sigs["latest_summary"] != ""].head(3)
        if not sigs.empty:
            lines.append("Latest status signals:")
            for _, row in sigs.iterrows():
                lines.append(f"- {row['project_name']}: {row['latest_summary']}")
            lines.append("")

    lines.append("Executive actions:")
    if r > 0:
        lines += [
            "- Assign exec owners to each Red project; confirm recovery plans with explicit scope/time/cost trade-offs.",
            "- Unblock dependencies and decision latency; validate critical path and resourcing.",
        ]
    elif a > 0:
        lines.append("- Increase cadence on Amber items; tighten milestone realism and RAID hygiene.")
    else:
        lines.append("- Maintain cadence; ensure RAG remains evidence-based and refreshed via governance updates.")

    return "\n".join(lines)


def _openai_exec_summary(**kwargs) -> str:
    api_key = None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        pass
    if not api_key:
        return _rule_based_exec_summary(**kwargs)

    compact = {
        "client_name":      kwargs["client_name"],
        "rag_counts":       kwargs["rag_counts"],
        "nfr_count_30d":    kwargs["nfr_count"],
        "projects":         (kwargs["projects_df"].head(20).to_dict("records") if kwargs["projects_df"] is not None and not kwargs["projects_df"].empty else []),
        "resources_unique": (int(kwargs["resources_df"]["resource_id"].nunique()) if kwargs["resources_df"] is not None and not kwargs["resources_df"].empty and "resource_id" in kwargs["resources_df"].columns else 0),
        "raids_top":        (kwargs["raids_df"].head(10).to_dict("records") if kwargs["raids_df"] is not None and not kwargs["raids_df"].empty else []),
        "actions_top":      (kwargs["actions_df"].head(15).to_dict("records") if kwargs["actions_df"] is not None and not kwargs["actions_df"].empty else []),
        "generated_at_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
    }

    prompt = f"""
You are a Senior Executive PMO Advisor producing a CEO-ready client summary.

Output format EXACTLY:

EXECUTIVE SUMMARY
2–4 sentences synthesising delivery confidence and what the RAG distribution implies.

PORTFOLIO HOTSPOTS
3–7 bullets (focus on Red then Amber; state clearly if data is missing)

RESOURCING
2–4 bullets on coverage and allocation visibility

EXEC ACTIONS
3–6 bullets — decisions/escalations leadership should take next

Rules:
- Do NOT invent information.
- If data missing, say "Not recorded".
- "NFR" means Notes for Record, not a delivery metric.
- Be concise and executive.

DATA (json):
{json.dumps(compact, default=str)}
""".strip()

    try:
        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4.1-mini", "input": prompt},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = None
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    text = c["text"]
                    break
            if text: break
        return (text or "").strip() or _rule_based_exec_summary(**kwargs)
    except Exception:
        return _rule_based_exec_summary(**kwargs)


# ============================================================
# UI
# ============================================================
st.markdown("<div class='page-title'>🏢 CEO Client Performance</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='page-sub'>Live projects • assigned resources • client RAG "
    "(override → snapshot → base) • executive summary</div>",
    unsafe_allow_html=True,
)

# ── Client selector ──────────────────────────────────────────
clients_df = load_clients()
if clients_df.empty:
    st.error("No clients found in the database.")
    pmo_footer()
    st.stop()

client_map = {row["client_name"]: int(row["client_id"]) for _, row in clients_df.iterrows()}

st.markdown("<div class='panel'>", unsafe_allow_html=True)
c1, c2 = st.columns([5, 1])
with c1:
    client_name = st.selectbox("Client", list(client_map.keys()))
with c2:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
st.markdown("</div>", unsafe_allow_html=True)

client_id = client_map[client_name]

# ── Load ─────────────────────────────────────────────────────
with st.spinner("Loading client data..."):
    projects  = load_live_projects_for_client(client_id)
    raids     = load_raids_for_client(client_id)
    actions   = load_actions_for_client(client_id)
    resources = load_resources_for_client(client_id, projects)
    nfr_count = load_nfr_count_for_client(client_id)

# effective_rag already resolved by the view (or fallback)
projects_count = len(projects) if not projects.empty else 0
resources_count = (
    int(resources["resource_id"].nunique())
    if resources is not None and not resources.empty and "resource_id" in resources.columns
    else 0
)

rag_counts = {"green": 0, "amber": 0, "red": 0, "total": projects_count}
if not projects.empty and "effective_rag" in projects.columns:
    s = projects["effective_rag"].fillna("").astype(str).str.strip().str.lower()
    rag_counts["green"] = int((s == "green").sum())
    rag_counts["amber"] = int((s == "amber").sum())
    rag_counts["red"]   = int((s == "red").sum())

client_rag = worst_rag(rag_counts["green"], rag_counts["amber"], rag_counts["red"])

# ── KPIs ─────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4, gap="medium")
with k1:
    st.markdown(f"""<div class="kpi"><div class="label">Live projects</div>
        <div class="value">{projects_count}</div>
        <div class="sub">Excludes closed / rejected</div></div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="kpi"><div class="label">Assigned resources</div>
        <div class="value">{resources_count}</div>
        <div class="sub">Unique people under client</div></div>""", unsafe_allow_html=True)
with k3:
    nfr_str = str(nfr_count) if nfr_count else "0"
    st.markdown(f"""<div class="kpi"><div class="label">Notes for Record (30d)</div>
        <div class="value">{nfr_str}</div>
        <div class="sub">weekly_nfr governance activity</div></div>""", unsafe_allow_html=True)
with k4:
    rag_label = (client_rag or "—").upper() if client_rag else "—"
    st.markdown(f"""<div class="kpi"><div class="label">Client RAG (effective)</div>
        <div class="value">{rag_label}</div>
        <div class="sub">G {rag_counts["green"]} / A {rag_counts["amber"]} / R {rag_counts["red"]}
        &nbsp; {rag_pill(client_rag)}</div></div>""", unsafe_allow_html=True)

rag_source_note = "exec_project_summary view" if table_exists("public", "exec_project_summary") else "projects table (raw)"
st.markdown(
    f"<div class='small-note'>Effective RAG source: {rag_source_note} "
    f"(priority: active override → latest snapshot → projects.rag_status)</div>",
    unsafe_allow_html=True,
)

# ── Debug / RAG Diagnostic expander ──────────────────────────
with st.expander("🔎 RAG Diagnostic & Data Coverage", expanded=False):
    st.markdown("#### Why is RAG showing as None?")
    st.markdown("""
RAG is resolved in this priority order. The first non-null value wins:
1. **Override** — `project_rag_override` (active, not expired)
2. **Snapshot** — `project_rag_snapshot` (latest `as_of`)
3. **Base** — `projects.rag_status`
4. **Status update** — `project_status_updates` (latest `updated_at`)

If all four are NULL for a project, RAG will show as None.
    """)

    if projects.empty:
        st.warning("No live/approved projects loaded for this client.")
    else:
        show_cols = [c for c in ["project_name", "status", "effective_rag", "rag_source", "health_score", "total_allocation_pct"] if c in projects.columns]
        st.dataframe(projects[show_cols].head(30), use_container_width=True, hide_index=True)

        # Raw source checks
        pids = [int(x) for x in projects["project_id"].dropna().tolist()] if "project_id" in projects.columns else []
        if pids:
            st.markdown("**Raw source counts for these projects:**")
            dc1, dc2, dc3, dc4 = st.columns(4)

            base_rag_count = int(projects["effective_rag"].notna().sum()) if "effective_rag" in projects.columns else 0
            none_count = int(projects["effective_rag"].isna().sum()) if "effective_rag" in projects.columns else len(projects)

            has_override = run_query(
                "SELECT COUNT(*) AS n FROM public.project_rag_override WHERE project_id = ANY(CAST(:pids AS bigint[])) AND is_active=TRUE AND (expires_at IS NULL OR expires_at > now())",
                {"pids": pids}
            )
            has_snapshot = run_query(
                "SELECT COUNT(DISTINCT project_id) AS n FROM public.project_rag_snapshot WHERE project_id = ANY(CAST(:pids AS bigint[]))",
                {"pids": pids}
            )
            has_base = run_query(
                "SELECT COUNT(*) AS n FROM public.projects WHERE project_id = ANY(CAST(:pids AS bigint[])) AND rag_status IS NOT NULL AND rag_status <> ''",
                {"pids": pids}
            )
            has_update = run_query(
                "SELECT COUNT(DISTINCT project_id) AS n FROM public.project_status_updates WHERE project_id = ANY(CAST(:pids AS bigint[]))",
                {"pids": pids}
            )

            def _safe_n(df): return int(df.iloc[0]["n"]) if df is not None and not df.empty else 0

            dc1.metric("Active overrides", _safe_n(has_override))
            dc2.metric("Projects with snapshot", _safe_n(has_snapshot))
            dc3.metric("Projects with base RAG", _safe_n(has_base))
            dc4.metric("Projects with status update", _safe_n(has_update))

            if none_count > 0:
                st.warning(
                    f"⚠️ {none_count} project(s) have no RAG from any source. "
                    "To fix: set `projects.rag_status`, add a status update, or run the RAG snapshot job."
                )

    st.markdown("---")
    if resources is None or resources.empty:
        st.info("No resources loaded — check resource_allocation / resource_pool or PM/DL fields on projects.")
    else:
        cols = [c for c in ["resource", "resource_id", "role", "project_name", "allocation_pct", "resource_email"] if c in resources.columns]
        st.dataframe(resources[cols].head(50), use_container_width=True, hide_index=True)
        st.write("Unique resource_id:", int(resources["resource_id"].nunique()) if "resource_id" in resources.columns else 0)

# ── Exec summary ──────────────────────────────────────────────
st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)
st.markdown("<div class='panel'>", unsafe_allow_html=True)

h1, h2 = st.columns([5, 1])
with h1:
    st.markdown("### 🧠 Live Executive Summary")
with h2:
    if st.button("⚡ Regenerate", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

summary_text = _openai_exec_summary(
    client_name=client_name,
    projects_df=projects,
    resources_df=resources,
    rag_counts=rag_counts,
    raids_df=raids,
    actions_df=actions,
    nfr_count=nfr_count,
)

st.markdown(
    f"""<div class="exec-box"><pre>{summary_text}</pre>
    <div class="exec-meta">Snapshot: {dt.datetime.utcnow().isoformat(timespec="seconds")} UTC</div>
    </div>""",
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

# ── Detail tabs ───────────────────────────────────────────────
tab_projects, tab_resources, tab_raids, tab_actions = st.tabs(
    ["📁 Projects", "👥 Resources", "📌 Open RAIDs", "📝 Open Actions"]
)

with tab_projects:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 📁 Live projects under this client")
    if projects.empty:
        st.info("No live projects found for this client.")
    else:
        show = [c for c in [
            "project_name", "status", "effective_rag", "rag_source",
            "health_score", "budget_rag", "budget_total", "budget_spent",
            "total_allocation_pct", "start_date", "end_date",
            "project_manager", "delivery_lead", "latest_summary", "last_status_update_at",
        ] if c in projects.columns]
        st.markdown("<div class='table-wrap'>", unsafe_allow_html=True)
        st.dataframe(projects[show], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with tab_resources:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 👥 Assigned resources under this client")
    if resources is None or resources.empty:
        st.info("No resources found. Populate resource_allocation → resource_pool, or fill project_manager / delivery_lead on projects.")
    else:
        cols = [c for c in ["resource", "role", "project_name", "allocation_pct", "resource_email"] if c in resources.columns]
        st.markdown("<div class='table-wrap'>", unsafe_allow_html=True)
        st.dataframe(resources[cols].drop_duplicates(), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
        if "resource_id" in resources.columns:
            st.caption(f"Unique resources: {int(resources['resource_id'].nunique())}")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_raids:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 📋 RAID Log Snapshot")
    if raids is None or raids.empty:
        st.success("No RAIDs recorded for this client's live projects.")
    else:
        _r_total = len(raids)
        _r_open  = int((raids["status"].astype(str).str.lower() == "open").sum()) if "status" in raids.columns else 0
        _r_upd   = pd.to_datetime(raids["updated_at"], errors="coerce") if "updated_at" in raids.columns else pd.Series(dtype="datetime64[ns]")
        _is_cl   = raids["status"].astype(str).str.lower().isin(["closed","completed"]) if "status" in raids.columns else pd.Series(False, index=raids.index)
        _r_stale = int(((_r_upd < (dt.datetime.utcnow() - dt.timedelta(days=30))) & ~_is_cl).sum())

        km1, km2, km3 = st.columns(3)
        km1.metric("Total RAIDs", _r_total)
        km2.metric("Open", _r_open)
        km3.metric("Stale open (30+ days)", _r_stale)

        _statuses = ["All"] + sorted(raids["status"].dropna().astype(str).str.title().unique().tolist())
        _sel = st.selectbox("Filter by status", _statuses, key="ceo_raid_status")
        _disp = raids.copy() if _sel == "All" else raids[raids["status"].astype(str).str.title() == _sel]
        _disp = _disp.dropna(axis=1, how="all")

        # First 20 rows always visible
        st.markdown("<div class='table-wrap'>", unsafe_allow_html=True)
        st.dataframe(_disp.head(20), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if len(_disp) > 20:
            with st.expander(f"🔍 View all {len(_disp)} rows", expanded=False):
                st.markdown("<div class='table-wrap'>", unsafe_allow_html=True)
                st.dataframe(_disp, use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)

        st.caption(f"Showing {min(20, len(_disp))} of {len(_disp)} entries (filtered from {_r_total} total)")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_actions:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 📝 Open actions for this client")
    if actions is None or actions.empty:
        st.success("No open actions recorded.")
    else:
        st.markdown("<div class='table-wrap'>", unsafe_allow_html=True)
        st.dataframe(actions, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

pmo_footer()