# ============================================================
# 31_Capacity_Manager.py — ScopeSight v3.6
# Capacity Management (All-clients + filter-down)
# ============================================================

import datetime as dt
import re

import pandas as pd
import streamlit as st

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="🔋 Capacity Management",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# INIT
# ============================================================
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🔋 Capacity Management")
render_sidebar()

TODAY = dt.date.today()
role = st.session_state.get("role", "user")
email = (st.session_state.get("email") or "").strip().lower()

# ============================================================
# STYLES
# ============================================================
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Cards / headers */
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

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0;
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

.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 12px;
    border: 2px solid #e0f2fe;
    background: white;
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
label { font-weight: 600 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# HELPERS
# ============================================================
def _as_date(x):
    if x is None or pd.isna(x):
        return None
    if isinstance(x, dt.date):
        return x
    return pd.to_datetime(x).date()


def _overlap_days(a_start, a_end, r_start, r_end):
    """Inclusive overlap days between [a_start, a_end] and [r_start, r_end]. a_end can be None -> treat as r_end."""
    if a_start is None:
        return 0
    a_start = _as_date(a_start)
    a_end = _as_date(a_end) or r_end
    r_start = _as_date(r_start)
    r_end = _as_date(r_end)

    if a_start is None or r_start is None or r_end is None:
        return 0

    start = max(a_start, r_start)
    end = min(a_end, r_end)
    if end < start:
        return 0
    return (end - start).days + 1


def table_exists(table_name: str) -> bool:
    df = run_query(
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=:t
        LIMIT 1
        """,
        {"t": table_name},
    )
    return df is not None and not df.empty


def _clean_skill_label(name: str) -> str:
    if name is None:
        return ""
    s = str(name).strip()
    s = re.sub(r"^\s*\d+\s*[-.)]\s*", "", s)
    s = re.sub(r"^\s*\d+\s+", "", s)
    return s.strip()


def _clean_skill_list_str(skill_csv: str) -> str:
    if not skill_csv:
        return ""
    parts = [p.strip() for p in str(skill_csv).split(",") if p.strip()]
    cleaned = {_clean_skill_label(p) for p in parts if _clean_skill_label(p)}
    return ", ".join(sorted(cleaned))


HAS_SKILLS = table_exists("skills") and table_exists("resource_skills")


def load_skills_with_display() -> pd.DataFrame:
    if not HAS_SKILLS:
        return pd.DataFrame(columns=["skill_name", "display_name"])

    df = run_query("SELECT skill_name FROM public.skills ORDER BY skill_name")
    if df is None or df.empty:
        return pd.DataFrame(columns=["skill_name", "display_name"])

    out = df.copy()
    out["skill_name"] = out["skill_name"].astype(str)
    out["display_name"] = out["skill_name"].apply(_clean_skill_label)

    dup = out["display_name"].duplicated(keep=False)
    out.loc[dup, "display_name"] = out.loc[dup].apply(
        lambda r: f"{r['display_name']} ({r['skill_name']})",
        axis=1,
    )

    return out.sort_values("display_name", kind="stable").reset_index(drop=True)


SKILLS_DF = load_skills_with_display()


def _band_factory(over_threshold=100, near_threshold=80, under_threshold=60):
    def _band(x):
        if x > over_threshold:
            return "🔴 Over"
        if x >= near_threshold:
            return "🟠 Near cap"
        if x < under_threshold:
            return "🟡 Under"
        return "🟢 OK"

    return _band


def _style_row(row):
    s = row.get("status", "")
    if "🔴" in s:
        return ["background-color: rgba(255,0,0,0.08)"] * len(row)
    if "🟠" in s:
        return ["background-color: rgba(255,165,0,0.10)"] * len(row)
    if "🟡" in s:
        return ["background-color: rgba(255,255,0,0.10)"] * len(row)
    return [""] * len(row)


# ============================================================
# DATA: ACCESSIBLE CLIENTS
# ============================================================
def load_accessible_clients():
    if role == "admin":
        df = run_query(
            """
            SELECT id, client_name
            FROM public.client_scaffold
            ORDER BY client_name
            """
        )
    else:
        df = run_query(
            """
            SELECT c.id, c.client_name
            FROM public.user_client_permissions u
            JOIN public.client_scaffold c ON c.id = u.client_id
            WHERE LOWER(u.user_email) = :email
            ORDER BY c.client_name
            """,
            {"email": email},
        )
    return df


clients = load_accessible_clients()

if clients is None or clients.empty:
    if role == "admin":
        st.error("❌ No clients exist in the system yet.")
    else:
        st.warning(
            "⚠️ You are not assigned to any clients. If this is unexpected, "
            "ask an administrator to assign you to a client."
        )
    pmo_footer()
    st.stop()

client_map = dict(zip(clients.client_name, clients.id))
client_names = clients.client_name.tolist()
all_client_ids = [int(client_map[n]) for n in client_names]


# ============================================================
# UI: PAGE INTRO
# ============================================================
st.markdown(
    """
<div class='info-box'>
  <strong style='color:#48bb78;'>💡 How to Use</strong><br/>
  Use <b>Snapshot</b> for a quick current-month view across all accessible clients.
  Use <b>Filter & Analyze</b> for custom ranges, client/project drill-down, and skills filtering.
</div>
""",
    unsafe_allow_html=True,
)

tab_snapshot, tab_analysis = st.tabs(["📊 Snapshot", "🔍 Filter & Analyze"])


# ============================================================
# TAB 1: SNAPSHOT
# ============================================================
with tab_snapshot:
    # Default to current month-to-date
    snapshot_start = TODAY.replace(day=1)
    snapshot_end = TODAY
    snapshot_days = (snapshot_end - snapshot_start).days + 1

    snapshot_allocs = run_query(
        """
        SELECT
            ra.allocation_id,
            ra.client_id,
            cs.client_name,
            ra.resource_id,
            rp.full_name,
            rp.department,
            rp.role,
            ra.project_id,
            p.project_name,
            ra.allocation_pct,
            ra.start_date,
            ra.end_date
        FROM public.resource_allocation ra
        JOIN public.resource_pool rp ON rp.resource_id = ra.resource_id
        JOIN public.projects p ON p.project_id = ra.project_id
        JOIN public.client_scaffold cs ON cs.id = ra.client_id
        WHERE ra.client_id = ANY(CAST(:cids AS int[]))
          AND ra.start_date <= :range_end
          AND (ra.end_date IS NULL OR ra.end_date >= :range_start)
          AND rp.is_active = TRUE
        ORDER BY cs.client_name, rp.full_name, p.project_name
        """,
        {"cids": all_client_ids, "range_start": snapshot_start, "range_end": snapshot_end},
    )

    st.markdown(
        """
        <div class='step-header'>
            <h4>📊 Current Snapshot</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class='info-row'>
            <strong>Period:</strong> {snapshot_start.strftime('%b %d, %Y')} to {snapshot_end.strftime('%b %d, %Y')} ({snapshot_days} days)
            &nbsp;•&nbsp;
            <strong>Scope:</strong> All {len(client_names)} accessible client(s)
            &nbsp;•&nbsp;
            <strong>Resources:</strong> Active only
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>📊 Status Legend</strong><br/>
            🔴 <b>Over</b> (>100%) — Resource needs immediate attention
            &nbsp;•&nbsp;
            🟠 <b>Near cap</b> (80-100%) — Nearly at full capacity
            &nbsp;•&nbsp;
            🟡 <b>Under</b> (<60%) — Available capacity
            &nbsp;•&nbsp;
            🟢 <b>OK</b> (60-80%) — Healthy balance
        </div>
        """,
        unsafe_allow_html=True,
    )

    if snapshot_allocs is None or snapshot_allocs.empty:
        st.info("ℹ️ No allocations found for current month snapshot.")
    else:
        snap_df = snapshot_allocs.copy()
        snap_df["start_date"] = snap_df["start_date"].apply(_as_date)
        snap_df["end_date"] = snap_df["end_date"].apply(_as_date)

        snap_df["overlap_days"] = snap_df.apply(
            lambda r: _overlap_days(r["start_date"], r["end_date"], snapshot_start, snapshot_end),
            axis=1,
        )
        snap_df["effective_pct"] = snap_df.apply(
            lambda r: float(r["allocation_pct"]) * (float(r["overlap_days"]) / float(snapshot_days))
            if snapshot_days > 0
            else 0.0,
            axis=1,
        )

        _band = _band_factory()

        snap_summary = (
            snap_df.groupby(["resource_id", "full_name", "department", "role"], dropna=False)
            .agg(
                total_alloc_pct=("effective_pct", "sum"),
                projects=("project_id", pd.Series.nunique),
                allocations=("allocation_id", "count"),
            )
            .reset_index()
        )

        snap_summary["status"] = snap_summary["total_alloc_pct"].apply(_band)
        snap_summary["total_alloc_pct"] = snap_summary["total_alloc_pct"].round(1)

        # Strong skills (rating >= 4)
        if HAS_SKILLS:
            ids = snap_summary["resource_id"].astype(int).unique().tolist()
            ids_sql = f"({','.join(str(i) for i in ids)})" if ids else "(-1)"

            strong = run_query(
                f"""
                SELECT
                    rs.resource_id,
                    STRING_AGG(s.skill_name, ', ' ORDER BY s.skill_name) AS strong_skills
                FROM public.resource_skills rs
                JOIN public.skills s ON s.skill_id = rs.skill_id
                WHERE rs.resource_id IN {ids_sql}
                  AND rs.rating >= 4
                GROUP BY rs.resource_id
                """
            )

            if strong is not None and not strong.empty:
                snap_summary = snap_summary.merge(strong, on="resource_id", how="left")
            else:
                snap_summary["strong_skills"] = ""

            snap_summary["strong_skills"] = (
                snap_summary["strong_skills"].fillna("").astype(str).apply(_clean_skill_list_str)
            )

        # Metrics
        over_threshold = 100
        under_threshold = 60

        total_resources = snap_summary["resource_id"].nunique()
        over_allocated = (snap_summary["total_alloc_pct"] > over_threshold).sum()
        under_utilized = (snap_summary["total_alloc_pct"] < under_threshold).sum()
        avg_allocation = snap_summary["total_alloc_pct"].mean()

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-label'>Total Resources</div>
                    <div class='metric-value'>{total_resources}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-label'>Over-Allocated</div>
                    <div class='metric-value' style='color: #dc2626;'>{over_allocated}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-label'>Under-Utilized</div>
                    <div class='metric-value' style='color: #ea580c;'>{under_utilized}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m4:
            st.markdown(
                f"""
                <div class='metric-card'>
                    <div class='metric-label'>Avg Allocation</div>
                    <div class='metric-value'>{avg_allocation:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Table
        snap_display = snap_summary.rename(
            columns={
                "full_name": "resource",
                "total_alloc_pct": "allocated_%",
                "projects": "#projects",
                "allocations": "#allocations",
            }
        )

        cols = ["resource", "department", "role"]
        if HAS_SKILLS and "strong_skills" in snap_display.columns:
            cols.append("strong_skills")
        cols += ["allocated_%", "status", "#projects", "#allocations"]

        snap_display = snap_display[cols].copy()

        st.dataframe(
            snap_display.style.apply(_style_row, axis=1),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# TAB 2: FILTER & ANALYZE
# ============================================================
with tab_analysis:
    st.markdown(
        """
        <div class='step-header'>
            <h4>🔍 Filter & Analyze</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>💡 Customize Your View</strong><br/>
            Use these controls to analyze specific time periods, clients, projects, or skills.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------
    # STEP 1: CLIENT SCOPE
    # -------------------------------
    st.markdown("##### 🌍 Client Scope")

    scope_mode = st.radio(
        "View scope",
        ["All accessible clients", "Filter to specific clients"],
        horizontal=True,
        key="cap_scope_mode",
    )

    if scope_mode == "All accessible clients":
        selected_clients = client_names[:]
    else:
        selected_clients = st.multiselect(
            "Select clients",
            options=client_names,
            default=client_names[:1] if client_names else [],
            key="cap_page_clients_multi",
        )

    selected_client_ids = [int(client_map[n]) for n in selected_clients]
    if not selected_client_ids:
        st.warning("⚠️ Please select at least one client to continue.")
        pmo_footer()
        st.stop()

    # -------------------------------
    # STEP 2: DATE RANGE & SETTINGS
    # -------------------------------
    st.markdown("##### 📅 Date Range & Settings")

    f1, f2, f3, f4, f5 = st.columns([1, 1, 1.3, 1, 1.2])

    with f1:
        range_start = st.date_input(
            "Range start",
            value=TODAY.replace(day=1),
            key="cap_page_range_start",
        )
    with f2:
        range_end = st.date_input(
            "Range end",
            value=TODAY,
            key="cap_page_range_end",
        )
    with f3:
        mode = st.selectbox(
            "Allocation calculation",
            ["Pro-rated by overlap (recommended)", "Simple sum (any overlap counts)"],
            key="cap_page_mode",
        )
    with f4:
        only_active = st.checkbox(
            "Active resources only",
            value=True,
            key="cap_page_active_only",
        )
    with f5:
        split_by_client = st.checkbox(
            "Show client breakdown",
            value=False,
            key="cap_page_split_by_client",
            help="If enabled, shows one row per resource per client.",
        )

    if range_end < range_start:
        st.error("❌ Range end must be on/after range start.")
        pmo_footer()
        st.stop()

    days_in_range = (range_end - range_start).days + 1

    # -------------------------------
    # STEP 3: OPTIONAL FILTERS
    # -------------------------------
    st.markdown("##### 🔽 Additional Filters (Optional)")

    selected_skill_name = None
    min_skill_rating = 3
    apply_skill_filter = False

    if HAS_SKILLS and SKILLS_DF is not None and not SKILLS_DF.empty:
        with st.expander("🧠 Filter by Skills Matrix", expanded=False):

            left, right = st.columns([2, 1])

            with left:
                skill_search = st.text_input(
                    "Search skills",
                    value="",
                    placeholder="Type to filter skills (e.g. 'Power BI', 'PMO', 'Python')",
                    key="cap_skill_search",
                )

            with right:
                min_skill_rating = st.select_slider(
                    "Min rating",
                    options=[0, 1, 2, 3, 4, 5],
                    value=3,
                    key="cap_page_skill_min_alt",
                )

            # searchable list
            skills_view = SKILLS_DF.copy()
            if skill_search.strip():
                skills_view = skills_view[
                    skills_view["display_name"].str.contains(skill_search.strip(), case=False, na=False)
                ]

            # selectable table (checkbox)
            if "select" not in skills_view.columns:
                skills_view.insert(0, "select", False)

            edited = st.data_editor(
                skills_view[["select", "display_name"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "select": st.column_config.CheckboxColumn("Select"),
                    "display_name": st.column_config.TextColumn("Skill"),
                },
                disabled=["display_name"],
                key="cap_skill_picker_table",
            )

            picked = edited[edited["select"] == True]  # noqa: E712
            if len(picked) > 1:
                st.warning("Pick 1 skill (for now). Untick extras.")
            elif len(picked) == 1:
                picked_display = picked.iloc[0]["display_name"]
                match = SKILLS_DF[SKILLS_DF["display_name"] == picked_display]
                if not match.empty:
                    selected_skill_name = match.iloc[0]["skill_name"]

            apply_skill_filter = st.checkbox(
                "Apply skill filter",
                value=False,
                key="cap_page_skill_apply_alt",
            )

    # -------------------------------
    # LOAD ALLOCATIONS IN RANGE
    # -------------------------------
    allocs_range = run_query(
        """
        SELECT
            ra.allocation_id,
            ra.client_id,
            cs.client_name,
            ra.resource_id,
            rp.full_name,
            rp.department,
            rp.role,
            ra.project_id,
            p.project_name,
            ra.allocation_pct,
            ra.start_date,
            ra.end_date
        FROM public.resource_allocation ra
        JOIN public.resource_pool rp ON rp.resource_id = ra.resource_id
        JOIN public.projects p ON p.project_id = ra.project_id
        JOIN public.client_scaffold cs ON cs.id = ra.client_id
        WHERE ra.client_id = ANY(CAST(:cids AS int[]))
          AND ra.start_date <= :range_end
          AND (ra.end_date IS NULL OR ra.end_date >= :range_start)
          AND (:active_only = FALSE OR rp.is_active = TRUE)
        ORDER BY cs.client_name, rp.full_name, p.project_name
        """,
        {"cids": selected_client_ids, "range_start": range_start, "range_end": range_end, "active_only": bool(only_active)},
    )

    if allocs_range is None or allocs_range.empty:
        st.info("ℹ️ No allocations overlap the selected date range.")
        pmo_footer()
        st.stop()

    df = allocs_range.copy()
    df["start_date"] = df["start_date"].apply(_as_date)
    df["end_date"] = df["end_date"].apply(_as_date)

    # -------------------------------
    # NARROW DOWN RESULTS
    # -------------------------------
    with st.expander("🔍 Narrow Down Results", expanded=False):
        fA, fB, fC = st.columns([1.2, 1.4, 1.4])

        with fA:
            client_filter = st.selectbox(
                "Client",
                options=["(All selected clients)"] + sorted(df["client_name"].dropna().unique().tolist()),
                key="cap_filter_client",
            )

        tmp = df.copy()
        if client_filter != "(All selected clients)":
            tmp = tmp[tmp["client_name"] == client_filter]

        with fB:
            project_filter = st.selectbox(
                "Project",
                options=["(All projects)"] + sorted(tmp["project_name"].dropna().unique().tolist()),
                key="cap_filter_project",
            )

        tmp2 = tmp.copy()
        if project_filter != "(All projects)":
            tmp2 = tmp2[tmp2["project_name"] == project_filter]

        with fC:
            resource_filter = st.selectbox(
                "Resource",
                options=["(All resources)"] + sorted(tmp2["full_name"].dropna().unique().tolist()),
                key="cap_filter_resource",
            )

        if client_filter != "(All selected clients)":
            df = df[df["client_name"] == client_filter]
        if project_filter != "(All projects)":
            df = df[df["project_name"] == project_filter]
        if resource_filter != "(All resources)":
            df = df[df["full_name"] == resource_filter]

    if df.empty:
        st.info("ℹ️ No allocations match the selected filters in this date range.")
        pmo_footer()
        st.stop()

    # Apply skills filter
    if HAS_SKILLS and apply_skill_filter and selected_skill_name:
        eligible = run_query(
            """
            SELECT DISTINCT rs.resource_id
            FROM public.resource_skills rs
            JOIN public.skills s ON s.skill_id = rs.skill_id
            WHERE s.skill_name = :sn
              AND rs.rating >= :minr
            """,
            {"sn": selected_skill_name, "minr": int(min_skill_rating)},
        )

        eligible_ids = eligible["resource_id"].astype(int).tolist() if eligible is not None and not eligible.empty else []
        df = df[df["resource_id"].astype(int).isin(eligible_ids)]

        if df.empty:
            st.info("ℹ️ No allocations match the selected Skills Matrix filter in this date range.")
            pmo_footer()
            st.stop()

    # -------------------------------
    # CALCULATE EFFECTIVE %
    # -------------------------------
    df["overlap_days"] = df.apply(
        lambda r: _overlap_days(r["start_date"], r["end_date"], range_start, range_end),
        axis=1,
    )

    if mode.startswith("Pro-rated"):
        df["effective_pct"] = df.apply(
            lambda r: float(r["allocation_pct"]) * (float(r["overlap_days"]) / float(days_in_range))
            if days_in_range > 0
            else 0.0,
            axis=1,
        )
    else:
        df["effective_pct"] = df["allocation_pct"].astype(float)

    # -------------------------------
    # FILTERED RESULTS
    # -------------------------------
    st.markdown("##### ✅ Filtered Results")

    _band = _band_factory()

    group_cols = ["resource_id", "full_name", "department", "role"]
    if split_by_client:
        group_cols = ["client_name"] + group_cols

    summary = (
        df.groupby(group_cols, dropna=False)
        .agg(
            total_alloc_pct=("effective_pct", "sum"),
            projects=("project_id", pd.Series.nunique),
            allocations=("allocation_id", "count"),
        )
        .reset_index()
    )

    summary["status"] = summary["total_alloc_pct"].apply(_band)
    summary["total_alloc_pct"] = summary["total_alloc_pct"].round(1)

    # Strong skills column
    if HAS_SKILLS:
        ids = summary["resource_id"].astype(int).unique().tolist()
        ids_sql = f"({','.join(str(i) for i in ids)})" if ids else "(-1)"

        strong = run_query(
            f"""
            SELECT
                rs.resource_id,
                STRING_AGG(s.skill_name, ', ' ORDER BY s.skill_name) AS strong_skills
            FROM public.resource_skills rs
            JOIN public.skills s ON s.skill_id = rs.skill_id
            WHERE rs.resource_id IN {ids_sql}
              AND rs.rating >= 4
            GROUP BY rs.resource_id
            """
        )

        if strong is not None and not strong.empty:
            summary = summary.merge(strong, on="resource_id", how="left")
        else:
            summary["strong_skills"] = ""

        summary["strong_skills"] = summary["strong_skills"].fillna("").astype(str).apply(_clean_skill_list_str)

    # Metrics
    over_threshold = 100
    under_threshold = 60

    total_resources = summary["resource_id"].nunique()
    over_allocated = (summary["total_alloc_pct"] > over_threshold).sum()
    under_utilized = (summary["total_alloc_pct"] < under_threshold).sum()
    avg_allocation = summary["total_alloc_pct"].mean()

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""
            <div class='metric-card'>
                <div class='metric-label'>Total Resources</div>
                <div class='metric-value'>{total_resources}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class='metric-card'>
                <div class='metric-label'>Over-Allocated</div>
                <div class='metric-value' style='color: #dc2626;'>{over_allocated}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class='metric-card'>
                <div class='metric-label'>Under-Utilized</div>
                <div class='metric-value' style='color: #ea580c;'>{under_utilized}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"""
            <div class='metric-card'>
                <div class='metric-label'>Avg Allocation</div>
                <div class='metric-value'>{avg_allocation:.1f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>📊 Status Legend</strong><br/>
            🔴 <b>Over</b> (>100%) — Resource needs immediate attention
            &nbsp;•&nbsp;
            🟠 <b>Near cap</b> (80-100%) — Nearly at full capacity
            &nbsp;•&nbsp;
            🟡 <b>Under</b> (<60%) — Available capacity
            &nbsp;•&nbsp;
            🟢 <b>OK</b> (60-80%) — Healthy balance
        </div>
        """,
        unsafe_allow_html=True,
    )

    display = summary.rename(
        columns={
            "client_name": "client",
            "full_name": "resource",
            "total_alloc_pct": "allocated_%",
            "projects": "#projects",
            "allocations": "#allocations",
        }
    )

    cols = []
    if split_by_client and "client" in display.columns:
        cols.append("client")
    cols += ["resource", "department", "role"]
    if HAS_SKILLS and "strong_skills" in display.columns:
        cols.append("strong_skills")
    cols += ["allocated_%", "status", "#projects", "#allocations"]

    display = display[cols].copy()

    st.dataframe(
        display.style.apply(_style_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # -------------------------------
    # DRILL DOWN
    # -------------------------------
    with st.expander("🔎 Drill-down (what is driving allocation?)", expanded=False):
        if split_by_client:
            summary["_pick_key"] = summary.apply(
                lambda r: f"{r.get('client_name', '')}||{int(r['resource_id'])}",
                axis=1,
            )

            pick = st.selectbox(
                "Select resource (client-specific)",
                options=summary["_pick_key"].tolist(),
                format_func=lambda k: f"{k.split('||')[0]} — {summary.set_index('_pick_key').loc[k, 'full_name']}",
                key="cap_page_pick_resource_client",
            )

            pick_client, pick_rid = pick.split("||")
            pick_rid = int(pick_rid)
            sub = df[(df["client_name"] == pick_client) & (df["resource_id"].astype(int) == pick_rid)].copy()
        else:
            pick_rid = st.selectbox(
                "Select resource",
                options=sorted(summary["resource_id"].astype(int).unique().tolist()),
                format_func=lambda rid: summary.set_index("resource_id").loc[rid, "full_name"],
                key="cap_page_pick_resource",
            )
            sub = df[df["resource_id"].astype(int) == int(pick_rid)].copy()

        sub["overlap_days"] = sub["overlap_days"].astype(int)
        sub["effective_pct"] = sub["effective_pct"].round(1)

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            sub[
                [
                    "client_name",
                    "project_name",
                    "allocation_pct",
                    "start_date",
                    "end_date",
                    "overlap_days",
                    "effective_pct",
                ]
            ].rename(
                columns={
                    "client_name": "client",
                    "allocation_pct": "alloc_%",
                    "effective_pct": "effective_%_in_range",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# FOOTER
# ============================================================
pmo_footer()
