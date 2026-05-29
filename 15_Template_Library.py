# ============================================================
# 15_📁_Template_Library.py — ScopeSight 1.0
# Central PMO Template Library (Gov Packs, RAID, NFR, etc.)
# ============================================================

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from auth.login import require_login
from modules.db import run_query, run_execute
from modules.storage import (
    upload_template_file,
    download_template_file,
    delete_template_file,
)
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# ------------------------------------------------------------
# DEV OVERRIDE
# ------------------------------------------------------------
query = st.query_params

if "dev" in query and query.get("dev") == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

require_login()

# ------------------------------------------------------------
# PAGE CONFIG
# ------------------------------------------------------------
st.set_page_config(
    page_title="📁 Template Library",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded",
)

set_pmo_theme(page_title="📁 PMO Template Library")
hide_streamlit_nav()
render_sidebar()

# ------------------------------------------------------------
# GLOBAL STYLES (match Weekly NFR formatting)
# ------------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Weekly NFR style language */
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
    font-weight: 700;
    text-align: center;
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
    font-weight: 700;
}

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0;
    color: #2d3748;
}

/* Left panel card (filters/upload) */
.panel-card {
    background: #FFFFFF;
    border: 2px solid #4facfe;
    border-radius: 12px;
    padding: 1.25rem;
    box-shadow: 0 4px 12px rgba(79, 172, 254, 0.10);
}

/* Template list card */
.template-card {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 16px 18px;
    border: 1px solid #E3E6F0;
    margin-bottom: 12px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.template-title {
    font-weight: 800;
    font-size: 1.08rem;
    color: #142D53;
    margin-bottom: 4px;
}
.template-desc {
    font-size: 0.9rem;
    color: #58657a;
    margin-bottom: 8px;
    line-height: 1.45;
}
.template-meta {
    font-size: 0.85rem;
    color: #7a869a;
}
.pill {
    background: #F0F2F6;
    padding: 2px 10px;
    border-radius: 999px;
    margin-right: 8px;
    display: inline-block;
    color: #142D53;
    font-size: 0.82rem;
}

/* Scroll helpers */
.template-scroll-box {
    max-height: 600px;
    overflow-y: auto;
    padding-right: 8px;
}

/* Scrollbar styling */
.template-scroll-box::-webkit-scrollbar { width: 8px; }
.template-scroll-box::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 10px; }
.template-scroll-box::-webkit-scrollbar-thumb { background: #888; border-radius: 10px; }
.template-scroll-box::-webkit-scrollbar-thumb:hover { background: #555; }

/* Buttons match app */
div.stButton > button {
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    color: white;
    font-size: 1.02rem;
    font-weight: 650;
    padding: 0.65rem 1.4rem;
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

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def get_current_user():
    email = st.session_state.get("email")
    if not email:
        return None

    rows = run_query(
        """
        SELECT user_id, email, role
        FROM users
        WHERE email = :email
        LIMIT 1
        """,
        {"email": email},
    )

    if rows is None or (isinstance(rows, pd.DataFrame) and rows.empty):
        return None

    row = rows.iloc[0] if isinstance(rows, pd.DataFrame) else rows[0]

    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "role": row.get("role", "user"),
    }


user = get_current_user()
role = user["role"] if user else "viewer"
user_id = user["user_id"] if user else None

if st.session_state.get("force_dev_mode"):
    role = "admin"


def as_dataframe(rows) -> pd.DataFrame:
    if rows is None:
        return pd.DataFrame()
    if isinstance(rows, pd.DataFrame):
        return rows
    return pd.DataFrame(rows)


# ------------------------------------------------------------
# DB LOADERS
# ------------------------------------------------------------
def load_templates() -> pd.DataFrame:
    rows = run_query(
        """
        SELECT
            t.template_id,
            t.template_name,
            t.template_type,
            t.description,
            t.file_path,
            t.uploaded_at,
            t.client_scope,
            u.email AS uploaded_by
        FROM templates t
        LEFT JOIN users u ON u.user_id = t.uploaded_by
        WHERE t.is_active = TRUE
        ORDER BY t.uploaded_at DESC
        """
    )
    return as_dataframe(rows)


def load_pending_delete_requests() -> pd.DataFrame:
    rows = run_query(
        """
        SELECT
            r.request_id,
            r.template_id,
            r.requested_at,
            r.reason,
            u.email AS requested_by,
            t.template_name,
            t.template_type,
            t.file_path
        FROM template_delete_requests r
        JOIN templates t ON t.template_id = r.template_id
        JOIN users u ON u.user_id = r.requested_by
        WHERE r.status = 'pending'
        ORDER BY r.requested_at ASC
        """
    )
    return as_dataframe(rows)


def has_rows(result) -> bool:
    if result is None:
        return False
    if isinstance(result, pd.DataFrame):
        return not result.empty
    try:
        return len(result) > 0
    except TypeError:
        return bool(result)


# ------------------------------------------------------------
# DELETE REQUEST HANDLING
# ------------------------------------------------------------
def create_delete_request(template_id: int, reason: str | None = None):
    existing = run_query(
        """
        SELECT request_id
        FROM template_delete_requests
        WHERE template_id = :tid
          AND requested_by = :uid
          AND status = 'pending'
        """,
        {"tid": template_id, "uid": user_id},
    )

    if has_rows(existing):
        st.info("You already have a pending delete request for this template.")
        return

    run_execute(
        """
        INSERT INTO template_delete_requests (
            template_id, requested_by, reason
        ) VALUES (:tid, :uid, :reason)
        """,
        {"tid": template_id, "uid": user_id, "reason": reason},
    )

    st.success("Delete request submitted for admin approval.")


def approve_delete_request(request_row: pd.Series):
    template_id = int(request_row["template_id"])
    request_id = int(request_row["request_id"])
    file_path = request_row["file_path"]

    # 1) Soft delete
    run_execute(
        "UPDATE templates SET is_active = FALSE WHERE template_id = :tid",
        {"tid": template_id},
    )

    # 2) Mark request as approved
    run_execute(
        """
        UPDATE template_delete_requests
        SET status = 'approved',
            reviewed_by = :uid,
            reviewed_at = NOW()
        WHERE request_id = :rid
        """,
        {"uid": user_id, "rid": request_id},
    )

    # 3) Remove from storage
    delete_template_file(file_path)

    st.success(f"Template '{request_row['template_name']}' deleted.")


def reject_delete_request(request_row: pd.Series, rejection_reason=None):
    rejection_note = f"\n[Admin note] {rejection_reason or 'No reason given.'}"

    run_execute(
        """
        UPDATE template_delete_requests
        SET status = 'rejected',
            reviewed_by = :uid,
            reviewed_at = NOW(),
            reason = COALESCE(reason, '') || :note
        WHERE request_id = :rid
        """,
        {
            "uid": user_id,
            "note": rejection_note,
            "rid": int(request_row["request_id"]),
        },
    )

    st.info(f"Delete request for '{request_row['template_name']}' rejected.")


# ------------------------------------------------------------
# MAIN LAYOUT (Tabbed)
# ------------------------------------------------------------
template_df = load_templates()

if role == "admin":
    tab_library, tab_admin = st.tabs(["📚 Template Library", "🛡 Admin Delete Requests"])
else:
    tab_library = st.container()
    tab_admin = None  # unused


# ===============================
# TAB: TEMPLATE LIBRARY (existing UI)
# ===============================
with tab_library:
    left_col, right_col = st.columns([2, 5])

    # ===============================
    # LEFT COLUMN — FILTERS + UPLOAD
    # ===============================
    with left_col:
        st.markdown("<div class='section-header'><h3>🔍 Filters & Upload</h3></div>", unsafe_allow_html=True)
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)

        st.markdown("<div class='step-header'><h4>Filter Templates</h4></div>", unsafe_allow_html=True)

        available_types = ["All", "Governance", "NFR", "Other"]
        if not template_df.empty:
            dynamic_types = template_df["template_type"].dropna().unique().tolist()
            available_types += sorted(dynamic_types)

        selected_type = st.selectbox("Template type", available_types, index=0)
        search_term = st.text_input("Search by name or description", "")

        st.markdown("<hr/>", unsafe_allow_html=True)

        # Upload section
        if role in ("user", "admin"):
            st.markdown("<div class='step-header'><h4>Upload New Template</h4></div>", unsafe_allow_html=True)

            st.markdown(
                """
                <div class='info-box'>
                    <strong style='color:#48bb78;'>💡 Recommended</strong><br/>
                    Use clear names (e.g., “Gov Pack v3 — Tier 1”) and keep descriptions short and specific.
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.form("upload_template_form", clear_on_submit=True):
                upload_file = st.file_uploader(
                    "Select file",
                    type=["pptx", "ppt", "xlsx", "xls", "docx", "doc", "pdf"],
                )

                upload_type = st.selectbox(
                    "Template category",
                    ["Governance", "NFR", "Other"],
                    index=0,
                )

                template_name = st.text_input("Template name (display)", "")
                description = st.text_area("Description (optional)", height=80)

                submitted = st.form_submit_button("Upload Template")

            if submitted:
                if not upload_file:
                    st.error("Please choose a file to upload.")
                elif not template_name.strip():
                    st.error("Please enter a template name.")
                else:
                    try:
                        # Upload file to storage
                        storage_path = upload_template_file(upload_file, upload_type)

                        # Insert into database using NAMED PARAMETERS
                        run_execute(
                            """
                            INSERT INTO templates (
                                template_name,
                                template_type,
                                description,
                                file_path,
                                uploaded_by,
                                client_scope,
                                is_active
                            ) VALUES (:name, :type, :desc, :path, :user, 'global', TRUE)
                            """,
                            {
                                "name": template_name.strip(),
                                "type": upload_type.strip(),
                                "desc": (description or "").strip() or None,
                                "path": storage_path,
                                "user": user_id,
                            },
                        )

                        st.success(f"✅ Template '{template_name}' uploaded successfully!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ Upload failed: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())

        else:
            st.info("Only Users and Admins can upload templates.")

        st.markdown("</div>", unsafe_allow_html=True)  # close panel-card

    # ======================
    # RIGHT COLUMN — LISTING
    # ======================
    with right_col:
        st.markdown("<div class='section-header'><h3>📚 Available Templates</h3></div>", unsafe_allow_html=True)

        if template_df.empty:
            st.info("No templates found yet.")
        else:
            df = template_df.copy()

            # Type filter
            if selected_type != "All":
                df = df[df["template_type"] == selected_type]

            # Search filter
            if search_term:
                s = search_term.lower()
                df = df[
                    df["template_name"].str.lower().str.contains(s)
                    | df["description"].fillna("").str.lower().str.contains(s)
                ]

            if df.empty:
                st.warning("No templates match your filters.")
            else:
                template_scroll = st.container(height=600)

                with template_scroll:
                    for _, row in df.iterrows():
                        with st.container():
                            st.markdown("<div class='template-card'>", unsafe_allow_html=True)

                            c1, c2, c3 = st.columns([5, 2, 1.5])

                            # ---------------------------
                            # Column 1 — Template Info
                            # ---------------------------
                            with c1:
                                st.markdown(
                                    f"""
                                    <div class="template-title">{row['template_name']}</div>
                                    <div class="template-desc">{row['description'] or 'No description provided'}</div>
                                    <div class="template-meta">
                                        <span class="pill">📁 {str(row['template_type']).title()}</span>
                                        <span>👤 {row['uploaded_by'] or 'Unknown'}</span>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

                            # ---------------------------
                            # Column 2 — Date
                            # ---------------------------
                            with c2:
                                uploaded_at = row["uploaded_at"]
                                if isinstance(uploaded_at, str):
                                    try:
                                        uploaded_at = datetime.fromisoformat(uploaded_at)
                                    except Exception:
                                        pass

                                date_str = (
                                    uploaded_at.strftime("%d %b %Y")
                                    if isinstance(uploaded_at, datetime)
                                    else str(uploaded_at)
                                )
                                time_str = (
                                    uploaded_at.strftime("%H:%M")
                                    if isinstance(uploaded_at, datetime)
                                    else ""
                                )

                                st.markdown(
                                    f"""
                                    <div style="text-align:right; padding-top:6px;">
                                        <div style="font-size:0.92rem; color:#142D53; font-weight:650;">
                                            📅 {date_str}
                                        </div>
                                        <div style="font-size:0.82rem; color:#7a869a;">
                                            {time_str}
                                        </div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

                            # ---------------------------
                            # Column 3 — Download & Delete
                            # ---------------------------
                            with c3:
                                file_bytes = download_template_file(row["file_path"])

                                bc1, bc2 = st.columns([1, 1])

                                with bc1:
                                    st.download_button(
                                        label="⬇️",
                                        data=file_bytes,
                                        file_name=os.path.basename(row["file_path"]),
                                        key=f"download_{row['template_id']}",
                                        help="Download template",
                                        use_container_width=True,
                                    )

                                with bc2:
                                    if role in ("user", "admin"):
                                        if st.button(
                                            "🗑️",
                                            key=f"del_btn_{row['template_id']}",
                                            help="Request deletion",
                                            use_container_width=True,
                                        ):
                                            st.session_state[f"show_delete_{row['template_id']}"] = True

                                # Delete confirmation UI
                                if st.session_state.get(f"show_delete_{row['template_id']}", False):
                                    st.markdown(
                                        """
                                        <div style="margin-top:12px;">
                                            <div class='step-header' style='margin:0.5rem 0 0.75rem 0;'>
                                                <h4>Request Deletion</h4>
                                            </div>
                                        </div>
                                        """,
                                        unsafe_allow_html=True,
                                    )

                                    reason = st.text_input(
                                        "Reason (optional)",
                                        key=f"reason_{row['template_id']}",
                                        placeholder="Why delete this template?",
                                    )

                                    submit_col, cancel_col = st.columns(2)

                                    with submit_col:
                                        if st.button(
                                            "✓ Submit",
                                            key=f"confirm_del_{row['template_id']}",
                                            type="primary",
                                            use_container_width=True,
                                        ):
                                            create_delete_request(
                                                template_id=int(row["template_id"]),
                                                reason=reason,
                                            )
                                            del st.session_state[f"show_delete_{row['template_id']}"]
                                            st.rerun()

                                    with cancel_col:
                                        if st.button(
                                            "✗ Cancel",
                                            key=f"cancel_del_{row['template_id']}",
                                            use_container_width=True,
                                        ):
                                            del st.session_state[f"show_delete_{row['template_id']}"]
                                            st.rerun()

                            st.markdown("</div>", unsafe_allow_html=True)  # close template-card


# ------------------------------------------------------------
# TAB: ADMIN PANEL (moved unchanged, just wrapped)
# ------------------------------------------------------------
if role == "admin" and tab_admin is not None:
    with tab_admin:
        st.markdown("<div class='section-header'><h3>🛡 Admin: Pending Delete Requests</h3></div>", unsafe_allow_html=True)

        pending = load_pending_delete_requests()

        if pending.empty:
            st.success("✅ No pending delete requests.")
        else:
            st.info(f"📋 {len(pending)} pending request(s) awaiting review")

            for _, req in pending.iterrows():
                with st.container():
                    st.markdown(
                        """
                        <div style="
                            background:#FFF9F5;
                            border-radius:12px;
                            padding:18px 20px;
                            border-left: 4px solid #FF6B35;
                            margin-bottom:16px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                        ">
                        """,
                        unsafe_allow_html=True,
                    )

                    col_header, col_meta = st.columns([3, 1])

                    with col_header:
                        st.markdown(
                            f"""
                            <div style="margin-bottom:12px;">
                                <span style="
                                    background:#FF6B35;
                                    color:white;
                                    padding:3px 10px;
                                    border-radius:6px;
                                    font-size:0.85rem;
                                    font-weight:600;
                                    margin-right:10px;
                                ">#{req['request_id']}</span>
                                <span style="font-size:1.1rem; font-weight:600; color:#142D53;">
                                    {req['template_name']}
                                </span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with col_meta:
                        st.markdown(
                            f"""
                            <div style="text-align:right;">
                                <div style="
                                    background:#F0F2F6;
                                    padding:4px 12px;
                                    border-radius:6px;
                                    font-size:0.85rem;
                                    color:#142D53;
                                    display:inline-block;
                                ">
                                    📁 {req['template_type']}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    st.markdown(
                        f"""
                        <div style="
                            background:white;
                            padding:12px 16px;
                            border-radius:8px;
                            margin:12px 0;
                        ">
                            <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:12px;">
                                <div>
                                    <div style="font-size:0.8rem; color:#888; margin-bottom:4px;">👤 REQUESTED BY</div>
                                    <div style="font-weight:500; color:#142D53;">{req['requested_by']}</div>
                                </div>
                                <div>
                                    <div style="font-size:0.8rem; color:#888; margin-bottom:4px;">📅 REQUESTED AT</div>
                                    <div style="font-weight:500; color:#142D53;">{req['requested_at']}</div>
                                </div>
                            </div>
                            <div>
                                <div style="font-size:0.8rem; color:#888; margin-bottom:6px;">💬 REASON</div>
                                <div style="
                                    background:#F8F9FA;
                                    padding:10px;
                                    border-radius:6px;
                                    color:#555;
                                    font-style:italic;
                                ">
                                    {req['reason'] or '<em>No reason provided</em>'}
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    col_approve, col_reject, _col_spacer = st.columns([1.5, 1.5, 2])

                    with col_approve:
                        if st.button(
                            "✅ Approve & Delete",
                            key=f"approve_{req['request_id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            approve_delete_request(req)
                            st.rerun()

                    with col_reject:
                        if st.button(
                            "❌ Reject",
                            key=f"reject_btn_{req['request_id']}",
                            use_container_width=True,
                        ):
                            st.session_state[f"show_reject_{req['request_id']}"] = True

                    if st.session_state.get(f"show_reject_{req['request_id']}", False):
                        st.markdown(
                            """
                            <div style="
                                border-left: 3px solid #DC3545;
                                padding-left: 12px;
                                margin-top: 12px;
                            ">
                            """,
                            unsafe_allow_html=True,
                        )

                        reject_note = st.text_input(
                            "Reason for rejection (optional)",
                            key=f"reject_note_{req['request_id']}",
                            placeholder="Explain why this request is being rejected...",
                        )

                        reject_col1, reject_col2 = st.columns(2)

                        with reject_col1:
                            if st.button(
                                "✓ Confirm Rejection",
                                key=f"confirm_reject_{req['request_id']}",
                                type="primary",
                                use_container_width=True,
                            ):
                                reject_delete_request(req, reject_note)
                                del st.session_state[f"show_reject_{req['request_id']}"]
                                st.rerun()

                        with reject_col2:
                            if st.button(
                                "Cancel",
                                key=f"cancel_reject_{req['request_id']}",
                                use_container_width=True,
                            ):
                                del st.session_state[f"show_reject_{req['request_id']}"]
                                st.rerun()

                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------
# FOOTER
# ------------------------------------------------------------
pmo_footer()
