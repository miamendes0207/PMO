import streamlit as st

def hide_streamlit_nav():
    st.markdown("""
    <style>

        /* Hide Streamlit top header */
        header[data-testid="stHeader"] {
            visibility: hidden !important;
            height: 0 !important;
        }

        /* Hide the main navigation container (most versions) */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        /* Hide new Streamlit navigation container (2024–2025 builds) */
        div[data-testid="stSidebarNavItems"] {
            display: none !important;
        }

        /* Hide nav blocks inside sidebar */
        nav[data-testid="stSidebarNav"] {
            display: none !important;
        }

        /* Hide navigation by role (older Streamlit versions) */
        nav[aria-label="Main navigation"] {
            display: none !important;
        }

        /* Hide UL-based navigation lists */
        ul[data-testid="stSidebarNav"] {
            display: none !important;
        }

        /* Hide the container that wraps page links (experimental builds) */
        div[aria-label="Main menu"] {
            display: none !important;
        }

        /* Kill any nav element under the sidebar */
        [data-testid="stSidebar"] nav {
            display: none !important;
        }

        /* Prevent empty nav space from collapsing weirdly */
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 0 !important;
        }

    </style>
    """, unsafe_allow_html=True)
