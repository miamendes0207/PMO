# ============================================================
# 32_Skills_Distribution.py — ScopeSight v4.1
# Skills Distribution - Simplified by Service Line, Position, Projects
# ============================================================

import re
import pandas as pd
import streamlit as st
import plotly.express as px

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# ---------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="🎯 Skills Distribution",
    page_icon="🎯",
    layout="wide",
)

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


# ---------------------------------------------------------
# SETUP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

set_pmo_theme(page_title="🎯 Skills Distribution")
render_sidebar()

# ---------------------------------------------------------
# STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

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

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0;
}

.warning-box {
    background: #fffbeb;
    border-left: 4px solid #f59e0b;
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

label { font-weight: 600 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# VALIDATE SKILLS MATRIX
# ---------------------------------------------------------
HAS_SKILLS = table_exists("skills") and table_exists("resource_skills")
SKILLS_HAS_CATEGORY = HAS_SKILLS and column_exists("skills", "category")

if not HAS_SKILLS:
    st.warning("⚠️ Skills Matrix not available (skills/resource_skills tables missing).")
    pmo_footer()
    st.stop()

# ---------------------------------------------------------
# LOAD USER
# ---------------------------------------------------------
email = (st.session_state.get("email") or "").strip().lower()
role = (st.session_state.get("role") or "").strip().lower()

if not email:
    st.error("❌ Unable to load your profile. Please log in again.")
    st.stop()

# ---------------------------------------------------------
# LOAD ALL RESOURCES WITH SKILLS
# ---------------------------------------------------------
ratings_df = run_query(
    f"""
    SELECT
        rp.resource_id,
        rp.full_name,
        rp.department,
        rp.role,
        s.skill_id,
        s.skill_name,
        {"s.category," if SKILLS_HAS_CATEGORY else "NULL::text AS category,"}
        rs.rating
    FROM public.resource_pool rp
    JOIN public.resource_skills rs ON rs.resource_id = rp.resource_id
    JOIN public.skills s ON s.skill_id = rs.skill_id
    WHERE rs.rating > 0
    """
)
ratings_df = safe_df(ratings_df)

if ratings_df.empty:
    st.info("ℹ️ No skills data found in the system.")
    pmo_footer()
    st.stop()

ratings_df["skill_label"] = ratings_df["skill_name"].astype(str).apply(clean_skill_label)
ratings_df["category"] = ratings_df["category"].fillna("Uncategorised").astype(str)
ratings_df["rating"] = pd.to_numeric(ratings_df["rating"], errors="coerce").fillna(0)

# ---------------------------------------------------------
# SERVICE LINE SOURCE (department)
# ---------------------------------------------------------
ratings_df["service_line"] = (
    ratings_df["department"]
    .fillna("Unassigned")
    .astype(str)
    .replace({"": "Unassigned"})
)

# ---------------------------------------------------------
# LOAD PROJECT ALLOCATIONS
# ---------------------------------------------------------
allocations_df = run_query(
    """
    SELECT DISTINCT
        ra.resource_id,
        p.project_name,
        p.project_id
    FROM public.resource_allocation ra
    JOIN public.projects p ON p.project_id = ra.project_id
    """
)
allocations_df = safe_df(allocations_df)

# ---------------------------------------------------------
# SNAPSHOT METRICS
# ---------------------------------------------------------
st.markdown(
    """
<div class='step-header'>
    <h4>📊 Overview</h4>
</div>
""",
    unsafe_allow_html=True,
)

total_resources = ratings_df["resource_id"].nunique()
total_skills = ratings_df["skill_label"].nunique()
total_categories = ratings_df["category"].nunique()
avg_rating = ratings_df["rating"].mean()

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
            <div class='metric-label'>Total Skills</div>
            <div class='metric-value'>{total_skills}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f"""
        <div class='metric-card'>
            <div class='metric-label'>Skill Categories</div>
            <div class='metric-value'>{total_categories}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f"""
        <div class='metric-card'>
            <div class='metric-label'>Avg Skill Rating</div>
            <div class='metric-value'>{avg_rating:.1f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br/><br/>", unsafe_allow_html=True)

# ---------------------------------------------------------
# ANALYSIS TABS
# ---------------------------------------------------------
st.markdown(
    """
<div class='step-header'>
    <h4>🔍 Analyze Skills Distribution</h4>
</div>
""",
    unsafe_allow_html=True,
)

tab_labels = ["🏢 Service Line Breakdown", "👥 By Position/Role", "📁 By Project", "📊 Skills Gap Analysis", "📋 Raw Data"]
tabs = st.tabs(tab_labels)
tab_index = 0

# ============================================================
# TAB: SERVICE LINE BREAKDOWN (LEAN)
# ============================================================
with tabs[tab_index]:
    st.markdown("#### 🏢 Service Line Breakdown")

    st.markdown(
        """
        <div class='info-row'>
            <strong>What you're seeing:</strong> An overview of skills by service line plus a drill-down chart.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Overview table
    sl_summary = (
        ratings_df.groupby("service_line")
        .agg(
            resources=("resource_id", "nunique"),
            skills=("skill_label", "nunique"),
            avg_rating=("rating", "mean"),
        )
        .reset_index()
        .sort_values("resources", ascending=False)
    )
    sl_summary["avg_rating"] = sl_summary["avg_rating"].round(2)

    st.markdown("##### Service Line Overview")
    st.dataframe(
        sl_summary.rename(columns={
            "service_line": "Service Line",
            "resources": "# Resources",
            "skills": "# Skills",
            "avg_rating": "Avg Rating",
        }),
        use_container_width=True,
        hide_index=True,
        height=320,
    )

    st.markdown("<br/>", unsafe_allow_html=True)

    # Drill-down (Avg Rating on X)
    st.markdown("##### Top Skills (Selected Service Line)")

    service_line_pick = st.selectbox(
        "Select service line",
        options=sorted(ratings_df["service_line"].unique()),
        key="sl_pick_lean",
    )

    sl_data = ratings_df[ratings_df["service_line"] == service_line_pick].copy()

    top_n = st.slider("How many skills to show?", 5, 30, 15, key="sl_topn_lean")

    # Aggregate skills: avg rating + people count (for confidence)
    top_skills = (
        sl_data.groupby("skill_label")
        .agg(
            avg_rating=("rating", "mean"),
            people=("resource_id", "nunique"),
        )
        .reset_index()
    )
    top_skills["avg_rating"] = top_skills["avg_rating"].round(2)

    # Optional: require at least 2 people so “avg” isn’t noisy
    min_people = st.slider("Minimum people per skill", 1, 10, 2, key="sl_min_people")
    top_skills = top_skills[top_skills["people"] >= min_people].copy()

    # Sort by highest avg rating (then people)
    top_skills = top_skills.sort_values(["avg_rating", "people"], ascending=[False, False]).head(top_n)

    if top_skills.empty:
        st.info("ℹ️ No skills found for this service line (try lowering the minimum people filter).")
    else:
        fig = px.bar(
            top_skills.sort_values("avg_rating", ascending=True),
            x="avg_rating",
            y="skill_label",
            orientation="h",
            labels={"avg_rating": "Avg Rating", "skill_label": "Skill"},
            color="people",
        )
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
        fig.update_xaxes(range=[0, 5])
        st.plotly_chart(fig, use_container_width=True)

tab_index += 1

# ============================================================
# TAB: BY POSITION/ROLE
# ============================================================
with tabs[tab_index]:
    st.markdown("#### 👥 Skills Distribution by Position/Role")

    st.markdown(
        """
        <div class='info-row'>
            <strong>What you're seeing:</strong> Which skills are concentrated in which roles 
            (Developers, Analysts, Project Managers, etc.)
        </div>
        """,
        unsafe_allow_html=True,
    )

    role_summary = (
        ratings_df.groupby("role")
        .agg(
            resources=("resource_id", "nunique"),
            skills=("skill_label", "nunique"),
            avg_rating=("rating", "mean"),
        )
        .reset_index()
        .sort_values("resources", ascending=False)
    )
    role_summary["avg_rating"] = role_summary["avg_rating"].round(2)

    st.markdown("##### Role Overview")
    st.dataframe(
        role_summary.rename(columns={
            "role": "Role/Position",
            "resources": "# Resources",
            "skills": "# Skills",
            "avg_rating": "Avg Rating",
        }),
        use_container_width=True,
        hide_index=True,
        height=300,
    )

    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("##### Top Skills by Role")

    role_pick = st.selectbox(
        "Select role/position",
        options=sorted(ratings_df["role"].dropna().unique()),
        key="role_pick",
    )

    role_data = ratings_df[ratings_df["role"] == role_pick].copy()

    top_role_skills = (
        role_data.groupby("skill_label")
        .agg(
            people=("resource_id", "nunique"),
            avg_rating=("rating", "mean"),
        )
        .reset_index()
        .sort_values("people", ascending=False)
        .head(15)
    )
    top_role_skills["avg_rating"] = top_role_skills["avg_rating"].round(2)

    fig = px.bar(
        top_role_skills,
        x="people",
        y="skill_label",
        orientation="h",
        labels={"people": "Number of People", "skill_label": "Skill"},
        color="avg_rating",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=500, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        f"""
        <div class='info-box'>
            <strong style='color:#48bb78;'>📊 {role_pick} Stats</strong><br/>
            Resources: <b>{role_data['resource_id'].nunique()}</b> • 
            Unique skills: <b>{role_data['skill_label'].nunique()}</b> • 
            Avg rating: <b>{role_data['rating'].mean():.2f}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

tab_index += 1

# ============================================================
# TAB: BY PROJECT
# ============================================================
with tabs[tab_index]:
    st.markdown("#### 📁 Skills Distribution by Project")

    st.markdown(
        """
        <div class='info-row'>
            <strong>What you're seeing:</strong> Which skills are available on each project 
            based on currently allocated resources
        </div>
        """,
        unsafe_allow_html=True,
    )

    if allocations_df.empty:
        st.info("ℹ️ No project allocations found.")
    else:
        project_skills = allocations_df.merge(ratings_df, on="resource_id", how="inner")

        project_summary = (
            project_skills.groupby("project_name")
            .agg(
                resources=("resource_id", "nunique"),
                skills=("skill_label", "nunique"),
                avg_rating=("rating", "mean"),
            )
            .reset_index()
            .sort_values("resources", ascending=False)
        )
        project_summary["avg_rating"] = project_summary["avg_rating"].round(2)

        st.markdown("##### Project Overview")
        st.dataframe(
            project_summary.rename(columns={
                "project_name": "Project",
                "resources": "# Resources",
                "skills": "# Skills",
                "avg_rating": "Avg Rating",
            }),
            use_container_width=True,
            hide_index=True,
            height=300,
        )

        st.markdown("<br/>", unsafe_allow_html=True)
        st.markdown("##### Skills Available on Project")

        project_pick = st.selectbox(
            "Select project",
            options=sorted(project_skills["project_name"].unique()),
            key="project_pick",
        )

        proj_data = project_skills[project_skills["project_name"] == project_pick].copy()

        proj_skill_summary = (
            proj_data.groupby("skill_label")
            .agg(
                people=("resource_id", "nunique"),
                avg_rating=("rating", "mean"),
                max_rating=("rating", "max"),
            )
            .reset_index()
            .sort_values("people", ascending=False)
        )
        proj_skill_summary["avg_rating"] = proj_skill_summary["avg_rating"].round(2)

        st.markdown(f"**Top 20 skills on {project_pick}**")
        st.dataframe(
            proj_skill_summary.head(20).rename(columns={
                "skill_label": "Skill",
                "people": "# People",
                "avg_rating": "Avg Rating",
                "max_rating": "Max Rating",
            }),
            use_container_width=True,
            hide_index=True,
            height=400,
        )

        with st.expander("🔍 View Resource Breakdown"):
            st.markdown("##### Resources and Their Skills on This Project")

            resource_pick = st.selectbox(
                "Select team member",
                options=sorted(proj_data["full_name"].unique()),
                key="proj_resource_pick",
            )

            resource_skills = proj_data[proj_data["full_name"] == resource_pick].copy()
            resource_skills = resource_skills[["skill_label", "category", "rating"]].sort_values(
                "rating",
                ascending=False,
            )

            st.dataframe(
                resource_skills.rename(columns={
                    "skill_label": "Skill",
                    "category": "Category",
                    "rating": "Rating",
                }),
                use_container_width=True,
                hide_index=True,
                height=300,
            )

tab_index += 1

# ============================================================
# TAB: SKILLS GAP ANALYSIS
# ============================================================
with tabs[tab_index]:
    st.markdown("#### 📊 Skills Gap Analysis")

    st.markdown(
        """
        <div class='info-row'>
            <strong>What you're seeing:</strong> Skills with the lowest average ratings (by role and by service line),
            highlighting training and development opportunities.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>💡 How to Use This</strong><br/>
            Low-rated skills show where your team could benefit from training or upskilling. 
            Focus on skills that are important to your projects but currently have low proficiency.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ----------------------------
    # Role gap analysis (existing)
    # ----------------------------
    st.markdown("##### Skills Development Opportunities by Role")

    gap_role_pick = st.selectbox(
        "Select role to analyze",
        options=sorted(ratings_df["role"].dropna().unique()),
        key="gap_role_pick",
    )

    gap_role_data = ratings_df[ratings_df["role"] == gap_role_pick].copy()

    role_skill_avg = (
        gap_role_data.groupby("skill_label")
        .agg(
            avg_rating=("rating", "mean"),
            people=("resource_id", "nunique"),
            max_rating=("rating", "max"),
            min_rating=("rating", "min"),
        )
        .reset_index()
    )
    role_skill_avg["avg_rating"] = role_skill_avg["avg_rating"].round(2)
    role_skill_avg = role_skill_avg[role_skill_avg["people"] >= 2].copy()

    lowest_rated = role_skill_avg.sort_values("avg_rating", ascending=True).head(10)

    if lowest_rated.empty:
        st.info(f"ℹ️ Not enough data to analyze gaps for {gap_role_pick}")
    else:
        fig = px.bar(
            lowest_rated,
            x="avg_rating",
            y="skill_label",
            orientation="h",
            labels={"avg_rating": "Average Rating", "skill_label": "Skill"},
            color="avg_rating",
            color_continuous_scale="RdYlGn",
            range_color=[0, 5],
        )
        fig.update_layout(height=450, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            lowest_rated.rename(columns={
                "skill_label": "Skill",
                "avg_rating": "Avg Rating",
                "people": "# People",
                "min_rating": "Lowest",
                "max_rating": "Highest",
            }),
            use_container_width=True,
            hide_index=True,
            height=300,
        )

    # ----------------------------
    # NEW: Service line gap analysis
    # ----------------------------
    st.markdown("<br/><br/>", unsafe_allow_html=True)
    st.markdown("##### Skills Development Opportunities by Service Line (Department)")

    gap_sl_pick = st.selectbox(
        "Select service line (department) to analyze",
        options=sorted(ratings_df["service_line"].dropna().unique()),
        key="gap_sl_pick",
    )

    gap_sl_data = ratings_df[ratings_df["service_line"] == gap_sl_pick].copy()

    sl_skill_avg = (
        gap_sl_data.groupby("skill_label")
        .agg(
            avg_rating=("rating", "mean"),
            people=("resource_id", "nunique"),
            max_rating=("rating", "max"),
            min_rating=("rating", "min"),
        )
        .reset_index()
    )
    sl_skill_avg["avg_rating"] = sl_skill_avg["avg_rating"].round(2)
    sl_skill_avg = sl_skill_avg[sl_skill_avg["people"] >= 2].copy()

    sl_lowest = sl_skill_avg.sort_values("avg_rating", ascending=True).head(10)

    if sl_lowest.empty:
        st.info(f"ℹ️ Not enough data to analyze gaps for {gap_sl_pick}")
    else:
        fig = px.bar(
            sl_lowest,
            x="avg_rating",
            y="skill_label",
            orientation="h",
            labels={"avg_rating": "Average Rating", "skill_label": "Skill"},
            color="avg_rating",
            color_continuous_scale="RdYlGn",
            range_color=[0, 5],
        )
        fig.update_layout(height=450, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            sl_lowest.rename(columns={
                "skill_label": "Skill",
                "avg_rating": "Avg Rating",
                "people": "# People",
                "min_rating": "Lowest",
                "max_rating": "Highest",
            }),
            use_container_width=True,
            hide_index=True,
            height=300,
        )

tab_index += 1

# ============================================================
# TAB: RAW DATA
# ============================================================
with tabs[tab_index]:
    st.markdown("#### 📋 Complete Skills Data")

    st.markdown(
        """
        <div class='info-row'>
            <strong>What you're seeing:</strong> All skills data in raw table format for export or analysis
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        category_filter = st.multiselect(
            "Filter by category",
            options=sorted(ratings_df["category"].unique()),
            default=sorted(ratings_df["category"].unique())[:3],
            key="raw_category",
        )

    with col2:
        min_rating_filter = st.slider(
            "Minimum rating",
            0, 5, 0,
            key="raw_min_rating",
            help="Only show skills with this rating or higher",
        )

    filtered_data = ratings_df[
        (ratings_df["category"].isin(category_filter)) &
        (ratings_df["rating"] >= min_rating_filter)
    ].copy()

    display_cols = ["full_name", "role", "service_line", "skill_label", "category", "rating"]

    st.markdown(f"**Showing {len(filtered_data)} skill entries**")
    st.dataframe(
        filtered_data[display_cols].rename(columns={
            "full_name": "Resource",
            "role": "Role",
            "service_line": "Service Line",
            "skill_label": "Skill",
            "category": "Category",
            "rating": "Rating",
        }).sort_values(["Resource", "Skill"]),
        use_container_width=True,
        hide_index=True,
        height=520,
    )

    st.markdown(
        """
        <div class='info-box'>
            <strong style='color:#48bb78;'>💡 Tip</strong><br/>
            You can copy this data to Excel or export it for further analysis
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<div style='margin: 3rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()
