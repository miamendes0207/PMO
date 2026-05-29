## ============================================================
# 29_Project_Gantt.py — ScopeSight v3.6 (Gantt Builder)
# ============================================================

import streamlit as st
import pandas as pd
import datetime as dt
import plotly.express as px
import json

# ---------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="📅 Project Gantt Builder",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# Auth + Layout
# ---------------------------------------------------------
from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# DB
from modules.db import run_query, run_execute

# Gantt DB helpers (must exist in modules/db.py)
from modules.db import (
    get_workstreams,
    add_workstream,
    update_workstream,
    delete_workstream,
    get_project_tasks,
    add_task,
    update_task,
    delete_task,
    get_active_resources,
    get_task_assignments,
    upsert_task_assignment,
    delete_task_assignment,
)

set_pmo_theme(page_title="📅 Project Gantt Builder")
render_sidebar()
hide_streamlit_nav()
require_login()

current_email = (st.session_state.get("email") or "").strip().lower()
current_role  = (st.session_state.get("role") or "user").strip().lower()

# ============================================================
# Department colour system (shared with Portfolio Pipeline)
# ============================================================
# Base hue per department (H, S%, L% in HSL)
DEPT_BASE_HSL = {
    "Fraud":                     (220, 90, 50),   # Blue
    "Advisory & Transformation": (0,   80, 45),   # Red
    "Tech & Data":               (142, 70, 35),   # Green
    "Other":                     (24,  90, 45),   # Orange
}

# Canonical swatch colours (used for legend + portfolio overview)
DEPT_SWATCH_COLOUR = {
    "Fraud":                     "#2563eb",
    "Advisory & Transformation": "#dc2626",
    "Tech & Data":               "#16a34a",
    "Other":                     "#ea580c",
}

# Raw string aliases → canonical bucket
DEPT_ALIASES = {
    "Fraud":                     ["fraud"],
    "Advisory & Transformation": ["advisory", "advisory & transformation", "transformation",
                                  "change", "strategy", "pmo", "operations",
                                  "risk", "risk & compliance"],
    "Tech & Data":               ["tech", "tech & data", "technology",
                                  "data", "data & analytics"],
}

def _to_dept(service_line: str) -> str:
    """Map any raw service_line / department string → canonical dept bucket."""
    sl = (service_line or "").strip().lower()
    for dept, aliases in DEPT_ALIASES.items():
        if sl in aliases or any(sl.startswith(a) for a in aliases):
            return dept
    return "Other"

def _hsl_to_hex(h: int, s: int, l: int) -> str:
    """Convert HSL (0-360, 0-100, 0-100) → #rrggbb."""
    s /= 100; l /= 100
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if   h < 60:  r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    r, g, b = int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"

def _build_item_colour_map(items: list) -> dict:
    """
    Given [(label, dept), ...], assign each label a unique shade within
    its department's hue family (L spread from 30 dark → 65 light).
    Single items get the canonical base shade.
    """
    from collections import defaultdict
    dept_items = defaultdict(list)
    for label, dept in items:
        dept_items[dept].append(label)

    colour_map = {}
    for dept, labels in dept_items.items():
        h, s, base_l = DEPT_BASE_HSL.get(dept, (0, 0, 50))
        n = len(labels)
        lightnesses = [base_l] if n == 1 else [
            int(30 + i * (65 - 30) / (n - 1)) for i in range(n)
        ]
        for label, l in zip(labels, lightnesses):
            colour_map[label] = _hsl_to_hex(h, s, l)
    return colour_map

# ============================================================
# Styles
# ============================================================
st.markdown("""
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

.nfr-card {
    background: white; border: 2px solid #4facfe; padding: 1.5rem;
    border-radius: 12px; margin: 1.25rem 0;
    box-shadow: 0 4px 12px rgba(79,172,254,0.15);
}
.nfr-card h3 { color:#0077be; margin:0 0 1rem 0; font-size:1.25rem; font-weight:700; }

.info-row {
    background:#f0f9ff; padding:0.75rem 1rem; margin:0.5rem 0;
    border-radius:6px; border-left:4px solid #4facfe;
}
.info-row strong { color:#0077be; }

.section-header {
    background: linear-gradient(90deg,#4facfe 0%,#00f2fe 100%);
    padding:1rem 1.5rem; border-radius:8px; margin:1rem 0;
}
.section-header h3 { color:white; margin:0; font-size:1.2rem; font-weight:700; }

.step-header { margin:1.5rem 0 1rem 0; padding-bottom:0.5rem; border-bottom:2px solid #e5e7eb; }
.step-header h4 { color:#1f2937; margin:0; font-size:1.15rem; font-weight:700; }

.info-box { background:#f0fff4; border-left:4px solid #48bb78; padding:1rem; border-radius:6px; margin:1rem 0; }

.metric-card { background:#f0f9ff; border:2px solid #bae6fd; border-radius:10px; padding:1.25rem; text-align:center; margin:0.5rem 0; }
.metric-value { font-size:2rem; font-weight:700; color:#0077be; margin:0.5rem 0; }
.metric-label { color:#0369a1; font-size:0.9rem; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; }

/* Department legend swatches */
.dept-legend { display:flex; gap:1.5rem; align-items:center; flex-wrap:wrap; margin:0.75rem 0 1.25rem 0; }
.dept-swatch { display:flex; align-items:center; gap:0.4rem; font-size:0.85rem; font-weight:600; color:#334155; }
.swatch-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; }

/* Dept pill shown in page header */
.dept-pill {
    display:inline-flex; align-items:center; gap:0.5rem;
    padding:0.4rem 1rem; border-radius:999px;
    font-size:0.9rem; font-weight:700; color:white;
    margin-left:0.75rem; vertical-align:middle;
}

div.stButton > button {
    background: linear-gradient(135deg,#4facfe 0%,#00f2fe 100%);
    color:white; font-size:1.05rem; font-weight:700;
    padding:0.65rem 1.5rem; border:none; border-radius:8px; transition:all 0.2s ease;
}
div.stButton > button:hover { transform:translateY(-1px); box-shadow:0 6px 12px rgba(79,172,254,0.35); }

[data-testid="stDataFrame"] div[role="grid"] { font-size:0.88rem; }
.block-container { padding-top:1.5rem; }
.small-muted { color:#6b7280; font-size:0.9rem; }
label { font-weight:600 !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# Helpers
# ============================================================
STATUS_ORDER = ["not_started", "in_progress", "blocked", "done"]

def _parse_json(value):
    if isinstance(value, dict): return value
    if isinstance(value, str):
        try: return json.loads(value)
        except Exception: return {}
    return {}

def _safe_date(v):
    if pd.isna(v) or v is None: return None
    if isinstance(v, dt.date): return v
    return pd.to_datetime(v).date()

def _load_user_id(email: str):
    if not email: return None
    df = run_query("SELECT user_id FROM users WHERE LOWER(email) = LOWER(:email)", {"email": email})
    if df is None or df.empty: return None
    return int(df.iloc[0]["user_id"])

def _clamp_int(v, lo=0, hi=100, default=0):
    try: v = int(v)
    except Exception: v = default
    return max(lo, min(hi, v))

def bind_percent_pair(num_key: str, slider_key: str, lo=0, hi=100):
    def _num_to_slider():
        st.session_state[slider_key] = _clamp_int(st.session_state.get(num_key, lo), lo, hi, lo)
    def _slider_to_num():
        st.session_state[num_key] = _clamp_int(st.session_state.get(slider_key, lo), lo, hi, lo)
    if num_key not in st.session_state and slider_key not in st.session_state:
        st.session_state[num_key] = lo; st.session_state[slider_key] = lo
    elif num_key in st.session_state and slider_key not in st.session_state:
        _num_to_slider()
    elif slider_key in st.session_state and num_key not in st.session_state:
        _slider_to_num()
    else:
        _num_to_slider()
    return _num_to_slider, _slider_to_num

@st.cache_data(show_spinner=False)
def _table_has_column(table_name: str, column_name: str) -> bool:
    df = run_query(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=:t AND column_name=:c",
        {"t": table_name, "c": column_name},
    )
    return df is not None and not df.empty

def _clear_gantt_ui_state():
    prefixes = ("ws_","edit_ws_","task_","edit_task_","assign_","remove_assign","task_pct_","edit_task_pct_","p_start","p_end")
    keep = {"client_select","project_select"}
    for k in list(st.session_state.keys()):
        if k in keep: continue
        if k.startswith(prefixes) or k in ("edit_ws_pick","edit_task_pick","assign_task_pick"):
            del st.session_state[k]
    try: st.cache_data.clear()
    except Exception: pass

def get_project_resources(project_id: int) -> pd.DataFrame:
    has_users_full_name = _table_has_column("users", "full_name")
    users_name_expr = "u.full_name" if has_users_full_name else "u.email"
    if _table_has_column("resource_pool", "user_id"):
        df = run_query(f"""
            SELECT rp.resource_id, COALESCE(rp.full_name, {users_name_expr}, u.email) AS full_name
            FROM public.user_project_permissions upp
            JOIN public.users u ON u.user_id = upp.user_id
            JOIN public.resource_pool rp ON rp.user_id = u.user_id
            WHERE upp.project_id = :pid AND COALESCE(rp.is_active, TRUE) = TRUE
            ORDER BY 2
        """, {"pid": project_id})
        return df if df is not None else pd.DataFrame()
    email_col = "email" if _table_has_column("resource_pool","email") else ("user_email" if _table_has_column("resource_pool","user_email") else None)
    if email_col:
        df = run_query(f"""
            SELECT rp.resource_id, COALESCE(rp.full_name, {users_name_expr}, u.email) AS full_name
            FROM public.user_project_permissions upp
            JOIN public.users u ON u.user_id = upp.user_id
            JOIN public.resource_pool rp ON LOWER(rp.{email_col}) = LOWER(u.email)
            WHERE upp.project_id = :pid AND COALESCE(rp.is_active, TRUE) = TRUE
            ORDER BY 2
        """, {"pid": project_id})
        return df if df is not None else pd.DataFrame()
    return pd.DataFrame()

def get_portfolio_projects(uid, role: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    if _table_has_column("projects","department"):
        sl_select = "p.department AS service_line"
    elif _table_has_column("projects","service_line"):
        sl_select = "p.service_line AS service_line"
    else:
        sl_select = "NULL::text AS service_line"

    base_sql = f"""
        SELECT p.project_id, p.project_name, p.project_code,
               p.project_start_date AS start_date, p.expected_end_date AS end_date,
               {sl_select}
        FROM public.projects p
    """
    where = """
        WHERE COALESCE(p.project_start_date, p.expected_end_date) IS NOT NULL
          AND (COALESCE(p.expected_end_date, p.project_start_date) >= :start)
          AND (COALESCE(p.project_start_date, p.expected_end_date) <= :end)
    """
    params = {"start": start, "end": end}
    if role not in ("admin","ceo","exec"):
        base_sql += " JOIN public.user_project_permissions upp ON upp.project_id = p.project_id "
        where += " AND upp.user_id = :uid "
        params["uid"] = uid
    df = run_query(base_sql + where + " ORDER BY p.project_name", params)
    return df if df is not None else pd.DataFrame()

def _get_project_department(project_id: int) -> str:
    """
    Read the department/service_line from the projects table for a single project
    and return the canonical bucket name.
    """
    if _table_has_column("projects", "department"):
        col = "department"
    elif _table_has_column("projects", "service_line"):
        col = "service_line"
    else:
        return "Other"

    df = run_query(
        f"SELECT {col} AS dept FROM public.projects WHERE project_id = :pid LIMIT 1",
        {"pid": project_id},
    )
    if df is None or df.empty:
        return "Other"
    return _to_dept(str(df.iloc[0]["dept"] or ""))

# ============================================================
# Portfolio Gantt (multi-project overview)
# ============================================================
def render_portfolio_gantt(df: pd.DataFrame):
    """
    Portfolio timeline.  Each project bar is coloured by its department,
    with per-item shading so multiple projects in the same dept are distinguishable.
    """
    if df is None or df.empty:
        st.info("ℹ️ No projects found in this date range.")
        return

    d = df.copy()
    d["Start"]  = pd.to_datetime(d["start_date"], errors="coerce")
    d["Finish"] = pd.to_datetime(d["end_date"],   errors="coerce")

    d = d[d["Start"].notna() | d["Finish"].notna()].copy()
    if d.empty:
        st.info("ℹ️ No projects have dates to plot.")
        return

    d["Start"]  = d["Start"].fillna(d["Finish"])
    d["Finish"] = d["Finish"].fillna(d["Start"] + pd.Timedelta(days=1))

    inv = d["Finish"] < d["Start"]
    if inv.any():
        tmp = d.loc[inv, "Start"].copy()
        d.loc[inv, "Start"]  = d.loc[inv, "Finish"]
        d.loc[inv, "Finish"] = tmp

    # Resolve department from service_line column
    raw_sl = d["service_line"].fillna("").astype(str)
    d["Department"] = raw_sl.apply(_to_dept)

    def _proj_label(r):
        code = (r.get("project_code") or "").strip()
        return f"{r['project_name']} ({code})" if code else r["project_name"]

    d["Project"] = d.apply(_proj_label, axis=1)

    # Build per-item shade map (same logic as pipeline page)
    item_colour_map = _build_item_colour_map(
        list(zip(d["Project"].tolist(), d["Department"].tolist()))
    )

    # Dept legend swatches above chart
    swatches = "".join([
        f"<div class='dept-swatch'>"
        f"<div class='swatch-dot' style='background:{colour}'></div>"
        f"{dept}</div>"
        for dept, colour in DEPT_SWATCH_COLOUR.items()
    ])
    st.markdown(f"<div class='dept-legend'>{swatches}</div>", unsafe_allow_html=True)

    fig = px.timeline(
        d.sort_values(["Department", "Start"]),
        x_start="Start",
        x_end="Finish",
        y="Project",
        color="Project",
        color_discrete_map=item_colour_map,
        hover_data={"Department": True, "service_line": True, "Start": True, "Finish": True},
    )
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_layout(
        height=max(520, 220 + 24 * len(d)),
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# Project-level Gantt (tasks on Y, colour by workstream)
# The workstream bars also inherit the project's dept colour family.
# ============================================================
def _render_gantt(tasks_df: pd.DataFrame, project_dept: str = "Other"):
    """
    Task-level Gantt.  Workstreams are coloured as shades of the project's
    department colour so the chart stays visually linked to the brand palette.
    """
    if tasks_df is None or tasks_df.empty:
        st.info("ℹ️ No tasks yet — add tasks below to see your timeline.")
        return

    df = tasks_df.copy()
    df["Start"]  = pd.to_datetime(df["start_date"], errors="coerce")
    df["Finish"] = pd.to_datetime(df["end_date"],   errors="coerce")

    df = df[df["Start"].notna()].copy()
    if df.empty:
        st.warning("⚠️ All tasks are missing start dates, so nothing can be plotted.")
        return

    df.loc[df["Finish"].isna(), "Finish"] = df.loc[df["Finish"].isna(), "Start"] + pd.Timedelta(days=1)

    inv = df["Finish"] < df["Start"]
    if inv.any():
        tmp = df.loc[inv, "Start"].copy()
        df.loc[inv, "Start"]  = df.loc[inv, "Finish"]
        df.loc[inv, "Finish"] = tmp

    def _mk_label(r):
        ws    = r.get("workstream_name") or "(No workstream)"
        title = r.get("title") or "(Untitled)"
        tid   = r.get("task_id")
        try:    return f"{ws} • {title}  #{int(tid)}"
        except: return f"{ws} • {title}"

    df["TaskLabel"] = df.apply(_mk_label, axis=1)

    def _bar_text(row):
        title = (row.get("title") or "").strip()
        pct   = int(row.get("percent_complete") or 0)
        short = (title[:22] + "…") if len(title) > 23 else title
        return f"{short} ({pct}%)"

    df["BarText"] = df.apply(_bar_text, axis=1)

    # Build per-workstream shades within the project's dept hue family
    workstreams = df["workstream_name"].fillna("(No workstream)").unique().tolist()
    ws_colour_map = _build_item_colour_map(
        [(ws, project_dept) for ws in workstreams]
    )
    # Map back onto the dataframe column used for colouring
    df["workstream_name"] = df["workstream_name"].fillna("(No workstream)")

    df = df.sort_values(["Start", "TaskLabel"])
    category_orders = {"TaskLabel": df["TaskLabel"].tolist()}

    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="TaskLabel",
        color="workstream_name",
        color_discrete_map=ws_colour_map,
        text="BarText",
        hover_data={
            "workstream_name": True, "title": True, "priority": True,
            "status": True, "percent_complete": True, "Start": True, "Finish": True,
        },
        category_orders=category_orders,
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_layout(
        height=max(520, 200 + 26 * len(df)),
        margin=dict(l=10, r=10, t=30, b=10),
        legend_title_text="Workstream",
    )
    st.plotly_chart(fig, use_container_width=True)


def _condensed_tasks_table(tasks_df: pd.DataFrame):
    if tasks_df is None or tasks_df.empty:
        st.info("ℹ️ No tasks to display yet.")
        return
    df = tasks_df.copy()
    df["start_date"] = df["start_date"].apply(_safe_date)
    df["end_date"]   = df["end_date"].apply(_safe_date)
    snap_cols = ["workstream_name","title","start_date","end_date","status","percent_complete","priority"]
    st.dataframe(
        df[snap_cols].rename(columns={
            "workstream_name":"Workstream","title":"Task","start_date":"Start",
            "end_date":"End","status":"Status","percent_complete":"% Done","priority":"Priority",
        }),
        use_container_width=True, hide_index=True, height=240,
    )

# ============================================================
# Project Selection Helper
# ============================================================
def select_project():
    user_id = _load_user_id(current_email)

    if current_role in ("admin","ceo","exec"):
        clients = run_query("""
            SELECT id AS client_id, client_name, client_code, settings
            FROM client_scaffold WHERE status='approved' ORDER BY client_name
        """)
    else:
        clients = run_query("""
            SELECT DISTINCT cs.id AS client_id, cs.client_name, cs.client_code, cs.settings
            FROM client_scaffold cs
            JOIN projects p ON p.client_id = cs.id
            JOIN user_project_permissions upp ON upp.project_id = p.project_id
            WHERE cs.status='approved' AND upp.user_id = :uid ORDER BY cs.client_name
        """, {"uid": user_id})

    if clients is None or clients.empty:
        return None

    client_label = st.selectbox("Select client", clients["client_name"], key="client_select")
    row = clients[clients["client_name"] == client_label].iloc[0]
    client_id     = int(row["client_id"])
    client_name   = row["client_name"]
    client_code   = row.get("client_code")
    client_config = _parse_json(row.get("settings")) or {}

    if current_role in ("admin","ceo","exec"):
        projects = run_query("""
            SELECT project_id, project_name, project_code
            FROM projects WHERE client_id=:cid ORDER BY project_name
        """, {"cid": client_id})
    else:
        projects = run_query("""
            SELECT DISTINCT p.project_id, p.project_name, p.project_code
            FROM projects p
            JOIN user_project_permissions upp ON upp.project_id = p.project_id
            WHERE p.client_id=:cid AND upp.user_id=:uid ORDER BY p.project_name
        """, {"cid": client_id, "uid": user_id})

    if projects is None or projects.empty:
        return None

    projects = projects.copy()
    projects["label"] = projects.apply(
        lambda r: f"{r['project_name']} ({r['project_code']})" if r["project_code"] else r["project_name"],
        axis=1,
    )
    project_label = st.selectbox("Select project", projects["label"], key="project_select")
    selected_row  = projects[projects["label"] == project_label].iloc[0]
    project_id    = int(selected_row["project_id"])
    project_name  = selected_row["project_name"]
    project_code  = selected_row["project_code"]

    return project_name, project_id, client_name, client_id, client_code, client_config, project_code

# ============================================================
# Resolve User
# ============================================================
uid = _load_user_id(current_email)
if uid is None:
    st.error("❌ Could not resolve user_id for current user.")
    pmo_footer()
    st.stop()

# ---------------------------------------------------------
# STEP 1: SELECT PROJECT
# ---------------------------------------------------------
st.markdown("<div class='step-header'><h4>📁 Select Your Project</h4></div>", unsafe_allow_html=True)

selection = select_project()
if not selection:
    st.warning("⚠️ No projects available or accessible.")
    pmo_footer()
    st.stop()

project_name, project_id, client_name, client_id, client_code, client_config, project_code = selection

# Clear stale state when project changes
prev_pid = st.session_state.get("_gantt_last_project_id")
if prev_pid != project_id:
    st.session_state["_gantt_last_project_id"] = project_id
    _clear_gantt_ui_state()
    st.rerun()

# Resolve department for this project — used to colour the task Gantt
project_dept   = _get_project_department(project_id)
dept_colour    = DEPT_SWATCH_COLOUR.get(project_dept, "#6b7280")

# Load project data
workstreams_df = get_workstreams(project_id)
tasks_df       = get_project_tasks(project_id)

# Show which dept this project belongs to
st.markdown(
    f"<span class='dept-pill' style='background:{dept_colour}'>"
    f"● {project_dept}</span>",
    unsafe_allow_html=True,
)

# ============================================================
# TOP-LEVEL TABS
# ============================================================
overview_tab, build_tab = st.tabs(["📊 Overview", "🛠️ Build & Manage"])

# ============================================================
# TAB: OVERVIEW
# ============================================================
with overview_tab:
    st.markdown("<div class='step-header'><h4>📊 Current Project Timeline</h4></div>", unsafe_allow_html=True)

    total_workstreams = len(workstreams_df) if workstreams_df is not None and not workstreams_df.empty else 0
    total_tasks  = len(tasks_df) if tasks_df is not None and not tasks_df.empty else 0
    tasks_done   = len(tasks_df[tasks_df["status"] == "done"]) if tasks_df is not None and not tasks_df.empty else 0
    avg_progress = int(tasks_df["percent_complete"].mean()) if tasks_df is not None and not tasks_df.empty else 0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Workstreams</div><div class='metric-value'>{total_workstreams}</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Total Tasks</div><div class='metric-value'>{total_tasks}</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Tasks Complete</div><div class='metric-value' style='color:#10b981;'>{tasks_done}</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Avg Progress</div><div class='metric-value'>{avg_progress}%</div></div>", unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("##### 📅 Timeline Visualization")

    # Pass project_dept so workstream bars are shaded in the dept colour family
    _render_gantt(tasks_df, project_dept=project_dept)

    st.markdown("##### 📋 Task Overview")
    _condensed_tasks_table(tasks_df)

# ============================================================
# TAB: BUILD & MANAGE
# ============================================================
with build_tab:
    if current_role != "user":
        st.info("ℹ️ Project editing is available to project users only.")
    else:
        st.markdown("<div class='step-header'><h4>🛠️ Build & Manage Your Plan</h4></div>", unsafe_allow_html=True)

        st.markdown("""
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 How It Works</strong><br/>
    • <b>Workstreams</b> organize your project into major phases or streams of work<br/>
    • <b>Tasks</b> are the individual activities within each workstream<br/>
    • <b>Resources</b> can be assigned to tasks with allocation percentages
</div>
""", unsafe_allow_html=True)

        tab_ws, tab_tasks, tab_assign = st.tabs(["🧩 Workstreams", "✅ Tasks", "👥 Assign Resources"])

        # ============================================================
        # WORKSTREAMS
        # ============================================================
        with tab_ws:
            st.markdown("#### 🧩 Manage Workstreams")
            st.markdown("<div class='info-row'><strong>What are workstreams?</strong> High-level phases or parallel tracks of work (e.g., \"Discovery\", \"Development\", \"Testing\")</div>", unsafe_allow_html=True)

            with st.expander("➕ Add New Workstream", expanded=False):
                ws_name = st.text_input("Workstream name", key="ws_name", placeholder="e.g., Discovery Phase")
                ws_desc = st.text_area("Description (optional)", key="ws_desc")
                ws_sort = st.number_input("Sort order", min_value=0, value=0, step=1, key="ws_sort", help="Lower numbers appear first")
                if st.button("Create Workstream", use_container_width=True, key="btn_create_ws"):
                    if not ws_name.strip():
                        st.error("❌ Workstream name is required.")
                    else:
                        add_workstream(project_id, ws_name.strip(), ws_desc.strip() if ws_desc else None, int(ws_sort))
                        st.success("✅ Workstream created successfully!")
                        st.rerun()

            if workstreams_df is None or workstreams_df.empty:
                st.info("ℹ️ No workstreams yet. Create one above to get started.")
            else:
                st.markdown("<br/>", unsafe_allow_html=True)
                st.markdown("##### Existing Workstreams")
                st.dataframe(
                    workstreams_df[["name","description","sort_order"]].rename(
                        columns={"name":"Workstream","description":"Description","sort_order":"Order"}
                    ),
                    use_container_width=True, hide_index=True, height=200,
                )

                with st.expander("✏️ Edit or Delete Workstream"):
                    ws_df = workstreams_df.copy()
                    ws_df["workstream_id"] = ws_df["workstream_id"].astype(int)
                    ws_pick     = st.selectbox("Select workstream", options=ws_df["name"].tolist(), key="edit_ws_pick")
                    selected_ws = ws_df[ws_df["name"] == ws_pick].iloc[0]
                    ws_id       = int(selected_ws["workstream_id"])

                    edit_name = st.text_input("Name", value=selected_ws["name"], key=f"edit_ws_name_{ws_id}")
                    edit_desc = st.text_area("Description", value=selected_ws["description"] or "", key=f"edit_ws_desc_{ws_id}")
                    edit_sort = st.number_input("Sort order", value=int(selected_ws["sort_order"]), key=f"edit_ws_sort_{ws_id}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("💾 Save Changes", use_container_width=True, key=f"btn_save_ws_{ws_id}"):
                            if not edit_name.strip():
                                st.error("❌ Workstream name is required.")
                            else:
                                try:
                                    update_workstream(ws_id, edit_name.strip(), edit_desc.strip() or None, int(edit_sort))
                                    st.success("Workstream updated.")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(f"❌ {e}")
                    with col2:
                        if st.button("🗑️ Delete", use_container_width=True, key=f"btn_delete_ws_{ws_id}"):
                            delete_workstream(ws_id)
                            st.success("✅ Workstream deleted!")
                            st.rerun()

        # ============================================================
        # TASKS
        # ============================================================
        with tab_tasks:
            st.markdown("#### ✅ Manage Tasks")
            st.markdown("<div class='info-row'><strong>What are tasks?</strong> Specific activities within a workstream (e.g., \"User interviews\", \"Build API\", \"QA testing\")</div>", unsafe_allow_html=True)

            if workstreams_df is None or workstreams_df.empty:
                st.warning("⚠️ Create a workstream first before adding tasks.")
            else:
                ws_map = dict(zip(workstreams_df["name"], workstreams_df["workstream_id"]))

                with st.expander("➕ Add New Task", expanded=False):
                    task_ws    = st.selectbox("Workstream", list(ws_map.keys()), key="task_ws")
                    task_title = st.text_input("Task name", key="task_title", placeholder="e.g., Conduct user research")
                    task_desc  = st.text_area("Description (optional)", key="task_desc")

                    col1, col2 = st.columns(2)
                    with col1: task_start = st.date_input("Start date", value=dt.date.today(), key="task_start")
                    with col2: task_end   = st.date_input("End date",   value=dt.date.today(), key="task_end")

                    col3, col4 = st.columns(2)
                    with col3: task_status = st.selectbox("Status",   STATUS_ORDER,               index=0, key="task_status")
                    with col4: task_prio   = st.selectbox("Priority", ["low","medium","high"],   index=1, key="task_prio")

                    num_to_slider, slider_to_num = bind_percent_pair("task_pct_num","task_pct_slider",0,100)
                    st.markdown("**Progress**")
                    col_a, col_b = st.columns([1, 2])
                    with col_a:
                        st.number_input("% complete", min_value=0, max_value=100, step=1, key="task_pct_num", on_change=num_to_slider)
                    with col_b:
                        st.slider("Progress slider", 0, 100, key="task_pct_slider", step=5, on_change=slider_to_num, label_visibility="collapsed")

                    if st.button("Create Task", use_container_width=True, key="btn_create_task"):
                        if not task_title.strip():
                            st.error("❌ Task name is required.")
                        elif task_end < task_start:
                            st.error("❌ End date must be on or after start date.")
                        else:
                            add_task(
                                project_id=project_id, workstream_id=int(ws_map[task_ws]),
                                title=task_title.strip(), description=task_desc.strip() if task_desc else None,
                                start_date=task_start, end_date=task_end, status=task_status,
                                percent_complete=int(st.session_state["task_pct_num"]),
                                priority=task_prio, created_by=current_email,
                            )
                            st.success("✅ Task created successfully!")
                            st.rerun()

                if tasks_df is None or tasks_df.empty:
                    st.info("ℹ️ No tasks yet. Create one above to get started.")
                else:
                    st.markdown("<br/>", unsafe_allow_html=True)
                    st.markdown("##### Existing Tasks")
                    _condensed_tasks_table(tasks_df)

                    with st.expander("✏️ Edit or Delete Task"):
                        tdf         = tasks_df.copy()
                        task_labels = (tdf["workstream_name"] + " • " + tdf["title"]).tolist()
                        task_pick   = st.selectbox("Select task", task_labels, key="edit_task_pick")
                        task_idx    = task_labels.index(task_pick)
                        selected_task = tdf.iloc[task_idx]
                        task_id     = int(selected_task["task_id"])

                        edit_ws = st.selectbox(
                            "Workstream", list(ws_map.keys()),
                            index=list(ws_map.keys()).index(selected_task["workstream_name"]) if selected_task["workstream_name"] in ws_map else 0,
                            key=f"edit_task_ws_{task_id}",
                        )
                        edit_title = st.text_input("Name", value=selected_task["title"], key=f"edit_task_title_{task_id}")
                        edit_desc  = st.text_area("Description", value=selected_task["description"] or "", key=f"edit_task_desc_{task_id}")

                        col1, col2 = st.columns(2)
                        with col1: edit_start = st.date_input("Start", value=_safe_date(selected_task["start_date"]), key=f"edit_task_start_{task_id}")
                        with col2: edit_end   = st.date_input("End",   value=_safe_date(selected_task["end_date"]),   key=f"edit_task_end_{task_id}")

                        col3, col4 = st.columns(2)
                        with col3:
                            edit_status = st.selectbox(
                                "Status", STATUS_ORDER,
                                index=STATUS_ORDER.index(selected_task["status"]) if selected_task["status"] in STATUS_ORDER else 0,
                                key=f"edit_task_status_{task_id}",
                            )
                        with col4:
                            edit_prio = st.selectbox(
                                "Priority", ["low","medium","high"],
                                index=["low","medium","high"].index(selected_task["priority"]) if selected_task["priority"] in ["low","medium","high"] else 1,
                                key=f"edit_task_prio_{task_id}",
                            )

                        if f"edit_task_pct_num_{task_id}" not in st.session_state:
                            st.session_state[f"edit_task_pct_num_{task_id}"]    = int(selected_task["percent_complete"] or 0)
                            st.session_state[f"edit_task_pct_slider_{task_id}"] = int(selected_task["percent_complete"] or 0)

                        num_to_slider, slider_to_num = bind_percent_pair(f"edit_task_pct_num_{task_id}", f"edit_task_pct_slider_{task_id}", 0, 100)
                        st.markdown("**Progress**")
                        col_a, col_b = st.columns([1, 2])
                        with col_a:
                            st.number_input("% complete", min_value=0, max_value=100, step=1, key=f"edit_task_pct_num_{task_id}", on_change=num_to_slider)
                        with col_b:
                            st.slider("Progress slider", 0, 100, key=f"edit_task_pct_slider_{task_id}", step=5, on_change=slider_to_num, label_visibility="collapsed")

                        col_save, col_delete = st.columns(2)
                        with col_save:
                            if st.button("💾 Save Changes", use_container_width=True, key=f"btn_save_task_{task_id}"):
                                if not edit_title.strip():
                                    st.error("❌ Task name is required.")
                                elif edit_end < edit_start:
                                    st.error("❌ End date must be on or after start date.")
                                else:
                                    update_task(task_id, {
                                        "workstream_id": int(ws_map[edit_ws]),
                                        "title": edit_title.strip(),
                                        "description": edit_desc.strip() or None,
                                        "start_date": edit_start, "end_date": edit_end,
                                        "status": edit_status,
                                        "percent_complete": int(st.session_state[f"edit_task_pct_num_{task_id}"]),
                                        "priority": edit_prio, "updated_by": current_email,
                                    })
                                    st.success("✅ Task updated!")
                                    st.rerun()
                        with col_delete:
                            if st.button("🗑️ Delete", use_container_width=True, key=f"btn_delete_task_{task_id}"):
                                delete_task(task_id)
                                st.success("✅ Task deleted!")
                                st.rerun()

        # ============================================================
        # ASSIGN RESOURCES
        # ============================================================
        with tab_assign:
            st.markdown("#### 👥 Assign Resources to Tasks")
            st.markdown("<div class='info-row'><strong>What's this for?</strong> Assign team members to specific tasks with their allocation percentage and estimated hours</div>", unsafe_allow_html=True)

            if tasks_df is None or tasks_df.empty:
                st.warning("⚠️ Create tasks first before assigning resources.")
            else:
                task_labels     = (tasks_df["workstream_name"] + " • " + tasks_df["title"]).tolist()
                task_pick       = st.selectbox("Select task", task_labels, key="assign_task_pick")
                task_idx        = task_labels.index(task_pick)
                selected_task_id = int(tasks_df.iloc[task_idx]["task_id"])

                resources_df = get_project_resources(project_id)

                if resources_df is None or resources_df.empty:
                    st.info("ℹ️ No project members found in the resource pool for this project.")
                else:
                    with st.expander("➕ Add Resource Assignment", expanded=True):
                        res_pick = st.selectbox("Resource", resources_df["full_name"].tolist(), key=f"assign_res_pick_{selected_task_id}")
                        res_id   = int(resources_df.loc[resources_df["full_name"] == res_pick, "resource_id"].iloc[0])

                        col1, col2 = st.columns(2)
                        with col1:
                            allocation_pct = st.number_input("Allocation %", min_value=1, max_value=100, value=100, step=5, key=f"assign_alloc_num_{selected_task_id}", help="What % of their time is allocated to this task?")
                        with col2:
                            planned_hours = st.number_input("Estimated hours (optional)", min_value=0.0, value=0.0, step=1.0, key=f"assign_hours_{selected_task_id}")

                        role_on_task = st.text_input("Role on task (optional)", key=f"assign_role_{selected_task_id}", placeholder="e.g., Lead Developer, QA Analyst")
                        notes        = st.text_area("Notes (optional)", key=f"assign_notes_{selected_task_id}")

                        if st.button("Add Assignment", use_container_width=True, key=f"btn_upsert_assign_{selected_task_id}"):
                            upsert_task_assignment(
                                task_id=selected_task_id, resource_id=res_id,
                                allocation_pct=int(allocation_pct),
                                planned_hours=float(planned_hours) if planned_hours and planned_hours > 0 else None,
                                role_on_task=role_on_task.strip() if role_on_task else None,
                                notes=notes.strip() if notes else None,
                                assignment_status="proposed",
                            )
                            st.success("✅ Resource assigned successfully!")
                            st.rerun()

                    existing = get_task_assignments(selected_task_id)
                    if existing is not None and not existing.empty:
                        st.markdown("<br/>", unsafe_allow_html=True)
                        st.markdown("##### Current Assignments")
                        st.dataframe(
                            existing[["full_name","allocation_pct","planned_hours","role_on_task","assignment_status"]].rename(
                                columns={"full_name":"Resource","allocation_pct":"Allocation %","planned_hours":"Hours","role_on_task":"Role","assignment_status":"Status"}
                            ),
                            use_container_width=True, hide_index=True, height=180,
                        )
                        with st.expander("🗑️ Remove Assignment"):
                            remove_name = st.selectbox("Select assignment to remove", existing["full_name"].tolist(), key=f"remove_assign_{selected_task_id}")
                            aid = int(existing.loc[existing["full_name"] == remove_name, "assignment_id"].iloc[0])
                            if st.button("Remove Assignment", use_container_width=True, key=f"btn_remove_assign_{selected_task_id}"):
                                delete_task_assignment(aid)
                                st.success("✅ Assignment removed!")
                                st.rerun()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.markdown("<div style='margin: 4rem 0 2rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()