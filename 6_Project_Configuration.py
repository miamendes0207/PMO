# ============================================================
# 6_⚙️_Project_Configuration.py — ScopeSight v2.3 (RAIDs Designer)
# Project Profile Creator (Tiered + Pending Approval Workflow)
# + Design-your-own RAIDs Log (optional fields + custom fields)
#
# FIXES vs v2.2:
# - mitigation fields always included in enabled_optional_fields payload
#   (so RAIDs log can find them via the standard path)
# - date_raised added as toggleable optional field
# - raids_config is stored BOTH at top-level settings.raids_config AND
#   as the top-level 'raids' key so Project Setup Approval has one
#   canonical source to copy when promoting to live
# ============================================================

import re
import json
import streamlit as st
from datetime import date

from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.log_utils import log_event
from modules.notifications_utils import send_notification
from auth.login import require_login
from modules.ui_hide_nav import hide_streamlit_nav
from modules.db import run_query, run_execute

# ============================================================
# 1️⃣ PAGE CONFIG (MUST BE FIRST)
# ============================================================
st.set_page_config(
    page_title="⚙️ Project Configuration",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 2️⃣ AUTH + NAV + THEME
# ============================================================
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="⚙️ Project Configuration Manager")

# ============================================================
# 3️⃣ SIDEBAR
# ============================================================
render_sidebar()

# ---------------------------------------------------------
# GLOBAL PAGE CSS
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height:0 !important; visibility:hidden !important; }

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

.info-row {
    background: #f0f9ff;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    border-radius: 6px;
    border-left: 4px solid #4facfe;
}
.info-row strong { color: #0077be; }

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

.small-muted { color:#64748b; font-size:0.9rem; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
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
    <strong style='color:#48bb78;'>💡 Workflow</strong><br/>
    Complete each section top-to-bottom, then submit for approval. An administrator will review and promote it to a live project.
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================
# SECTION 1 — PROJECT DETAILS
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>📁 Project Details</h3>
</div>
""",
    unsafe_allow_html=True,
)

# Client selection
clients_df = run_query(
    """
    SELECT id AS client_id, client_name, client_code
    FROM client_scaffold
    WHERE status = 'approved'
    ORDER BY client_name
"""
)

if clients_df is None or clients_df.empty:
    st.error("❌ No approved clients exist. Create & approve a client before adding a project.")
    st.stop()

client_map = {
    f"{row.client_name} ({row.client_code})": (row.client_id, row.client_name, row.client_code)
    for _, row in clients_df.iterrows()
}

selected_label = st.selectbox("Select Parent Client *", list(client_map.keys()))
client_id, client_name, client_code = client_map[selected_label]

# Project metadata
st.markdown(
    """
<div class='step-header'>
    <h4>Project Metadata</h4>
</div>
""",
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)
with col1:
    project_name = st.text_input("Project Name *")
    project_code = st.text_input("Project Code (3–6 letters, e.g., DIGIP) *").upper()
    project_manager = st.text_input("Project Manager (optional)")

with col2:
    project_start = st.date_input("Project Start Date *")
    expected_end = st.date_input("Expected End Date (optional)", value=None)
    description = st.text_area("Project Description (optional)", "Enter a short description.", height=112)

# Service Line
st.markdown(
    """
<div class='step-header'>
    <h4>Service Line Ownership</h4>
</div>
""",
    unsafe_allow_html=True,
)

SERVICE_LINE_OPTIONS = ["Fraud", "Advisory & Transformation", "Tech & Data", "Other"]

sl1, sl2 = st.columns([4, 2])
with sl1:
    service_line = st.selectbox(
        "Service Line *",
        SERVICE_LINE_OPTIONS,
        index=0,
        help="Used for portfolio reporting and colouring (Exec Gantt / Pipeline).",
    )
with sl2:
    service_line_other = ""
    if service_line == "Other":
        service_line_other = st.text_input("Specify", placeholder="e.g., Strategy")

service_line_final = (service_line_other or "").strip() if service_line == "Other" else service_line

# ============================================================
# SECTION 2 — DELIVERY TIER
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>🏷️ Delivery Tier</h3>
</div>
""",
    unsafe_allow_html=True,
)

tier_choice = st.radio(
    "Select Project Tier",
    ["Tier 1 – 🔵 Strategic / High Governance", "Tier 2 – 🟢 Standard / Flexible"],
)
tier_value = "tier_1" if tier_choice.startswith("Tier 1") else "tier_2"

col_t1, col_t2 = st.columns(2)
with col_t1:
    st.markdown(
        """
        <div class="nfr-card" style="border-color:#1E3A8A; height:240px; display:flex; flex-direction:column; justify-content:flex-start;">
            <h3 style="color:#1E3A8A; margin-bottom:1rem;">🔵 Tier 1 – High Governance</h3>
            <div class="info-row" style="border-left-color:#1E3A8A; flex:1;">
                <strong>What you get</strong><br/>
                • Data-driven progress, risks, dependencies, performance overview.<br/>
                • In-depth narrative with forward-looking strategic insights.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_t2:
    st.markdown(
        """
        <div class="nfr-card" style="border-color:#166534; height:240px; display:flex; flex-direction:column; justify-content:flex-start;">
            <h3 style="color:#166534; margin-bottom:1rem;">🟢 Tier 2 – Standard Delivery</h3>
            <div class="info-row" style="border-left-color:#166534; flex:1;">
                <strong>What you get</strong><br/>
                • Concise, high-level summary of status, milestones, and priority risks.<br/>
                • Essential information for routine oversight with minimal overhead.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# SECTION 3 — PROJECT ACCESS
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>🔐 Project Access List</h3>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>Who can access this project?</strong><br/>
    Add participants and assign their access role. This list is saved with the submission and applied when the project is approved.
</div>
""",
    unsafe_allow_html=True,
)

role_options = {"CEO": "ceo", "Executive": "exec", "User": "user", "Viewer": "viewer"}

if "project_access_rows" not in st.session_state:
    st.session_state.project_access_rows = [{"email": st.session_state.get("email"), "role": "user"}]


def add_access_row():
    st.session_state.project_access_rows.append({"email": "", "role": "viewer"})


remove_indices = []

for idx, row in enumerate(st.session_state.project_access_rows):
    c1, c2, c3 = st.columns([5, 3, 1])

    with c1:
        row["email"] = st.text_input(f"Email {idx+1}", value=row["email"], key=f"email_{idx}")

    with c2:
        label_list = list(role_options.keys())
        value_list = list(role_options.values())
        current_val = row.get("role") or "viewer"
        sel_index = value_list.index(current_val) if current_val in value_list else value_list.index("viewer")
        picked_label = st.selectbox(f"Role {idx+1}", label_list, index=sel_index, key=f"role_{idx}")
        row["role"] = role_options.get(picked_label, "user")

    with c3:
        st.write("")  # vertical alignment nudge
        st.write("")
        if st.button("❌", key=f"remove_{idx}"):
            remove_indices.append(idx)

for i in sorted(remove_indices, reverse=True):
    del st.session_state.project_access_rows[i]

st.button("➕ Add Person", on_click=add_access_row)

access_list = [
    {"email": r["email"].strip(), "role": (r.get("role") or "viewer")}
    for r in st.session_state.project_access_rows
    if (r.get("email") or "").strip()
]

# ============================================================
# SECTION 4 — PROJECT BRANDING
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>🎨 Project Branding</h3>
</div>
""",
    unsafe_allow_html=True,
)

colB1, colB2 = st.columns(2)
with colB1:
    brand_primary = st.color_picker("Primary Colour", "#142D53")
with colB2:
    brand_secondary = st.color_picker("Secondary Colour", "#1E74BB")

# ============================================================
# SECTION 5 — RAIDs LOG DESIGN
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>📌 RAIDs Log Design (Optional)</h3>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>Personalise this project's RAIDs log</strong><br/>
    Choose which optional RAID fields you want, then add any extra client-specific fields.
    Mitigation fields are always included and cannot be disabled.
</div>
""",
    unsafe_allow_html=True,
)

# ── Always-on fields (never shown as toggleable, always in the payload) ──
ALWAYS_ON_FIELDS = ["mitigation_plan", "mitigation_status"]

# ── Optional fields the user can toggle ──
# NOTE: date_raised added here so it can be configured per-project.
OPTIONAL_FIELDS = [
    ("date_raised",    "Date Raised"),
    ("owner_plen",     "Plenitude Owner"),
    ("owner_client",   "Client Owner"),
    ("probability",    "Probability (1–5)"),
    ("severity",       "Severity (1–5)"),
    ("planned_close",  "Planned Closure Date"),
    ("next_review",    "Next Review Date"),
    ("related_issue",  "Related Reference"),
    ("comments",       "Comments"),
]

DEFAULT_OPTIONAL = {"date_raised", "owner_plen", "planned_close", "probability", "severity"}

st.markdown("#### Optional columns")
st.caption("Mitigation Plan and Mitigation Status are always enabled for all projects.")

selected_optional: list[str] = list(ALWAYS_ON_FIELDS)  # always included

cA, cB = st.columns(2)
for i, (k, label) in enumerate(OPTIONAL_FIELDS):
    with (cA if i % 2 == 0 else cB):
        if st.checkbox(label, value=(k in DEFAULT_OPTIONAL), key=f"raid_opt_{k}"):
            selected_optional.append(k)

st.markdown("---")
st.markdown("#### Custom fields (client-specific)")

if "raid_custom_fields" not in st.session_state:
    st.session_state.raid_custom_fields = []


def _mk_snake(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9_ ]+", "", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def add_custom_field():
    st.session_state.raid_custom_fields.append(
        {"key": "", "label": "", "type": "text", "required": False, "options": ""}
    )


FIELD_TYPES = ["text", "number", "date", "select", "multiselect", "checkbox"]

st.button("➕ Add custom field", on_click=add_custom_field)

remove_cf = []
for idx, cf in enumerate(st.session_state.raid_custom_fields):
    cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([2, 3, 2, 1, 3, 1])

    with cc1:
        raw_key = st.text_input(
            "Key",
            value=cf.get("key", ""),
            key=f"cf_key_{idx}",
            help="Stored as JSON. Use snake_case (e.g., steering_ref).",
        )
        cf["key"] = _mk_snake(raw_key)
        if raw_key and cf["key"] != raw_key.strip().lower():
            st.caption(f"Normalised: `{cf['key']}`")

    with cc2:
        cf["label"] = st.text_input("Label", value=cf.get("label", ""), key=f"cf_label_{idx}")

    with cc3:
        cf["type"] = st.selectbox(
            "Type",
            FIELD_TYPES,
            index=FIELD_TYPES.index(cf.get("type", "text")) if cf.get("type", "text") in FIELD_TYPES else 0,
            key=f"cf_type_{idx}",
        )

    with cc4:
        cf["required"] = st.checkbox("Req", value=bool(cf.get("required", False)), key=f"cf_req_{idx}")

    with cc5:
        cf["options"] = st.text_input(
            "Options (comma-separated)",
            value=cf.get("options", ""),
            key=f"cf_opts_{idx}",
            help="Only used for select / multiselect types.",
        )

    with cc6:
        st.write("")
        st.write("")
        if st.button("❌", key=f"cf_rm_{idx}"):
            remove_cf.append(idx)

for i in sorted(remove_cf, reverse=True):
    del st.session_state.raid_custom_fields[i]

# ── Build raids_config payload ──
custom_fields_clean = []
seen_keys = set()
for cf in st.session_state.raid_custom_fields:
    k = (cf.get("key") or "").strip()
    label = (cf.get("label") or "").strip()
    if not k or not label or k in seen_keys:
        continue
    seen_keys.add(k)
    entry = {
        "key": k,
        "label": label,
        "type": (cf.get("type") or "text").lower(),
        "required": bool(cf.get("required", False)),
    }
    if entry["type"] in ["select", "multiselect"]:
        entry["options"] = [o.strip() for o in (cf.get("options") or "").split(",") if o.strip()]
    custom_fields_clean.append(entry)

raids_config = {
    "enabled_optional_fields": selected_optional,   # includes ALWAYS_ON_FIELDS
    "custom_fields": custom_fields_clean,
    "rules": {"require_mitigation_for": ["Risk", "Issue"]},
}

# ============================================================
# SUBMIT
# ============================================================
st.markdown("<br/>", unsafe_allow_html=True)

if st.button("📨 Submit Project for Approval", use_container_width=True):

    if not (project_name or "").strip():
        st.error("⚠ Project name is required.")
        st.stop()

    if not (project_code or "").strip():
        st.error("⚠ Project code is required.")
        st.stop()

    if not re.fullmatch(r"[A-Z]{3,6}", (project_code or "").strip().upper()):
        st.error("⚠ Project code must be 3–6 letters (A–Z).")
        st.stop()

    if not (service_line_final or "").strip():
        st.error("⚠ Service Line is required.")
        st.stop()

    submitted_by_email = st.session_state.get("email")

    # settings block — raids_config lives INSIDE settings too so the
    # RAIDs log (which reads settings.raids_config) gets it after approval.
    settings_block = {
        "tier": tier_value,
        "branding": {"primary": brand_primary, "secondary": brand_secondary},
        "raids_config": raids_config,
    }

    try:
        run_execute(
            """
            INSERT INTO project_scaffold (
                client_id,
                client_name,
                project_name,
                project_code,
                tier,
                service_line,
                description,
                project_start_date,
                expected_end_date,
                project_manager,
                submitted_by,
                submitted_on,
                access_list,
                raids_config,
                actions_config,
                nfr_config,
                settings,
                status
            )
            VALUES (
                :client_id,
                :client_name,
                :project_name,
                :project_code,
                :tier,
                :service_line,
                :description,
                :project_start_date,
                :expected_end_date,
                :project_manager,
                (SELECT user_id FROM users WHERE email = :submitted_email),
                NOW(),
                CAST(:access_list AS jsonb),
                CAST(:raids AS jsonb),
                CAST(:actions AS jsonb),
                CAST(:nfr AS jsonb),
                CAST(:settings AS jsonb),
                'awaiting_approval'
            )
        """,
            {
                "client_id": client_id,
                "client_name": client_name,
                "project_name": project_name.strip(),
                "project_code": project_code.strip(),
                "tier": tier_value,
                "service_line": service_line_final,
                "description": description,
                "project_start_date": project_start,
                "expected_end_date": expected_end,
                "project_manager": project_manager,
                "submitted_email": submitted_by_email,
                "access_list": json.dumps(access_list),
                "raids": json.dumps(raids_config),   # top-level raids_config column
                "actions": json.dumps({}),
                "nfr": json.dumps({}),
                "settings": json.dumps(settings_block),  # also nested for RAIDs log read path
            },
        )

    except Exception as err:
        st.error(f"❌ Could not save project scaffold: {err}")
        st.stop()

    log_event(
        "project_submitted",
        {
            "project_name": project_name,
            "project_code": project_code,
            "client": client_name,
            "tier": tier_value,
            "service_line": service_line_final,
            "submitted_email": submitted_by_email,
            "raids_config": raids_config,
        },
    )

    send_notification(
        "project_submitted",
        {
            "project_name": project_name,
            "client_name": client_name,
            "service_line": service_line_final,
            "submitted_email": submitted_by_email,
        },
    )

    st.success(f"✅ Project '{project_name}' has been submitted for approval!")
    st.info("Awaiting approval in the Project Setup Approval console.")

pmo_footer()