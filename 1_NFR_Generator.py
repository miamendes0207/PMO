# ============================================================
# 1_📘_NFR_Generator.py — ScopeSight v3.2 (Enhanced UI)
# Daily NFR Generator (client_scaffold → projects)
# Fully updated to properly route DAILY NFRs to daily_nfr table
# ============================================================

import streamlit as st
import datetime as dt
import time
import os
import json
from docx import Document
import logging

# DB utilities
from modules.db import run_query

# Auth
from auth.login import require_login

# UI + Layout
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# NFR generator (core engine + safe wrapper)
from modules.nfr.nfr_generator import generate_nfr_safe
from modules.nfr.nfr_daily import save_daily_nfr

# Tier-aware background agent imports (OpenAI-backed)
from modules.nfr.nfr_agent_T1 import analyse_transcript_with_agent_t1
from modules.nfr.nfr_agent_T2 import analyse_transcript_with_agent_t2

# Logging
from modules.log_utils import log_event

logger = logging.getLogger("nfr_engine")

from modules.db import notify
from modules.notifications_overlay import render_notifications_overlay


# -----------------------------------------------------------
# Auth & Layout Bootstrap
# -----------------------------------------------------------
set_pmo_theme(page_title="🧾 NFR Generator")
render_sidebar()
hide_streamlit_nav()

st.markdown("""
<style>
header[data-testid="stHeader"] { 
    height: 0px !important; 
    visibility: hidden !important; 
}

/* Enhanced card styling */
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

.nfr-card .info-row {
    background: #f0f9ff;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border-radius: 6px;
    border-left: 4px solid #4facfe;
}

.nfr-card .info-row strong {
    color: #0077be;
}

/* Section headers */
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

/* Info boxes */
.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
    height: 100%;
}

/* Upload area styling */
.upload-section {
    background: #ffffff;
    border: 2px dashed #4facfe;
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
    margin: 1rem 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

/* Generate button enhancement */
div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.1rem;
    font-weight: 600;
    padding: 0.75rem 2rem;
    border: none;
    border-radius: 8px;
    transition: all 0.3s ease;
}

div.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 12px rgba(79, 172, 254, 0.4);
}

/* Results card */
.results-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 2rem;
    margin: 2rem 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
</style>
""", unsafe_allow_html=True)

require_login()
current_email = st.session_state.get("email")
current_role = st.session_state.get("role", "user")

render_notifications_overlay(current_email or "")


# ============================================================
# Helpers
# ============================================================
def _parse_json(value):
    """Safe JSON parse for DB JSONB fields."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _load_user_id(email: str):
    if not email:
        return None
    df = run_query("SELECT user_id FROM users WHERE email = :email", {"email": email})
    if df is None or df.empty:
        return None
    return int(df.iloc[0]["user_id"])


def _resolve_tier_from_client_config(client_config: dict) -> str:
    tier = (
        client_config.get("tier")
        or client_config.get("project_tier")
        or "T2"
    )
    tier = str(tier).strip().upper()
    if tier not in ("T1", "T2"):
        tier = "T2"
    return tier


# ============================================================
# CLIENT → PROJECT SELECTOR
# ============================================================
def select_project():
    user_id = _load_user_id(current_email)

    # ---------------------------
    # 1) Load allowed clients
    # ---------------------------
    if current_role in ("admin", "ceo", "exec"):
        clients = run_query("""
            SELECT 
                id AS client_id,
                client_name,
                client_code,
                settings
            FROM client_scaffold
            WHERE status = 'approved'
            ORDER BY client_name
        """)
    else:
        clients = run_query("""
            SELECT DISTINCT
                cs.id AS client_id,
                cs.client_name,
                cs.client_code,
                cs.settings
            FROM client_scaffold cs
            JOIN projects p ON p.client_id = cs.id
            JOIN user_project_permissions upp ON upp.project_id = p.project_id
            WHERE cs.status = 'approved'
              AND upp.user_id = :uid
            ORDER BY cs.client_name
        """, {"uid": user_id})

    if clients is None or clients.empty:
        return None, None, None, None, None, {}, None, "T2"

    client_label = st.selectbox("Select Client", clients["client_name"])
    row = clients[clients["client_name"] == client_label].iloc[0]

    client_id = int(row["client_id"])
    client_name = row["client_name"]
    client_code = row.get("client_code")
    client_config = _parse_json(row.get("settings")) or {}

    # Resolve tier from client config (since projects.settings doesn't exist)
    client_tier = _resolve_tier_from_client_config(client_config)

    # ---------------------------
    # 2) Load projects for client (NO settings column)
    # ---------------------------
    if current_role in ("admin", "ceo", "exec"):
        projects = run_query("""
            SELECT 
                project_id,
                project_name,
                project_code
            FROM projects
            WHERE client_id = :cid
            ORDER BY project_name
        """, {"cid": client_id})
    else:
        projects = run_query("""
            SELECT DISTINCT
                p.project_id,
                p.project_name,
                p.project_code
            FROM projects p
            JOIN user_project_permissions upp ON upp.project_id = p.project_id
            WHERE p.client_id = :cid
              AND upp.user_id = :uid
            ORDER BY p.project_name
        """, {"cid": client_id, "uid": user_id})

    if projects is None or projects.empty:
        return None, None, client_name, client_id, client_code, client_config, None, client_tier

    projects = projects.copy()
    projects["label"] = projects.apply(
        lambda r: f"{r['project_name']} ({r['project_code']})"
        if r["project_code"] else r["project_name"],
        axis=1,
    )

    project_label = st.selectbox("Select Project", projects["label"])
    selected_row = projects[projects["label"] == project_label].iloc[0]

    project_id = int(selected_row["project_id"])
    project_name = selected_row["project_name"]
    project_code = selected_row["project_code"]

    # Project tier currently inherits from client tier
    project_tier = client_tier

    return (
        project_name,
        project_id,
        client_name,
        client_id,
        client_code,
        client_config,
        project_code,
        project_tier,
    )

# -----------------------------------------------------------
# Project Selection Card
# -----------------------------------------------------------
st.markdown("""
<div class='section-header'>
    <h3>📁 Project Selection</h3>
</div>
""", unsafe_allow_html=True)

selection = select_project()

if not selection or selection[0] is None:
    st.error("⚠ No project selected or available.")
    pmo_footer()
    st.stop()

project_name, project_id, client_name, client_id, client_code, client_config, project_code, project_tier = selection

# ============================================================
# TRANSCRIPT INPUT
# ============================================================
st.markdown("""
<div class='section-header'>
    <h3>📤 Transcript Input</h3>
</div>
""", unsafe_allow_html=True)

st.markdown("<p style='color: #666; margin: 1rem 0;'>Upload a transcript file or paste your meeting notes below</p>",
            unsafe_allow_html=True)

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("<div class='upload-section'>", unsafe_allow_html=True)
    uploaded = st.file_uploader("📎 Upload Transcript", ["txt", "docx"], help="Supported formats: .txt, .docx")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class='info-box'>
        <strong style='color: #48bb78;'>💡 Quick Tips</strong><br/>
        <span style='color: #2d3748;'>• Supported formats: .txt, .docx<br/>
        • Maximum file size: 200MB<br/>
        • Paste text directly below if preferred</span>
    </div>
    """, unsafe_allow_html=True)

manual_text = st.text_area("✍️ Or paste transcript text here:", height=200,
                           placeholder="Paste your meeting transcript or notes here...")

text = None

if uploaded:
    if uploaded.name.lower().endswith(".txt"):
        raw = uploaded.getvalue()
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("latin-1", errors="ignore")
        st.success(f"✅ Loaded: {uploaded.name}")

    elif uploaded.name.lower().endswith(".docx"):
        doc = Document(uploaded)
        text = "\n".join(p.text for p in doc.paragraphs)
        st.success(f"✅ Loaded: {uploaded.name}")

elif manual_text.strip():
    text = manual_text

# ============================================================
# MEETING DETAILS
# ============================================================
st.markdown("""
<div class='section-header'>
    <h3>📝 Meeting Details</h3>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    meeting_name = st.text_input(
        "📋 Meeting Name",
        client_config.get("meeting_title", f"{project_name} – Project Meeting"),
    )

    meeting_date = st.date_input("📅 Meeting Date", dt.date.today())

with col2:
    meeting_time = st.text_input(
        "🕐 Meeting Time",
        client_config.get("default_time", "10:00"),
    )

    meeting_location = st.text_input(
        "📍 Location",
        client_config.get("default_location", "Microsoft Teams"),
    )

generated_by = st.text_input(
    "👤 Generated By",
    client_config.get("generated_by", current_email or "ScopeSight PMO Automation"),
)

# Overrides passed into NFR generator
overrides = {
    "MEETING_NAME": meeting_name,
    "DATE": meeting_date.strftime("%d/%m/%Y"),
    "TIME": meeting_time,
    "LOCATION": meeting_location,
    "Generated By": generated_by,
    "CLIENT_NAME": client_name,
    "CLIENT_CODE": client_code,
    "PROJECT_NAME": project_name,
    "PROJECT_CODE": project_code,
    "PROJECT_TIER": project_tier,
}

# ============================================================
# GENERATE NFR
# ============================================================
st.markdown("<div style='margin: 3rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)

if st.button("🚀 Generate NFR Document", use_container_width=True, type="primary"):

    if not text or len(text.strip()) < 10:
        st.error("⚠ Transcript is empty or too short. Please provide meeting notes.")
        st.stop()

    progress = st.progress(0, "Processing…")
    time.sleep(0.2)
    progress.progress(25, "Parsing transcript…")

    input_identifier = client_code

    # ------------------------------------------------------------
    # TIER-AWARE BACKGROUND AGENT STEP (OpenAI-backed)
    # ------------------------------------------------------------
    progress.progress(35, f"Analysing transcript (agent {project_tier})…")
    try:
        if project_tier == "T1":
            agent_out = analyse_transcript_with_agent_t1(
                text=text,
                overrides=overrides,
                client_config=client_config,
            )
        else:
            agent_out = analyse_transcript_with_agent_t2(
                text=text,
                overrides=overrides,
                client_config=client_config,
            )
    except Exception as e:
        st.error(f"❌ Agent analysis failed ({project_tier}): {e}")
        pmo_footer()
        st.stop()

    final_overrides = {**overrides, **(getattr(agent_out, "derived_overrides", None) or {})}
    final_text = getattr(agent_out, "cleaned_text", None) or text

    # ------------------------------------------------------------
    # GENERATE NFR (existing generator)
    # ------------------------------------------------------------
    with st.spinner("🔄 Generating NFR…"):
        result, error = generate_nfr_safe(input_identifier, agent_out.structured_data, final_overrides)

    if error:
        st.error(f"❌ Error generating NFR: {error}")
        pmo_footer()
        st.stop()

    # ------------------------------------------------------------
    # SAVE DAILY NFR TO DATABASE
    # ------------------------------------------------------------
    try:
        engine_payload = {
            "agent_tier": project_tier,
            "agent_structured_data": getattr(agent_out, "structured_data", None),
            "agent_flags": getattr(agent_out, "flags", None),
            "final_overrides": final_overrides,
            "generator_structured_data": getattr(result, "structured_data", None),
        }

        record_id = save_daily_nfr(
            client_id=client_id,
            project_id=project_id,
            meeting_title=meeting_name,
            engine_output=engine_payload,
            generated_by=generated_by,
        )
        progress.progress(50, "Saving to database…")

        # ------------------------------------------------------------
        # NOTIFICATIONS (new system): NFR generated
        # ------------------------------------------------------------
        try:
            notify(
                event_type="nfr.generated",
                title=f"NFR generated: {meeting_name}",
                body=(
                    f"Client: {client_name}\n"
                    f"Project: {project_name}\n"
                    f"Meeting date: {meeting_date.strftime('%d/%m/%Y')}\n"
                    f"Record ID: {record_id}"
                ),
                severity="info",
                project_id=project_id,
                client_id=client_id,
                created_by=(current_email or "").strip().lower(),
                meta={
                    "entity_type": "daily_nfr",
                    "entity_id": int(record_id) if record_id is not None else None,
                    "meeting_title": meeting_name,
                },
            )
        except Exception:
            # Never break NFR flow due to notifications
            pass

    except Exception as e:
        st.error(f"⚠️ Could not save Daily NFR to DB: {e}")
        st.stop()

    progress.progress(70, "Formatting document…")
    time.sleep(0.3)
    progress.progress(100, "Done!")

    st.markdown("<div style='margin: 2rem 0;'></div>", unsafe_allow_html=True)
    st.success("🎉 NFR generated successfully!")

    # ----------------------------
    # LOG EVENT
    # ----------------------------
    log_event(
        "generated_nfr",
        {
            "client": client_name,
            "client_id": client_id,
            "client_code": client_code,
            "project": project_name,
            "project_id": project_id,
            "project_code": project_code,
            "project_tier": project_tier,
            "filename": os.path.basename(result.doc_path),
        },
    )

    # ----------------------------
    # RESULTS SECTION
    # ----------------------------
    st.markdown("""
    <div class='results-card'>
        <h3 style='color: #0077be; margin-top: 0;'>📊 NFR Generation Complete</h3>
        <p style='color: #666;'>Your Notes for Record has been generated and saved to the database.</p>
    </div>
    """, unsafe_allow_html=True)

    # Download button
    with open(result.doc_path, "rb") as f:
        file_bytes = f.read()

    st.download_button(
        "📄 Download NFR Document",
        file_bytes,
        file_name=os.path.basename(result.doc_path),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
        type="primary"
    )

    # ----------------------------
    # STRUCTURED DATA EXPANDER
    # ----------------------------
    with st.expander("🔍 View Extracted NFR Structure", expanded=False):
        st.subheader(f"Agent Output ({project_tier})")
        st.json(getattr(agent_out, "structured_data", {}) or {})

        flags = getattr(agent_out, "flags", None) or []
        if flags:
            st.subheader("Agent Flags")
            st.write(flags)

        st.subheader("Generator Structured Data")
        st.json(getattr(result, "structured_data", {}) or {})

    st.info(f"💾 Saved to database with Record ID: {record_id}")

# -----------------------------------------------------------
# FOOTER
# -----------------------------------------------------------
st.markdown("<div style='margin: 4rem 0 2rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()
