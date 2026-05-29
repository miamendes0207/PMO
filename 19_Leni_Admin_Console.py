# ============================================================
# 🧷 Leni Admin Console — ScopeSight 1.0
# DB-backed Knowledge & Learning Manager
# ============================================================

import os
import streamlit as st
import pandas as pd

# Authentication & Role
from auth.login import require_login

# UI Modules
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# DB Tools
from modules.db import run_query, run_execute


# ---------------------------------------------------------
# DEV MODE OVERRIDE BOOTSTRAP
# ---------------------------------------------------------
query = st.query_params

if "dev" in query and query["dev"] == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True


# ---------------------------------------------------------
# REQUIRE LOGIN
# ---------------------------------------------------------
require_login()


# ---------------------------------------------------------
# THEME, SIDEBAR, NAV
# ---------------------------------------------------------
hide_streamlit_nav()
set_pmo_theme(page_title="🧷 Leni Admin Console")

render_sidebar()

# ---------------------------------------------------------
# CUSTOM CSS (after sidebar)
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        header[data-testid="stHeader"] {
            height: 0px !important;
            visibility: hidden !important;
        }

        /* Shared admin visual language */
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
            font-size: 1.05rem;
            font-weight: 600;
        }

        .info-box {
            background: #f0fff4;
            border-left: 4px solid #48bb78;
            padding: 1rem;
            border-radius: 4px;
            margin: 1rem 0 1.5rem 0;
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


# ---------------------------------------------------------
# ROLE VALIDATION
# ---------------------------------------------------------
role = st.session_state.get("role", "user")
if role != "admin":
    st.error("🚫 Only administrators can access the Leni Admin Console.")
    pmo_footer()
    st.stop()


# ---------------------------------------------------------
# PAGE INTRO (CENTRALISED)
# ---------------------------------------------------------

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#2f855a;'>💡 Tip</strong><br/>
    Use the tabs to move between <b>Knowledge</b>, <b>Add/Delete</b>,
    <b>Pending Auto-Learn</b> and <b>Module Rules</b>.
</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# LOAD DATA ONCE
# ---------------------------------------------------------
kb = run_query(
    """
    SELECT id, question, answer, category, client, tags, created_at
    FROM leni_knowledge
    ORDER BY created_at DESC
"""
)

pending = run_query(
    """
    SELECT id, question, answer, category, client, tags, created_at
    FROM leni_pending
    ORDER BY created_at DESC
"""
)

rules = run_query("SELECT * FROM leni_classification_rules ORDER BY module")

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_kb, tab_manage, tab_pending, tab_rules = st.tabs(
    [
        "📚 Knowledge Base Entries",
        "➕ Add / Delete Knowledge",
        "🧠 Pending Auto-Learned",
        "🧩 Module Classification / Rules",
    ]
)

# ============================================================
# TAB 1 — KNOWLEDGE BASE ENTRIES
# ============================================================
with tab_kb:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📚 Knowledge Base Entries</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if kb is not None and not kb.empty:
        with st.container():
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            st.dataframe(kb, use_container_width=True, height=350)
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Knowledge base is empty.")

    st.markdown("<hr/>", unsafe_allow_html=True)

# ============================================================
# TAB 2 — ADD / DELETE KNOWLEDGE
# ============================================================
with tab_manage:
    st.markdown(
        """
        <div class='section-header'>
            <h3>➕ Add / Delete Knowledge</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Add
    st.markdown(
        """
        <div class='step-header'>
            <h4>➕ Add Knowledge Entry</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("add_kb"):
        q = st.text_input("Question", key="kb_q")
        a = st.text_area("Answer", key="kb_a")
        cat = st.text_input("Category", key="kb_cat")
        client = st.text_input("Client (optional)", key="kb_client")
        tags = st.text_input("Tags (comma separated)", key="kb_tags")

        submit_kb = st.form_submit_button("Add Entry")

        if submit_kb:
            run_execute(
                """
                INSERT INTO leni_knowledge (question, answer, category, client, tags)
                VALUES (:q, :a, :cat, :client, :tags)
            """,
                {"q": q, "a": a, "cat": cat, "client": client, "tags": tags},
            )

            st.success("Entry added successfully.")
            st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)

    # Delete
    st.markdown(
        """
        <div class='step-header'>
            <h4>🗑️ Delete Knowledge Entry</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    delete_id = st.number_input(
        "Entry ID", min_value=0, step=1, key="delete_id"
    )

    if st.button("Delete Entry", use_container_width=False):
        run_execute(
            "DELETE FROM leni_knowledge WHERE id = :id", {"id": delete_id}
        )
        st.success("Entry deleted.")
        st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)

# ============================================================
# TAB 3 — PENDING AUTO-LEARNED ITEMS
# ============================================================
with tab_pending:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🧠 Pending Auto-Learned Entries</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if pending is not None and not pending.empty:
        with st.container():
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            st.dataframe(pending, use_container_width=True, height=350)
            st.markdown("</div>", unsafe_allow_html=True)

        # Approve
        st.markdown(
            """
            <div class='step-header'>
                <h4>✔ Approve Entry</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pid = st.number_input(
            "Entry ID to approve", min_value=0, step=1, key="approve_id"
        )

        if st.button("Approve", use_container_width=False):
            run_execute(
                """
                INSERT INTO leni_knowledge (question, answer, category, client, tags)
                SELECT question, answer, category, client, tags
                FROM leni_pending WHERE id = :id
            """,
                {"id": pid},
            )

            run_execute("DELETE FROM leni_pending WHERE id = :id", {"id": pid})
            st.success("Entry approved and added to knowledge base.")
            st.rerun()

        # Reject
        st.markdown(
            """
            <div class='step-header'>
                <h4>✖ Reject Entry</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        rid = st.number_input(
            "Entry ID to reject", min_value=0, step=1, key="reject_id"
        )

        if st.button("Reject", use_container_width=False):
            run_execute("DELETE FROM leni_pending WHERE id = :id", {"id": rid})
            st.warning("Entry rejected.")
            st.rerun()
    else:
        st.success("No pending auto-learning items — Leni is fully updated.")

    st.markdown("<hr/>", unsafe_allow_html=True)

# ============================================================
# TAB 4 — MODULE CLASSIFICATION / RULES
# ============================================================
with tab_rules:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🧩 Module Classification Rules</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if rules is not None and not rules.empty:
        with st.container():
            st.markdown('<div class="table-container">', unsafe_allow_html=True)
            st.dataframe(rules, use_container_width=True, height=350)
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No classification rules configured yet.")

    st.markdown(
        """
        <div class='step-header'>
            <h4>➕ Add Classification Rule</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("add_rule"):
        module = st.text_input("Module (e.g., 'NFR Generator')")
        keywords = st.text_input("Keywords (comma separated)")

        save_rule = st.form_submit_button("Save Rule")
        if save_rule:
            run_execute(
                """
                INSERT INTO leni_classification_rules (module, keywords)
                VALUES (:module, :keywords)
            """,
                {"module": module, "keywords": keywords},
            )

            st.success("Rule added successfully.")
            st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
