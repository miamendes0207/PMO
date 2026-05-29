# ============================================================
# 30_🧭_Portfolio_Pipeline.py — ScopeSight v3.6 (UPDATED)
# Portfolio Pipeline Builder (Exec/CEO/Admin)
# Builder-style UX
# ============================================================

import datetime as dt
import streamlit as st
import pandas as pd
import plotly.express as px

from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

from modules.db import run_query
from modules.db import (
    get_pipeline_items,
    add_pipeline_item,
    update_pipeline_item,
    delete_pipeline_item,
)

# ---------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="🧭 Portfolio Pipeline",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

set_pmo_theme(page_title="🧭 Portfolio Pipeline")
render_sidebar()
hide_streamlit_nav()
require_login()

current_email = (st.session_state.get("email") or "").strip().lower()
current_role = (st.session_state.get("role") or "user").strip().lower()

if current_role not in ("exec", "ceo", "admin"):
    st.error("❌ You do not have access to the Portfolio Pipeline page.")
    pmo_footer()
    st.stop()

# ============================================================
# Department colour mapping
# ============================================================
# Base hue per department (H, S%, L% in HSL)
DEPT_BASE_HSL = {
    "Fraud":                     (220, 90, 50),   # Blue
    "Advisory & Transformation": (0,   80, 45),   # Red
    "Tech & Data":               (142, 70, 35),   # Green
    "Other":                     (24,  90, 45),   # Orange
}

# Canonical display colour (midpoint shade) for legend swatches only
DEPT_SWATCH_COLOUR = {
    "Fraud":                     "#2563eb",
    "Advisory & Transformation": "#dc2626",
    "Tech & Data":               "#16a34a",
    "Other":                     "#ea580c",
}

# Which raw service_line values map to each bucket
DEPT_ALIASES = {
    "Fraud":                     ["fraud"],
    "Advisory & Transformation": ["advisory", "advisory & transformation", "transformation", "change", "strategy", "pmo", "operations", "risk", "risk & compliance"],
    "Tech & Data":               ["tech", "tech & data", "technology", "data", "data & analytics"],
}

def _to_dept(service_line: str) -> str:
    """Map a raw service_line string to one of the four department buckets."""
    sl = (service_line or "").strip().lower()
    for dept, aliases in DEPT_ALIASES.items():
        if sl in aliases or any(sl.startswith(a) for a in aliases):
            return dept
    return "Other"

def _hsl_to_hex(h: int, s: int, l: int) -> str:
    """Convert HSL (0-360, 0-100, 0-100) to a #rrggbb hex string."""
    s /= 100
    l /= 100
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if   h < 60:  r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    r, g, b = (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))
    return f"#{r:02x}{g:02x}{b:02x}"

def _build_item_colour_map(items: list) -> dict:
    """
    Given a list of (item_label, dept) tuples, assign each item a distinct
    shade within its department's hue family.

    Shades are spread across L=30..65 (dark to light) so they stay clearly
    within the department hue while remaining individually distinguishable.
    """
    from collections import defaultdict
    dept_items = defaultdict(list)
    for label, dept in items:
        dept_items[dept].append(label)

    colour_map = {}
    for dept, labels in dept_items.items():
        h, s, base_l = DEPT_BASE_HSL.get(dept, (0, 0, 50))
        n = len(labels)
        if n == 1:
            lightnesses = [base_l]
        else:
            lo, hi = 30, 65
            step = (hi - lo) / (n - 1)
            lightnesses = [int(lo + i * step) for i in range(n)]

        for label, l in zip(labels, lightnesses):
            colour_map[label] = _hsl_to_hex(h, s, l)

    return colour_map

# ============================================================
# Styles
# ============================================================
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

.nfr-card {
    background: white;
    border: 2px solid #4facfe;
    padding: 1.5rem;
    border-radius: 12px;
    margin: 1.25rem 0;
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.15);
}

.info-row {
    background: #f0f9ff;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border-radius: 6px;
    border-left: 4px solid #4facfe;
}
.info-row strong { color: #0077be; }

.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1rem 0 1rem 0;
}
.section-header h3 {
    color: white;
    margin: 0;
    font-size: 1.2rem;
    font-weight: 700;
}

.step-header {
    margin: 1.5rem 0 1rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e5e7eb;
}
.step-header h4 {
    color: #1f2937;
    margin: 0;
    font-size: 1.15rem;
    font-weight: 700;
}

.metric-card {
    background: #f0f9ff;
    border: 2px solid #bae6fd;
    border-radius: 10px;
    padding: 1.25rem;
    text-align: center;
    margin: 0.5rem 0;
}

.metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #0077be;
    margin: 0.5rem 0;
}

.metric-label {
    color: #0369a1;
    font-size: 0.9rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Dept legend swatches */
.dept-legend {
    display: flex;
    gap: 1.5rem;
    align-items: center;
    flex-wrap: wrap;
    margin: 0.75rem 0 1.25rem 0;
}
.dept-swatch {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: #334155;
}
.swatch-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
}

div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.05rem;
    font-weight: 700;
    padding: 0.65rem 1.5rem;
    border: none;
    border-radius: 8px;
    transition: all 0.2s ease;
}
div.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 12px rgba(79, 172, 254, 0.35);
}

[data-testid="stDataFrame"] div[role="grid"] { font-size: 0.88rem; }
.block-container { padding-top: 1.5rem; }
.small-muted { color: #6b7280; font-size: 0.9rem; }
label { font-weight: 600 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# Helpers
# ============================================================
STAGES = ["discovery", "proposal", "negotiation", "won", "lost", "parked"]
STATUSES = ["open", "won", "lost", "parked"]


def _safe_date(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, dt.date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def _clamp_int(v, lo=0, hi=100, default=50):
    try:
        v = int(v)
    except Exception:
        v = default
    return max(lo, min(hi, v))


def _label_row(r) -> str:
    client = (r.get("client_name") or "").strip()
    nm = (r.get("item_name") or "").strip()
    return f"{client} • {nm}" if client else nm


def render_pipeline_timeline(df: pd.DataFrame):
    """
    Timeline plotting logic with explicit department colour mapping:
      Fraud = Blue (#2563eb)
      Advisory & Transformation = Red (#dc2626)
      Tech & Data = Green (#16a34a)
      Other = Orange (#ea580c)
    """
    if df is None or df.empty:
        st.info("ℹ️ No pipeline items found in this date range.")
        return

    d = df.copy()

    # Coerce all date-like columns
    for col in [
        "start_date", "end_date", "target_close_date",
        "est_start_date", "est_end_date", "proposal_deadline",
    ]:
        if col in d.columns:
            d[col] = pd.to_datetime(d[col], errors="coerce")

    # Plotting dates (prefer estimated)
    d["PlotStart"] = None
    d["PlotFinish"] = None

    if "est_start_date" in d.columns:
        d["PlotStart"] = d["est_start_date"]
    if "start_date" in d.columns:
        d["PlotStart"] = d["PlotStart"].fillna(d["start_date"])
    if "target_close_date" in d.columns:
        d["PlotStart"] = d["PlotStart"].fillna(d["target_close_date"])

    if "est_end_date" in d.columns:
        d["PlotFinish"] = d["est_end_date"]
    if "end_date" in d.columns:
        d["PlotFinish"] = d["PlotFinish"].fillna(d["end_date"])

    d["PlotFinish"] = d["PlotFinish"].fillna(d["PlotStart"] + pd.Timedelta(days=1))

    d = d[d["PlotStart"].notna()].copy()
    if d.empty:
        st.info("ℹ️ Nothing has dates to plot yet.")
        return

    inv = d["PlotFinish"] < d["PlotStart"]
    if inv.any():
        tmp = d.loc[inv, "PlotStart"].copy()
        d.loc[inv, "PlotStart"] = d.loc[inv, "PlotFinish"]
        d.loc[inv, "PlotFinish"] = tmp

    # Map service_line → department bucket, then build per-item shade map
    raw_sl = d.get("service_line", pd.Series([""] * len(d)))
    d["Department"] = raw_sl.fillna("").astype(str).apply(_to_dept)

    d["Item"] = d.apply(_label_row, axis=1)

    # Build colour map: each item gets its own shade within its dept hue family
    item_colour_map = _build_item_colour_map(
        list(zip(d["Item"].tolist(), d["Department"].tolist()))
    )

    hover_map = {
        "client_name": True,
        "item_name": True,
        "service_line": True,
        "Department": True,
        "stage": True,
        "probability": True,
        "est_value": True,
        "PlotStart": True,
        "PlotFinish": True,
    }
    for extra in [
        "proposal_deadline", "est_start_date", "est_end_date",
        "start_date", "end_date", "target_close_date", "owner_email", "status",
    ]:
        if extra in d.columns:
            hover_map[extra] = True

    fig = px.timeline(
        d.sort_values(["Department", "PlotStart"]),
        x_start="PlotStart",
        x_end="PlotFinish",
        y="Item",
        color="Item",
        color_discrete_map=item_colour_map,
        hover_data=hover_map,
    )
    fig.update_yaxes(autorange="reversed", title=None)
    # Hide the per-item legend (too noisy) — dept legend swatches shown above chart instead
    fig.update_layout(
        height=max(520, 220 + 24 * len(d)),
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# STEP 1: Time window + filters
# ============================================================
st.markdown(
    """
<div class='step-header'>
    <h4>📁 Select Your Window</h4>
</div>
""",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    w_start = st.date_input("Window starts", value=dt.date.today() - dt.timedelta(days=90), key="pipe_w_start")
with c2:
    w_end = st.date_input("Window ends", value=dt.date.today() + dt.timedelta(days=180), key="pipe_w_end")
with c3:
    stage_filter = st.multiselect("Stage filter", STAGES, default=STAGES, key="pipe_stage_filter")

if w_end < w_start:
    st.error("❌ End date must be on or after start date.")
    pmo_footer()
    st.stop()

df = get_pipeline_items(start=str(w_start), end=str(w_end))
if df is None:
    df = pd.DataFrame()

if not isinstance(df, pd.DataFrame) or df.empty:
    df = pd.DataFrame()

if "stage" not in df.columns:
    df["stage"] = ""
else:
    df["stage"] = df["stage"].fillna("").astype(str).str.lower()

# ============================================================
# STEP 2: Snapshot metrics
# ============================================================
st.markdown(
    """
<div class='step-header'>
    <h4>📊 Current Snapshot</h4>
</div>
""",
    unsafe_allow_html=True,
)

count_items = int(len(df)) if not df.empty else 0
total_value = float(df["est_value"].fillna(0).sum()) if ("est_value" in df.columns and not df.empty) else 0.0

weighted_value = 0.0
if not df.empty and "est_value" in df.columns and "probability" in df.columns:
    weighted_value = float((df["est_value"].fillna(0) * (df["probability"].fillna(0) / 100.0)).sum())

avg_prob = int(df["probability"].fillna(0).mean()) if ("probability" in df.columns and not df.empty) else 0

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Pipeline Items</div><div class='metric-value'>{count_items}</div></div>",
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Avg Probability</div><div class='metric-value'>{avg_prob}%</div></div>",
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Total Value</div><div class='metric-value'>{total_value:,.0f}</div></div>",
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Weighted Value</div><div class='metric-value'>{weighted_value:,.0f}</div></div>",
        unsafe_allow_html=True,
    )

# ============================================================
# Tabs
# ============================================================
tab_tl, tab_table, tab_manage = st.tabs(["📅 Timeline", "📋 Overview", "🛠️ Manage Pipeline"])

with tab_tl:
    st.markdown("##### 📅 Timeline Visualization")
    st.caption("Timeline plots **estimated delivery dates** first, then falls back to start/end/close. Bars are coloured by department.")

    # Department legend swatches (base shades for reference)
    swatches = "".join([
        f"<div class='dept-swatch'>"
        f"<div class='swatch-dot' style='background:{colour}'></div>"
        f"{dept}</div>"
        for dept, colour in DEPT_SWATCH_COLOUR.items()
    ])
    st.markdown(f"<div class='dept-legend'>{swatches}</div>", unsafe_allow_html=True)

    render_pipeline_timeline(df)

with tab_table:
    st.markdown("##### 📋 Pipeline Overview")
    if df.empty:
        st.info("ℹ️ No items found.")
    else:
        view_cols = [
            "client_name", "item_name", "service_line", "stage", "probability",
            "est_value", "proposal_deadline",
            "est_start_date", "est_end_date",
            "start_date", "end_date", "target_close_date",
            "owner_email", "status",
        ]
        view_cols = [c for c in view_cols if c in df.columns]
        st.dataframe(df[view_cols], use_container_width=True, hide_index=True, height=320)

with tab_manage:
    st.markdown("#### 🛠️ Build & Manage Your Pipeline")

    st.markdown(
        """
        <div class='info-row'>
            <strong>How this works:</strong> Add pipeline items (opportunities/initiatives),
            track stage, probability and value, and visualize the window on a timeline.
            <br/><span class='small-muted'>New: Proposal deadline + Estimated delivery start/end dates.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    clients = run_query(
        """
        SELECT id AS client_id, client_name
        FROM public.client_scaffold
        WHERE status = 'approved'
        ORDER BY client_name
        """
    )
    clients = clients if clients is not None else pd.DataFrame(columns=["client_id", "client_name"])

    # CREATE
    with st.expander("➕ Add New Pipeline Item", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            if not clients.empty:
                client_pick = st.selectbox("Client", options=clients["client_name"].tolist(), key="pipe_new_client")
                client_row = clients[clients["client_name"] == client_pick].iloc[0]
                new_client_id = int(client_row["client_id"])
                new_client_name = str(client_row["client_name"])
            else:
                new_client_id = None
                new_client_name = st.text_input("Client name", key="pipe_new_client_text")
        with c2:
            new_service_line = st.selectbox(
                "Service line / Department",
                ["Fraud", "Advisory & Transformation", "Tech & Data", "Other"],
                key="pipe_new_sl",
            )

        new_item_name = st.text_input("Item name", key="pipe_new_name", placeholder="e.g., Retail Fraud Analytics Programme")
        new_stage = st.selectbox("Stage", STAGES, index=0, key="pipe_new_stage")

        c3, c4, c5 = st.columns(3)
        with c3:
            new_prob = st.number_input("Probability %", min_value=0, max_value=100, value=50, step=5, key="pipe_new_prob")
        with c4:
            new_value = st.number_input("Estimated value", min_value=0.0, value=0.0, step=1000.0, key="pipe_new_value")
        with c5:
            new_status = st.selectbox("Status", STATUSES, index=0, key="pipe_new_status")

        d1, d2, d3 = st.columns(3)
        with d1:
            new_start = st.date_input("Start date (optional)", value=None, key="pipe_new_start")
        with d2:
            new_end = st.date_input("End date (optional)", value=None, key="pipe_new_end")
        with d3:
            new_close = st.date_input("Target close date (optional)", value=None, key="pipe_new_close")

        d4, d5, d6 = st.columns(3)
        with d4:
            new_prop_deadline = st.date_input("Proposal / bid deadline (optional)", value=None, key="pipe_new_prop_deadline")
        with d5:
            new_est_start = st.date_input("Estimated start (delivery)", value=None, key="pipe_new_est_start")
        with d6:
            new_est_end = st.date_input("Estimated end (delivery)", value=None, key="pipe_new_est_end")

        new_owner = st.text_input("Owner email (optional)", value=current_email, key="pipe_new_owner")
        new_notes = st.text_area("Notes (optional)", key="pipe_new_notes")

        if st.button("Create Pipeline Item", use_container_width=True, key="btn_pipe_create"):
            if not (new_item_name or "").strip():
                st.error("❌ Item name is required.")
            elif new_end and new_start and new_end < new_start:
                st.error("❌ End date must be on or after start date.")
            elif new_est_end and new_est_start and new_est_end < new_est_start:
                st.error("❌ Estimated end must be on or after estimated start.")
            else:
                add_pipeline_item(
                    {
                        "client_id": new_client_id,
                        "client_name": (new_client_name or "").strip() or None,
                        "item_name": new_item_name.strip(),
                        "service_line": (new_service_line or "").strip() or None,
                        "stage": new_stage,
                        "probability": _clamp_int(new_prob, 0, 100, 50),
                        "est_value": float(new_value) if new_value and new_value > 0 else None,
                        "start_date": new_start,
                        "end_date": new_end,
                        "target_close_date": new_close,
                        "proposal_deadline": new_prop_deadline,
                        "est_start_date": new_est_start,
                        "est_end_date": new_est_end,
                        "owner_email": (new_owner or "").strip() or None,
                        "status": new_status,
                        "notes": (new_notes or "").strip() or None,
                    }
                )
                st.success("✅ Pipeline item created!")
                st.rerun()

    # Edit / Delete
    st.markdown("<br/>", unsafe_allow_html=True)
    if df.empty:
        st.info("ℹ️ No pipeline items in this window yet.")
    else:
        st.markdown("##### Existing Pipeline Items")
        labels = df.apply(
            lambda r: f"{(r.get('client_name') or '').strip()} • {r.get('item_name')}  #{int(r.get('pipeline_id'))}",
            axis=1,
        ).tolist()

        with st.expander("✏️ Edit or Delete Pipeline Item", expanded=False):
            pick = st.selectbox("Select item", options=labels, key="pipe_edit_pick")
            idx = labels.index(pick)
            row = df.iloc[idx]
            pid = int(row["pipeline_id"])

            cur_client_name = (row.get("client_name") or "").strip()
            cur_item = (row.get("item_name") or "").strip()
            cur_sl = (row.get("service_line") or "").strip()
            cur_stage = (row.get("stage") or "discovery").strip().lower()
            cur_prob = _clamp_int(row.get("probability"), 0, 100, 50)
            cur_val = float(row.get("est_value") or 0)
            cur_status = (row.get("status") or "open").strip().lower()

            # Map existing raw value → canonical dept bucket for the selectbox default
            DEPT_OPTIONS = list(DEPT_SWATCH_COLOUR.keys())
            cur_dept = _to_dept(cur_sl)
            cur_dept_idx = DEPT_OPTIONS.index(cur_dept) if cur_dept in DEPT_OPTIONS else 3

            e1, e2 = st.columns(2)
            with e1:
                edit_client_name = st.text_input("Client name", value=cur_client_name, key=f"pipe_edit_client_{pid}")
            with e2:
                edit_service_line = st.selectbox(
                    "Service line / Department",
                    DEPT_OPTIONS,
                    index=cur_dept_idx,
                    key=f"pipe_edit_sl_{pid}",
                )

            edit_item_name = st.text_input("Item name", value=cur_item, key=f"pipe_edit_name_{pid}")
            edit_stage = st.selectbox(
                "Stage",
                STAGES,
                index=STAGES.index(cur_stage) if cur_stage in STAGES else 0,
                key=f"pipe_edit_stage_{pid}",
            )

            f1, f2, f3 = st.columns(3)
            with f1:
                edit_prob = st.number_input("Probability %", 0, 100, value=int(cur_prob), step=5, key=f"pipe_edit_prob_{pid}")
            with f2:
                edit_value = st.number_input("Estimated value", min_value=0.0, value=float(cur_val), step=1000.0, key=f"pipe_edit_val_{pid}")
            with f3:
                edit_status = st.selectbox(
                    "Status",
                    STATUSES,
                    index=STATUSES.index(cur_status) if cur_status in STATUSES else 0,
                    key=f"pipe_edit_status_{pid}",
                )

            g1, g2, g3 = st.columns(3)
            with g1:
                edit_start = st.date_input("Start date", value=_safe_date(row.get("start_date")), key=f"pipe_edit_start_{pid}")
            with g2:
                edit_end = st.date_input("End date", value=_safe_date(row.get("end_date")), key=f"pipe_edit_end_{pid}")
            with g3:
                edit_close = st.date_input("Target close date", value=_safe_date(row.get("target_close_date")), key=f"pipe_edit_close_{pid}")

            h1, h2, h3 = st.columns(3)
            with h1:
                edit_prop_deadline = st.date_input(
                    "Proposal / bid deadline",
                    value=_safe_date(row.get("proposal_deadline")),
                    key=f"pipe_edit_prop_deadline_{pid}",
                )
            with h2:
                edit_est_start = st.date_input(
                    "Estimated start (delivery)",
                    value=_safe_date(row.get("est_start_date")),
                    key=f"pipe_edit_est_start_{pid}",
                )
            with h3:
                edit_est_end = st.date_input(
                    "Estimated end (delivery)",
                    value=_safe_date(row.get("est_end_date")),
                    key=f"pipe_edit_est_end_{pid}",
                )

            edit_owner = st.text_input("Owner email", value=(row.get("owner_email") or "").strip(), key=f"pipe_edit_owner_{pid}")
            edit_notes = st.text_area("Notes", value=(row.get("notes") or ""), key=f"pipe_edit_notes_{pid}")

            csave, cdel = st.columns(2)
            with csave:
                if st.button("💾 Save Changes", use_container_width=True, key=f"btn_pipe_save_{pid}"):
                    if not (edit_item_name or "").strip():
                        st.error("❌ Item name is required.")
                    elif edit_end and edit_start and edit_end < edit_start:
                        st.error("❌ End date must be on or after start date.")
                    elif edit_est_end and edit_est_start and edit_est_end < edit_est_start:
                        st.error("❌ Estimated end must be on or after estimated start.")
                    else:
                        update_pipeline_item(
                            pid,
                            {
                                "client_id": None,
                                "client_name": (edit_client_name or "").strip() or None,
                                "item_name": edit_item_name.strip(),
                                "service_line": (edit_service_line or "").strip() or None,
                                "stage": edit_stage,
                                "probability": _clamp_int(edit_prob, 0, 100, 50),
                                "est_value": float(edit_value) if edit_value and edit_value > 0 else None,
                                "start_date": edit_start,
                                "end_date": edit_end,
                                "target_close_date": edit_close,
                                "proposal_deadline": edit_prop_deadline,
                                "est_start_date": edit_est_start,
                                "est_end_date": edit_est_end,
                                "owner_email": (edit_owner or "").strip() or None,
                                "status": edit_status,
                                "notes": (edit_notes or "").strip() or None,
                            },
                        )
                        st.success("✅ Pipeline item updated!")
                        st.rerun()

            with cdel:
                if st.button("🗑️ Delete", use_container_width=True, key=f"btn_pipe_del_{pid}"):
                    delete_pipeline_item(pid)
                    st.success("✅ Pipeline item deleted!")
                    st.rerun()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.markdown("<div style='margin: 4rem 0 2rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()