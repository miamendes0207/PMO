# ============================================================
# 3_📌_RAIDs_Log_Assistant.py — ScopeSight v4.5.0
# RAIDs Log Assistant — Styled to match Project Configuration
#
# FIXES vs v4.4.5:
# - load_raids_config_for_project now has a reliable 3-tier read path:
#     1. projects.settings  -> settings["raids_config"]   (primary — written on approval)
#     2. project_settings table key "raids_config"        (secondary / fallback)
#     3. projects.raids_config column                     (legacy fallback)
# - mitigation_plan and mitigation_status are now written on INSERT
#   (add_raid_entry already filters to real table columns, so they are
#    inserted only when those columns exist in the raids table)
# - "owner_client" bind key is always provided to ensure_add_raid_binds
#   so add_raid_entry never raises a missing-bind error
# ============================================================

from __future__ import annotations

import datetime as dt
import json
from typing import Dict, Any, List

import pandas as pd
import streamlit as st

from modules.ui_hide_nav import hide_streamlit_nav
from auth.login import require_login
from modules.db import (
    run_query,
    run_execute,
    add_raid_entry,
    save_raid_file,  # noqa: F401
    notify,
)
from modules.raids.raids_ai import expand_shorthand_entry
from modules.raids.raids_config import BRAND_COLOURS  # noqa: F401
from modules.log_utils import log_event
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.permissions import get_project_member_emails
from modules.notifications_overlay import render_notifications_overlay


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="📌 RAIDs Assistant",
    page_icon="📌",
    layout="wide",
)

require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="📌 RAIDs Assistant")
render_sidebar()

try:
    render_notifications_overlay(st.session_state.get("email", ""))
except Exception:
    pass


# ============================================================
# STYLES
# ============================================================
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height:0 !important; visibility:hidden !important; }
.block-container { padding-top: 1.25rem; padding-bottom: 2rem; }

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

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
}

.raid-type-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1.25rem 0 1rem 0;
    display: flex;
    align-items: center;
    gap: 0.75rem;
}
.raid-type-header.risk         { border-left-color: #dc2626; background: #fff5f5; }
.raid-type-header.assumption   { border-left-color: #2563eb; background: #eff6ff; }
.raid-type-header.issue        { border-left-color: #f59e0b; background: #fffbeb; }
.raid-type-header.dependency   { border-left-color: #7c3aed; background: #f5f3ff; }

.raid-type-title { font-size: 1.1rem; font-weight: 700; margin: 0; color: #0f172a; }

.raid-counts { margin-left: auto; display: flex; align-items: center; gap: 0.4rem; }
.pill {
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    color: #0077be;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
    white-space: nowrap;
}
.pill.total  { background: #f0f9ff; border-color: #bae6fd; color: #0077be; }
.pill.open   { background: #ecfeff; border-color: #a5f3fc; color: #0369a1; }
.pill.closed { background: #f1f5f9; border-color: #cbd5e1; color: #334155; }

.raid-card-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin-bottom: 1rem;
}
.raid-card-title { font-size: 1.05rem; font-weight: 700; color: #0f172a; margin: 0; }
.raid-card-meta  { font-size: 0.88rem; color: #64748b; margin-top: 0.3rem; }

.mitigation-container {
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-left: 4px solid #f59e0b;
    border-radius: 6px;
    padding: 0.9rem 1rem;
    margin: 0.75rem 0;
}
.mitigation-empty {
    background: #fef2f2;
    border: 1px dashed #ef4444;
    border-radius: 6px;
    padding: 0.75rem;
    text-align: center;
    color: #991b1b;
    font-weight: 700;
}

.ai-section {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin: 0.75rem 0 1rem 0;
}
.ai-title { font-size: 1rem; font-weight: 700; color: #0077be; margin: 0; }

div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white !important;
    font-size: 1rem;
    font-weight: 600;
    padding: 0.65rem 1.5rem;
    border: none !important;
    border-radius: 8px;
    transition: all 0.2s ease;
}
div.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 12px rgba(79, 172, 254, 0.35);
}
label { font-weight: 600 !important; }
.small-muted { color:#64748b; font-size:0.9rem; }
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CONSTANTS & HELPERS
# ============================================================
RAID_TYPE_ICONS = {
    "Risk": "🔴",
    "Assumption": "🔵",
    "Issue": "🟠",
    "Dependency": "🟣",
}

STATUS_OPTIONS = ["Open", "Amber", "Red", "Green", "Closed", "Completed"]
CLOSED_STATUSES = {"closed", "completed"}

ADD_RAID_REQUIRED_BINDS = [
    "client_id", "project_id", "raid_type", "type", "title", "description", "comments",
    "probability", "severity", "score",
    "new_probability", "new_severity", "revised_score",
    "owner_plen", "owner_client", "raised_by", "internal_external",
    "status", "date_raised", "planned_close", "date_closed", "next_review",
    "related_issue", "modified_by",
    # mitigation — add_raid_entry filters to real cols so these are safe to include
    "mitigation_plan", "mitigation_status",
]


def normalize_raid_type(rt: str) -> str:
    if not rt:
        return "Risk"
    mapping = {
        "risk": "Risk", "risks": "Risk",
        "assumption": "Assumption", "assumptions": "Assumption",
        "issue": "Issue", "issues": "Issue",
        "dependency": "Dependency", "dependencies": "Dependency",
    }
    return mapping.get(str(rt).strip().lower(), str(rt).strip().capitalize())


def normalize_status(s: str) -> str:
    s0 = (s or "").strip()
    if not s0:
        return "Open"
    low = s0.lower()
    mapping = {
        "open": "Open", "amber": "Amber", "red": "Red",
        "green": "Green", "closed": "Closed", "completed": "Completed",
    }
    return mapping.get(low, s0[:1].upper() + s0[1:])


def is_closed_status(s: str) -> bool:
    return (s or "").strip().lower() in CLOSED_STATUSES


def _safe_date(v):
    try:
        if pd.isna(v) or v is None:
            return None
        if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
            return v
        return pd.to_datetime(v).date()
    except Exception:
        return None


def _json_dict(v) -> dict:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            out = json.loads(v)
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}
    return {}


def calculate_score_level(score: int) -> str:
    if score <= 5:
        return "low"
    if score <= 12:
        return "medium"
    return "high"


def _priority_from(score: int, status: str) -> str:
    s = (status or "").strip().lower()
    if s in CLOSED_STATUSES:
        return "Closed"
    if s == "red":
        return "Critical"
    if s == "amber":
        return "High"
    lvl = calculate_score_level(int(score or 0))
    return {"high": "High", "medium": "Medium", "low": "Low"}.get(lvl, "Medium")


def _notify_safe(event_type: str, payload: dict):
    for fn in [
        lambda: notify(event_type, payload),
        lambda: notify(event_type=event_type, **payload),
        lambda: notify({**payload, "event_type": event_type}),
    ]:
        try:
            fn()
            return
        except Exception:
            pass


def _emit_raid_event(*, event_type, project_id, actor_email, raid_id, raid_type, title, status, score, due_date):
    try:
        priority = _priority_from(score, status)
        due_str  = due_date.isoformat() if isinstance(due_date, dt.date) else "n/a"
        msgs = {
            "raid.created": (f"New RAID logged: {title}",  f"Type: {raid_type} | Priority: {priority} | Due: {due_str}", "info"),
            "raid.updated": (f"RAID updated: {title}",     f"Type: {raid_type} | Priority: {priority} | Due: {due_str}", "info"),
            "raid.closed":  (f"RAID closed: {title}",      f"Closed by {actor_email}", "warning"),
        }
        notif_title, notif_body, severity = msgs.get(event_type, (f"RAID event: {title}", f"Status: {status}", "info"))
        _notify_safe(event_type, {
            "project_id":   int(project_id),
            "actor_email":  actor_email,
            "title":        notif_title,
            "body":         notif_body,
            "entity_type":  "raid",
            "entity_id":    int(raid_id),
            "severity":     severity,
        })
    except Exception:
        pass


def table_has_column(table: str, column: str) -> bool:
    try:
        df = run_query(
            "SELECT 1 AS ok FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c LIMIT 1",
            {"t": table, "c": column},
        )
        return df is not None and not df.empty
    except Exception:
        return False


# ============================================================
# RAIDs CONFIG LOADING  (3-tier read path)
# ============================================================
DEFAULT_ENABLED_OPTIONAL = {
    "owner_plen", "planned_close", "next_review",
    "probability", "severity",
    "mitigation_plan", "mitigation_status",
    "related_issue", "comments",
    "date_raised", "owner_client",
}
DEFAULT_REQUIRE_MITIGATION_FOR = {"Risk", "Issue"}


def load_raids_config_for_project(project_id: int) -> dict:
    """
    3-tier read path for raids_config, in priority order:

    Tier 1 — projects.settings  (JSON column) → settings["raids_config"]
             Written by Project Setup Approval on approval.

    Tier 2 — project_settings table, key = "raids_config"
             Written by set_project_setting() as a secondary copy.

    Tier 3 — projects.raids_config  (legacy JSONB column, if it exists)
    """
    pid = int(project_id)

    # ── Tier 1: projects.settings ────────────────────────────────────────
    if table_has_column("projects", "settings"):
        try:
            df = run_query(
                "SELECT settings FROM projects WHERE project_id = :pid LIMIT 1",
                {"pid": pid},
            )
            if df is not None and not df.empty:
                settings = _json_dict(df.iloc[0].get("settings"))
                rc = settings.get("raids_config")
                if isinstance(rc, dict) and rc:
                    return rc
        except Exception:
            pass

    # ── Tier 2: project_settings table ───────────────────────────────────
    try:
        df = run_query(
            "SELECT setting_value FROM project_settings "
            "WHERE project_id = :pid AND setting_key = 'raids_config' LIMIT 1",
            {"pid": pid},
        )
        if df is not None and not df.empty:
            rc = _json_dict(df.iloc[0].get("setting_value"))
            if rc:
                return rc
    except Exception:
        pass

    # ── Tier 3: projects.raids_config column (legacy) ────────────────────
    if table_has_column("projects", "raids_config"):
        try:
            df = run_query(
                "SELECT raids_config FROM projects WHERE project_id = :pid LIMIT 1",
                {"pid": pid},
            )
            if df is not None and not df.empty:
                rc = _json_dict(df.iloc[0].get("raids_config"))
                if rc:
                    return rc
        except Exception:
            pass

    return {}


def get_project_raids_design(project_id: int):
    rc = load_raids_config_for_project(project_id) or {}
    raw_fields = rc.get("enabled_optional_fields")
    # Only fall back to defaults when there is genuinely NO config (rc was empty / key absent).
    # An explicit empty list [] means the project designer chose no optional fields — respect that.
    if raw_fields is None:
        enabled_optional = set(DEFAULT_ENABLED_OPTIONAL)
    else:
        enabled_optional = set(raw_fields)
    custom_fields = rc.get("custom_fields") or []
    if not isinstance(custom_fields, list):
        custom_fields = []
    rules                  = rc.get("rules") if isinstance(rc.get("rules"), dict) else {}
    require_mitigation_for = set(rules.get("require_mitigation_for") or []) or set(DEFAULT_REQUIRE_MITIGATION_FOR)
    return enabled_optional, custom_fields, require_mitigation_for


def render_custom_fields(prefix: str, existing: dict, fields: list[dict]) -> dict:
    out      = {}
    existing = _json_dict(existing)
    if not fields:
        st.info("No custom fields configured for this project.")
        return out

    for f in fields:
        key   = (f.get("key") or "").strip()
        label = (f.get("label") or key).strip()
        ftype = (f.get("type") or "text").lower()
        req   = bool(f.get("required", False))
        opts  = f.get("options") or []
        if not key:
            continue

        widget_key = f"{prefix}cf_{key}"
        show_label = label + (" *" if req else "")

        if ftype == "number":
            try:
                default = float(existing.get(key)) if existing.get(key) not in ("", None) else 0.0
            except Exception:
                default = 0.0
            val = st.number_input(show_label, value=default, key=widget_key)

        elif ftype == "date":
            val = st.date_input(show_label, value=_safe_date(existing.get(key)) or dt.date.today(), key=widget_key)

        elif ftype == "select":
            options = [""] + list(opts)
            default = existing.get(key) if existing.get(key) in opts else ""
            idx     = options.index(default) if default in options else 0
            val     = st.selectbox(show_label, options=options, index=idx, key=widget_key)

        elif ftype == "multiselect":
            default = existing.get(key) if isinstance(existing.get(key), list) else []
            val     = st.multiselect(show_label, options=list(opts), default=default, key=widget_key)

        elif ftype == "checkbox":
            val = st.checkbox(show_label, value=bool(existing.get(key)), key=widget_key)

        else:
            val = st.text_input(show_label, value=str(existing.get(key) or ""), key=widget_key)

        out[key] = val

    return out


def validate_required_custom_fields(custom_vals: dict, fields: list[dict]) -> list[str]:
    missing = []
    for f in fields or []:
        if not bool(f.get("required", False)):
            continue
        key   = (f.get("key") or "").strip()
        label = (f.get("label") or key).strip()
        if not key:
            continue
        v     = custom_vals.get(key)
        ftype = (f.get("type") or "text").lower()
        if ftype == "checkbox":
            if v is not True:
                missing.append(label)
        elif ftype == "multiselect":
            if not isinstance(v, list) or len(v) == 0:
                missing.append(label)
        else:
            if v is None or str(v).strip() == "":
                missing.append(label)
    return missing


# ============================================================
# AI ASSISTANT HELPERS
# ============================================================
def expand_shorthand_options(section_label: str, shorthand: str, history: List[str]):
    return {
        tone: expand_shorthand_entry(f"{section_label} — {tone}", shorthand, history) or {}
        for tone in ["Concise", "Detailed", "Formal"]
    }


def apply_expanded_to_session(section_label: str, expanded: dict, rid=None):
    if not expanded:
        return

    if rid is None:
        key_map = {
            "title":            f"{section_label}_title",
            "description":      f"{section_label}_description",
            "comments":         f"{section_label}_comments",
            "status":           f"{section_label}_status",
            "probability":      f"{section_label}_prob",
            "severity":         f"{section_label}_sev",
            "mitigation_plan":  f"{section_label}_mitigation",
            "mitigation":       f"{section_label}_mitigation",
            "related_issue":    f"{section_label}_related",
            "owner_plen":       f"{section_label}_owner_plen",
            "owner_client":     f"{section_label}_owner_client",
            "planned_close":    f"{section_label}_planned_close",
            "next_review":      f"{section_label}_next_review",
            "date_raised":      f"{section_label}_date_raised",
            "internal_external": f"{section_label}_class",
        }
    else:
        key_map = {
            "title":            f"{section_label}_edit_title_{rid}",
            "description":      f"{section_label}_edit_description_{rid}",
            "comments":         f"{section_label}_edit_comments_{rid}",
            "status":           f"{section_label}_edit_status_{rid}",
            "probability":      f"{section_label}_edit_prob_{rid}",
            "severity":         f"{section_label}_edit_sev_{rid}",
            "mitigation_plan":  f"{section_label}_edit_mitigation_{rid}",
            "mitigation":       f"{section_label}_edit_mitigation_{rid}",
            "related_issue":    f"{section_label}_edit_related_{rid}",
            "owner_plen":       f"{section_label}_edit_owner_plen_{rid}",
            "owner_client":     f"{section_label}_edit_owner_client_{rid}",
            "planned_close":    f"{section_label}_edit_planned_close_{rid}",
            "next_review":      f"{section_label}_edit_next_review_{rid}",
            "date_raised":      f"{section_label}_edit_date_raised_{rid}",
            "internal_external": f"{section_label}_edit_class_{rid}",
        }

    for field, value in (expanded or {}).items():
        wk = key_map.get(field)
        if wk:
            st.session_state[wk] = value


def format_ai_preview(expanded: dict) -> str:
    if not expanded:
        return ""
    parts          = []
    mitigation_val = expanded.get("mitigation_plan") or expanded.get("mitigation") or ""
    for key, label in [("title", "Title"), ("description", "Description"), ("comments", "Comments")]:
        if expanded.get(key):
            parts.append(f"**{label}:** {expanded[key]}")
    if mitigation_val:
        parts.insert(2, f"**Mitigation:** {mitigation_val}")
    return "\n".join(parts).strip()


def ensure_add_raid_binds(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure every key that add_raid_entry may reference exists in the dict.
    add_raid_entry filters to actual DB columns before insert, so providing
    extra keys here is harmless.
    """
    out = dict(record or {})
    for k in ADD_RAID_REQUIRED_BINDS:
        out.setdefault(k, None)
    return out


# ============================================================
# PAGE INTRO
# ============================================================
user_email = st.session_state.get("email", "unknown@user")
audit_name = (
    st.session_state.get("name")
    or st.session_state.get("full_name")
    or st.session_state.get("display_name")
    or (user_email.split("@")[0] if "@" in user_email else user_email)
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 How to use</strong><br/>
    Select a client and project, then use the tabs below to view, edit, or add RAIDs entries. Use the AI Assistant to draft entries from shorthand notes.
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CLIENT / PROJECT SELECTION
# ============================================================
st.markdown(
    """
<div class='section-header'>
    <h3>🏢 Client &amp; Project</h3>
</div>
""",
    unsafe_allow_html=True,
)

clients_df = run_query(
    "SELECT id AS client_id, client_name FROM client_scaffold WHERE status = 'approved' ORDER BY client_name"
)

if clients_df is None or clients_df.empty:
    st.error("⚠ No approved clients found.")
    pmo_footer()
    st.stop()

col_client, col_project = st.columns(2)

with col_client:
    client_name = st.selectbox("Select Client", clients_df["client_name"])
    client_id   = int(clients_df.loc[clients_df["client_name"] == client_name, "client_id"].iloc[0])

projects_df = run_query(
    "SELECT project_id, project_name FROM projects WHERE client_id = :cid AND LOWER(status) = 'open' ORDER BY project_name",
    {"cid": client_id},
)

with col_project:
    if projects_df is None or projects_df.empty:
        st.warning("⚠ This client has no open projects.")
        pmo_footer()
        st.stop()
    project_name = st.selectbox("Select Project", projects_df["project_name"])

project_id = int(projects_df.loc[projects_df["project_name"] == project_name, "project_id"].iloc[0])

# Load per-project RAIDs design
enabled_optional, custom_fields_schema, require_mitigation_for = get_project_raids_design(project_id)


# ============================================================
# LOAD PROJECT MEMBERS & RAIDS
# ============================================================
members          = get_project_member_emails(project_id)
email_to_label   = {m["user_email"]: f"{m['display_name']} ({m['user_email']})" for m in (members or [])}
owner_options    = [""] + list(email_to_label.keys())


def owner_format(v: str) -> str:
    return "Unassigned" if not v else email_to_label.get(v, v)


raids_df = run_query(
    "SELECT * FROM raids WHERE project_id = :pid ORDER BY created_at DESC",
    {"pid": project_id},
)

if raids_df is None or raids_df.empty:
    raids_df = pd.DataFrame(columns=["raid_id", "client_id", "project_id", "raid_type", "title", "status", "created_at"])

for col in [
    "description", "comments", "probability", "severity", "score", "revised_score",
    "owner_plen", "owner_client", "raised_by", "internal_external", "date_raised",
    "planned_close", "date_closed", "next_review", "related_issue",
    "mitigation_plan", "mitigation_status", "modified_by", "custom_fields",
]:
    if col not in raids_df.columns:
        raids_df[col] = None if col == "custom_fields" else ""

if not raids_df.empty:
    raids_df["raid_type"]          = raids_df["raid_type"].apply(normalize_raid_type)
    raids_df["status"]             = raids_df["status"].apply(normalize_status)
    raids_df["internal_external"]  = raids_df["internal_external"].apply(
        lambda x: "External" if (x or "").strip() == "External" else "Internal"
    )


# ============================================================
# RAID TYPE TABS
# ============================================================
tab_risks, tab_assumptions, tab_issues, tab_dependencies = st.tabs(
    ["🔴 Risks", "🔵 Assumptions", "🟠 Issues", "🟣 Dependencies"]
)


def render_raid_section(section_label: str, raid_type: str, df: pd.DataFrame):
    raid_type = normalize_raid_type(raid_type)
    raid_icon = RAID_TYPE_ICONS.get(raid_type, "📌")
    type_df   = df[df["raid_type"] == raid_type].copy() if not df.empty else pd.DataFrame()

    if not type_df.empty and "status" in type_df.columns:
        is_closed    = type_df["status"].fillna("").astype(str).apply(is_closed_status)
        closed_count = int(is_closed.sum())
        open_count   = int(len(type_df) - closed_count)
    else:
        open_count = closed_count = 0

    st.markdown(
        f"""
<div class="raid-type-header {raid_type.lower()}">
    <span style="font-size:1.2rem;">{raid_icon}</span>
    <h4 class="raid-type-title">{section_label}</h4>
    <div class="raid-counts">
        <span class="pill total">{len(type_df)} total</span>
        <span class="pill open">{open_count} open</span>
        <span class="pill closed">{closed_count} closed / completed</span>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── VIEW ─────────────────────────────────────────────────────────────
    with st.expander(f"📋 View Existing {section_label}", expanded=True):
        if type_df.empty:
            st.info(f"No {section_label.lower()} found for this project.")
        else:
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                filter_status = st.multiselect(
                    "Filter by Status",
                    ["Open", "Closed", "Completed"],
                    default=["Open"],
                    key=f"filter_status_{section_label}",
                )
            with col_filter2:
                filter_class = st.radio(
                    "Classification",
                    ["All", "Internal", "External"],
                    horizontal=True,
                    key=f"filter_class_{section_label}",
                )

            view_df = type_df.copy()

            if filter_status:
                wanted  = {normalize_status(x) for x in filter_status}
                view_df = view_df[view_df["status"].apply(normalize_status).isin(wanted)]

            if filter_class != "All":
                view_df = view_df[view_df["internal_external"] == filter_class]

            if view_df.empty:
                st.info("No items match the current filters.")
            else:
                base_cols    = ["raid_id", "title", "status", "internal_external"]
                optional_map = {
                    "probability":      "probability",
                    "severity":         "severity",
                    "planned_close":    "planned_close",
                    "next_review":      "next_review",
                    "owner_plen":       "owner_plen",
                    "owner_client":     "owner_client",
                    "mitigation_status":"mitigation_status",
                    "related_issue":    "related_issue",
                }
                display_cols = base_cols + [optional_map[k] for k in optional_map if k in enabled_optional]
                display_cols = [c for c in display_cols if c in view_df.columns]
                display_df   = view_df[display_cols].copy()

                display_df.rename(
                    columns={
                        "raid_id":          "ID",
                        "title":            "Title",
                        "status":           "Status",
                        "internal_external":"Class",
                        "probability":      "Prob",
                        "severity":         "Sev",
                        "planned_close":    "Due",
                        "next_review":      "Next Review",
                        "owner_plen":       "Owner (Plen)",
                        "owner_client":     "Owner (Client)",
                        "mitigation_status":"Mitigation",
                        "related_issue":    "Related",
                    },
                    inplace=True,
                )

                if custom_fields_schema and st.checkbox("Show custom fields in table", key=f"show_cf_table_{section_label}"):
                    raw_cf = view_df.get("custom_fields")
                    for f in custom_fields_schema:
                        k   = (f.get("key") or "").strip()
                        lbl = (f.get("label") or k).strip()
                        if k:
                            display_df[lbl] = raw_cf.apply(lambda d: (_json_dict(d)).get(k, ""))

                st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── EDIT ─────────────────────────────────────────────────────────────
    with st.expander(f"✏️ Edit Existing {section_label[:-1]}", expanded=False):
        if type_df.empty:
            st.info(f"No {section_label.lower()} to edit yet — add one below.")
            # NOTE: do NOT return here — that would prevent the Add New expander from rendering
        else:
            edit_ids     = type_df["raid_id"].astype(int).tolist()
            selected_rid = st.selectbox(
                f"Select {section_label[:-1]} to Edit",
                edit_ids,
                key=f"edit_select_{section_label}",
                format_func=lambda x: f"ID {x}: {type_df.loc[type_df['raid_id'] == x, 'title'].iloc[0]}",
            )

            row = type_df.loc[type_df["raid_id"] == selected_rid].iloc[0]
            rid = int(row["raid_id"])

            mitigation_enabled = ("mitigation_plan" in enabled_optional) or ("mitigation_status" in enabled_optional)
            mitigation_required = (raid_type in require_mitigation_for) and mitigation_enabled
            scoring_enabled     = ("probability" in enabled_optional) or ("severity" in enabled_optional)

            try:
                prob_now  = int(row.get("probability") or 0)
                sev_now   = int(row.get("severity") or 0)
                score_now = int(row.get("revised_score") or row.get("score") or (prob_now * sev_now))
            except Exception:
                prob_now = sev_now = score_now = 0

            st.markdown(
                f"""
<div class="raid-card-header">
    <div class="raid-card-title">{raid_icon} {row.get("title", "")}</div>
    <div class="raid-card-meta">
        Status: <strong>{row.get('status', 'Open')}</strong> &nbsp;·&nbsp;
        Class: <strong>{row.get('internal_external', 'Internal')}</strong> &nbsp;·&nbsp;
        Score: <strong>{score_now}</strong>
    </div>
</div>
""",
                unsafe_allow_html=True,
            )

            tab_labels = ["🤖 AI Assistant", "📝 Details"]
            if scoring_enabled:
                tab_labels.append("🎯 Scoring")
            if mitigation_enabled:
                tab_labels.append("🛡️ Mitigation")
            if custom_fields_schema:
                tab_labels.append("🧩 Custom Fields")
            tab_labels.append("👥 Owners & Dates")

            tabs        = st.tabs(tab_labels)
            name_to_tab = {name: tabs[i] for i, name in enumerate(tab_labels)}

            # AI
            with name_to_tab["🤖 AI Assistant"]:
                st.markdown('<div class="ai-section"><div class="ai-title">🧠 AI Quick Update</div></div>', unsafe_allow_html=True)
                shorthand = st.text_area(
                    "Describe the update in shorthand",
                    placeholder="e.g., 'Supplier confirmed delivery delay of 2 weeks, need to adjust timeline'",
                    height=100,
                    key=f"ai_edit_{section_label}_{rid}",
                )
                opts_key = f"ai_opts_edit_{section_label}_{rid}"
                pick_key = f"ai_pick_edit_{section_label}_{rid}"

                if st.button("🧠 Generate Options", key=f"gen_edit_{section_label}_{rid}", use_container_width=True):
                    if not shorthand.strip():
                        st.warning("Please enter some shorthand text first.")
                    else:
                        with st.spinner("Generating options..."):
                            history = type_df["description"].dropna().tail(10).tolist()
                            st.session_state[opts_key] = expand_shorthand_options(section_label, shorthand, history)
                        st.session_state[pick_key] = "Formal"
                        st.success("✅ Generated 3 options — choose one below.")

                options = st.session_state.get(opts_key) or {}
                if options:
                    choice = st.radio("Choose style", ["Concise", "Detailed", "Formal"], horizontal=True, key=pick_key)
                    st.text_area(
                        "Preview",
                        value=format_ai_preview(options.get(choice) or {}),
                        height=200,
                        disabled=True,
                        label_visibility="collapsed",
                        key=f"preview_edit_{section_label}_{rid}_{choice}",
                    )
                    if st.button("✅ Apply to Form", key=f"apply_edit_{section_label}_{rid}", use_container_width=True):
                        apply_expanded_to_session(section_label, options.get(choice) or {}, rid=rid)
                        st.success("✅ Applied! Review other tabs and save when ready.")
                        st.rerun()

            # Details
            with name_to_tab["📝 Details"]:
                title_e       = st.text_input("Title *", value=row.get("title", "") or "", key=f"{section_label}_edit_title_{rid}")
                description_e = st.text_area("Description", value=row.get("description", "") or "", height=150, key=f"{section_label}_edit_description_{rid}")

                comments_e = ""
                if "comments" in enabled_optional:
                    comments_e = st.text_area("Comments", value=row.get("comments", "") or "", height=100, key=f"{section_label}_edit_comments_{rid}")

                colA, colB = st.columns(2)
                with colA:
                    classification_e = st.radio(
                        "Classification", ["Internal", "External"], horizontal=True,
                        index=0 if row.get("internal_external") == "Internal" else 1,
                        key=f"{section_label}_edit_class_{rid}",
                    )
                with colB:
                    status_val = normalize_status(row.get("status", "Open"))
                    status_e   = st.selectbox(
                        "Status", STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(status_val) if status_val in STATUS_OPTIONS else 0,
                        key=f"{section_label}_edit_status_{rid}",
                    )

                related_e = ""
                if "related_issue" in enabled_optional:
                    related_e = st.text_input("Related Reference", value=row.get("related_issue", "") or "", key=f"{section_label}_edit_related_{rid}")

            # Scoring
            prob_e = sev_e = None
            score_e = score_now
            if scoring_enabled:
                with name_to_tab["🎯 Scoring"]:
                    col1s, col2s, col3s = st.columns(3)
                    with col1s:
                        prob_e = st.number_input("Probability (1–5)", min_value=1, max_value=5, value=int(row.get("probability") or 3), key=f"{section_label}_edit_prob_{rid}")
                    with col2s:
                        sev_e  = st.number_input("Severity (1–5)", min_value=1, max_value=5, value=int(row.get("severity") or 3), key=f"{section_label}_edit_sev_{rid}")
                    with col3s:
                        score_e = int(prob_e) * int(sev_e)
                        st.markdown(
                            f"""
<div style="border:1px solid #bae6fd; border-radius:8px; padding:1rem; text-align:center; background:#f0f9ff;">
    <div style="font-size:2.2rem; font-weight:900; color:#0077be;">{score_e}</div>
    <div style="color:#64748b; font-weight:700; font-size:0.85rem;">Risk Score</div>
</div>""",
                            unsafe_allow_html=True,
                        )

            # Mitigation
            mitigation_e = mit_status_e = ""
            if mitigation_enabled:
                with name_to_tab["🛡️ Mitigation"]:
                    if mitigation_required:
                        st.markdown('<div class="mitigation-container">⚠️ <strong>Mitigation plan is required for this RAID type.</strong></div>', unsafe_allow_html=True)
                    mitigation_e = st.text_area(
                        "Mitigation Plan *" if mitigation_required else "Mitigation Plan",
                        value=row.get("mitigation_plan", "") or "",
                        height=180,
                        key=f"{section_label}_edit_mitigation_{rid}",
                    )
                    if "mitigation_status" in enabled_optional:
                        mit_opts = ["Planned", "In Progress", "Active", "Implemented", "Not Required"]
                        current  = (row.get("mitigation_status") or "Planned").strip()
                        idx      = mit_opts.index(current) if current in mit_opts else 0
                        mit_status_e = st.selectbox("Mitigation Status", mit_opts, index=idx, key=f"{section_label}_edit_mit_status_{rid}")
                    else:
                        mit_status_e = (row.get("mitigation_status") or "Planned").strip()

                    if mitigation_required and not mitigation_e.strip():
                        st.markdown('<div class="mitigation-empty">⚠️ No mitigation plan defined!</div>', unsafe_allow_html=True)

            # Custom Fields
            custom_vals_e = {}
            if custom_fields_schema:
                with name_to_tab["🧩 Custom Fields"]:
                    custom_vals_e = render_custom_fields(f"{section_label}_{rid}_", _json_dict(row.get("custom_fields")), custom_fields_schema)

            # Owners & Dates
            with name_to_tab["👥 Owners & Dates"]:
                colm1, colm2 = st.columns(2)
                with colm1:
                    st.text_input("Raised By", value=row.get("raised_by", "") or audit_name, key=f"{section_label}_edit_raised_{rid}", disabled=True)
                    owner_plen_e = (row.get("owner_plen") or "").strip()
                    if "owner_plen" in enabled_optional:
                        if members:
                            opts = owner_options[:]
                            if owner_plen_e and owner_plen_e not in opts:
                                opts = [owner_plen_e] + opts
                            owner_plen_e = st.selectbox("Plenitude Owner", options=opts, index=opts.index(owner_plen_e) if owner_plen_e in opts else 0, format_func=owner_format, key=f"{section_label}_edit_owner_plen_{rid}")
                        else:
                            owner_plen_e = st.text_input("Plenitude Owner (email)", value=owner_plen_e, key=f"{section_label}_edit_owner_plen_{rid}")

                with colm2:
                    owner_client_e = (row.get("owner_client") or "").strip()
                    if "owner_client" in enabled_optional:
                        owner_client_e = st.text_input("Client Owner", value=owner_client_e, key=f"{section_label}_edit_owner_client_{rid}")
                    else:
                        st.text_input("Client Owner", value=owner_client_e, disabled=True, key=f"{section_label}_edit_owner_client_disabled_{rid}")

                colD1, colD2, colD3 = st.columns(3)
                date_raised_e   = _safe_date(row.get("date_raised"))   or dt.date.today()
                planned_close_e = _safe_date(row.get("planned_close")) or dt.date.today()
                next_review_e   = _safe_date(row.get("next_review"))   or dt.date.today()

                if "date_raised" in enabled_optional:
                    with colD1:
                        date_raised_e = st.date_input("Date Raised", value=date_raised_e, key=f"{section_label}_edit_date_raised_{rid}")
                if "planned_close" in enabled_optional:
                    with colD2:
                        planned_close_e = st.date_input("Planned Closure", value=planned_close_e, key=f"{section_label}_edit_planned_close_{rid}")
                if "next_review" in enabled_optional:
                    with colD3:
                        next_review_e = st.date_input("Next Review", value=next_review_e, key=f"{section_label}_edit_next_review_{rid}")

            st.markdown("---")
            col_save, col_close = st.columns([3, 1])

            with col_save:
                if st.button("💾 Save Changes", key=f"save_edit_{section_label}_{rid}", use_container_width=True, type="primary"):
                    if not title_e.strip():
                        st.error("❌ Title is required")
                        st.stop()
                    if mitigation_required and not mitigation_e.strip():
                        st.error("❌ Mitigation plan is required for this RAID type")
                        st.stop()
                    if custom_fields_schema:
                        missing = validate_required_custom_fields(custom_vals_e, custom_fields_schema)
                        if missing:
                            st.error("❌ Missing required custom fields: " + ", ".join(missing))
                            st.stop()

                    update_values = {
                        "title":            title_e,
                        "description":      description_e,
                        "internal_external":classification_e,
                        "status":           normalize_status(status_e),
                        "modified_by":      user_email,
                    }
                    if "comments" in enabled_optional:
                        update_values["comments"] = comments_e
                    if "related_issue" in enabled_optional:
                        update_values["related_issue"] = related_e

                    if scoring_enabled:
                        update_values.update({
                            "probability":    int(prob_e),
                            "severity":       int(sev_e),
                            "score":          int(score_e),
                            "new_probability":int(prob_e),
                            "new_severity":   int(sev_e),
                            "revised_score":  int(score_e),
                        })

                    if mitigation_enabled:
                        if "mitigation_plan" in enabled_optional:
                            update_values["mitigation_plan"] = mitigation_e
                        if "mitigation_status" in enabled_optional:
                            update_values["mitigation_status"] = mit_status_e

                    if "owner_plen" in enabled_optional:
                        update_values["owner_plen"] = (owner_plen_e or "").strip()
                    if "owner_client" in enabled_optional:
                        update_values["owner_client"] = owner_client_e
                    if "date_raised" in enabled_optional:
                        update_values["date_raised"] = date_raised_e
                    if "planned_close" in enabled_optional:
                        update_values["planned_close"] = planned_close_e
                    if "next_review" in enabled_optional:
                        update_values["next_review"] = next_review_e
                    if custom_fields_schema:
                        update_values["custom_fields"] = json.dumps(custom_vals_e)

                    sets, params = [], {"rid": int(rid)}
                    for k, v in update_values.items():
                        sets.append(f"{k} = :{k}")
                        params[k] = v
                    try:
                        run_execute(f"UPDATE raids SET {', '.join(sets)} WHERE raid_id = :rid", params)
                    except Exception as e:
                        st.error(f"❌ Update failed: {e}")
                        st.stop()

                    log_event("raids_update", {"client_id": client_id, "project_id": project_id, "raid_id": rid, "action": "updated"})
                    _emit_raid_event(
                        event_type="raid.updated",
                        project_id=project_id,
                        actor_email=user_email,
                        raid_id=rid,
                        raid_type=raid_type,
                        title=title_e,
                        status=normalize_status(status_e),
                        score=int(score_e or 0),
                        due_date=planned_close_e if "planned_close" in enabled_optional else None,
                    )
                    st.success("✅ Changes saved successfully!")
                    st.rerun()

            with col_close:
                already_closed = is_closed_status(row.get("status") or "")
                if st.button("🔒 Close", key=f"close_edit_{section_label}_{rid}", use_container_width=True, disabled=already_closed):
                    try:
                        run_execute(
                            "UPDATE raids SET status='Closed', date_closed=NOW(), modified_by=:u WHERE raid_id=:rid",
                            {"u": user_email, "rid": int(rid)},
                        )
                    except Exception as e:
                        st.error(f"❌ Close failed: {e}")
                        st.stop()

                    log_event("raids_update", {"client_id": client_id, "project_id": project_id, "raid_id": rid, "action": "closed"})
                    _emit_raid_event(
                        event_type="raid.closed",
                        project_id=project_id,
                        actor_email=user_email,
                        raid_id=rid,
                        raid_type=raid_type,
                        title=str(row.get("title", "") or f"RAID {rid}"),
                        status="Closed",
                        score=int(score_now or 0),
                        due_date=_safe_date(row.get("planned_close")) if "planned_close" in enabled_optional else None,
                    )
                    st.success("✅ RAID closed")
                    st.rerun()

    # ── ADD NEW ───────────────────────────────────────────────────────────
    with st.expander(f"➕ Add New {section_label[:-1]}", expanded=False):
        mitigation_enabled  = ("mitigation_plan" in enabled_optional) or ("mitigation_status" in enabled_optional)
        mitigation_required = (raid_type in require_mitigation_for) and mitigation_enabled
        scoring_enabled     = ("probability" in enabled_optional) or ("severity" in enabled_optional)

        tab_labels = ["🤖 AI Assistant", "📝 Details"]
        if scoring_enabled:
            tab_labels.append("🎯 Scoring")
        if mitigation_enabled:
            tab_labels.append("🛡️ Mitigation")
        if custom_fields_schema:
            tab_labels.append("🧩 Custom Fields")
        tab_labels.append("👥 Owners & Dates")

        tabs        = st.tabs(tab_labels)
        name_to_tab = {name: tabs[i] for i, name in enumerate(tab_labels)}

        with name_to_tab["🤖 AI Assistant"]:
            st.markdown('<div class="ai-section"><div class="ai-title">🧠 AI Draft Assistant</div></div>', unsafe_allow_html=True)
            shorthand = st.text_area(
                "Quick description",
                placeholder="e.g., 'Key supplier may delay component delivery by 3 weeks due to logistics issues'",
                height=100,
                key=f"ai_new_{section_label}",
            )
            opts_key = f"ai_opts_new_{section_label}"
            pick_key = f"ai_pick_new_{section_label}"

            if st.button("🧠 Generate Options", key=f"gen_new_{section_label}", use_container_width=True, type="primary"):
                if not shorthand.strip():
                    st.warning("Please enter a description first.")
                else:
                    with st.spinner("Generating 3 options..."):
                        history = type_df["description"].dropna().tail(10).tolist() if not type_df.empty else []
                        st.session_state[opts_key] = expand_shorthand_options(section_label, shorthand, history)
                    st.session_state[pick_key] = "Formal"
                    st.success("✅ Generated 3 options — choose one below.")

            options = st.session_state.get(opts_key) or {}
            if options:
                choice = st.radio("Choose your preferred style", ["Concise", "Detailed", "Formal"], horizontal=True, key=pick_key)
                st.text_area(
                    "Preview",
                    value=format_ai_preview(options.get(choice) or {}),
                    height=250,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"preview_new_{section_label}_{choice}",
                )
                if st.button("✅ Apply to Form", key=f"apply_new_{section_label}", use_container_width=True):
                    apply_expanded_to_session(section_label, options.get(choice) or {}, rid=None)
                    st.success("✅ Applied! Review other tabs and add when ready.")
                    st.rerun()

        with name_to_tab["📝 Details"]:
            title       = st.text_input("Title *", key=f"{section_label}_title", placeholder=f"Brief summary of this {raid_type.lower()}")
            description = st.text_area("Description", height=150, key=f"{section_label}_description")

            comments = ""
            if "comments" in enabled_optional:
                comments = st.text_area("Comments", height=100, key=f"{section_label}_comments")

            colx1, colx2 = st.columns(2)
            with colx1:
                classification = st.radio("Classification", ["Internal", "External"], horizontal=True, key=f"{section_label}_class")
            with colx2:
                status = st.selectbox("Status", STATUS_OPTIONS, key=f"{section_label}_status")

            related = ""
            if "related_issue" in enabled_optional:
                related = st.text_input("Related Reference", key=f"{section_label}_related")

        # Safe defaults — widgets may not be rendered if scoring_enabled=False.
        # Reading from session_state means we always have a usable int even if
        # the scoring tab was never visited this run.
        prob  = st.session_state.get(f"{section_label}_prob",  3)
        sev   = st.session_state.get(f"{section_label}_sev",   3)
        score = None  # computed below if scoring_enabled
        if scoring_enabled:
            with name_to_tab["🎯 Scoring"]:
                colp1, colp2, colp3 = st.columns(3)
                with colp1:
                    prob = st.number_input("Probability (1–5)", min_value=1, max_value=5, value=3, key=f"{section_label}_prob")
                with colp2:
                    sev  = st.number_input("Severity (1–5)",    min_value=1, max_value=5, value=3, key=f"{section_label}_sev")
                with colp3:
                    score = int(prob) * int(sev)
                    st.markdown(
                        f"""
<div style="border:1px solid #bae6fd; border-radius:8px; padding:1rem; text-align:center; background:#f0f9ff;">
    <div style="font-size:2.2rem; font-weight:900; color:#0077be;">{score}</div>
    <div style="color:#64748b; font-weight:700; font-size:0.85rem;">Risk Score</div>
</div>""",
                        unsafe_allow_html=True,
                    )

        # ── Mitigation (now properly captured for insert) ─────────────
        mitigation: str = ""
        mit_status: str | None = None   # None is safe for DB; "" can violate CHECK constraints
        if mitigation_enabled:
            with name_to_tab["🛡️ Mitigation"]:
                if mitigation_required:
                    st.markdown('<div class="mitigation-container">⚠️ <strong>Mitigation plan is required for this RAID type.</strong></div>', unsafe_allow_html=True)
                mitigation = st.text_area(
                    "Mitigation Plan *" if mitigation_required else "Mitigation Plan",
                    height=180,
                    key=f"{section_label}_mitigation",
                )

                if "mitigation_status" in enabled_optional:
                    mit_status = st.selectbox(
                        "Mitigation Status",
                        ["Planned", "In Progress", "Active", "Implemented", "Not Required"],
                        key=f"{section_label}_mit_status",
                    )
                else:
                    mit_status = "Planned"   # default when field not shown but column exists

                if mitigation_required and not mitigation.strip():
                    st.markdown('<div class="mitigation-empty">⚠️ Mitigation plan required before saving!</div>', unsafe_allow_html=True)

        custom_vals_new = {}
        if custom_fields_schema:
            with name_to_tab["🧩 Custom Fields"]:
                custom_vals_new = render_custom_fields(f"{section_label}_new_", {}, custom_fields_schema)

        with name_to_tab["👥 Owners & Dates"]:
            colm1, colm2 = st.columns(2)
            with colm1:
                st.text_input("Raised By", value=audit_name, key=f"{section_label}_raised", disabled=True)
                owner_plen = ""
                if "owner_plen" in enabled_optional:
                    if members:
                        owner_plen = st.selectbox("Plenitude Owner", options=owner_options, format_func=owner_format, key=f"{section_label}_owner_plen")
                    else:
                        owner_plen = st.text_input("Plenitude Owner (email)", key=f"{section_label}_owner_plen")
            with colm2:
                owner_client = ""
                if "owner_client" in enabled_optional:
                    owner_client = st.text_input("Client Owner", key=f"{section_label}_owner_client")

            colD1, colD2, colD3 = st.columns(3)
            date_raised = planned_close = next_review = dt.date.today()
            if "date_raised" in enabled_optional:
                with colD1:
                    date_raised = st.date_input("Date Raised", value=dt.date.today(), key=f"{section_label}_date_raised")
            if "planned_close" in enabled_optional:
                with colD2:
                    planned_close = st.date_input("Planned Closure", value=dt.date.today(), key=f"{section_label}_planned_close")
            if "next_review" in enabled_optional:
                with colD3:
                    next_review = st.date_input("Next Review", value=dt.date.today(), key=f"{section_label}_next_review")

        st.markdown("---")
        if st.button(f"✅ Add {section_label[:-1]}", key=f"save_new_{section_label}", use_container_width=True, type="primary"):
            if not (title or "").strip():
                st.error("❌ Title is required")
                st.stop()
            if mitigation_required and not (mitigation or "").strip():
                st.error("❌ Mitigation plan is required for this RAID type")
                st.stop()
            if custom_fields_schema:
                missing = validate_required_custom_fields(custom_vals_new, custom_fields_schema)
                if missing:
                    st.error("❌ Missing required custom fields: " + ", ".join(missing))
                    st.stop()

            # ── Build insert record ──────────────────────────────────
            record = {
                "client_id":        client_id,
                "project_id":       project_id,
                "raid_type":        raid_type,
                "type":             raid_type,
                "title":            title,
                "description":      description,
                "raised_by":        audit_name,
                "internal_external":classification,
                "status":           normalize_status(status),
                "modified_by":      user_email,
                "date_closed":      None,
            }

            record["comments"]     = comments if "comments" in enabled_optional else None
            record["related_issue"]= related  if "related_issue" in enabled_optional else None

            if scoring_enabled:
                record.update({
                    "probability":    int(prob),
                    "severity":       int(sev),
                    "score":          int(score),
                    "new_probability":int(prob),
                    "new_severity":   int(sev),
                    "revised_score":  int(score),
                })
            else:
                record.update({
                    "probability": None, "severity": None, "score": None,
                    "new_probability": None, "new_severity": None, "revised_score": None,
                })

            # ── Mitigation fields — always pass a clean value, never "" ─
            if mitigation_enabled:
                record["mitigation_plan"]   = (mitigation or None)  if "mitigation_plan"   in enabled_optional else None
                record["mitigation_status"] = (mit_status or None)  if "mitigation_status" in enabled_optional else None
            else:
                record["mitigation_plan"]   = None
                record["mitigation_status"] = None

            record["owner_plen"]   = (owner_plen   or "").strip() if "owner_plen"   in enabled_optional else None
            record["owner_client"] = (owner_client or "").strip() if "owner_client" in enabled_optional else None

            record["date_raised"]   = date_raised   if "date_raised"   in enabled_optional else None
            record["planned_close"] = planned_close if "planned_close" in enabled_optional else None
            record["next_review"]   = next_review   if "next_review"   in enabled_optional else None

            if custom_fields_schema and custom_vals_new:
                record["custom_fields"] = custom_vals_new  # add_raid_entry serialises dicts to JSON

            # Guarantee all fixed bind keys exist before calling add_raid_entry
            record = ensure_add_raid_binds(record)

            try:
                rid_new = add_raid_entry(record, user_email=user_email)
            except Exception as e:
                st.error(f"❌ Failed to create RAID: {e}")
                with st.expander("Show insert payload"):
                    st.json({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in record.items()})
                st.stop()

            if not rid_new:
                st.error("❌ Failed to create RAID — check logs")
                st.stop()

            log_event("raids_update", {"client_id": client_id, "project_id": project_id, "raid_id": rid_new, "action": "created"})
            _emit_raid_event(
                event_type="raid.created",
                project_id=project_id,
                actor_email=user_email,
                raid_id=int(rid_new),
                raid_type=raid_type,
                title=title,
                status=normalize_status(status),
                score=int(score or 0),
                due_date=planned_close if "planned_close" in enabled_optional else None,
            )
            st.success(f"✅ {section_label[:-1]} added successfully (ID: {rid_new})")
            st.rerun()


# ============================================================
# RENDER TABS
# ============================================================
with tab_risks:
    render_raid_section("Risks", "Risk", raids_df)

with tab_assumptions:
    render_raid_section("Assumptions", "Assumption", raids_df)

with tab_issues:
    render_raid_section("Issues", "Issue", raids_df)

with tab_dependencies:
    render_raid_section("Dependencies", "Dependency", raids_df)

pmo_footer()