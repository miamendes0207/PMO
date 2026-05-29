# ============================================================
# 8_🔔_Notifications_Manager.py — ScopeSight v5
# ============================================================

import datetime as dt
import streamlit as st
import pandas as pd

from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

from modules.notifications_config import EVENT_TYPES, ALL_EVENT_TYPES

from modules.db import (
    get_user_assigned_projects,
    get_notification_prefs,
    upsert_notification_pref,
    clear_notification_prefs_for_scope,
)

# ---------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="🔔 Notifications",
    page_icon="🔔",
    layout="wide",
    initial_sidebar_state="expanded",
)

set_pmo_theme(page_title="🔔 Notifications")
render_sidebar()
hide_streamlit_nav()
require_login()

current_email = (st.session_state.get("email") or "").strip().lower()
current_role = (st.session_state.get("role") or "user").strip().lower()

# ---------------------------------------------------------
# Styles
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Page header */
.page-hero {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    padding: 1.4rem 1.8rem;
    border-radius: 12px;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.page-hero h2 {
    color: white;
    margin: 0;
    font-size: 1.5rem;
    font-weight: 900;
    line-height: 1.2;
}
.page-hero p {
    color: rgba(255,255,255,0.88);
    margin: 0.25rem 0 0 0;
    font-size: 0.9rem;
}

/* Scope banner */
.scope-banner {
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-left: 5px solid #4facfe;
    border-radius: 8px;
    padding: 0.7rem 1.1rem;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.92rem;
    color: #0369a1;
}
.scope-banner strong { color: #0c4a6e; }

/* Bulk action bar */
.bulk-bar {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.75rem;
}

/* Event rows */
.event-row { padding: 0.15rem 0; }
.event-label { font-weight: 700; color: #111827; font-size: 0.95rem; }
.event-code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Courier New", monospace;
    font-size: 0.75rem;
    color: #94a3b8;
    margin-top: 0.1rem;
}

/* Column headers */
.col-header {
    font-size: 0.78rem;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* Group title strip */
.group-strip {
    background: #f1f5f9;
    border-radius: 6px;
    padding: 0.45rem 0.8rem;
    margin-bottom: 0.6rem;
    font-size: 0.97rem;
    font-weight: 800;
    color: #0f172a;
}

/* Card for reminders */
.card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.1rem 1.2rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    margin-top: 0.5rem;
}

/* Save toast override */
div[data-testid="stSuccessMessage"] {
    border-radius: 8px;
}

/* Buttons */
div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 0.92rem;
    font-weight: 800;
    padding: 0.55rem 1rem;
    border: none;
    border-radius: 10px;
    transition: all 0.2s ease;
}
div.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 14px rgba(79,172,254,0.3);
}

/* Danger button (clear) */
div[data-testid="column"]:last-of-type div.stButton > button {
    background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
}

label { font-weight: 600 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
DELIVERY_OPTIONS = ["instant", "daily", "weekly"]
DELIVERY_ICONS = {"instant": "⚡", "daily": "📅", "weekly": "🗓️"}


def _safe_df(df, cols=None):
    if not isinstance(df, pd.DataFrame) or df is None:
        df = pd.DataFrame()
    if cols:
        for c in cols:
            if c not in df.columns:
                df[c] = None
    return df


def _pref_lookup(prefs_df: pd.DataFrame, project_id, event_type: str):
    if prefs_df.empty:
        return None
    d = prefs_df.copy()
    d["_pid"] = d["project_id"].fillna(-1).astype(int)
    wanted = -1 if project_id is None else int(project_id)
    m = d[(d["_pid"] == wanted) & (d["event_type"] == event_type)]
    if m.empty:
        return None
    return m.iloc[0]


def _default_pref(prefs_df: pd.DataFrame, project_id, event_type: str, default_digest: str):
    row = _pref_lookup(prefs_df, project_id, event_type)
    if row is None:
        return True, True, False, default_digest
    return (
        bool(row.get("enabled", True)),
        bool(row.get("channel_in_app", True)),
        bool(row.get("channel_email", False)),
        str(row.get("digest_mode") or default_digest),
    )


def _apply_bulk(user_email: str, scope_project_id, digest_mode: str, mode: str):
    prefs_df = get_notification_prefs(user_email)
    prefs_df = _safe_df(prefs_df)
    for et in ALL_EVENT_TYPES:
        enabled, in_app, email, _dm = _default_pref(prefs_df, scope_project_id, et, digest_mode)
        if mode == "enable_all":
            enabled, in_app, email = True, True, email
        elif mode == "disable_all":
            enabled, in_app, email = False, False, False
        elif mode == "inapp_only":
            enabled, in_app, email = True, True, False
        upsert_notification_pref(
            user_email=user_email,
            project_id=scope_project_id,
            event_type=et,
            in_app=in_app,
            email=email,
            enabled=enabled,
            digest_mode=digest_mode,
        )


def _count_enabled(prefs_df, project_id):
    """Return (enabled_count, total) for a given scope."""
    total = len(ALL_EVENT_TYPES)
    if prefs_df.empty:
        return total, total  # defaults = all enabled
    d = prefs_df.copy()
    d["_pid"] = d["project_id"].fillna(-1).astype(int)
    wanted = -1 if project_id is None else int(project_id)
    scoped = d[d["_pid"] == wanted]
    enabled_count = scoped[scoped["enabled"] == True].shape[0]
    # rows not in prefs default to enabled
    saved_types = set(scoped["event_type"].tolist())
    implicit = len([e for e in ALL_EVENT_TYPES if e not in saved_types])
    return enabled_count + implicit, total


# ---------------------------------------------------------
# Load data
# ---------------------------------------------------------
projects = get_user_assigned_projects(current_email)
projects = _safe_df(projects, cols=["project_id", "project_name", "project_code"])

prefs = get_notification_prefs(current_email)
prefs = _safe_df(prefs, cols=["user_email", "project_id", "event_type", "channel_in_app", "channel_email", "enabled", "digest_mode", "updated_at"])

# ============================================================
# Scope + Delivery row
# ============================================================
col_scope, col_proj, col_delivery = st.columns([1.3, 2.2, 1.2])

with col_scope:
    scope = st.radio(
        "Scope",
        ["Global (all projects)", "Specific project"],
        index=0,
        help="Global settings apply to all assigned projects. Project-level settings override Global for that project.",
    )

with col_proj:
    selected_project_id = None
    selected_project_label = None
    if scope == "Specific project":
        if projects.empty:
            st.warning("⚠️ You're not allocated to any projects yet.")
        else:
            labels = projects.apply(
                lambda r: f"{r['project_name']}  ({(r.get('project_code') or '').strip()})  #{int(r['project_id'])}",
                axis=1,
            ).tolist()
            selected_project_label = st.selectbox("Project", labels, key="notif_proj_pick")
            idx = labels.index(selected_project_label)
            selected_project_id = int(projects.iloc[idx]["project_id"])
    else:
        st.caption("Applies to all your assigned projects unless overridden per project.")

with col_delivery:
    digest_mode = st.selectbox(
        "Delivery frequency",
        DELIVERY_OPTIONS,
        index=0,
        key="notif_digest_mode",
        format_func=lambda x: f"{DELIVERY_ICONS.get(x, '')} {x.capitalize()}",
        help="How often you receive notifications. 'Instant' means as they happen.",
    )

scope_project_id = None if scope == "Global (all projects)" else selected_project_id

# Scope context banner
enabled_n, total_n = _count_enabled(prefs, scope_project_id)
scope_label = "All assigned projects" if scope_project_id is None else f"Project #{scope_project_id}"
st.markdown(
    f"""
<div class='scope-banner'>
    <span>{'🌐' if scope_project_id is None else '📁'}</span>
    <span>Editing: <strong>{scope_label}</strong> &nbsp;·&nbsp;
    {enabled_n}/{total_n} event types enabled &nbsp;·&nbsp;
    {DELIVERY_ICONS.get(digest_mode, '')} {digest_mode.capitalize()} delivery</span>
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================
# Bulk actions
# ============================================================
with st.container():
    st.markdown("<div class='bulk-bar'>", unsafe_allow_html=True)
    st.caption("⚡ Quick actions — apply to all event types in the current scope")
    ba1, ba2, ba3, ba4 = st.columns([1, 1, 1.15, 1.5])

    with ba1:
        if st.button("✅ Enable all", use_container_width=True, key="notif_enable_all"):
            with st.spinner("Saving…"):
                _apply_bulk(current_email, scope_project_id, digest_mode, "enable_all")
            st.toast("All notifications enabled.", icon="✅")
            st.rerun()

    with ba2:
        if st.button("🚫 Disable all", use_container_width=True, key="notif_disable_all"):
            with st.spinner("Saving…"):
                _apply_bulk(current_email, scope_project_id, digest_mode, "disable_all")
            st.toast("All notifications disabled.", icon="🚫")
            st.rerun()

    with ba3:
        if st.button("📲 In-app only", use_container_width=True, key="notif_inapp_only"):
            with st.spinner("Saving…"):
                _apply_bulk(current_email, scope_project_id, digest_mode, "inapp_only")
            st.toast("Switched to in-app only.", icon="📲")
            st.rerun()

    with ba4:
        if st.button("🧹 Clear custom prefs", use_container_width=True, key="notif_clear_scope"):
            with st.spinner("Clearing…"):
                clear_notification_prefs_for_scope(current_email, scope_project_id)
            st.toast("Custom preferences cleared — defaults restored.", icon="🧹")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# ============================================================
# Tabs
# ============================================================
tab_prefs, tab_summary, tab_reminders = st.tabs(
    ["⚙️ Preferences", "📋 Summary", "⏰ Reminders"]
)

# ---------------------------------------------------------
# Preferences tab
# ---------------------------------------------------------
with tab_prefs:
    if scope == "Specific project" and selected_project_id is None:
        st.info("👆 Select a project above to edit project-level preferences.")
    else:
        st.caption(
            "Changes are saved automatically as you toggle. "
            "Greyed-out In-app / Email toggles mean the event is disabled."
        )

        changed_any = False
        prefs_now = get_notification_prefs(current_email)
        prefs_now = _safe_df(prefs_now)

        for group, items in EVENT_TYPES.items():
            with st.expander(group, expanded=True):
                st.markdown(f"<div class='group-strip'>{group}</div>", unsafe_allow_html=True)

                # Column headers
                h1, h2, h3, h4 = st.columns([2.8, 0.9, 0.9, 0.9])
                with h1:
                    st.markdown("<div class='col-header'>Event</div>", unsafe_allow_html=True)
                with h2:
                    st.markdown("<div class='col-header'>Enabled</div>", unsafe_allow_html=True)
                with h3:
                    st.markdown("<div class='col-header'>In-app</div>", unsafe_allow_html=True)
                with h4:
                    st.markdown("<div class='col-header'>Email</div>", unsafe_allow_html=True)

                st.markdown("<hr style='margin:0.4rem 0 0.6rem 0; border-color:#f1f5f9;'/>", unsafe_allow_html=True)

                for (event_type, label) in items:
                    enabled, in_app, email, _dm = _default_pref(prefs_now, scope_project_id, event_type, digest_mode)

                    c1, c2, c3, c4 = st.columns([2.8, 0.9, 0.9, 0.9])

                    with c1:
                        st.markdown(
                            f"""<div class="event-row">
                                <div class="event-label">{label}</div>
                                <div class="event-code">{event_type}</div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                    with c2:
                        enabled_new = st.toggle(
                            "Enabled",
                            value=enabled,
                            label_visibility="collapsed",
                            key=f"en__{scope_project_id}__{event_type}",
                        )

                    with c3:
                        in_app_new = st.toggle(
                            "In-app",
                            value=in_app if enabled_new else False,
                            label_visibility="collapsed",
                            key=f"ia__{scope_project_id}__{event_type}",
                            disabled=not enabled_new,
                        )

                    with c4:
                        email_new = st.toggle(
                            "Email",
                            value=email if enabled_new else False,
                            label_visibility="collapsed",
                            key=f"em__{scope_project_id}__{event_type}",
                            disabled=not enabled_new,
                        )

                    if (enabled_new != enabled) or (in_app_new != in_app) or (email_new != email) or (digest_mode != _dm):
                        upsert_notification_pref(
                            user_email=current_email,
                            project_id=scope_project_id,
                            event_type=event_type,
                            in_app=in_app_new,
                            email=email_new,
                            enabled=enabled_new,
                            digest_mode=digest_mode,
                        )
                        changed_any = True

        if changed_any:
            st.toast("Preferences saved.", icon="✅")

# ---------------------------------------------------------
# Summary tab
# ---------------------------------------------------------
with tab_summary:
    prefs_now = get_notification_prefs(current_email)
    prefs_now = _safe_df(prefs_now)

    if prefs_now.empty:
        st.info(
            "No custom preferences saved yet — all events use their defaults (enabled, in-app only). "
            "Use the **Preferences** tab to customise."
        )
    else:
        # Stats row
        total_saved = len(prefs_now)
        enabled_saved = prefs_now[prefs_now["enabled"] == True].shape[0]
        email_saved = prefs_now[prefs_now["channel_email"] == True].shape[0]

        m1, m2, m3 = st.columns(3)
        m1.metric("Custom rules saved", total_saved)
        m2.metric("Enabled", enabled_saved)
        m3.metric("Email delivery on", email_saved)

        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

        # Filter helpers
        fcol1, fcol2 = st.columns([1.5, 1.5])
        with fcol1:
            filter_scope = st.selectbox(
                "Filter by scope",
                ["All", "Global", "Project-specific"],
                key="sum_filter_scope",
            )
        with fcol2:
            filter_enabled = st.selectbox(
                "Filter by status",
                ["All", "Enabled only", "Disabled only"],
                key="sum_filter_enabled",
            )

        show = prefs_now.copy()
        show["Scope"] = show["project_id"].apply(lambda x: "Global" if pd.isna(x) else f"Project #{int(x)}")

        if filter_scope == "Global":
            show = show[show["Scope"] == "Global"]
        elif filter_scope == "Project-specific":
            show = show[show["Scope"] != "Global"]

        if filter_enabled == "Enabled only":
            show = show[show["enabled"] == True]
        elif filter_enabled == "Disabled only":
            show = show[show["enabled"] == False]

        show = show.rename(
            columns={
                "event_type": "Event Type",
                "enabled": "Enabled",
                "channel_in_app": "In-app",
                "channel_email": "Email",
                "digest_mode": "Delivery",
                "updated_at": "Last updated",
            }
        )
        show = show[["Scope", "Event Type", "Enabled", "In-app", "Email", "Delivery", "Last updated"]]

        st.dataframe(show, use_container_width=True, hide_index=True, height=400)
        st.caption(f"Showing {len(show)} of {total_saved} saved rules.")

# ---------------------------------------------------------
# Reminders tab
# ---------------------------------------------------------
with tab_reminders:
    st.markdown(
        """
<div style='background:#fffbeb; border:1px solid #fde68a; border-left:5px solid #f59e0b;
     border-radius:8px; padding:0.8rem 1.1rem; margin-bottom:1rem; font-size:0.92rem; color:#92400e;'>
    ⏰ <strong>Reminders</strong> are time-based alerts — no manual trigger needed.
    You'll be notified about items that are <strong>overdue</strong> or <strong>due soon</strong>.
    <br/><span style='font-size:0.85rem; color:#b45309; margin-top:0.2rem; display:block;'>
    Requires a scheduled background job to emit reminder events.
    </span>
</div>
""",
        unsafe_allow_html=True,
    )

    r1, r2, r3 = st.columns([1, 1.2, 1.6])

    with r1:
        reminders_enabled = st.toggle("Enable reminders", value=True, key="notif_rem_enabled")

    with r2:
        due_soon_days = st.selectbox(
            "Due-soon window",
            [3, 7, 14, 21],
            index=1,
            key="notif_rem_days",
            help="You'll be alerted when items are due within this many days.",
            disabled=not reminders_enabled,
        )

    with r3:
        frequency = st.selectbox(
            "Run frequency",
            ["daily", "weekdays", "weekly"],
            index=0,
            key="notif_rem_freq",
            format_func=lambda x: {"daily": "📅 Daily", "weekdays": "🗓️ Weekdays only", "weekly": "📆 Weekly"}.get(x, x),
            disabled=not reminders_enabled,
        )

    t1, t2 = st.columns([1, 3])
    with t1:
        reminder_time = st.time_input(
            "Send at",
            value=dt.time(8, 30),
            key="notif_rem_time",
            disabled=not reminders_enabled,
        )
    with t2:
        if reminders_enabled:
            st.success(f"Reminders active — will run {frequency} at {reminder_time.strftime('%H:%M')} for items due within **{due_soon_days} days**.")
        else:
            st.warning("Reminders are currently disabled.")

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("**What reminders cover**")
    st.markdown(
        "RAID items due soon or overdue, Actions due soon or overdue, and custom deadlines "
        "(once you configure your deadline sources)."
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
    st.info(
        "💡 To activate reminders, wire up the scheduled job to emit "
        "`raid.due_soon`, `raid.overdue`, `action.due_soon`, and `action.overdue` events. "
        "Settings here will take effect once that job is running.",
        icon="ℹ️",
    )

    # Uncomment when DB helpers are ready:
    # if st.button("💾 Save reminder settings", use_container_width=True, disabled=not reminders_enabled):
    #     upsert_reminder_settings(...)
    #     st.toast("Reminder settings saved.", icon="✅")
    #     st.rerun()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.markdown("<div style='margin: 3rem 0 2rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()