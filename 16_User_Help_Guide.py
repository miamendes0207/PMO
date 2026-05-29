# ============================================================
# 16_🗃️_User_Help_Guide.py — ScopeSight 1.0
# Plenitude PMO User Help & Module Overview
# ============================================================

import streamlit as st

from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# ---------------------------------------------------------
# PAGE CONFIG (must be first Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="🗃️ User Help Guide",
    page_icon="🗃️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# AUTH + THEME
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🗃️ User Help Guide")
render_sidebar()

# ---------------------------------------------------------
# GLOBAL STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Section headers */
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
    text-align: center;
}

/* Module cards */
.module-card {
    border: 2px solid #4facfe;
    border-radius: 12px;
    background: #FFFFFF;
    padding: 18px;
    text-align: center;
    min-height: 210px;
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.10);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}
.module-icon { font-size: 1.7rem; margin-bottom: 8px; }
.module-title { font-size: 1.05rem; font-weight: 800; color: #0077be; }
.module-desc { font-size: 0.95rem; color: #2d3748; margin-top: 6px; line-height: 1.45; }

.leni-bubble {
    margin-bottom: 15px;
    padding: 14px;
    background: #F7F9FC;
    border-radius: 12px;
    border: 1px solid #DDE3EC;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.leni-bubble .leni-title { font-weight: 800; color: #0077be; }
.leni-bubble .leni-body { margin-top: 6px; color: #2d3748; line-height: 1.5; }

div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.05rem;
    font-weight: 600;
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

# ---------------------------------------------------------
# INTRO
# ---------------------------------------------------------
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 Tip</strong><br/>
    Your menu changes based on your role. If you can’t see a module, request access from an administrator.
</div>
""",
    unsafe_allow_html=True,
)

# =========================================================
# 🤖 LENI — TOP OF PAGE
# =========================================================
from modules.va_engine import (
    answer_question,
    record_feedback,
    suggest_new_knowledge
)

st.markdown(
    """
<div class='section-header'>
    <h3>🤖 Leni — Your PMO Assistant</h3>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>Ask anything</strong><br/>
    Ask questions about how to use the platform. Leni learns from every interaction.
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------
# SESSION STATE
# --------------------------
if "help_chat" not in st.session_state:
    st.session_state.help_chat = []

if "last_knowledge_id" not in st.session_state:
    st.session_state.last_knowledge_id = None

if "last_debug" not in st.session_state:
    st.session_state.last_debug = None

if "pending_correction" not in st.session_state:
    st.session_state.pending_correction = False

if "last_question" not in st.session_state:
    st.session_state.last_question = None

# --------------------------
# INPUT FIRST
# --------------------------
with st.form("leni_form", clear_on_submit=True):
    user_text = st.text_input("Ask Leni…", key="leni_input")
    submitted = st.form_submit_button("Send")

if submitted:
    user_query = (user_text or "").strip()
    if not user_query:
        st.warning("Please type a question first.")
    else:
        st.session_state.help_chat.append({"role": "user", "content": user_query})
        st.session_state.last_question = user_query
        st.session_state.help_chat.append({"role": "assistant", "content": "Thinking…"})
        st.rerun()

# --------------------------
# COMPUTE ANSWER
# --------------------------
if st.session_state.help_chat:
    last = st.session_state.help_chat[-1]
    if last.get("role") == "assistant" and last.get("content") == "Thinking…":
        try:
            result = answer_question(
                user_question=st.session_state.last_question,
                user_email=st.session_state.get("email"),
                client_name=st.session_state.get("client_name"),
                user_role=st.session_state.get("role"),
            )

            ai_answer = result.get("answer") or ""
            knowledge_id = result.get("knowledge_id")
            debug = result.get("debug")

            st.session_state.help_chat[-1] = {"role": "assistant", "content": ai_answer}
            st.session_state.last_knowledge_id = knowledge_id
            st.session_state.last_debug = debug
            st.session_state.pending_correction = False

        except Exception as e:
            st.session_state.help_chat[-1] = {
                "role": "assistant",
                "content": f"Sorry — something went wrong answering that. ({type(e).__name__})"
            }
            st.session_state.last_knowledge_id = None
            st.session_state.last_debug = {"ui_error": type(e).__name__}

        st.rerun()

# --------------------------
# ANSWERS UNDER INPUT
# --------------------------
MAX_MESSAGES = 8
if st.session_state.help_chat:
    st.markdown("<div class='step-header'><h4>Conversation</h4></div>", unsafe_allow_html=True)

    for msg in st.session_state.help_chat[-MAX_MESSAGES:]:
        r = msg.get("role")
        c = msg.get("content", "")

        if r == "user":
            st.markdown(
                f"""
                <div class='leni-bubble user'>
                    <div class='leni-title'>🧑 You</div>
                    <div class='leni-body'>{c}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class='leni-bubble'>
                    <div class='leni-title'>🤖 Leni</div>
                    <div class='leni-body'>{c}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("---")

# --------------------------
# FEEDBACK
# --------------------------
if st.session_state.last_knowledge_id is not None:
    st.markdown("<div class='step-header'><h4>Feedback</h4></div>", unsafe_allow_html=True)
    st.markdown("Was this helpful?")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("👍 Yes", key="leni_yes"):
            record_feedback(
                knowledge_id=st.session_state.last_knowledge_id,
                rating=+1,
                user_email=st.session_state.get("email"),
            )
            st.success("Thanks! Leni appreciates your feedback")
            st.session_state.last_knowledge_id = None
            st.session_state.pending_correction = False
            st.rerun()

    with col2:
        if st.button("👎 No", key="leni_no"):
            st.warning("Thanks — help Leni improve by suggesting a better answer.")
            st.session_state.pending_correction = True

if st.session_state.pending_correction:
    corrected = st.text_area("How should Leni answer this question?", key="leni_correction_box")

    if st.button("Submit correction", key="leni_submit_correction"):
        if not (corrected or "").strip():
            st.warning("Please type a corrected answer first.")
        else:
            suggest_new_knowledge(
                question=st.session_state.get("last_question"),
                answer=corrected,
                user_email=st.session_state.get("email"),
            )
            st.success("Thanks! Your suggestion has been submitted for admin review.")
            st.session_state.pending_correction = False
            st.session_state.last_knowledge_id = None
            st.rerun()

# =========================================================
# MODULE HELP CONTENT (UPDATED TO MATCH YOUR MENU LIST)
# =========================================================
def module_card(icon: str, title: str, desc: str):
    st.markdown(
        f"""
        <div class="module-card">
            <div class="module-icon">{icon}</div>
            <div class="module-title">{title}</div>
            <div class="module-desc">{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str):
    st.markdown(
        f"""
<div class='section-header'>
    <h3>{title}</h3>
</div>
""",
        unsafe_allow_html=True,
    )


MODULES = {
    "🧠 Meeting Intelligence": [
        ("🧾", "Daily NFR Generator", "Generate structured Notes for Record from Teams transcripts."),
        ("📘", "Weekly NFR Consolidator", "Merge daily NFRs into weekly client-ready summaries."),
    ],
    "⚠️ RAID & Action Management": [
        ("📌", "RAID Log Assistant", "AI-assisted creation of risks, issues, dependencies and actions."),
        ("📝", "Action Register Manager", "Extract, track and manage actions across delivery."),
        ("💡", "RAIDs Log", "Maintain RAID register with scoring, status, owners and mitigations."),
    ],
    "📄 Reporting & Governance": [
        ("📊", "Governance Pack Dashboard", "Generate executive-ready governance packs using project data."),
        ("📂", "Template Library", "Central repository of reusable PMO templates for consistent delivery."),
    ],
    # Full Delivery & Resourcing set (admin/user view)
    "📦 Delivery & Resourcing": [
        ("🧑‍🔧", "Resource Allocation Manager", "Edit allocations, manage capacity, skills filters and visibility."),
        ("📅", "Gannt Chart Builder", "Build and manage a project Gantt, assign resources, track delivery."),
        ("🔋", "Capacity Manager", "Plan capacity, track utilisation, forecast demand."),
        ("👥", "Bench Management", "View resources who are unallocated or underutilised."),
        ("🎯", "Skills Distribution", "Skills and gap analysis across teams / portfolio."),
        ("🧩", "My Work", "Your personal work queue across actions, RAID items and assigned tasks."),
    ],
    # Exec version excludes My Work + Gannt Chart Builder
    "📦 Delivery & Resourcing (Exec)": [
        ("🧑‍🔧", "Resource Allocation Manager", "Edit allocations, manage capacity, skills filters and visibility."),
        ("🔋", "Capacity Manager", "Plan capacity, track utilisation, forecast demand."),
        ("👥", "Bench Management", "View resources who are unallocated or underutilised."),
        ("🎯", "Skills Distribution", "Skills and gap analysis across teams / portfolio."),
    ],
    "🚀 Coming Soon": [
        ("🔧", "SharePoint Connector", "Export documents and packs directly to SharePoint. (Coming soon)"),
    ],
    "👤 User Tools": [
        ("⚙️", "Project Configuration Manager", "Create and manage project profiles, templates and settings."),
        ("🧮", "Project Submission Tracker", "Track project submissions, approvals and rejections."),
    ],
    "⚙️ Settings": [
        ("👤", "My Profile", "View and update your account details and password."),
        ("🔔", "Notifications Manager", "Manage notifications"),
    ],
    "🙋 Support": [
        ("🗃️", "User Help Guide", "This module—overview of platform features and how to use them."),
    ],
    "CEO Tools": [
        ("📈", "Portfolio Overview", "Portfolio-wide delivery snapshot across assigned accounts."),
        ("🏢", "Client Performance", "Compare client delivery trends and operational effectiveness."),
        ("🗂️", "Resource Distribution", "High-level view of resource distribution across the business."),
    ],
    "🧑‍💼 Executive Tools": [
        ("📈", "Client Summary", "High-level client snapshot: status, KPIs, risks and actions."),
        ("📊", "Project Summary", "Executive overview of project health, milestones, risks and actions."),
        ("🧭", "Portfolio Pipeline", "Forward-looking pipeline view across initiatives and demand."),
    ],
    "🛠️ Admin Tools": [
        ("🔐", "User Access Manager", "Manage user accounts, roles and module permissions."),
        ("🪪", "Project Setup", "Review and approve new project setup submissions."),
        ("🎛️", "Clients Admin", "Create, approve and manage clients."),
        ("🔄", "Admin Resource Pool", "Maintain resource records, skills, availability and active status."),
        ("💬", "Feedback Manager", "Review user feedback and refine knowledge responses."),
    ],
    "🤖 Leni System": [
        ("💡", "Leni Knowledge Analytics", "Analyse knowledge coverage, accuracy and trends."),
        ("🧷", "Leni Admin Console", "Manage Leni knowledge base and approve new suggestions."),
    ],
    "⚙️ System & Audit": [
        ("📜", "Activity Log Viewer", "Audit platform activity for troubleshooting and governance."),
        ("🔋", "OpenAI Quota Status", "Monitor API usage, consumption limits and remaining quota."),
    ],
}


def show_section(title: str, items: list[tuple[str, str, str]], cols: int = 3):
    section_header(title)
    n = max(1, cols)
    rows = [items[i:i+n] for i in range(0, len(items), n)]
    for r in rows:
        cs = st.columns(n)
        for i in range(n):
            with cs[i]:
                if i < len(r):
                    icon, name, desc = r[i]
                    module_card(icon, name, desc)
                else:
                    st.empty()


role = st.session_state.get("role", "user")

# ADMIN: everything
if role == "admin":
    show_section("🧠 Meeting Intelligence", MODULES["🧠 Meeting Intelligence"], cols=2)
    show_section("⚠️ RAID & Action Management", MODULES["⚠️ RAID & Action Management"], cols=3)
    show_section("📄 Reporting & Governance", MODULES["📄 Reporting & Governance"], cols=3)
    show_section("📦 Delivery & Resourcing", MODULES["📦 Delivery & Resourcing"], cols=3)
    show_section("👤 User Tools", MODULES["👤 User Tools"], cols=3)
    show_section("⚙️ Settings", MODULES["⚙️ Settings"], cols=2)
    show_section("🙋 Support", MODULES["🙋 Support"], cols=2)
    show_section("🧑‍💼 Executive Tools", MODULES["🧑‍💼 Executive Tools"], cols=3)
    show_section("CEO Tools", MODULES["CEO Tools"], cols=3)
    show_section("🛠️ Admin Tools", MODULES["🛠️ Admin Tools"], cols=3)
    show_section("🤖 Leni System", MODULES["🤖 Leni System"], cols=3)
    show_section("⚙️ System & Audit", MODULES["⚙️ System & Audit"], cols=3)
    show_section("🚀 Coming Soon", MODULES["🚀 Coming Soon"], cols=3)

# EXEC: Exec tools + exec delivery/resourcing + settings/support
elif role == "exec":
    show_section("🧑‍💼 Executive Tools", MODULES["🧑‍💼 Executive Tools"], cols=2)
    show_section("📦 Delivery & Resourcing", MODULES["📦 Delivery & Resourcing (Exec)"], cols=3)
    show_section("⚙️ Settings", MODULES["⚙️ Settings"], cols=2)
    show_section("🙋 Support", MODULES["🙋 Support"], cols=2)

# CEO: CEO tools + settings/support
elif role == "ceo":
    show_section("CEO Tools", MODULES["CEO Tools"], cols=3)
    show_section("⚙️ Settings", MODULES["⚙️ Settings"], cols=2)
    show_section("🙋 Support", MODULES["🙋 Support"], cols=2)

# USER: main modules + delivery/resourcing + tools + settings/support
elif role == "user":
    show_section("🧠 Meeting Intelligence", MODULES["🧠 Meeting Intelligence"], cols=2)
    show_section("⚠️ RAID & Action Management", MODULES["⚠️ RAID & Action Management"], cols=3)
    show_section("📄 Reporting & Governance", MODULES["📄 Reporting & Governance"], cols=3)
    show_section("📦 Delivery & Resourcing", MODULES["📦 Delivery & Resourcing"], cols=3)
    show_section("👤 User Tools", MODULES["👤 User Tools"], cols=3)
    show_section("⚙️ Settings", MODULES["⚙️ Settings"], cols=2)
    show_section("🙋 Support", MODULES["🙋 Support"], cols=2)

# VIEWER: only what they can see (per your list)
else:
    show_section("🧠 Meeting Intelligence", MODULES["🧠 Meeting Intelligence"], cols=2)
    show_section("⚠️ RAID & Action Management", MODULES["⚠️ RAID & Action Management"], cols=3)
    show_section("📄 Reporting & Governance", MODULES["📄 Reporting & Governance"], cols=3)

    # viewer Delivery & Resourcing: only My Work (per your tuple list)
    section_header("📦 Delivery & Resourcing")
    c1, c2, c3 = st.columns(3)
    with c1:
        module_card("🧩", "My Work", "Your personal work queue across actions, RAID items and assigned tasks.")
    with c2:
        st.empty()
    with c3:
        st.empty()

    show_section("⚙️ Settings", MODULES["⚙️ Settings"], cols=2)
    show_section("🙋 Support", MODULES["🙋 Support"], cols=2)

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
