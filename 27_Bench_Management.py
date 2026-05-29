# ============================================================
# 27_👥_Bench_Management.py — ScopeSight v3.3
# Bench Management: Unallocated + Underutilised Resources
# ============================================================

import re
import datetime as dt

import pandas as pd
import streamlit as st
import plotly.express as px

from auth.login import require_login
from modules.db import run_query  # (optional) add run_execute if you want notes persistence
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
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


def column_exists(table_name: str, column_name: str) -> bool:
    df = run_query(
        """
        SELECT 1 AS ok
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name=:t
          AND column_name=:c
        LIMIT 1
        """,
        {"t": table_name, "c": column_name},
    )
    return df is not None and not df.empty


def clean_skill_label(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    return re.sub(r"^\s*\d+\s*[-–—.)]*\s*", "", s).strip()


def safe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df if df is not None else pd.DataFrame()


def to_date(series):
    return pd.to_datetime(series, errors="coerce").dt.date


# ---------------------------------------------------------
# SETUP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

st.set_page_config(
    page_title="👥 Bench Management",
    page_icon="👥",
    layout="wide",
)

set_pmo_theme(page_title="👥 Bench Management (Unallocated + Underutilised)")
render_sidebar()

# ---------------------------------------------------------
# STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height:0 !important; visibility:hidden !important; }

.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.25rem 0 1rem 0;
}
.section-header h3 { margin: 0; color: white; font-size: 1.2rem; font-weight: 600; }

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem 1.25rem;
    border-radius: 6px;
    margin-bottom: 1rem;
}
.warning-box {
    background: #fffaf0;
    border-left: 4px solid #ed8936;
    padding: 1rem 1.25rem;
    border-radius: 6px;
    margin-bottom: 1rem;
}

.control-panel {
    background: white;
    border: 1px solid #e2e8f0;
    padding: 1.25rem;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

h2 { text-align:center !important; margin-top:18px !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# LOAD USER
# ---------------------------------------------------------
email = st.session_state.get("email")
if not email:
    st.error("Unable to load your profile. Please log in again.")
    st.stop()

role = (st.session_state.get("role") or "").strip().lower()
email = email.strip().lower()

# ---------------------------------------------------------
# CLIENT SCOPE
# ---------------------------------------------------------
if role == "admin":
    clients_df = run_query(
        """
        SELECT id AS client_id, client_name
        FROM public.client_scaffold
        ORDER BY client_name
        """
    )
else:
    has_user_email = column_exists("user_client_permissions", "user_email")
    has_email_col = column_exists("user_client_permissions", "email")

    if has_user_email:
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
    elif has_email_col:
        clients_df = run_query(
            """
            SELECT c.id AS client_id, c.client_name
            FROM public.user_client_permissions u
            JOIN public.client_scaffold c ON c.id = u.client_id
            WHERE LOWER(u.email) = :email
            ORDER BY c.client_name
            """,
            {"email": email},
        )
    else:
        st.error("Cannot resolve user email column in user_client_permissions (expected user_email or email).")
        pmo_footer()
        st.stop()

if clients_df is None or clients_df.empty:
    if role == "admin":
        st.error("No clients exist in the system.")
    else:
        st.warning("You are not assigned to any clients. Ask an admin to assign you.")
    pmo_footer()
    st.stop()

client_ids = clients_df["client_id"].astype(int).tolist()

# ---------------------------------------------------------
# CONTROLS (TOP)
# ---------------------------------------------------------
st.markdown(
    """
<div class='section-header'>
  <h3>⚙️ Bench Rules</h3>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
  <strong>How “bench” is calculated:</strong><br/>
  • <b>Unallocated</b> = total allocation = 0%<br/>
  • <b>Underutilised</b> = total allocation &lt; your threshold (e.g., 40%)<br/>
  • Optional: filter to <b>current allocations only</b> (active today)
</div>
""",
    unsafe_allow_html=True,
)

cA, cB, cC = st.columns([1.2, 1.0, 1.2])
today = dt.date.today()

with cA:
    use_current_only = st.checkbox(
        "Current allocations only",
        value=True,
        help="If on: only allocations active today are counted.",
        key="bm_current_only",
    )
with cB:
    under_threshold = st.slider(
        "Underutilised threshold (%)",
        min_value=5,
        max_value=90,
        value=40,
        step=5,
        key="bm_threshold",
    )
with cC:
    bench_focus = st.selectbox(
        "Show",
        ["All bench (unallocated + underutilised)", "Unallocated only", "Underutilised only"],
        index=0,
        key="bm_focus",
    )

# ---------------------------------------------------------
# LOAD ALLOCATIONS + RESOURCE MASTER
# ---------------------------------------------------------
# Pull allocations in scope (including resource details)
alloc_df = run_query(
    """
    SELECT
        ra.client_id,
        ra.resource_id,
        rp.full_name,
        rp.role,
        rp.department,
        ra.allocation_pct,
        ra.start_date,
        ra.end_date,
        p.project_name,
        c.client_name
    FROM public.resource_allocation ra
    JOIN public.resource_pool rp ON rp.resource_id = ra.resource_id
    JOIN public.projects p ON p.project_id = ra.project_id
    JOIN public.client_scaffold c ON c.id = ra.client_id
    WHERE ra.client_id = ANY(:client_ids)
    """,
    {"client_ids": client_ids},
)
alloc_df = safe_df(alloc_df)

# Also pull all resources (so we can find truly unallocated people who have no allocation rows)
rp_has_is_active = column_exists("resource_pool", "is_active")
rp_df = run_query(
    f"""
    SELECT resource_id, full_name, role, department
    {", is_active" if rp_has_is_active else ""}
    FROM public.resource_pool
    """
)
rp_df = safe_df(rp_df)

if rp_df.empty:
    st.info("No resources found in resource_pool.")
    pmo_footer()
    st.stop()

if rp_has_is_active:
    rp_df = rp_df[rp_df["is_active"].fillna(True) == True].copy()

# Normalise
if not alloc_df.empty:
    alloc_df["allocation_pct"] = pd.to_numeric(alloc_df["allocation_pct"], errors="coerce").fillna(0.0)
    alloc_df["start_date"] = to_date(alloc_df["start_date"])
    alloc_df["end_date"] = to_date(alloc_df["end_date"])

    if use_current_only:
        alloc_df = alloc_df[
            (alloc_df["start_date"].isna() | (alloc_df["start_date"] <= today))
            & (alloc_df["end_date"].isna() | (alloc_df["end_date"] >= today))
        ].copy()

# Compute total utilisation per resource (from alloc rows)
if alloc_df.empty:
    util_df = rp_df[["resource_id", "full_name"]].copy()
    util_df["total_alloc"] = 0.0
else:
    util_df = (
        alloc_df.groupby(["resource_id", "full_name"], dropna=True)["allocation_pct"]
        .sum()
        .reset_index()
        .rename(columns={"allocation_pct": "total_alloc"})
    )

# Merge onto resource master (ensures resources with no allocation rows appear as 0%)
master = rp_df.merge(util_df[["resource_id", "total_alloc"]], on="resource_id", how="left")
master["total_alloc"] = pd.to_numeric(master["total_alloc"], errors="coerce").fillna(0.0)

# Bench classification
master["bench_type"] = "OK"
master.loc[master["total_alloc"] == 0, "bench_type"] = "Unallocated"
master.loc[(master["total_alloc"] > 0) & (master["total_alloc"] < under_threshold), "bench_type"] = "Underutilised"

# Apply focus filter
bench = master[master["bench_type"].isin(["Unallocated", "Underutilised"])].copy()
if bench_focus == "Unallocated only":
    bench = bench[bench["bench_type"] == "Unallocated"].copy()
elif bench_focus == "Underutilised only":
    bench = bench[bench["bench_type"] == "Underutilised"].copy()

# ---------------------------------------------------------
# TOP METRICS
# ---------------------------------------------------------
total_resources = int(master["resource_id"].nunique())
bench_count = int(bench["resource_id"].nunique())
unalloc_count = int((bench["bench_type"] == "Unallocated").sum())
under_count = int((bench["bench_type"] == "Underutilised").sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Resources", total_resources)
c2.metric("Bench (in view)", bench_count)
c3.metric("Unallocated", unalloc_count)
c4.metric(f"Under < {under_threshold}%", under_count)

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_dash, tab_unalloc, tab_under, tab_skills = st.tabs(
    ["📊 Dashboard", "🔍 Unallocated", "📉 Underutilised", "🎯 Skills Finder"]
)

# ============================================================
# TAB — DASHBOARD
# ============================================================
with tab_dash:
    st.markdown(
        """
<div class='section-header'><h3>📊 Bench Overview</h3></div>
""",
        unsafe_allow_html=True,
    )

    if bench.empty:
        st.success("No bench resources found for the current scope and settings.")
    else:
        # Bench distribution chart
        dist = bench["bench_type"].value_counts().reset_index()
        dist.columns = ["Bench Type", "Count"]
        fig = px.bar(dist, x="Bench Type", y="Count")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            """
<div class='info-box'>
  <strong>Suggested actions:</strong><br/>
  • Review <b>Unallocated</b> first (fastest wins).<br/>
  • Use <b>Skills Finder</b> to shortlist for upcoming demand.<br/>
  • For <b>Underutilised</b>, check partial allocations and likely end-dates.
</div>
""",
            unsafe_allow_html=True,
        )

        # Quick bench table
        show_cols = ["bench_type", "full_name", "role", "department", "total_alloc"]
        view = bench[show_cols].rename(
            columns={
                "bench_type": "Bench Type",
                "full_name": "Resource",
                "total_alloc": "Total Allocation (%)",
                "role": "Role",
                "department": "Department",
            }
        ).sort_values(["Bench Type", "Total Allocation (%)", "Resource"], ascending=[True, True, True])

        st.dataframe(view, use_container_width=True, hide_index=True, height=420)

# ============================================================
# TAB — UNALLOCATED
# ============================================================
with tab_unalloc:
    st.markdown(
        f"""
<div class='section-header'><h3>🔍 Unallocated Resources (0%)</h3></div>
""",
        unsafe_allow_html=True,
    )

    unalloc = master[master["bench_type"] == "Unallocated"].copy()

    if unalloc.empty:
        st.info("No unallocated resources found.")
    else:
        f1, f2, f3 = st.columns(3)
        with f1:
            dept_opts = sorted([d for d in unalloc["department"].dropna().astype(str).unique().tolist() if d.strip()])
            depts = st.multiselect("Department", options=dept_opts, default=dept_opts, key="u_dept")
        with f2:
            role_opts = sorted([r for r in unalloc["role"].dropna().astype(str).unique().tolist() if r.strip()])
            roles = st.multiselect("Role", options=role_opts, default=role_opts, key="u_role")
        with f3:
            q = st.text_input("🔍 Search", key="u_search")

        u = unalloc.copy()
        if depts:
            u = u[u["department"].fillna("").astype(str).isin(set(depts))]
        if roles:
            u = u[u["role"].fillna("").astype(str).isin(set(roles))]
        if q.strip():
            s = q.strip().lower()
            u = u[u["full_name"].fillna("").str.lower().str.contains(s)]

        st.caption(f"Showing {len(u)} of {len(unalloc)} unallocated resources")

        st.dataframe(
            u.rename(columns={"full_name": "Resource", "total_alloc": "Total Allocation (%)"})[
                ["Resource", "role", "department", "Total Allocation (%)"]
            ].rename(columns={"role": "Role", "department": "Department"}),
            use_container_width=True,
            hide_index=True,
            height=420,
        )

# ============================================================
# TAB — UNDERUTILISED
# ============================================================
with tab_under:
    st.markdown(
        f"""
<div class='section-header'><h3>📉 Underutilised Resources (&lt; {under_threshold}%)</h3></div>
""",
        unsafe_allow_html=True,
    )

    under = master[(master["bench_type"] == "Underutilised")].copy()

    if under.empty:
        st.info("No underutilised resources found.")
    else:
        # If allocations exist, show their current assignments to explain "why under"
        # Aggregate project/client list per resource
        if alloc_df.empty:
            under_detail = under.copy()
            under_detail["Current Assignments"] = ""
        else:
            ad = alloc_df.copy()
            ad["allocation_pct"] = pd.to_numeric(ad["allocation_pct"], errors="coerce").fillna(0.0)

            roll = (
                ad.groupby(["resource_id"])  # already date-scoped if current_only
                .apply(lambda x: "; ".join(
                    sorted(set(
                        (x["client_name"].fillna("").astype(str) + " — " + x["project_name"].fillna("").astype(str))
                        .tolist()
                    ))
                ))
                .reset_index(name="Current Assignments")
            )

            under_detail = under.merge(roll, on="resource_id", how="left")
            under_detail["Current Assignments"] = under_detail["Current Assignments"].fillna("")

        f1, f2, f3 = st.columns(3)
        with f1:
            dept_opts = sorted([d for d in under_detail["department"].dropna().astype(str).unique().tolist() if d.strip()])
            depts = st.multiselect("Department", options=dept_opts, default=dept_opts, key="ud_dept")
        with f2:
            role_opts = sorted([r for r in under_detail["role"].dropna().astype(str).unique().tolist() if r.strip()])
            roles = st.multiselect("Role", options=role_opts, default=role_opts, key="ud_role")
        with f3:
            q = st.text_input("🔍 Search", key="ud_search")

        ud = under_detail.copy()
        if depts:
            ud = ud[ud["department"].fillna("").astype(str).isin(set(depts))]
        if roles:
            ud = ud[ud["role"].fillna("").astype(str).isin(set(roles))]
        if q.strip():
            s = q.strip().lower()
            ud = ud[ud["full_name"].fillna("").str.lower().str.contains(s)]

        st.caption(f"Showing {len(ud)} of {len(under_detail)} underutilised resources")

        st.dataframe(
            ud.rename(columns={"full_name": "Resource", "total_alloc": "Total Allocation (%)"})[
                ["Resource", "role", "department", "Total Allocation (%)", "Current Assignments"]
            ].rename(columns={"role": "Role", "department": "Department"}),
            use_container_width=True,
            hide_index=True,
            height=460,
        )

# ============================================================
# TAB — SKILLS FINDER (BENCH ONLY)
# ============================================================
with tab_skills:
    st.markdown(
        """
<div class='section-header'><h3>🎯 Skills Finder (Bench Only)</h3></div>
""",
        unsafe_allow_html=True,
    )

    HAS_SKILLS = table_exists("skills") and table_exists("resource_skills")
    SKILLS_HAS_CATEGORY = HAS_SKILLS and column_exists("skills", "category")

    if bench.empty:
        st.info("No bench resources in scope to analyse skills.")
        st.stop()

    if not HAS_SKILLS:
        st.warning("Skills Matrix not available (skills/resource_skills tables missing).")
        st.stop()

    bench_ids = bench["resource_id"].dropna().astype(int).unique().tolist()
    bench_sql = f"({','.join(str(i) for i in bench_ids)})"

    ratings = run_query(
        f"""
        SELECT
            rp.resource_id,
            rp.full_name,
            s.skill_id,
            s.skill_name,
            rs.rating
        FROM public.resource_skills rs
        JOIN public.skills s ON s.skill_id = rs.skill_id
        JOIN public.resource_pool rp ON rp.resource_id = rs.resource_id
        WHERE rs.resource_id IN {bench_sql}
        """
    )
    ratings = safe_df(ratings)
    if ratings.empty:
        st.info("No Skills Matrix ratings found for bench resources.")
        st.stop()

    ratings["skill_label"] = ratings["skill_name"].astype(str).apply(clean_skill_label)
    ratings["rating"] = pd.to_numeric(ratings["rating"], errors="coerce").fillna(0)

    pivot = (
        ratings.pivot_table(
            index="full_name",
            columns="skill_label",
            values="rating",
            aggfunc="max",
            fill_value=0,
        )
        .sort_index(axis=0)
        .sort_index(axis=1)
    )

    # Categories
    skills_meta = run_query(
        "SELECT skill_name, category FROM public.skills"
        if SKILLS_HAS_CATEGORY
        else "SELECT skill_name, NULL::text AS category FROM public.skills"
    )
    skills_meta = safe_df(skills_meta)
    skills_meta["skill_label"] = skills_meta["skill_name"].astype(str).apply(clean_skill_label)
    skills_meta["category"] = skills_meta["category"].fillna("Uncategorised").astype(str)
    label_to_cat = dict(zip(skills_meta["skill_label"], skills_meta["category"]))

    available_skills = list(pivot.columns)
    available_cats = sorted({label_to_cat.get(lbl, "Uncategorised") for lbl in available_skills})

    ctrl, out = st.columns([1, 2.2])

    with ctrl:
        st.markdown('<div class="control-panel">', unsafe_allow_html=True)
        st.markdown("#### 🔍 Filters")

        cats = st.multiselect(
            "📁 Category",
            options=available_cats,
            default=available_cats,
            key="bm_cat",
        )

        skills_after_cat = [lbl for lbl in available_skills if label_to_cat.get(lbl, "Uncategorised") in set(cats)]

        MS_KEY = "bm_selected_skills"
        if MS_KEY not in st.session_state:
            st.session_state[MS_KEY] = skills_after_cat[: min(10, len(skills_after_cat))]

        st.session_state[MS_KEY] = [s for s in st.session_state[MS_KEY] if s in skills_after_cat]

        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ All", use_container_width=True, key="bm_all"):
                st.session_state[MS_KEY] = skills_after_cat
                st.rerun()
        with b2:
            if st.button("❌ Clear", use_container_width=True, key="bm_clear"):
                st.session_state[MS_KEY] = []
                st.rerun()

        selected_skills = st.multiselect(
            "🎯 Skills",
            options=skills_after_cat,
            key=MS_KEY,
        )

        st.markdown("### Display")
        show_rows = st.slider("Resources", 5, 100, min(30, pivot.shape[0]), key="bm_rows")

        st.markdown("<hr style='border:none; height:1px; background:#e2e8f0; margin: 1.25rem 0;'/>",
                    unsafe_allow_html=True)

        st.markdown("#### 🔎 Lookup")
        pick = st.selectbox(
            "Select skill",
            options=(skills_after_cat if skills_after_cat else available_skills),
            key="bm_pick",
        )
        min_rating = st.select_slider("Min rating", options=[0, 1, 2, 3, 4, 5], value=3, key="bm_min")

        st.markdown("</div>", unsafe_allow_html=True)

    with out:
        c1, c2, c3 = st.columns(3)
        c1.metric("Bench Resources", pivot.shape[0])
        c2.metric("Total Skills", pivot.shape[1])
        c3.metric("Selected", len(selected_skills))

        st.markdown(
            """
<div class='section-header'><h3>🎯 Bench Skills Heatmap</h3></div>
""",
            unsafe_allow_html=True,
        )

        if not selected_skills:
            st.info("👈 Select skills to display the heatmap")
        else:
            view = pivot[selected_skills].head(show_rows)
            fig = px.imshow(
                view,
                aspect="auto",
                labels=dict(x="Skill", y="Resource", color="Rating"),
                color_continuous_scale="Blues",
            )
            fig.update_layout(margin=dict(l=10, r=10, t=25, b=10), height=450)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            f"""
<div class='section-header'><h3>👥 Resources: {pick}</h3></div>
""",
            unsafe_allow_html=True,
        )

        tbl = (
            pivot[[pick]]
            .rename(columns={pick: "Rating"})
            .reset_index()
            .rename(columns={"full_name": "Resource"})
        )

        # bring utilisation
        util_small = master.rename(columns={"full_name": "Resource"})[["Resource", "total_alloc", "bench_type"]].copy()
        util_small = util_small.rename(columns={"total_alloc": "Total Allocation (%)", "bench_type": "Bench Type"})

        tbl = tbl.merge(util_small, on="Resource", how="left")
        tbl["Total Allocation (%)"] = pd.to_numeric(tbl["Total Allocation (%)"], errors="coerce").fillna(0)
        tbl = tbl[tbl["Rating"] >= int(min_rating)].copy()
        tbl = tbl.sort_values(["Rating", "Total Allocation (%)", "Resource"], ascending=[False, True, True])

        if tbl.empty:
            st.info(f"No bench resources with rating ≥ {min_rating}")
        else:
            st.dataframe(tbl, use_container_width=True, hide_index=True, height=320)

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<div style='margin: 3rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()