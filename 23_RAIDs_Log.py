# ============================================================
# 23_📋_RAIDs_Log.py — ScopeSight v3.4
# RAIDs Log (Read-only view + Export) — Tab layout
#
# FIXES vs v3.3:
# - load_raids_config_for_project: added project_settings table
#   as tier-2 read path (matching the 3-tier path in the assistant)
# - get_project_raids_design: empty list [] no longer falls back to
#   defaults — respects the project designer's explicit choice
# - render_type_tab: status filter now built from actual DB values
#   so non-standard statuses (In Progress, On Hold, etc.) are visible
# - compute_attention_sets: removed dead `today` variable
# - Export: buf.seek(0) added so download button gets real bytes
# - add_custom_fields_columns: fixed lambda closure over loop var k
# ============================================================

import datetime as dt
import json
from io import BytesIO

import pandas as pd
import streamlit as st

from modules.ui_hide_nav import hide_streamlit_nav
from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="📋 RAIDs Log",
    page_icon="📋",
    layout="wide",
)

require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="📋 RAIDs Log")
render_sidebar()


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

.step-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1.25rem 0 1rem 0;
}
.step-header h4 { color: #0077be; margin: 0; font-size: 1.1rem; font-weight: 600; }

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
}

.attention-card {
    border-left: 4px solid #4facfe;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin: 0.75rem 0;
}
.attention-card.overdue  { border-left-color: #ef4444; background: #fff5f5; }
.attention-card.upcoming { border-left-color: #f59e0b; background: #fffbeb; }
.attention-card h4 { margin: 0 0 0.4rem 0; font-size: 0.95rem; font-weight: 700; }
.attention-card.overdue h4  { color: #991b1b; }
.attention-card.upcoming h4 { color: #92400e; }

.type-strip {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1rem 0 0.75rem 0;
}
.type-strip.risk        { border-left-color: #dc2626; background: #fff5f5; }
.type-strip.assumption  { border-left-color: #2563eb; background: #eff6ff; }
.type-strip.issue       { border-left-color: #f59e0b; background: #fffbeb; }
.type-strip.dependency  { border-left-color: #7c3aed; background: #f5f3ff; }
.type-strip h4 { margin: 0; font-size: 1rem; font-weight: 700; color: #0f172a; }
.type-meta { font-size: 0.85rem; color: #64748b; font-weight: 600; }

div.stButton > button,
div.stDownloadButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.05rem;
    font-weight: 600;
    padding: 0.65rem 1.5rem;
    border: none;
    border-radius: 8px;
    transition: all 0.2s ease;
}
div.stButton > button:hover,
div.stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 12px rgba(79, 172, 254, 0.35);
}
label { font-weight: 600 !important; }
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CONSTANTS & HELPERS
# ============================================================
SECTION_TO_TYPE = {
    "Risks": "Risk",
    "Assumptions": "Assumption",
    "Issues": "Issue",
    "Dependencies": "Dependency",
}

TYPE_ICONS = {
    "Risk": "🔴", "Assumption": "🔵", "Issue": "🟠", "Dependency": "🟣",
}

CLOSED_STATUSES = {"closed", "completed"}

DEFAULT_ENABLED_OPTIONAL = {
    "owner_plen", "owner_client", "planned_close", "next_review",
    "probability", "severity", "revised_score", "mitigation_status",
    "internal_external", "status", "created_at", "related_issue",
}

OPTIONAL_COLS = {
    "internal_external": "internal_external",
    "owner_plen": "owner_plen",
    "owner_client": "owner_client",
    "probability": "probability",
    "severity": "severity",
    "revised_score": "revised_score",
    "planned_close": "planned_close",
    "next_review": "next_review",
    "created_at": "created_at",
    "mitigation_status": "mitigation_status",
    "related_issue": "related_issue",
    "status": "status",
}

RENAME_MAP = {
    "raid_id": "ID", "raid_type": "Type", "title": "Title",
    "internal_external": "Class", "owner_plen": "Plen Owner",
    "owner_client": "Client Owner", "revised_score": "Score",
    "planned_close": "Planned Close", "next_review": "Next Review",
    "created_at": "Created", "mitigation_status": "Mitigation",
    "related_issue": "Related", "probability": "Prob",
    "severity": "Sev", "status": "Status",
}


def _safe_date(v):
    try:
        if pd.isna(v) or v is None:
            return None
        if isinstance(v, dt.date):
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


def load_raids_config_for_project(project_id: int) -> dict:
    """
    3-tier read path — must match the assistant page exactly so both
    pages always display the same columns for the same project.

    Tier 1: projects.settings  → settings["raids_config"]   (written on approval)
    Tier 2: project_settings table key "raids_config"        (secondary fallback)
    Tier 3: projects.raids_config column                     (legacy fallback)
    """
    # Tier 1
    if table_has_column("projects", "settings"):
        try:
            df = run_query(
                "SELECT settings FROM projects WHERE project_id = :pid LIMIT 1",
                {"pid": int(project_id)},
            )
            if df is not None and not df.empty:
                settings = df.iloc[0].get("settings") or {}
                if isinstance(settings, str):
                    try:
                        settings = json.loads(settings)
                    except Exception:
                        settings = {}
                if isinstance(settings, dict):
                    rc = settings.get("raids_config") or {}
                    if rc and isinstance(rc, dict):
                        return rc
        except Exception:
            pass

    # Tier 2 — project_settings table (keyed store)
    try:
        df = run_query(
            "SELECT setting_value FROM project_settings "
            "WHERE project_id = :pid AND setting_key = 'raids_config' LIMIT 1",
            {"pid": int(project_id)},
        )
        if df is not None and not df.empty:
            raw = df.iloc[0].get("setting_value")
            if raw:
                rc = raw if isinstance(raw, dict) else _json_dict(raw)
                if rc:
                    return rc
    except Exception:
        pass

    # Tier 3 — legacy projects.raids_config column
    if table_has_column("projects", "raids_config"):
        try:
            df = run_query(
                "SELECT raids_config FROM projects WHERE project_id = :pid LIMIT 1",
                {"pid": int(project_id)},
            )
            if df is not None and not df.empty:
                rc = df.iloc[0].get("raids_config") or {}
                if isinstance(rc, str):
                    try:
                        rc = json.loads(rc)
                    except Exception:
                        rc = {}
                if rc and isinstance(rc, dict):
                    return rc
        except Exception:
            pass

    return {}


def get_project_raids_design(project_id: int):
    rc = load_raids_config_for_project(project_id) or {}
    raw_fields = rc.get("enabled_optional_fields")
    # Only fall back to defaults when there is genuinely NO config (key absent).
    # An explicit [] means the designer chose no optional fields — respect that.
    if raw_fields is None:
        enabled_optional = set(DEFAULT_ENABLED_OPTIONAL)
    else:
        enabled_optional = set(raw_fields)

    custom_fields = rc.get("custom_fields") or []
    if not isinstance(custom_fields, list):
        custom_fields = []
    clean_cf = []
    for f in custom_fields:
        if not isinstance(f, dict):
            continue
        k = (f.get("key") or "").strip()
        if not k:
            continue
        clean_cf.append({
            "key": k,
            "label": (f.get("label") or k).strip(),
            "type": (f.get("type") or "text").strip().lower(),
            "required": bool(f.get("required", False)),
            "options": f.get("options") or [],
        })
    return enabled_optional, clean_cf


def add_custom_fields_columns(df: pd.DataFrame, schema: list) -> pd.DataFrame:
    if df is None or df.empty or not schema or "custom_fields" not in df.columns:
        return df
    out = df.copy()
    cf_series = out["custom_fields"].apply(_json_dict)
    for f in schema:
        k = f.get("key")
        lbl = f.get("label") or k
        if k:
            # FIX: capture k by default argument to avoid closure over loop variable
            out[lbl] = cf_series.apply(lambda d, _k=k: d.get(_k, ""))
    return out


def build_display_table(
    df: pd.DataFrame,
    enabled_optional: set,
    schema: list,
    include_custom: bool,
    drop_type: bool = False,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    base_cols = ["raid_id", "raid_type", "title"]
    dynamic   = [OPTIONAL_COLS[k] for k in OPTIONAL_COLS if k in enabled_optional]
    existing  = [c for c in base_cols + dynamic if c in df.columns]
    out       = df[existing].copy()

    if include_custom:
        out = add_custom_fields_columns(
            out.assign(custom_fields=df.get("custom_fields")), schema
        )
        out.drop(columns=["custom_fields"], inplace=True, errors="ignore")

    for dc in ["planned_close", "next_review"]:
        if dc in out.columns:
            out[dc] = out[dc].apply(_safe_date)
    if "created_at" in out.columns:
        out["created_at"] = pd.to_datetime(out["created_at"], errors="coerce")

    out.rename(
        columns={k: v for k, v in RENAME_MAP.items() if k in out.columns},
        inplace=True,
    )

    if drop_type and "Type" in out.columns:
        out.drop(columns=["Type"], inplace=True)

    return out


def compute_attention_sets(df: pd.DataFrame):
    # FIX: removed dead `today` variable — comparisons use dt.date.today() directly
    if df is None or df.empty or "planned_close" not in df.columns:
        return pd.DataFrame(), pd.DataFrame()
    tmp = df.copy()
    tmp["_due"] = tmp["planned_close"].apply(_safe_date)
    is_open = (
        ~tmp.get("status", pd.Series(dtype=str))
        .astype(str).str.strip().str.lower()
        .isin(CLOSED_STATUSES)
    )
    overdue = tmp[
        is_open & tmp["_due"].notna() & (tmp["_due"] < dt.date.today())
    ].copy()
    upcoming = tmp[
        is_open
        & tmp["_due"].notna()
        & (tmp["_due"] >= dt.date.today())
        & (tmp["_due"] <= dt.date.today() + dt.timedelta(days=7))
    ].copy()
    return overdue, upcoming


def render_type_tab(
    rtype: str,
    df: pd.DataFrame,
    enabled_optional: set,
    schema: list,
    include_custom: bool,
):
    icon = TYPE_ICONS.get(rtype, "📌")
    sub  = df[df["raid_type"] == rtype].copy() if "raid_type" in df.columns else pd.DataFrame()

    if sub.empty:
        st.info(f"No {rtype.lower()}s logged for this project.")
        return

    is_closed    = sub["status"].astype(str).str.strip().str.lower().isin(CLOSED_STATUSES)
    open_count   = int((~is_closed).sum())
    closed_count = int(is_closed.sum())

    st.markdown(
        f"""
<div class="type-strip {rtype.lower()}">
    <h4>{icon} {rtype}s</h4>
    <span class="type-meta">
        {len(sub)} total &nbsp;·&nbsp;
        <span style="color:#0369a1;">{open_count} open</span> &nbsp;·&nbsp;
        {closed_count} closed / completed
    </span>
</div>
""",
        unsafe_allow_html=True,
    )

    # FIX: build status filter options from actual DB values so non-standard
    # statuses (In Progress, On Hold, etc.) are visible and filterable,
    # rather than hardcoding ["Open", "Closed", "Completed"].
    actual_statuses = sorted(
        sub["status"].dropna().astype(str).str.strip().unique().tolist()
    )
    default_open = [s for s in actual_statuses if s.lower() not in CLOSED_STATUSES]

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_status = st.multiselect(
            "Filter by Status",
            options=actual_statuses,
            default=default_open,
            key=f"log_status_{rtype}",
        )
    with col_f2:
        filter_class = st.radio(
            "Classification", ["All", "Internal", "External"],
            horizontal=True, key=f"log_class_{rtype}",
        )

    view = sub.copy()
    if filter_status:
        view = view[view["status"].isin(filter_status)]
    if filter_class != "All" and "internal_external" in view.columns:
        view = view[view["internal_external"] == filter_class]

    if view.empty:
        st.info("No items match the current filters.")
    else:
        st.dataframe(
            build_display_table(view, enabled_optional, schema, include_custom, drop_type=True),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# PAGE INTRO
# ============================================================
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>📋 RAIDs Log</strong><br/>
    Read-only view of all RAIDs entries. Select a client and project below,
    then browse by tab. Use the RAIDs Assistant to add or edit entries.
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

project_id = int(
    projects_df.loc[projects_df["project_name"] == project_name, "project_id"].iloc[0]
)
enabled_optional, custom_fields_schema = get_project_raids_design(project_id)

include_custom = False
if custom_fields_schema:
    include_custom = st.checkbox("Include custom fields in tables", value=True)

# ============================================================
# LOAD RAIDS
# ============================================================
raids_df = run_query(
    "SELECT * FROM raids WHERE project_id = :pid ORDER BY created_at DESC",
    {"pid": project_id},
)

if raids_df is None or raids_df.empty:
    st.info("No RAIDs found for this project.")
    pmo_footer()
    st.stop()

if "status" not in raids_df.columns:
    raids_df["status"] = "Open"

# ============================================================
# MAIN TABS
# ============================================================
tab_overview, tab_risks, tab_assumptions, tab_issues, tab_dependencies, tab_export = st.tabs([
    "📊 Overview",
    "🔴 Risks",
    "🔵 Assumptions",
    "🟠 Issues",
    "🟣 Dependencies",
    "📥 Export",
])

# ── OVERVIEW ──────────────────────────────────────────────
with tab_overview:

    overdue, upcoming = compute_attention_sets(raids_df)

    if not overdue.empty or not upcoming.empty:
        st.markdown(
            """
<div class='section-header'>
    <h3>⚠️ Items Requiring Attention</h3>
</div>
""",
            unsafe_allow_html=True,
        )
        attn_cols = ["raid_id", "raid_type", "title", "status"]
        for k in ["owner_plen", "planned_close", "revised_score"]:
            if k in enabled_optional and k in raids_df.columns:
                attn_cols.append(k)

        def _prep_attn(df_part: pd.DataFrame) -> pd.DataFrame:
            tmp = df_part[[c for c in attn_cols if c in df_part.columns]].copy()
            if "planned_close" in tmp.columns:
                tmp["planned_close"] = tmp["planned_close"].apply(_safe_date)
            tmp.rename(
                columns={k: v for k, v in RENAME_MAP.items() if k in tmp.columns},
                inplace=True,
            )
            return tmp

        if not overdue.empty:
            st.markdown(
                '<div class="attention-card overdue"><h4>🔴 Overdue</h4></div>',
                unsafe_allow_html=True,
            )
            st.dataframe(_prep_attn(overdue).head(20), use_container_width=True, hide_index=True)

        if not upcoming.empty:
            st.markdown(
                '<div class="attention-card upcoming"><h4>🟡 Due within 7 days</h4></div>',
                unsafe_allow_html=True,
            )
            st.dataframe(_prep_attn(upcoming).head(20), use_container_width=True, hide_index=True)

    else:
        st.markdown(
            """
<div class='info-box'>
    <strong style='color:#48bb78;'>✅ All clear</strong><br/>
    No overdue or upcoming items due within 7 days.
</div>
""",
            unsafe_allow_html=True,
        )

    # Summary by type
    st.markdown(
        """
<div class='section-header'>
    <h3>📊 Summary by Type</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if "raid_type" in raids_df.columns:
        summary_rows = []
        for rtype in ["Risk", "Assumption", "Issue", "Dependency"]:
            sub = raids_df[raids_df["raid_type"] == rtype]
            if sub.empty:
                continue
            is_closed = sub["status"].astype(str).str.strip().str.lower().isin(CLOSED_STATUSES)
            summary_rows.append({
                "Type":                f"{TYPE_ICONS.get(rtype, '')} {rtype}s",
                "Total":               len(sub),
                "Open":                int((~is_closed).sum()),
                "Closed / Completed":  int(is_closed.sum()),
            })
        if summary_rows:
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # Full snapshot — first 15 rows, expander for all
    st.markdown(
        """
<div class='section-header'>
    <h3>📋 Full Snapshot</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    full_table = build_display_table(
        raids_df, enabled_optional, custom_fields_schema, include_custom
    )
    st.dataframe(full_table.head(15), use_container_width=True, hide_index=True)

    with st.expander("🔍 View all rows", expanded=False):
        st.dataframe(full_table, use_container_width=True, hide_index=True)

# ── TYPE TABS ─────────────────────────────────────────────
with tab_risks:
    render_type_tab("Risk", raids_df, enabled_optional, custom_fields_schema, include_custom)

with tab_assumptions:
    render_type_tab("Assumption", raids_df, enabled_optional, custom_fields_schema, include_custom)

with tab_issues:
    render_type_tab("Issue", raids_df, enabled_optional, custom_fields_schema, include_custom)

with tab_dependencies:
    render_type_tab("Dependency", raids_df, enabled_optional, custom_fields_schema, include_custom)

# ── EXPORT ────────────────────────────────────────────────
with tab_export:
    st.markdown(
        """
<div class='section-header'>
    <h3>📥 Export RAIDs</h3>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class='info-box'>
    <strong style='color:#48bb78;'>Export options</strong><br/>
    Choose a version and download. Each RAID type is written to its own sheet in the workbook.
</div>
""",
        unsafe_allow_html=True,
    )

    col_choice, _ = st.columns([2, 3])
    with col_choice:
        choice = st.selectbox("Export Version", ["All", "Internal Only", "External Only"])

    frames = {}
    for section, rtype in SECTION_TO_TYPE.items():
        sub = (
            raids_df[raids_df["raid_type"] == rtype].copy()
            if "raid_type" in raids_df.columns
            else pd.DataFrame()
        )
        if choice == "Internal Only" and "internal_external" in sub.columns:
            sub = sub[sub["internal_external"] == "Internal"]
        elif choice == "External Only" and "internal_external" in sub.columns:
            sub = sub[sub["internal_external"] == "External"]
        frames[section] = build_display_table(
            sub, enabled_optional, custom_fields_schema, include_custom, drop_type=True
        )

    # FIX: seek(0) so the download button receives the full written bytes,
    # not an empty buffer at the end-of-stream position.
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in frames.items():
            if frame is not None and not frame.empty:
                frame.to_excel(writer, sheet_name=name[:31], index=False)
    buf.seek(0)

    st.download_button(
        "⬇️ Download RAIDs Excel",
        buf.getvalue(),
        file_name=f"{project_name}_RAIDs_{choice.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

pmo_footer()