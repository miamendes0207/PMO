import streamlit as st
import base64
from pathlib import Path

# ---------------------------------------------------------
# PLENITUDE THEME
# ---------------------------------------------------------

PLENITUDE_THEME = """
<style>
:root {
    --pmo-bg: #FFFFFF;
    --pmo-text: #142D53;
    --pmo-accent: #1E74BB;
    --pmo-green: #A3C73E;
    --pmo-card-bg: #F8F9FC;
    --pmo-border: #D3D7E0;
}

/* BACKGROUND */
body, .main {
    background-color: var(--pmo-bg) !important;
    color: var(--pmo-text) !important;
}

/* TEXT */
h1, h2, h3, h4, h5, h6,
body p, 
body label, 
body span, 
body li {
    color: var(--pmo-text) !important;
}


/* BUTTONS */
.stButton > button {
    background-color: var(--pmo-text) !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    border: none !important;
    padding: 0.6rem 1rem !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 6px rgba(0,0,0,0.15);
    transition: all 0.2s ease-in-out;
}
.stButton > button:hover {
    background-color: var(--pmo-accent) !important;
    transform: scale(1.03);
}
.stButton > button * {
    color: #FFFFFF !important;
}

/* INPUTS */
.stTextInput > div > div > input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] {
    background-color: var(--pmo-card-bg) !important;
    color: var(--pmo-text) !important;
    border: 1px solid var(--pmo-border) !important;
}

/* DIVIDER */
hr {
    border: none !important;
    border-top: 3px solid var(--pmo-green) !important;
    margin: 1.5rem 0 !important;
}

/* FOOTER FIX — fully centered */
.pmo-footer {
    position: fixed;
    bottom: 0;
    width: 100% !important;
    left: 0 !important;
    right: 0 !important;
    background-color: var(--pmo-card-bg);
    border-top: 2px solid var(--pmo-green);

    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    text-align: center !important;

    padding: 12px 0;
    font-size: 0.9rem;
    color: var(--pmo-text);
    z-index: 9999 !important;
}

/* Prevent footer overlap */
.main {
    margin-bottom: 120px !important;
}

/* DROPDOWN CARD STYLE */
.scope-card {
    border: 1px solid var(--pmo-border);
    background-color: #FFFFFF;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}
.scope-card:hover {
    box-shadow: 0 4px 10px rgba(0,0,0,0.10);
    transition: 0.2s ease;
}
</style>
"""

# ---------------------------------------------------------
# APPLY THEME + HEADER
# ---------------------------------------------------------

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules.notifications_overlay import render_notifications_overlay


def set_pmo_theme(page_title: str | None = None):
    """
    Applies Plenitude theme + renders header.
    Also injects global in-app notifications overlay
    for authenticated users.
    """

    # ---------------------------------------------------------
    # GLOBAL AUTO-REFRESH (every 60 seconds)
    # ---------------------------------------------------------
    st_autorefresh(interval=600_000, key="global_refresh")

    # Apply core theme
    st.markdown(PLENITUDE_THEME, unsafe_allow_html=True)

    # Render header
    _render_header(page_title)

    # ---------------------------------------------------------
    # GLOBAL NOTIFICATIONS OVERLAY
    # ---------------------------------------------------------
    if st.session_state.get("auth"):
        email = (st.session_state.get("email") or "").strip().lower()
        if email:
            render_notifications_overlay(email)


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

def _render_header(page_title: str | None = None):
    logo_path = Path("assets/plenitude_logo.png")

    if logo_path.exists():
        encoded = base64.b64encode(logo_path.read_bytes()).decode()
        logo_html = f"<img src='data:image/png;base64,{encoded}' width='160'/>"
    else:
        logo_html = "<h1>Plenitude Consulting</h1>"

    st.markdown(
        f"""
        <div style='text-align:center; margin-top:5px;'>
            {logo_html}
            <h1 style='margin:12px 0 4px 0;'>Plenitude Consulting PMO Platform</h1>
            <p style='margin:0; font-size:1rem; color:var(--pmo-accent);'>
                Project Governance • Delivery Excellence • Automation
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    if page_title:
        st.markdown(
            f"""
            <h2 style='text-align:center; margin-top:8px; color:var(--pmo-accent);'>
                {page_title}
            </h2>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<hr/>", unsafe_allow_html=True)
# ---------------------------------------------------------
# DASHBOARD STYLING
# ---------------------------------------------------------
def apply_pmo_dashboard_styling():
    st.markdown("""
    <style>
        :root {
            --pmo-blue: #142D53;
            --pmo-accent: #1E74BB;
            --pmo-green: #A3C73E;
            --pmo-grey: #D3D7E0;
            --pmo-card: #F8F9FC;
        }

        .pmo-tile {
            background: var(--pmo-blue);
            border-radius: 14px;
            padding: 18px;
            color: white !important;        /* FORCE ALL TEXT INSIDE TO BE WHITE */
            text-align: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }

        .pmo-tile-number,
        .pmo-tile-label,
        .pmo-tile * {
            color: white !important;        /* ENSURE ALL CHILD ELEMENTS ALSO WHITE */
        }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

def pmo_footer():
    st.markdown(
        """
        <div class="pmo-footer">
            © 2026 Plenitude Consulting • ScopeSight PMO Automation Platform
        </div>
        """,
        unsafe_allow_html=True
    )






