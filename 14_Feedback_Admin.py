# ============================================================
# 14_💬_Feedback_Admin.py — ScopeSight v3.2
# Admin Feedback Dashboard + Analytics (metadata-aware)
# ============================================================

import os
import json
from datetime import timedelta
import pandas as pd
import plotly.express as px
import streamlit as st

from auth.login import require_login
from modules.db import run_query
from modules.ui_hide_nav import hide_streamlit_nav
from modules.ui_sidebar import render_sidebar
from modules.ui_branding import set_pmo_theme, pmo_footer


# ============================================================
# PAGE CONFIG (MUST BE FIRST STREAMLIT CALL)
# ============================================================
st.set_page_config(
    page_title="💬 Feedback Admin",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Theme / UI (safe after set_page_config)
set_pmo_theme(page_title="💬 Feedback Admin Dashboard")
hide_streamlit_nav()

# Render sidebar BEFORE any auth stop/rerun risks
render_sidebar()

# Auth AFTER sidebar mounts
require_login()

if st.session_state.get("role") != "admin":
    st.error("⛔ You do not have permission to access this page.")
    pmo_footer()
    st.stop()


# ============================================================
# STYLES (match Project Submission Tracker / Weekly NFR look)
# ============================================================
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Shared visual language */
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 2rem 0 1rem 0;
}
.section-header h3 {
    color: white;
    margin: 0;
    font-size: 1.2rem;
    font-weight: 600;
}

.step-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1.25rem 0 1rem 0;
}
.step-header h4 {
    color: #0077be;
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
}

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
}

.nfr-card {
    background: white;
    border: 2px solid #4facfe;
    padding: 1.5rem;
    border-radius: 12px;
    margin: 1.5rem 0;
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.15);
}
.nfr-card h3 {
    color: #0077be;
    margin: 0 0 1rem 0;
    font-size: 1.3rem;
    font-weight: 600;
}

.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e6f2ff;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# INTRO (Tracker-style header + tip box)
# ============================================================
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 Tip</strong><br/>
    Use the Search & Export tab to filter and export feedback. Summary & Analytics reflects the current filtered view.
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# LOAD FEEDBACK DATA (include metadata JSONB)
# ============================================================
df = run_query("""
    SELECT
        id AS feedback_id,
        submitted_by,
        email,
        feedback_type,
        feedback,
        metadata,
        created_at
    FROM feedback_log
    ORDER BY created_at DESC
""")

if df.empty:
    st.info("ℹ️ No feedback has been submitted yet.")
    pmo_footer()
    st.stop()

df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")


# ============================================================
# METADATA NORMALISATION (JSONB -> columns)
# ============================================================
def _meta_get(meta, key):
    # meta may come back as dict (psycopg) or string (driver/config)
    if isinstance(meta, dict):
        return meta.get(key)
    if isinstance(meta, str):
        try:
            return json.loads(meta).get(key)
        except Exception:
            return None
    return None

df["context_module"] = df["metadata"].apply(lambda m: _meta_get(m, "module"))
df["user_agent"] = df["metadata"].apply(lambda m: _meta_get(m, "user_agent"))
df["session_id"] = df["metadata"].apply(lambda m: _meta_get(m, "session_id"))

# Optional: fill blanks for cleaner UX
df["context_module"] = df["context_module"].fillna("Unknown")


# ============================================================
# DEFAULT FILTERS (same logic as before, just defaulted here)
# ============================================================
min_date = df["created_at"].min().date()
max_date = df["created_at"].max().date()
default_start = max(min_date, max_date - timedelta(days=30))
default_end = max_date

# These will be overridden inside Search tab, but we need defaults
date_range = (default_start, default_end)
module_filter = []
type_filter = []
keyword = ""

# ============================================================
# MAIN TABS
# ============================================================
tab_summary, tab_search = st.tabs([
    "📈 Summary & Analytics",
    "🔎 Search & Export"
])

# ============================================================
# TAB 2 — SEARCH/FILTER + FULL TABLE + EXPORT (filters live here)
# ============================================================
with tab_search:
    st.markdown(
        """
<div class='section-header'>
    <h3>🔎 Search & Filter</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.expander("Open filters", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            date_range = st.date_input(
                "Date Range",
                (default_start, default_end),
                min_value=min_date,
                max_value=max_date,
                key="fb_date_range",
            )

        with col2:
            module_filter = st.multiselect(
                "Module:",
                sorted(df["context_module"].dropna().unique()),
                key="fb_module_filter",
            )

        with col3:
            type_filter = st.multiselect(
                "Feedback Type:",
                sorted(df["feedback_type"].dropna().unique()),
                key="fb_type_filter",
            )

        keyword = st.text_input(
            "Keyword Search (email, message, module, metadata):",
            key="fb_keyword",
        )

# ============================================================
# APPLY FILTERS (UNCHANGED LOGIC)
# ============================================================
filtered = df.copy()

start_date, end_date = date_range
filtered = filtered[
    (filtered["created_at"].dt.date >= start_date) &
    (filtered["created_at"].dt.date <= end_date)
]

if module_filter:
    filtered = filtered[filtered["context_module"].isin(module_filter)]

if type_filter:
    filtered = filtered[filtered["feedback_type"].isin(type_filter)]

if keyword.strip():
    key = keyword.lower()

    search_cols = ["submitted_by", "email", "feedback_type", "feedback",
                   "context_module", "user_agent", "session_id", "metadata"]

    filtered = filtered[
        filtered[search_cols]
        .astype(str)
        .apply(lambda row: row.str.lower().str.contains(key, na=False))
        .any(axis=1)
    ]

# ============================================================
# TAB 1 — SUMMARY OVERVIEW + ANALYTICS (reflects filtered)
# ============================================================
with tab_summary:
    st.markdown(
        """
<div class='section-header'>
    <h3>📈 Summary Overview</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    colA, colB, colC, colD = st.columns(4)
    colA.metric("Total Feedback", len(filtered))
    colB.metric("Unique Users", int(filtered["email"].nunique()))
    colC.metric("Modules Covered", int(filtered["context_module"].nunique()))
    colD.metric("Avg. Length (chars)", int(filtered["feedback"].astype(str).str.len().mean() or 0))

    st.markdown(
        """
<div class='section-header'>
    <h3>📊 Analytics</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    a1, a2, a3 = st.tabs(["📅 Over Time", "📘 By Category", "🧩 By Module"])

    with a1:
        st.markdown(
            """
<div class='step-header'>
    <h4>Feedback Submitted Per Day</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        if filtered.empty:
            st.info("No data available.")
        else:
            time_df = filtered.copy()
            time_df["date"] = time_df["created_at"].dt.date

            timeline = (
                time_df.groupby("date")
                .size()
                .reset_index(name="count")
                .sort_values("date")
            )

            chart = px.line(
                timeline,
                x="date",
                y="count",
                markers=True,
                title=None,
            )
            st.plotly_chart(chart, use_container_width=True)

    with a2:
        st.markdown(
            """
<div class='step-header'>
    <h4>Feedback by Category</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        if filtered.empty:
            st.info("No data available.")
        else:
            dist = (
                filtered.groupby("feedback_type")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            )

            chart2 = px.bar(
                dist,
                x="feedback_type",
                y="count",
                text_auto=True,
                title=None,
            )
            st.plotly_chart(chart2, use_container_width=True)

    with a3:
        st.markdown(
            """
<div class='step-header'>
    <h4>Feedback by Module</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        if filtered.empty:
            st.info("No data available.")
        else:
            mod = (
                filtered.groupby("context_module")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            )

            chart3 = px.bar(
                mod,
                x="context_module",
                y="count",
                text_auto=True,
                title=None,
            )
            st.plotly_chart(chart3, use_container_width=True)

# ============================================================
# Continue TAB 2 — FULL TABLE + EXPORT (uses filtered)
# ============================================================
with tab_search:
    st.markdown(
        """
<div class='section-header'>
    <h3>📄 Full Feedback Table</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    display_cols = [
        "feedback_id", "created_at", "context_module",
        "submitted_by", "email", "feedback_type", "feedback",
        "user_agent", "session_id"
    ]

    st.markdown('<div class="table-container">', unsafe_allow_html=True)
    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
<div class='section-header'>
    <h3>📤 Export Feedback</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    col1.download_button(
        "⬇️ Download CSV",
        data=filtered[display_cols].to_csv(index=False).encode("utf-8"),
        file_name="feedback_export.csv",
        mime="text/csv",
        use_container_width=True
    )

    excel_path = "feedback_export.xlsx"
    filtered[display_cols].to_excel(excel_path, index=False)

    with open(excel_path, "rb") as f:
        col2.download_button(
            "⬇️ Download Excel",
            data=f.read(),
            file_name=excel_path,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# ============================================================
# FOOTER
# ============================================================
pmo_footer()
