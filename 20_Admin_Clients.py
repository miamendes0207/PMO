# ============================================================
# 20_🎛️_Admin_Clients.py — ScopeSight v2.1
# Client Administration (Create • Update • Secure Delete • Approve/Deny Pending)
# Uses client_scaffold as the single source of truth
# ============================================================

import streamlit as st
import json
import bcrypt

from auth.login import require_login
from modules.db import run_query, run_execute
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav
from modules.log_utils import log_event
from modules.notifications_utils import send_notification

from modules.client_filesystem import (
    ensure_client_folder,
    delete_client_folder,
    safe_fs_name,
)

# -----------------------------------------------------------
# Helper: Centered Subheader (kept)
# -----------------------------------------------------------
def subheader_center(text: str):
    st.markdown(
        f"<h3 style='text-align:center; margin-top:1.6rem; margin-bottom:0.8rem;'>{text}</h3>",
        unsafe_allow_html=True
    )

# -----------------------------------------------------------
# Helpers: schema-safe column/table checks
# -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def _table_exists(table_name: str) -> bool:
    df = run_query(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=:t
        LIMIT 1
        """,
        {"t": table_name},
    )
    return df is not None and not df.empty

@st.cache_data(show_spinner=False)
def _has_col(table_name: str, col: str) -> bool:
    df = run_query(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
        """,
        {"t": table_name, "c": col},
    )
    return df is not None and not df.empty

def _get_admin_user_id() -> int | None:
    em = (st.session_state.get("email") or "").strip().lower()
    if not em:
        return None
    df = run_query("SELECT user_id FROM public.users WHERE LOWER(email)=:e LIMIT 1", {"e": em})
    if df is None or df.empty:
        return None
    try:
        return int(df.iloc[0]["user_id"])
    except Exception:
        return None

def _update_access_request_for_client(client_id: int, decision: str, notes: str):
    """
    Optional: keep access_requests in sync for new_client requests.
    Will quietly no-op if table/columns don't exist.
    """
    if not _table_exists("access_requests"):
        return

    # Detect likely columns
    has_status = _has_col("access_requests", "status")
    has_reviewed_on = _has_col("access_requests", "reviewed_on")
    has_review_notes = _has_col("access_requests", "review_notes")
    has_target_id = _has_col("access_requests", "target_id")
    has_request_type = _has_col("access_requests", "request_type")

    if not (has_target_id and has_request_type):
        return

    sets = []
    params = {"cid": client_id, "notes": (notes or "").strip()}

    if has_status:
        sets.append("status = :st")
        params["st"] = "approved" if decision == "approve" else "rejected"
    if has_reviewed_on:
        sets.append("reviewed_on = NOW()")
    if has_review_notes:
        sets.append("review_notes = :notes")

    if not sets:
        return

    run_execute(
        f"""
        UPDATE public.access_requests
        SET {", ".join(sets)}
        WHERE request_type = 'new_client'
          AND target_id = :cid
        """,
        params,
    )

# -----------------------------------------------------------
# INIT
# -----------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🎛️ Client Administration")
render_sidebar()

role = st.session_state.get("role", "user")
if role != "admin":
    st.error("🚫 Only administrators may manage clients.")
    pmo_footer()
    st.stop()

admin_uid = _get_admin_user_id()

# ---------------------------------------------------------
# STYLES (match Project Submission Tracker / Weekly NFR look)
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Shared visual language */
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
# INTRO
# ---------------------------------------------------------

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 Tip</strong><br/>
    Pending client submissions come from CEO/Exec requests. Approving them makes them available across the app (where pages filter <code>status='approved'</code>).
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================
# LOAD CLIENTS
# ============================================================
clients_df = run_query("""
    SELECT
        id              AS scaffold_id,
        client_name,
        client_code,
        tier,
        description,
        submitted_on,
        approved_on,
        settings
    FROM public.client_scaffold
    WHERE status = 'approved'
    ORDER BY client_name
""")

pending_df = run_query("""
    SELECT
        id              AS scaffold_id,
        client_name,
        client_code,
        tier,
        description,
        status,
        submitted_by,
        submitted_on,
        approved_on,
        rejected_on,
        rejection_reason,
        settings
    FROM public.client_scaffold
    WHERE status IN ('pending','awaiting_approval')
    ORDER BY submitted_on DESC
""")

rejected_df = run_query("""
    SELECT
        id              AS scaffold_id,
        client_name,
        client_code,
        tier,
        description,
        status,
        submitted_by,
        submitted_on,
        rejected_on,
        rejection_reason
    FROM public.client_scaffold
    WHERE status IN ('rejected','withdrawn')
    ORDER BY submitted_on DESC
    LIMIT 200
""")

# ============================================================
# TABS
# ============================================================
tab_pending, tab_existing, tab_create, tab_update = st.tabs([
    "🕒 Pending Approvals",
    "📋 Existing + Delete",
    "➕ Create New",
    "✏️ Update Client",
])

# ============================================================
# TAB 0 — PENDING CLIENT REQUESTS (APPROVE / REJECT)
# ============================================================
with tab_pending:
    st.markdown(
        """
<div class='section-header'>
    <h3>🕒 Pending Client Approvals</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if pending_df is None or pending_df.empty:
        st.success("✅ No pending client submissions.")
    else:
        show = pending_df.copy()
        for c in ["submitted_on", "approved_on", "rejected_on"]:
            if c in show.columns:
                show[c] = show[c].astype(str)

        st.markdown(
            """
<div class='step-header'>
    <h4>Pending Submissions</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            show[["scaffold_id", "client_name", "client_code", "status", "submitted_by", "submitted_on"]],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            """
<div class='step-header'>
    <h4>Approve or Reject</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        pick_map = {
            f"{r.client_name} ({r.client_code}) [#{int(r.scaffold_id)}]": int(r.scaffold_id)
            for _, r in pending_df.iterrows()
        }
        choice = st.selectbox("Select pending client:", list(pick_map.keys()), key="pending_pick")
        scaffold_id = pick_map[choice]

        row = pending_df[pending_df["scaffold_id"] == scaffold_id].iloc[0]
        client_name = row.get("client_name") or ""
        client_code = row.get("client_code") or ""
        current_status = row.get("status") or "pending"

        st.markdown(
            f"""
            <div class='nfr-card'>
                <h3>Submission Details</h3>
                <div class='info-row'><strong>Client:</strong> {client_name}</div>
                <div class='info-row'><strong>Code:</strong> <code>{client_code}</code></div>
                <div class='info-row'><strong>Status:</strong> {current_status}</div>
                <div class='info-row'><strong>Submitted by:</strong> {row.get('submitted_by')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        admin_notes = st.text_area("Admin notes", key="pending_admin_notes")

        colA, colB = st.columns(2)

        # --------------------------
        # APPROVE
        # --------------------------
        if colA.button("✅ Approve Client", use_container_width=True, key="btn_approve_pending"):
            # Build dynamic update based on available columns
            sets = ["status = 'approved'", "approved_on = NOW()"]
            params = {"id": scaffold_id}

            if _has_col("client_scaffold", "approved_by") and admin_uid is not None:
                sets.append("approved_by = :ab")
                params["ab"] = admin_uid

            # Clear rejection fields if they exist
            if _has_col("client_scaffold", "rejected_on"):
                sets.append("rejected_on = NULL")
            if _has_col("client_scaffold", "rejected_by"):
                sets.append("rejected_by = NULL")
            if _has_col("client_scaffold", "rejection_reason"):
                sets.append("rejection_reason = NULL")

            run_execute(
                f"UPDATE public.client_scaffold SET {', '.join(sets)} WHERE id = :id",
                params,
            )

            # Ensure folder exists (safe)
            if client_code:
                ensure_client_folder(client_code)

            log_event("client_approved", {
                "client_name": client_name,
                "client_code": client_code,
                "approved_by": st.session_state.get("email"),
                "notes": (admin_notes or "").strip(),
            })
            send_notification("client_approved", {
                "client_name": client_name,
                "client_code": client_code,
                "approved_by": st.session_state.get("email"),
                "notes": (admin_notes or "").strip(),
            })

            _update_access_request_for_client(scaffold_id, "approve", admin_notes or "")

            st.success(f"✅ Approved '{client_name}'. It will now appear across the app where clients are filtered as approved.")
            st.rerun()

        # --------------------------
        # REJECT
        # --------------------------
        if colB.button("❌ Reject Client", use_container_width=True, key="btn_reject_pending"):
            reason = (admin_notes or "").strip()
            if not reason:
                st.error("Please add a rejection reason in the Admin notes box.")
                st.stop()

            sets = ["status = 'rejected'"]
            params = {"id": scaffold_id}

            if _has_col("client_scaffold", "rejected_on"):
                sets.append("rejected_on = NOW()")
            if _has_col("client_scaffold", "rejected_by") and admin_uid is not None:
                sets.append("rejected_by = :rb")
                params["rb"] = admin_uid
            if _has_col("client_scaffold", "rejection_reason"):
                sets.append("rejection_reason = :rr")
                params["rr"] = reason

            run_execute(
                f"UPDATE public.client_scaffold SET {', '.join(sets)} WHERE id = :id",
                params,
            )

            log_event("client_rejected", {
                "client_name": client_name,
                "client_code": client_code,
                "rejected_by": st.session_state.get("email"),
                "reason": reason,
            })
            send_notification("client_rejected", {
                "client_name": client_name,
                "client_code": client_code,
                "rejected_by": st.session_state.get("email"),
                "reason": reason,
            })

            _update_access_request_for_client(scaffold_id, "reject", reason)

            st.success(f"❌ Rejected '{client_name}'. It remains visible only as a rejected submission to admins/requester (depending on views).")
            st.rerun()

    # Optional: show recent rejected/withdrawn
    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown(
        """
<div class='step-header'>
    <h4>Recently Rejected / Withdrawn</h4>
</div>
""",
        unsafe_allow_html=True,
    )

    if rejected_df is None or rejected_df.empty:
        st.info("No rejected/withdrawn clients logged.")
    else:
        rshow = rejected_df.copy()
        for c in ["submitted_on", "rejected_on"]:
            if c in rshow.columns:
                rshow[c] = rshow[c].astype(str)
        st.dataframe(
            rshow[["scaffold_id", "client_name", "client_code", "status", "submitted_on", "rejected_on", "rejection_reason"]],
            use_container_width=True,
            hide_index=True,
        )

# ============================================================
# TAB 1 — EXISTING CLIENT LIST + DELETE
# ============================================================
with tab_existing:
    st.markdown(
        """
<div class='section-header'>
    <h3>📋 Existing Clients</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if clients_df is not None and not clients_df.empty:
        display = clients_df.copy()
        for col in ["submitted_on", "approved_on"]:
            if col in display.columns:
                display[col] = display[col].astype(str)

        st.markdown(
            """
<div class='step-header'>
    <h4>Snapshot</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(
            display[["scaffold_id", "client_name", "client_code", "submitted_on", "approved_on"]],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No approved clients found.")

    # ----------------------------
    # DELETE CLIENT (unchanged logic)
    # ----------------------------
    if clients_df is not None and not clients_df.empty:
        st.markdown(
            """
<div class='section-header'>
    <h3>🗑️ Delete a Client</h3>
</div>
""",
            unsafe_allow_html=True,
        )

        client_map = {
            f"{row.client_name} ({row.client_code}) [#{row.scaffold_id}]":
                (row.scaffold_id, row.client_code)
            for _, row in clients_df.iterrows()
        }

        choice = st.selectbox("Select a client to delete:", list(client_map.keys()), key="delete_pick")
        scaffold_id, client_code = client_map[choice]

        delete_trigger = st.button("🗑️ Delete Selected Client", type="primary")

        if "delete_mode" not in st.session_state:
            st.session_state["delete_mode"] = False

        if delete_trigger:
            st.session_state["delete_mode"] = True

        if st.session_state["delete_mode"]:
            st.error("⚠️ WARNING: This is permanent")

            st.markdown("""
            <b>Deleting a client will:</b><br>
            • Remove the scaffold entry<br>
            • Delete the client's filesystem folder<br>
            • Log a permanent system event<br><br>
            <b>This cannot be undone.</b>
            """, unsafe_allow_html=True)

            pwd = st.text_input("Re-enter your admin password:", type="password")

            colA, colB = st.columns(2)
            confirm = colA.button("🔥 Confirm Delete")
            cancel = colB.button("Cancel")

            if cancel:
                st.session_state["delete_mode"] = False
                st.rerun()

            if confirm:
                # Validate admin password
                pwd_row = run_query("SELECT password_hash FROM users WHERE email = :e", {
                    "e": st.session_state.get("email")
                })

                if pwd_row is None or pwd_row.empty:
                    st.error("Authentication error.")
                else:
                    stored_hash = pwd_row.iloc[0]["password_hash"].encode()

                    if not bcrypt.checkpw(pwd.encode(), stored_hash):
                        st.error("❌ Incorrect password.")
                    else:
                        # Fetch name before deletion
                        row = run_query(
                            "SELECT client_name FROM client_scaffold WHERE id = :id",
                            {"id": scaffold_id}
                        )
                        client_name = row.iloc[0]["client_name"] if row is not None and not row.empty else client_code

                        # Delete DB record
                        run_execute("DELETE FROM client_scaffold WHERE id = :id", {
                            "id": scaffold_id
                        })

                        # Delete folder
                        delete_client_folder(client_code)

                        # Log + notify
                        log_event("client_deleted", {
                            "client_name": client_name,
                            "client_code": client_code,
                            "deleted_by": st.session_state.get("email")
                        })

                        send_notification("client_deleted", {
                            "client_name": client_name,
                            "client_code": client_code,
                            "deleted_by": st.session_state.get("email")
                        })

                        st.success(f"🗑️ Client '{client_name}' permanently deleted.")
                        st.session_state["delete_mode"] = False
                        st.rerun()

# ============================================================
# TAB 2 — CREATE NEW CLIENT
# ============================================================
with tab_create:
    st.markdown(
        """
<div class='section-header'>
    <h3>➕ Create New Client</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("create_client_form"):
        client_name = st.text_input("Client Name")
        suggested_code = safe_fs_name(client_name or "")
        client_code_input = st.text_input("Client Code", value="", placeholder="e.g. demo_client")

        if suggested_code:
            st.caption(f"Suggested code: `{suggested_code}`")

        st.markdown(
            """
<div class='step-header'>
    <h4>🎨 Branding Settings</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            brand_primary = st.color_picker("Primary Brand Colour", "#142D53")
        with col2:
            brand_secondary = st.color_picker("Secondary Brand Colour", "#1E74BB")

        submit_create = st.form_submit_button("Create Client")

        if submit_create:
            if not client_name:
                st.error("Client name is required.")
                st.stop()

            # Final client code
            final_code = client_code_input.strip() or suggested_code
            final_code = safe_fs_name(final_code)

            if not final_code:
                st.error("Invalid client code.")
                st.stop()

            email = st.session_state.get("email")

            settings_block = {
                "branding": {
                    "primary": brand_primary,
                    "secondary": brand_secondary
                }
            }

            # Insert scaffold entry (approved)
            run_execute("""
                INSERT INTO client_scaffold (
                    client_name, client_code,
                    tier, description,
                    submitted_by, submitted_on,
                    status,
                    access_list, raids_config, actions_config, nfr_config,
                    settings,
                    approved_on
                )
                VALUES (
                    :name, :code,
                    'tier_1', '',
                    (SELECT user_id FROM users WHERE email = :email),
                    NOW(),
                    'approved',
                    '[]'::jsonb,
                    '{}'::jsonb,
                    '{}'::jsonb,
                    '{}'::jsonb,
                    CAST(:settings AS jsonb),
                    NOW()
                )
            """, {
                "name": client_name.strip(),
                "code": final_code,
                "email": email,
                "settings": json.dumps(settings_block)
            })

            ensure_client_folder(final_code)

            log_event("client_created", {
                "client_name": client_name.strip(),
                "client_code": final_code,
                "created_by": email
            })

            send_notification("client_created", {
                "client_name": client_name.strip(),
                "client_code": final_code,
                "created_by": email
            })

            st.success(f"✅ Client '{client_name}' created.")
            st.rerun()

# ============================================================
# TAB 3 — UPDATE EXISTING CLIENTS
# ============================================================
with tab_update:
    st.markdown(
        """
<div class='section-header'>
    <h3>✏️ Update Client</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if clients_df is not None and not clients_df.empty:
        lookup = {
            f"{row.client_name} ({row.client_code}) [#{row.scaffold_id}]": row.scaffold_id
            for _, row in clients_df.iterrows()
        }

        selection = st.selectbox("Select a client to update", list(lookup.keys()), key="update_pick")
        scaffold_id = lookup[selection]

        current = clients_df[clients_df.scaffold_id == scaffold_id].iloc[0]

        st.markdown(
            """
<div class='step-header'>
    <h4>✏️ Basic Details</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        new_name = st.text_input("Client Name", value=current.client_name)
        st.text_input("Client Code (immutable)", value=current.client_code, disabled=True)

        st.markdown(
            """
<div class='step-header'>
    <h4>🎨 Branding Settings</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        raw_settings = current.settings
        if isinstance(raw_settings, str):
            try:
                settings_obj = json.loads(raw_settings)
            except Exception:
                settings_obj = {}
        else:
            settings_obj = raw_settings or {}

        branding = settings_obj.get("branding", {})

        colA, colB = st.columns(2)
        with colA:
            brand_primary = st.color_picker("Primary Brand", branding.get("primary", "#142D53"))
        with colB:
            brand_secondary = st.color_picker("Secondary Brand", branding.get("secondary", "#1E74BB"))

        if st.button("💾 Save Changes", key="btn_save_client_changes"):
            updated_settings = {
                "branding": {
                    "primary": brand_primary,
                    "secondary": brand_secondary
                }
            }

            run_execute("""
                UPDATE client_scaffold
                SET client_name = :name,
                    settings    = CAST(:settings AS jsonb)
                WHERE id = :id
            """, {
                "id": scaffold_id,
                "name": new_name.strip(),
                "settings": json.dumps(updated_settings)
            })

            log_event("client_updated", {
                "scaffold_id": int(scaffold_id),
                "client_name": new_name.strip(),
                "client_code": current.client_code,
                "updated_by": st.session_state.get("email")
            })

            send_notification("client_updated", {
                "client_name": new_name.strip(),
                "client_code": current.client_code,
                "updated_by": st.session_state.get("email")
            })

            st.success("✅ Client updated successfully.")
            st.rerun()

    else:
        st.info("No clients available for update.")

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
