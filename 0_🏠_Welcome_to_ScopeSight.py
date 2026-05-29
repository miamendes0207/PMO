## ============================================================
# 0_🏠_Welcome_to_ScopeSight.py — ScopeSight 1.0
# ============================================================

import sys, os
from datetime import timedelta

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import json

from auth.login import require_login
from modules.db import run_query, run_execute
from modules.export_pdf import export_dashboard_pdf
from modules.ui_branding import set_pmo_theme, apply_pmo_dashboard_styling, pmo_footer
from modules.ui_hide_nav import hide_streamlit_nav
from modules.ui_sidebar import render_sidebar, get_accessible_module_labels


# ------------------------------------------------------------
# PAGE CONFIG
# ------------------------------------------------------------
st.set_page_config(
    page_title="Welcome to ScopeSight",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# AUTH FIRST
require_login()

# THEME FIRST
set_pmo_theme(page_title="🏠 Welcome to ScopeSight")

# HIDE STREAMLIT OG SIDEBAR
hide_streamlit_nav()

# ---------------------------------------------------------
# STYLES
# ---------------------------------------------------------
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
    text-align: center;
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

/* Keep existing tile styling as-is (functional UI component), just reduce vertical gaps slightly */
</style>
""",
    unsafe_allow_html=True,
)

# SIDEBAR LAST
render_sidebar()


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def normalize(df: pd.DataFrame | None):
    """Convert DB result → list[dict] safely."""
    if df is None:
        return []
    if isinstance(df, pd.DataFrame):
        if df.empty:
            return []
        return df.to_dict(orient="records")
    return df


def safe_count(sql: str, params: dict | None = None) -> int:
    """Run COUNT(*) query safely and return 0 on error/empty."""
    df = run_query(sql, params)
    if df is None or df.empty:
        return 0
    return int(df.iloc[0][0])


def pmo_tile(icon: str, label: str, value, color: str = "#142D53"):
    st.markdown(
        f"""
        <div style="
            background:{color};
            padding:18px;
            border-radius:12px;
            color:white;
            text-align:center;
            box-shadow:0 3px 8px rgba(0,0,0,0.15);
        ">
            <div style="font-size:2rem; font-weight:800;">{icon}</div>
            <div style="font-size:2.2rem; font-weight:900; margin-top:2px;">{value}</div>
            <div style="font-size:1.1rem; opacity:0.95; margin-top:4px;">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# ROLE DISPATCH
# ============================================================

import modules.role_dashboards as rd

role = st.session_state.get("role", "viewer")
user_id = st.session_state.get("user_id")

if role == "ceo":
    rd.render_ceo_dashboard(user_id)
elif role == "exec":
    rd.render_exec_dashboard(user_id)
elif role == "user":
    rd.render_user_dashboard(user_id)
elif role == "viewer":
    rd.render_viewer_dashboard(user_id)
else:
    rd.render_admin_dashboard(user_id)

# ============================================================
# FEEDBACK & SUPPORT SECTION
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>💬 Feedback & Support</h3>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>Need help or have an idea?</strong><br/>
    Share your suggestions, report issues, or request enhancements for ScopeSight below.
</div>
""",
    unsafe_allow_html=True,
)

# Make sure feedback_log exists
create_feedback_sql = """
CREATE TABLE IF NOT EXISTS feedback_log (
    id SERIAL PRIMARY KEY,
    submitted_by TEXT,
    email TEXT,
    feedback_type TEXT NOT NULL,
    feedback TEXT NOT NULL,
    module_name TEXT,
    user_agent TEXT,
    session_id TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
"""
run_execute(create_feedback_sql)

with st.expander("✍️ Submit feedback", expanded=True):
    with st.form("feedback_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            feedback_type = st.selectbox(
                "Feedback category:",
                ["Feature Request", "Bug Report", "General Feedback", "Support Request"],
            )

        with col2:
            role = st.session_state.get("role", "user")

            # ✅ DB-role driven list from sidebar registry
            module_options = get_accessible_module_labels(role) or []
            if "Other / Not Sure" not in module_options:
                module_options.append("Other / Not Sure")

            module_name = st.selectbox("Related module:", module_options)

        user_name = st.text_input(
            "Your Name (optional)", value=st.session_state.get("full_name", "")
        )
        user_email = st.text_input(
            "Contact Email (optional)", value=st.session_state.get("email", "")
        )

        feedback_text = st.text_area(
            "Describe your feedback:",
            placeholder="Please provide as much detail as possible…",
        )

        submitted = st.form_submit_button("Submit Feedback", use_container_width=True)

        if submitted:
            if not feedback_text.strip():
                st.warning("⚠️ Please enter some feedback before submitting.")
            else:
                insert_sql = """
                INSERT INTO feedback_log (
                    submitted_by, email, feedback_type, feedback, module_name, user_agent, session_id
                )
                VALUES (:submitted_by, :email, :feedback_type, :feedback, :module_name, :user_agent, :session_id)
                """
                run_execute(
                    insert_sql,
                    {
                        "submitted_by": user_name
                        or st.session_state.get("email", "Unknown User"),
                        "email": user_email or "Not Provided",
                        "feedback_type": feedback_type,
                        "feedback": feedback_text.strip(),
                        "module_name": module_name,
                        "user_agent": st.session_state.get("user_agent", "Unknown"),
                        "session_id": st.session_state.get("session_id", "Unknown"),
                    },
                )

                st.success("✅ Thank you! Your feedback has been submitted.")
                st.balloons()


# ------------------------------------------------------------
# FOOTER
# ------------------------------------------------------------
st.markdown("<hr/>", unsafe_allow_html=True)
pmo_footer()
