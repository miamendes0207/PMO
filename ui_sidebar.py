# ============================================================
# ui_sidebar.py — ScopeSight v2.2 (DB-role driven)
# Unified Sidebar + Single Source of Truth for page visibility
# (Admin / CEO / Exec / User / Viewer)
# ============================================================

import streamlit as st
from pathlib import Path


# ------------------------------------------------------------
# PAGE SWITCH HELPER
# ------------------------------------------------------------
def go_to_page(page_path: str):
    try:
        st.switch_page(page_path)
    except Exception:
        st.error("Page navigation is not supported in this Streamlit version.")


# ------------------------------------------------------------
# LOGOUT HANDLER
# ------------------------------------------------------------
def _logout():
    st.session_state.clear()
    st.session_state["auth"] = False
    st.rerun()


# ------------------------------------------------------------
# SIDEBAR CSS
# ------------------------------------------------------------
SIDEBAR_STYLE = """
<style>
[data-testid="stSidebar"] .block-container {
    padding-top: 1.6rem;
}

/* Avatar bubble */
.scopesight-avatar {
    width:78px;
    height:78px;
    border-radius:50%;
    background:#1E74BB;
    color:white;
    font-size:2.2rem;
    display:flex;
    align-items:center;
    justify-content:center;
    margin:0 auto 8px auto;
    box-shadow:0 3px 12px rgba(0,0,0,0.15);
}

/* Email / Role label */
.scopesight-email {
    text-align:center;
    margin-top:4px;
    font-weight:600;
    font-size:1rem;
    color:#142D53;
}

/* Logout button */
.logout-button > button {
    background-color:#1E74BB !important;
    color:white !important;
    border-radius:8px !important;
    width:100% !important;
}

/* Home button wrap */
.home-btn-wrap > button {
    background-color:#1E74BB !important;
    color:white !important;
    border-radius:8px !important;
    width:100% !important;
}

/* Hide Streamlit default Pages nav (so only our sidebar shows) */
[data-testid="stSidebarNav"] {
    display: none !important;
}
</style>
"""


# ============================================================
# SINGLE SOURCE OF TRUTH: NAV REGISTRY
# Each item:
#   group, page_path, label, roles_allowed
# Notes:
# - roles are DB-driven via st.session_state["role"]
# - labels are what you should show in Feedback module selectbox
# ============================================================
NAV_REGISTRY = [
    # --- Meeting Intelligence ---
    ("🧠 Meeting Intelligence", "pages/1_NFR_Generator.py", "🧾 Daily NFR Generator", {"admin", "user", "viewer"}),
    ("🧠 Meeting Intelligence", "pages/2_Weekly_NFR.py", "📘 Weekly NFR Consolidator", {"admin", "user", "viewer"}),

    # --- RAID & Action ---
    ("⚠️ RAID & Action Management", "pages/3_RAID_Log_Assistant.py", "📌 RAID Log Assistant", {"admin", "user", "viewer"}),
    ("⚠️ RAID & Action Management", "pages/4_Action_Manager.py", "📝 Action Register Manager", {"admin", "user", "viewer"}),
    ("⚠️ RAID & Action Management", "pages/23_RAIDs_Log.py", "💡 RAIDs Log", {"admin", "user", "viewer"}),

    # --- Reporting & Governance ---
    ("📄 Reporting & Governance", "pages/5_Governance_Pack_Dashboard.py", "📊 Governance Pack Dashboard", {"admin", "user", "viewer"}),
    ("📄 Reporting & Governance", "pages/15_Template_Library.py", "📂 Template Library", {"admin", "user", "viewer"}),

    # --- Delivery & Resourcing ---
    ("📦 Delivery & Resourcing", "pages/28_Resource_Allocation_Manager.py", "🧑‍🔧 Resource Allocation Manager", {"admin", "exec", "user"}),
    ("📦 Delivery & Resourcing", "pages/29_Project_Gannt.py", "📅 Gannt Chart Builder", {"admin", "user"}),
    ("📦 Delivery & Resourcing", "pages/31_Capacity_Management.py", "🔋 Capacity Manager", {"admin", "exec"}),
    ("📦 Delivery & Resourcing", "pages/27_Bench_Management.py", "👥 Bench Management", {"admin", "exec"}),
    ("📦 Delivery & Resourcing", "pages/32_Skills_Distribution.py", "🎯 Skills Distribution", {"admin", "exec"}),
    ("📦 Delivery & Resourcing", "pages/30_My_Work.py", "🧩 My Work", {"admin", "viewer", "user"}),

    # --- Coming soon ---
    ("🚀 Coming Soon", "pages/7_Sharepoint_Connector.py", "🔧 SharePoint Connector", {"admin"}),

    # --- User Tools ---
    ("👤 User Tools", "pages/6_Project_Configuration.py", "⚙️ Project Configuration Manager", {"admin", "user"}),
    ("👤 User Tools", "pages/13_Project_Submission_Tracker.py", "🧮 Project Submission Tracker", {"admin", "user"}),

    # --- Settings ---
    ("⚙️ Settings", "pages/10_My_Profile.py", "👤 My Profile", {"admin", "user", "ceo", "exec", "viewer"}),
    ("⚙️ Settings", "pages/8_Notifications_Manager.py", "🔔 Notifications Manager", {"admin", "user", "exec", "viewer", "ceo"}),

    # --- Support ---
    ("🙋 Support", "pages/16_User_Help_Guide.py", "🗃️ User Help Guide", {"admin", "user", "viewer", "ceo", "exec"}),

    # --- CEO Tools ---
    ("CEO Tools", "pages/24_CEO_Client_Performance.py", "🏢 Client Performance", {"admin", "ceo"}),
    ("CEO Tools", "pages/33_Resource_Distribution.py", "🗂️ Resource Distribution", {"admin", "ceo"}),

    # --- Executive Tools ---
    ("🧑‍💼 Executive Tools", "pages/25_Exec_Client_Summary.py", "📈 Client Summary", {"admin", "exec"}),
    ("🧑‍💼 Executive Tools", "pages/26_Exec_Project_Summary.py", "📊 Project Summary", {"admin", "exec"}),
    ("🧑‍💼 Executive Tools", "pages/34_Portfolio_Pipeline.py", "🧭 Portfolio Pipeline", {"admin", "exec"}),

    # --- Admin Tools ---
    ("🛠️ Admin Tools", "pages/9_User_Access_Manager.py", "🔐 User Access Manager", {"admin"}),
    ("🛠️ Admin Tools", "pages/11_Project_Setup_Approval.py", "🪪 Project Setup", {"admin"}),
    ("🛠️ Admin Tools", "pages/20_Admin_Clients.py", "🎛️ Clients Admin", {"admin"}),
    ("🛠️ Admin Tools", "pages/21_Admin_Resource_Pool.py", "🔄 Admin Resource Pool", {"admin"}),
    ("🛠️ Admin Tools", "pages/14_Feedback_Admin.py", "💬 Feedback Manager", {"admin"}),
    ("🛠️ Admin Tools","pages/22_RAG_Engine.py", "RAG Engine", {"admin"}),

    # --- Leni System ---
    ("🤖 Leni System", "pages/18_Leni_Knowledge_Analytics.py", "💡 Leni Knowledge Analytics", {"admin"}),
    ("🤖 Leni System", "pages/19_Leni_Admin_Console.py", "🧷 Leni Admin Console", {"admin"}),


    # --- System & Audit ---
    ("⚙️ System & Audit", "pages/12_Activity_Log_Viewer.py", "📜 Activity Log Viewer", {"admin"}),
    ("⚙️ System & Audit", "pages/17_OpenAI_Quota_Status.py", "🔋 OpenAI Quota Status", {"admin"}),
]


# ------------------------------------------------------------
# DB-ROLE FILTER HELPERS (reused by Sidebar + Feedback form)
# ------------------------------------------------------------
def _norm_role(role: str) -> str:
    return (role or "user").strip().lower()


def get_allowed_nav_items(role: str):
    """
    Returns NAV_REGISTRY items that the role can access.
    Each item is (group, path, label, roles_allowed).
    """
    role = _norm_role(role)
    return [item for item in NAV_REGISTRY if role in item[3]]


def get_accessible_module_labels(role: str) -> list[str]:
    """
    Clean unique list of labels suitable for a Feedback 'Related module' selectbox.
    (No group headings, just page labels.)
    """
    allowed = get_allowed_nav_items(role)
    labels = sorted({label for (_group, _path, label, _roles) in allowed})
    return labels


def _group_items(items):
    """
    Convert flat NAV_REGISTRY items into:
      { group_name: [(path, label), ...], ...}
    preserving original order.
    """
    grouped = {}
    for group, path, label, _roles in items:
        grouped.setdefault(group, []).append((path, label))
    return grouped


# ------------------------------------------------------------
# LOGIN SIDEBAR
# ------------------------------------------------------------
def render_login_sidebar():
    """
    Login-only sidebar:
    - White background
    - Deep Plenitude navy border (#192B56)
    - Centered logo
    - Secure-access callout box
    - Footer pinned to bottom
    """
    st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)

    st.markdown(
        """
        <style>
        /* Sidebar container */
        [data-testid="stSidebar"] {
            background: #FFFFFF !important;
            border-right: 4px solid #192B56 !important;
            box-shadow: 2px 0 12px rgba(0,0,0,0.05);
        }

        /* Flex column for sticky footer */
        [data-testid="stSidebar"] .block-container {
            padding-top: 1.4rem !important;
            display: flex !important;
            flex-direction: column !important;
            min-height: 100vh !important;
        }

        /* Center text by default */
        [data-testid="stSidebar"] * {
            text-align: center;
        }

        /* Headings */
        [data-testid="stSidebar"] h2 {
            color: #192B56 !important;
            font-weight: 900 !important;
            margin-bottom: 0.2rem !important;
        }

        [data-testid="stSidebar"] h3 {
            color: #192B56 !important;
            font-weight: 800 !important;
            margin-top: 0.2rem !important;
            margin-bottom: 0.4rem !important;
        }

        /* Secure access callout box */
        .login-secure-box {
            background: #F5F9FF;
            border: 1px solid #C7DBF2;
            border-radius: 10px;
            padding: 0.9rem 0.8rem;
            margin: 0.8rem 0 1rem 0;
            font-size: 0.85rem;
            color: #142D53;
            line-height: 1.4;
        }

        /* Footer pinned to bottom */
        .login-sidebar-footer {
            margin-top: auto !important;
            padding: 0.9rem 0 0.6rem 0;
            font-size: 0.75rem;
            color: #6B7280;
            line-height: 1.35;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        # Centered logo
        col_l, col_c, col_r = st.columns([1, 3, 1])
        with col_c:
            logo_path = Path("assets/plenitude_logo.png")
            if logo_path.exists():
                st.image(str(logo_path), width=180)

        # Titles
        st.markdown("## ScopeSight 1.0")
        st.markdown("### Plenitude Consulting")
        st.caption("PMO Automation Platform")

        st.divider()

        # Secure access box
        st.markdown(
            """
            <div class="login-secure-box">
                <strong>Secure access required</strong><br/>
                Contact your PMO administrator for access.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Footer
        st.markdown(
            '<div class="login-sidebar-footer">'
            "© 2026 Plenitude Consulting • ScopeSight PMO Automation Platform"
            "</div>",
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------
# SHARED PROFILE SECTION
# ------------------------------------------------------------
def _render_user_profile_section():
    email = st.session_state.get("email", "Unknown User")
    role = st.session_state.get("role", "user")

    initials = "".join([p[0].upper() for p in email.split("@")[0].split(".") if p])

    st.sidebar.markdown(
        f"""
        <div class="scopesight-avatar">{initials}</div>
        <div class="scopesight-email">{email}</div>
        <div style='text-align:center; font-size:0.85rem; opacity:0.7;'>{role}</div>
        <hr/>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# SECTION TITLE
# ------------------------------------------------------------
def sidebar_section_title(title: str):
    st.sidebar.divider()
    st.sidebar.markdown(
        f"<div style='text-align:center; font-weight:800; font-size:1.3rem;'>{title}</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)


# ------------------------------------------------------------
# HOME BUTTON
# ------------------------------------------------------------
def sidebar_home_button():
    st.sidebar.markdown("<div class='home-btn-wrap'>", unsafe_allow_html=True)
    if st.sidebar.button("🏠 Home", key="home_btn", use_container_width=True):
        go_to_page("0_🏠_Welcome_to_ScopeSight.py")
    st.sidebar.markdown("</div>", unsafe_allow_html=True)


# ------------------------------------------------------------
# GENERIC NAV RENDERER
# ------------------------------------------------------------
def _render_grouped_nav(grouped_pages: dict, expanded_default: bool = False):
    """
    grouped_pages: { group_name: [(path, label), ...], ... }
    """
    for group_name, pages in grouped_pages.items():
        with st.sidebar.expander(group_name, expanded=expanded_default):
            for path, label in pages:
                st.page_link(path, label=label)


# ============================================================
# ROLE SIDEBARS
#  - pages come from NAV_REGISTRY.
# ============================================================

def render_admin_sidebar():
    role = "admin"
    allowed = get_allowed_nav_items(role)
    grouped = _group_items(allowed)

    with st.sidebar:
        st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)
        _render_user_profile_section()

        if st.sidebar.button("🔒 Logout", key="logout_top_admin", use_container_width=True):
            _logout()

        # Main navigation (core groups + delivery)
        sidebar_section_title("ScopeSight Navigation")
        main_groups_order = [
            "🧠 Meeting Intelligence",
            "⚠️ RAID & Action Management",
            "📄 Reporting & Governance",
            "📦 Delivery & Resourcing",
            "🚀 Coming Soon",
            "👤 User Tools",
            "⚙️ Settings",
            "🙋 Support",
        ]
        main_grouped = {g: grouped[g] for g in main_groups_order if g in grouped}
        _render_grouped_nav(main_grouped, expanded_default=False)

        # CEO Navigation section
        sidebar_section_title("CEO Navigation")
        if "CEO Tools" in grouped:
            with st.sidebar.expander("CEO Navigation", expanded=False):
                for path, label in grouped["CEO Tools"]:
                    st.page_link(path, label=label)

        # Exec Navigation section
        if "🧑‍💼 Executive Tools" in grouped:
            with st.sidebar.expander("🧑‍💼 Exec Navigation", expanded=False):
                for path, label in grouped["🧑‍💼 Executive Tools"]:
                    st.page_link(path, label=label)

        # Admin tools section
        sidebar_section_title("Admin Navigation")
        admin_groups_order = ["🛠️ Admin Tools", "🤖 Leni System", "⚙️ System & Audit"]
        admin_grouped = {g: grouped[g] for g in admin_groups_order if g in grouped}
        _render_grouped_nav(admin_grouped, expanded_default=False)

        sidebar_home_button()


def render_ceo_sidebar():
    role = "ceo"
    allowed = get_allowed_nav_items(role)
    grouped = _group_items(allowed)

    with st.sidebar:
        st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)
        _render_user_profile_section()

        if st.sidebar.button("🔒 Logout", key="logout_top_ceo", use_container_width=True):
            _logout()

        sidebar_section_title("ScopeSight Navigation")

        # CEO tools
        if "CEO Tools" in grouped:
            with st.sidebar.expander("CEO Tools", expanded=False):
                for path, label in grouped["CEO Tools"]:
                    st.page_link(path, label=label)

        # Support (help guide)
        support_pages = []
        if "🙋 Support" in grouped:
            support_pages = [(p, l) for (p, l) in grouped["🙋 Support"] if "Help Guide" in l]
        if support_pages:
            with st.sidebar.expander("🙋 Support", expanded=False):
                for path, label in support_pages:
                    st.page_link(path, label=label)

                # Delivery & Resourcing
                if "⚙️ Settings" in grouped:
                    with st.sidebar.expander("⚙️ Settings", expanded=False):
                        for path, label in grouped["⚙️ Settings"]:
                            st.page_link(path, label=label)

        sidebar_home_button()


def render_exec_sidebar():
    role = "exec"
    allowed = get_allowed_nav_items(role)
    grouped = _group_items(allowed)

    with st.sidebar:
        st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)
        _render_user_profile_section()

        if st.sidebar.button("🔒 Logout", key="logout_top_exec", use_container_width=True):
            _logout()

        sidebar_section_title("ScopeSight Navigation")

        # Exec tools
        if "🧑‍💼 Executive Tools" in grouped:
            with st.sidebar.expander("🧑‍💼 Executive Tools", expanded=False):
                for path, label in grouped["🧑‍💼 Executive Tools"]:
                    st.page_link(path, label=label)

        # Delivery & Resourcing
        if "📦 Delivery & Resourcing" in grouped:
            with st.sidebar.expander("📦 Delivery & Resourcing", expanded=False):
                for path, label in grouped["📦 Delivery & Resourcing"]:
                    st.page_link(path, label=label)

                # Support (help guide)
                support_pages = []
                if "🙋 Support" in grouped:
                    support_pages = [(p, l) for (p, l) in grouped["🙋 Support"] if "Help Guide" in l]
                if support_pages:
                    with st.sidebar.expander("🙋 Support", expanded=False):
                        for path, label in support_pages:
                            st.page_link(path, label=label)

        # Delivery & Resourcing
        if "⚙️ Settings" in grouped:
            with st.sidebar.expander("⚙️ Settings", expanded=False):
                for path, label in grouped["⚙️ Settings"]:
                    st.page_link(path, label=label)


        sidebar_home_button()


def render_user_sidebar():
    role = "user"
    allowed = get_allowed_nav_items(role)
    grouped = _group_items(allowed)

    with st.sidebar:
        st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)
        _render_user_profile_section()

        if st.sidebar.button("🔒 Logout", key="logout_top_user", use_container_width=True):
            _logout()

        sidebar_section_title("ScopeSight Navigation")

        groups_order = [
            "🧠 Meeting Intelligence",
            "⚠️ RAID & Action Management",
            "📄 Reporting & Governance",
            "📦 Delivery & Resourcing",
            "👤 User Tools",
            "🙋 Support",
            "⚙️ Settings",
        ]
        ordered = {g: grouped[g] for g in groups_order if g in grouped}
        _render_grouped_nav(ordered, expanded_default=False)

        sidebar_home_button()


def render_viewer_sidebar():
    role = "viewer"
    allowed = get_allowed_nav_items(role)
    grouped = _group_items(allowed)

    with st.sidebar:
        st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)
        _render_user_profile_section()

        if st.sidebar.button("🔒 Logout", key="logout_top_viewer", use_container_width=True):
            _logout()

        sidebar_section_title("ScopeSight Navigation")

        groups_order = [
            "🧠 Meeting Intelligence",
            "⚠️ RAID & Action Management",
            "📄 Reporting & Governance",
            "📦 Delivery & Resourcing",
            "👤 User Tools",
            "🙋 Support",
            "⚙️ Settings",
        ]

        ordered = {g: grouped[g] for g in groups_order if g in grouped}
        _render_grouped_nav(ordered, expanded_default=False)

        sidebar_home_button()


# ============================================================
# MAIN ROUTING
# ============================================================
def render_sidebar():
    role = _norm_role(st.session_state.get("role", "user"))

    if role == "admin":
        render_admin_sidebar()
    elif role == "ceo":
        render_ceo_sidebar()
    elif role == "exec":
        render_exec_sidebar()
    elif role == "viewer":
        render_viewer_sidebar()
    else:
        render_user_sidebar()
