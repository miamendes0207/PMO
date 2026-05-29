# ============================================================
# 33_Resource_Distribution.py — ScopeSight v3.3
# CEO Bird’s Eye: Capacity, Bench & Risk Concentration
# ============================================================

import datetime as dt
import pandas as pd
import streamlit as st
import plotly.express as px

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
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


def safe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df if df is not None else pd.DataFrame()


def to_date(series):
    return pd.to_datetime(series, errors="coerce").dt.date


# ---------------------------------------------------------
# SETUP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

st.set_page_config(page_title="🗂️ Resource Distribution", page_icon="🗂️", layout="wide")
set_pmo_theme(page_title="🗂️ Resource Distribution")
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

.exec-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 1rem 1.25rem;
    border-radius: 10px;
    margin-bottom: 1rem;
}

.warning-box {
    background: #fffaf0;
    border-left: 4px solid #ed8936;
    padding: 1rem 1.25rem;
    border-radius: 6px;
    margin-bottom: 1rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# ACCESS CONTROL
# ---------------------------------------------------------
role = (st.session_state.get("role") or "").strip().lower()
if role not in ("ceo", "admin", "exec"):
    st.error("This page is restricted to CEO/Exec/Admin roles.")
    st.stop()

today = dt.date.today()

# ---------------------------------------------------------
# EXEC CONTROLS
# ---------------------------------------------------------

c1, c2, c3, c4 = st.columns([1.2, 1.0, 1.0, 1.2])
with c1:
    use_current_only = st.checkbox("Current allocations only", value=True, help="Only count allocations active today.")
with c2:
    bench_threshold = st.slider("Bench threshold (%)", 5, 90, 40, 5)
with c3:
    over_threshold = st.slider("Over-cap threshold (%)", 100, 200, 110, 5)
with c4:
    show_people = st.toggle("Allow person-level drill-down", value=False)

# ---------------------------------------------------------
# LOAD RESOURCE MASTER
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# LOAD ALLOCATIONS (PORTFOLIO-WIDE)
# ---------------------------------------------------------
alloc_df = run_query(
    """
    SELECT
        ra.client_id,
        ra.resource_id,
        ra.allocation_pct,
        ra.start_date,
        ra.end_date,
        c.client_name,
        p.project_name
    FROM public.resource_allocation ra
    JOIN public.client_scaffold c ON c.id = ra.client_id
    JOIN public.projects p ON p.project_id = ra.project_id
    """
)
alloc_df = safe_df(alloc_df)

if not alloc_df.empty:
    alloc_df["allocation_pct"] = pd.to_numeric(alloc_df["allocation_pct"], errors="coerce").fillna(0.0)
    alloc_df["start_date"] = to_date(alloc_df["start_date"])
    alloc_df["end_date"] = to_date(alloc_df["end_date"])

    if use_current_only:
        alloc_df = alloc_df[
            (alloc_df["start_date"].isna() | (alloc_df["start_date"] <= today))
            & (alloc_df["end_date"].isna() | (alloc_df["end_date"] >= today))
        ].copy()

# Total utilisation per resource
if alloc_df.empty:
    util = rp_df[["resource_id"]].copy()
    util["total_alloc"] = 0.0
else:
    util = (
        alloc_df.groupby("resource_id", dropna=True)["allocation_pct"]
        .sum()
        .reset_index()
        .rename(columns={"allocation_pct": "total_alloc"})
    )

master = rp_df.merge(util, on="resource_id", how="left")
master["total_alloc"] = pd.to_numeric(master["total_alloc"], errors="coerce").fillna(0.0)

# Classifications
master["status"] = "OK"
master.loc[master["total_alloc"] == 0, "status"] = "Unallocated"
master.loc[(master["total_alloc"] > 0) & (master["total_alloc"] < bench_threshold), "status"] = "Underutilised"
master.loc[master["total_alloc"] >= over_threshold, "status"] = "Over Capacity"

# ---------------------------------------------------------
# KPIs
# ---------------------------------------------------------
total_resources = int(master["resource_id"].nunique())
avg_util = float(round(master["total_alloc"].mean(), 1)) if total_resources else 0.0
over_ct = int((master["status"] == "Over Capacity").sum())
unalloc_ct = int((master["status"] == "Unallocated").sum())
under_ct = int((master["status"] == "Underutilised").sum())
bench_ct = unalloc_ct + under_ct

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Resources", total_resources)
k2.metric("Avg Utilisation", f"{avg_util}%")
k3.metric(f"Over ≥ {over_threshold}%", over_ct)
k4.metric("Bench (0% + under)", bench_ct)
k5.metric("Unallocated", unalloc_ct)

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_portfolio, tab_clients, tab_functions, tab_bench = st.tabs(
    ["📊 Portfolio", "🏢 Clients", "🧩 Functions", "🪑 Bench Summary"]
)

# ============================================================
# PORTFOLIO TAB
# ============================================================
with tab_portfolio:
    st.markdown("<div class='section-header'><h3>📊 Portfolio Snapshot</h3></div>", unsafe_allow_html=True)

    # Util bands
    bands = master.copy()
    bands["Band"] = pd.cut(
        bands["total_alloc"],
        bins=[-1, 0.01, bench_threshold, 80, 100, 1000],
        labels=["0% (Unallocated)", f"<{bench_threshold}% (Under)", "80–100%", "100%", f">{100}%"],
    )

    dist = bands["Band"].value_counts().reset_index()
    dist.columns = ["Band", "Count"]

    fig = px.bar(dist, x="Band", y="Count")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        """
<div class='warning-box'>
  <strong>Interpretation:</strong><br/>
  • Rising <b>Over Capacity</b> suggests delivery risk and burnout.<br/>
  • Rising <b>Bench</b> suggests margin leakage unless demand is imminent.<br/>
  • CEO action: rebalance across clients + accelerate redeployment.
</div>
""",
        unsafe_allow_html=True,
    )

# ============================================================
# CLIENTS TAB
# ============================================================
with tab_clients:
    st.markdown("<div class='section-header'><h3>🏢 Client Hotspots</h3></div>", unsafe_allow_html=True)

    if alloc_df.empty:
        st.info("No allocations found (cannot compute client hotspots).")
    else:
        # Util per client per resource (then roll up)
        tmp = alloc_df.groupby(["client_name", "resource_id"], dropna=True)["allocation_pct"].sum().reset_index()

        # join resource meta
        tmp = tmp.merge(rp_df[["resource_id", "department", "role", "full_name"]], on="resource_id", how="left")

        client_roll = (
            tmp.groupby("client_name")
            .agg(
                resources=("resource_id", "nunique"),
                avg_alloc=("allocation_pct", "mean"),
                over_cap=("allocation_pct", lambda s: int((s >= over_threshold).sum())),
                under=("allocation_pct", lambda s: int(((s > 0) & (s < bench_threshold)).sum())),
                unalloc=("allocation_pct", lambda s: int((s == 0).sum())),
            )
            .reset_index()
        )
        client_roll["bench"] = client_roll["under"] + client_roll["unalloc"]
        client_roll["avg_alloc"] = client_roll["avg_alloc"].round(1)

        cA, cB = st.columns([1.2, 1.0])
        with cA:
            metric_choice = st.selectbox(
                "Rank clients by",
                ["Over Capacity", "Bench", "Avg Allocation", "Resources"],
                index=0,
                key="ceo_client_rank",
            )
        with cB:
            top_n = st.slider("Top N", 5, 30, 10, key="ceo_client_topn")

        sort_map = {
            "Over Capacity": ("over_cap", False),
            "Bench": ("bench", False),
            "Avg Allocation": ("avg_alloc", False),
            "Resources": ("resources", False),
        }
        col, asc = sort_map[metric_choice]
        view = client_roll.sort_values(col, ascending=asc).head(top_n)

        st.dataframe(
            view.rename(
                columns={
                    "client_name": "Client",
                    "resources": "Resources",
                    "avg_alloc": "Avg Allocation (%)",
                    "over_cap": f"Over ≥ {over_threshold}%",
                    "bench": "Bench",
                    "unalloc": "Unallocated",
                    "under": f"Under < {bench_threshold}%",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        # Optional drill down to people
        if show_people:
            pick_client = st.selectbox("Drill into client", options=sorted(client_roll["client_name"].unique()), key="ceo_pick_client")
            sub = tmp[tmp["client_name"] == pick_client].copy()
            sub["Status"] = sub["allocation_pct"].apply(
                lambda x: "Over" if x >= over_threshold else "Under" if (x > 0 and x < bench_threshold) else "OK" if x > 0 else "Unallocated"
            )
            sub = sub.sort_values(["Status", "allocation_pct"], ascending=[True, False])
            st.dataframe(
                sub.rename(columns={"full_name": "Resource", "allocation_pct": "Allocation (%)", "department": "Department", "role": "Role"})[
                    ["Status", "Resource", "Department", "Role", "Allocation (%)"]
                ],
                use_container_width=True,
                hide_index=True,
                height=380,
            )

# ============================================================
# FUNCTIONS TAB
# ============================================================
with tab_functions:
    st.markdown("<div class='section-header'><h3>🧩 Function & Department Hotspots</h3></div>", unsafe_allow_html=True)

    dept_roll = (
        master.groupby("department", dropna=False)
        .agg(
            resources=("resource_id", "nunique"),
            avg_alloc=("total_alloc", "mean"),
            over=("status", lambda s: int((s == "Over Capacity").sum())),
            bench=("status", lambda s: int((s.isin(["Unallocated", "Underutilised"])).sum())),
        )
        .reset_index()
    )
    dept_roll["avg_alloc"] = dept_roll["avg_alloc"].round(1)
    dept_roll["department"] = dept_roll["department"].fillna("Unspecified")

    fig = px.bar(dept_roll.sort_values("bench", ascending=False), x="department", y="bench")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Department", yaxis_title="Bench headcount")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        dept_roll.rename(
            columns={
                "department": "Department",
                "resources": "Resources",
                "avg_alloc": "Avg Allocation (%)",
                "over": f"Over ≥ {over_threshold}%",
                "bench": "Bench",
            }
        ).sort_values("Bench", ascending=False),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

# ============================================================
# BENCH SUMMARY TAB
# ============================================================
with tab_bench:
    st.markdown("<div class='section-header'><h3>🪑 Bench Summary</h3></div>", unsafe_allow_html=True)

    bench_df = master[master["status"].isin(["Unallocated", "Underutilised"])].copy()
    if bench_df.empty:
        st.success("No bench detected under current settings.")
    else:
        # Aggregate by role
        role_roll = (
            bench_df.groupby("role", dropna=False)
            .agg(headcount=("resource_id", "nunique"))
            .reset_index()
        )
        role_roll["role"] = role_roll["role"].fillna("Unspecified")
        role_roll = role_roll.sort_values("headcount", ascending=False)

        fig = px.bar(role_roll.head(15), x="role", y="headcount")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Role", yaxis_title="Bench headcount")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            role_roll.rename(columns={"role": "Role", "headcount": "Bench headcount"}),
            use_container_width=True,
            hide_index=True,
            height=380,
        )

        if show_people:
            with st.expander("👥 Show bench people (CEO drill-down)", expanded=False):
                st.dataframe(
                    bench_df.rename(columns={"full_name": "Resource", "total_alloc": "Total Allocation (%)"})[
                        ["status", "Resource", "department", "role", "Total Allocation (%)"]
                    ].rename(columns={"status": "Status", "department": "Department", "role": "Role"}),
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<div style='margin: 3rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()
