# ============================================================
# 21_🔄_Admin_Resource_Pool.py — ScopeSight v3.8
# Admin Resource Pool + Allocations (Tabbed + Waiting Area)
# ============================================================

import streamlit as st
import pandas as pd

from auth.login import require_login
from modules.db import run_query, run_execute
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# INIT
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🔄 Admin — Resource Pool")
render_sidebar()

role = st.session_state.get("role", "user")
if role != "admin":
    st.error("🚫 Only administrators may manage the resource pool.")
    st.stop()

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
# INTRO (Tracker-style header + green divider + tip)
# ---------------------------------------------------------
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#48bb78;'>💡 Tip</strong><br/>
    Use the <b>Waiting Area</b> to triage newly created users (auto-linked resources),
    then complete their resource profile and activate them.
</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def table_exists(table_name: str) -> bool:
    df = run_query(
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=:t
        LIMIT 1
        """,
        {"t": table_name},
    )
    return df is not None and not df.empty


HAS_SKILLS = table_exists("skills") and table_exists("resource_skills")

def load_skill_list():
    if not HAS_SKILLS:
        return []
    df = run_query("SELECT skill_name FROM public.skills ORDER BY skill_name")
    if df is None or df.empty:
        return []
    return df["skill_name"].astype(str).tolist()

# ---------------------------------------------------------
# SKILLS HELPERS (Matrix-aware)
# ---------------------------------------------------------
def load_skills_with_display():
    """
    Returns a dataframe of skills with display-friendly fields.
    Safe to call even if tables exist but are empty.
    """
    if not HAS_SKILLS:
        return pd.DataFrame(columns=["skill_id", "skill_name"])

    df = run_query(
        """
        SELECT
            skill_id,
            skill_name
        FROM public.skills
        ORDER BY skill_name
        """
    )

    if df is None:
        return pd.DataFrame(columns=["skill_id", "skill_name"])

    return df


# Load skills once
SKILLS_DF = load_skills_with_display()
ALL_SKILLS = (
    SKILLS_DF["skill_name"].astype(str).tolist()
    if not SKILLS_DF.empty and "skill_name" in SKILLS_DF.columns
    else []
)

SKILLS_DF = load_skills_with_display()

def build_user_options(exclude_user_ids=None):
    if users_df is None or users_df.empty:
        return {}

    exclude_user_ids = set(exclude_user_ids or [])
    options = {}
    for _, row in users_df.iterrows():
        uid = row["user_id"]
        if uid in exclude_user_ids:
            continue
        label_name = row["full_name"] or row["email"]
        label = f"{label_name} <{row['email']}>"
        options[label] = uid
    return options


# ---------------------------------------------------------
# LOAD USERS (for linking resources ↔ user accounts)
# ---------------------------------------------------------
users_df = run_query(
    """
    SELECT user_id, email, COALESCE(full_name, '') AS full_name
    FROM public.users
    ORDER BY full_name, email
    """
)

# ---------------------------------------------------------
# LOAD RESOURCE POOL (include rp.email + aggregated matrix skills)
# ---------------------------------------------------------
if HAS_SKILLS:
    resource_df = run_query(
        """
        WITH strong AS (
            SELECT
                rs.resource_id,
                STRING_AGG(s.skill_name, ', ' ORDER BY s.skill_name) AS strong_skills
            FROM public.resource_skills rs
            JOIN public.skills s ON s.skill_id = rs.skill_id
            WHERE rs.rating >= 4
            GROUP BY rs.resource_id
        )
        SELECT 
            rp.resource_id,
            rp.full_name,
            rp.role,
            rp.department,
            rp.skillset,
            rp.email AS resource_email,
            rp.is_active,
            rp.created_at,
            rp.user_id,
            u.email AS user_email,
            COALESCE(strong.strong_skills, '') AS strong_skills
        FROM public.resource_pool rp
        LEFT JOIN public.users u ON rp.user_id = u.user_id
        LEFT JOIN strong ON strong.resource_id = rp.resource_id
        ORDER BY rp.full_name
        """
    )
else:
    resource_df = run_query(
        """
        SELECT 
            rp.resource_id,
            rp.full_name,
            rp.role,
            rp.skillset,
            rp.department,
            rp.email AS resource_email,
            rp.is_active,
            rp.created_at,
            rp.user_id,
            u.email AS user_email
        FROM public.resource_pool rp
        LEFT JOIN public.users u ON rp.user_id = u.user_id
        ORDER BY rp.full_name
        """
    )

if resource_df is None:
    resource_df = pd.DataFrame()

# ---------------------------------------------------------
# WAITING AREA (definition = linked user but inactive)
# ---------------------------------------------------------
waiting_df = pd.DataFrame()
if not resource_df.empty:
    waiting_df = resource_df[
        (resource_df.get("user_id").notna())
        & (~resource_df.get("is_active").fillna(False).astype(bool))
    ].copy()

# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab_waiting, tab_current, tab_search, tab_new, tab_edit_delete = st.tabs(
    [
        "🕒 Waiting Area",
        "📋 Current Resources",
        "🔍 Search / Filter",
        "➕ New Resource",
        "✏️ Edit / 🗑️ Delete",
    ]
)

# ============================================================
# TAB 0: WAITING AREA (unchanged; still uses legacy fields)
# ============================================================
with tab_waiting:
    st.markdown(
        """
<div class='section-header'>
    <h3>🕒 Waiting Area</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class='info-box'>
    <strong style='color:#48bb78;'>What is this?</strong><br/>
    This shows resources that are already linked to a <b>user account</b> but are <b>inactive</b>.
    Complete the profile and activate them when ready.
</div>
""",
        unsafe_allow_html=True,
    )

    if waiting_df.empty:
        st.info("No users are currently waiting for triage.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>Waiting List</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        show_cols = [
            "resource_id",
            "full_name",
            "user_email",
            "resource_email",
            "role",
            "department",
            "strong_skills" if HAS_SKILLS else "skillset",
            "is_active",
            "created_at",
        ]
        show_cols = [c for c in show_cols if c in waiting_df.columns]

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(waiting_df[show_cols], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")

        st.markdown(
            """
<div class='step-header'>
    <h4>🧩 Triage & Activate</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        waiting_options = {
            f"{row.get('full_name') or '(No name)'} — {row.get('user_email') or 'No email'} (Resource #{int(row['resource_id'])})": int(row["resource_id"])
            for _, row in waiting_df.iterrows()
        }

        selected_waiting_label = st.selectbox(
            "Select a waiting resource",
            list(waiting_options.keys()),
            key="waiting_select_resource",
        )
        selected_resource_id = waiting_options[selected_waiting_label]

        rec = run_query(
            "SELECT * FROM public.resource_pool WHERE resource_id = :id",
            {"id": selected_resource_id},
        )

        if rec is None or rec.empty:
            st.error("Could not load selected resource record.")
        else:
            rec = rec.iloc[0]

            with st.form("waiting_triage_form"):
                full_name_w = st.text_input("Full Name", rec.get("full_name") or "")
                role_w = st.text_input("Role / Job Title", rec.get("role") or "")
                dept_w = st.text_input("Department", rec.get("department") or "")
                skill_w = st.text_input("Skillset (legacy comma-separated)", rec.get("skillset") or "")

                col_a, col_b = st.columns(2)
                with col_a:
                    activate_now = st.checkbox("Activate now ✅", value=True)
                with col_b:
                    linked_user_id = rec.get("user_id")
                    st.markdown(
                        f"<div style='padding-top:30px; font-size:0.95rem; color:#444;'>"
                        f"<b>Linked user_id:</b> {linked_user_id if linked_user_id is not None else 'None'}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                save_waiting = st.form_submit_button("💾 Save Triage")

            if save_waiting:
                run_execute(
                    """
                    UPDATE public.resource_pool
                    SET full_name = :n,
                        role = :r,
                        department = :d,
                        skillset = :s,
                        is_active = :a
                    WHERE resource_id = :id
                    """,
                    {
                        "id": selected_resource_id,
                        "n": full_name_w,
                        "r": role_w,
                        "d": dept_w,
                        "s": skill_w,
                        "a": bool(activate_now),
                    },
                )
                st.success("✅ Waiting resource updated.")
                st.rerun()

        st.markdown("---")

        st.markdown(
            """
<div class='step-header'>
    <h4>⚡ Quick Actions</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Mark Selected as Active", use_container_width=True, key="waiting_mark_active"):
                run_execute(
                    "UPDATE public.resource_pool SET is_active = TRUE WHERE resource_id = :id",
                    {"id": selected_resource_id},
                )
                st.success("Marked as Active.")
                st.rerun()
        with col2:
            if st.button("⛔ Keep Selected Inactive", use_container_width=True, key="waiting_mark_inactive"):
                run_execute(
                    "UPDATE public.resource_pool SET is_active = FALSE WHERE resource_id = :id",
                    {"id": selected_resource_id},
                )
                st.success("Kept Inactive.")
                st.rerun()

# ============================================================
# TAB 1: CURRENT RESOURCES (UPDATED: show matrix skills + skill filter)
# ============================================================
with tab_current:
    st.markdown(
        """
<div class='section-header'>
    <h3>📋 Current Resources</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if not HAS_SKILLS:
        st.warning(
            "Skills Matrix tables not found (skills/resource_skills). "
            "This page will show legacy skillset only."
        )

    if resource_df.empty:
        st.info("No resources found.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>View Options</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        colA, colB, colC = st.columns([1, 1.2, 1.2])
        with colA:
            active_only = st.checkbox("Show Active Only", value=True, key="cur_active_only")
        with colB:
            selected_skill = None
            min_rating = 3
            if HAS_SKILLS and ALL_SKILLS:
                selected_skill = st.selectbox("Filter by skill", ["(Any)"] + ALL_SKILLS, index=0, key="cur_skill_filter")
        with colC:
            if HAS_SKILLS and ALL_SKILLS:
                min_rating = st.select_slider("Min rating", options=[0, 1, 2, 3, 4, 5], value=3, key="cur_min_rating")

        view_df = resource_df.copy()

        if active_only and "is_active" in view_df.columns:
            view_df = view_df[view_df["is_active"].fillna(False).astype(bool)]

        # If skill filter selected, re-query using matrix tables (fast + accurate)
        if HAS_SKILLS and selected_skill and selected_skill != "(Any)":
            filtered = run_query(
                """
                WITH strong AS (
                    SELECT
                        rs.resource_id,
                        STRING_AGG(s.skill_name, ', ' ORDER BY s.skill_name) AS strong_skills
                    FROM public.resource_skills rs
                    JOIN public.skills s ON s.skill_id = rs.skill_id
                    WHERE rs.rating >= 4
                    GROUP BY rs.resource_id
                )
                SELECT
                    rp.resource_id,
                    rp.full_name,
                    rp.role,
                    rp.department,
                    rp.email AS resource_email,
                    rp.is_active,
                    u.email AS user_email,
                    COALESCE(strong.strong_skills, '') AS strong_skills,
                    rs.rating AS skill_rating
                FROM public.resource_pool rp
                JOIN public.resource_skills rs ON rs.resource_id = rp.resource_id
                JOIN public.skills s ON s.skill_id = rs.skill_id
                LEFT JOIN public.users u ON rp.user_id = u.user_id
                LEFT JOIN strong ON strong.resource_id = rp.resource_id
                WHERE s.skill_name = :sn
                  AND rs.rating >= :minr
                  AND (:active_only = FALSE OR rp.is_active = TRUE)
                ORDER BY rp.full_name
                """,
                {"sn": selected_skill, "minr": int(min_rating), "active_only": bool(active_only)},
            )
            if filtered is not None:
                view_df = filtered

        st.markdown(
            """
<div class='step-header'>
    <h4>Snapshot</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        display_cols = [
            "resource_id",
            "full_name",
            "role",
            "department",
            "resource_email",
            "user_email",
            "strong_skills" if HAS_SKILLS else "skillset",
            "skill_rating" if HAS_SKILLS else None,
            "is_active",
            "created_at",
        ]
        display_cols = [c for c in display_cols if c and c in view_df.columns]

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(view_df[display_cols], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# TAB 2: SEARCH / FILTER (UPDATED: matrix-driven skill filtering)
# ============================================================
with tab_search:
    st.markdown(
        """
<div class='section-header'>
    <h3>🔍 Search / Filter Resources</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if resource_df.empty:
        st.info("No resources available to search.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>Filters</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            departments = sorted([d for d in resource_df["department"].dropna().unique()]) if "department" in resource_df.columns else []
            dept_filter = st.multiselect("Filter by Department", departments, key="search_dept")
        with col2:
            roles = sorted([r for r in resource_df["role"].dropna().unique()]) if "role" in resource_df.columns else []
            role_filter = st.multiselect("Filter by Role / Job Title", roles, key="search_role")

        active_only = st.checkbox("Active only", value=True, key="search_active_only")

        # Skills Matrix filters
        if HAS_SKILLS and ALL_SKILLS:
            st.markdown(
                """
<div class='step-header'>
    <h4>🧠 Skills Matrix Filters</h4>
</div>
""",
                unsafe_allow_html=True,
            )
            skill_filter = st.multiselect("Skills (must meet min rating)", ALL_SKILLS, key="search_skills")
            min_rating = st.select_slider("Minimum rating", options=[0, 1, 2, 3, 4, 5], value=3, key="search_min_rating")
        else:
            st.info("Skills Matrix not available in this environment (using legacy fields only).")
            skill_filter = []
            min_rating = 0

        # Build query dynamically (AND logic for multiple skills)
        base_sql = """
        WITH strong AS (
            SELECT
                rs.resource_id,
                STRING_AGG(s.skill_name, ', ' ORDER BY s.skill_name) AS strong_skills
            FROM public.resource_skills rs
            JOIN public.skills s ON s.skill_id = rs.skill_id
            WHERE rs.rating >= 4
            GROUP BY rs.resource_id
        )
        SELECT
            rp.resource_id,
            rp.full_name,
            rp.role,
            rp.department,
            rp.email AS resource_email,
            rp.is_active,
            u.email AS user_email,
            COALESCE(strong.strong_skills, '') AS strong_skills
        FROM public.resource_pool rp
        LEFT JOIN public.users u ON rp.user_id = u.user_id
        LEFT JOIN strong ON strong.resource_id = rp.resource_id
        WHERE 1=1
        """

        params = {}

        if active_only:
            base_sql += " AND rp.is_active = TRUE "

        if dept_filter:
            base_sql += " AND rp.department = ANY(:dept) "
            params["dept"] = dept_filter

        if role_filter:
            base_sql += " AND rp.role = ANY(:role) "
            params["role"] = role_filter

        # Apply matrix skill constraints (each selected skill must exist at >= min_rating)
        if HAS_SKILLS and skill_filter:
            for i, sk in enumerate(skill_filter):
                key = f"sk{i}"
                base_sql += f"""
                AND EXISTS (
                    SELECT 1
                    FROM public.resource_skills rs
                    JOIN public.skills s ON s.skill_id = rs.skill_id
                    WHERE rs.resource_id = rp.resource_id
                      AND s.skill_name = :{key}
                      AND rs.rating >= :minr
                )
                """
                params[key] = sk
            params["minr"] = int(min_rating)

        base_sql += " ORDER BY rp.full_name "

        filtered_df = None
        if HAS_SKILLS:
            filtered_df = run_query(base_sql, params)
        else:
            # fallback: no skills tables -> filter resource_df locally (dept/role/active only)
            filtered_df = resource_df.copy()
            if active_only and "is_active" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["is_active"].fillna(False).astype(bool)]
            if dept_filter and "department" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["department"].isin(dept_filter)]
            if role_filter and "role" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["role"].isin(role_filter)]

        st.markdown(
            """
<div class='step-header'>
    <h4>Filtered Results</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        display_cols = [
            "resource_id",
            "full_name",
            "role",
            "department",
            "resource_email",
            "user_email",
            "strong_skills" if HAS_SKILLS else "skillset",
            "is_active",
            "created_at" if "created_at" in filtered_df.columns else None,
        ]
        display_cols = [c for c in display_cols if c and c in filtered_df.columns]

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# TAB 3: ADD NEW RESOURCE (unchanged; still uses legacy skillset)
# ============================================================
with tab_new:
    st.markdown(
        """
<div class='section-header'>
    <h3>➕ Add New Resource</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("add_resource_form"):
        st.markdown(
            """
<div class='step-header'>
    <h4>Resource Details</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        full_name = st.text_input("Full Name")
        role_title = st.text_input("Role / Job Title")
        skillset = st.text_input("Skillset (legacy comma-separated)")
        department = st.text_input("Department")
        is_active = st.checkbox("Active", value=True)

        st.markdown(
            """
<div class='step-header'>
    <h4>Link to User Account (optional)</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        existing_linked_ids = (
            resource_df["user_id"].dropna().unique().tolist()
            if (not resource_df.empty and "user_id" in resource_df.columns)
            else []
        )
        user_options = build_user_options(exclude_user_ids=existing_linked_ids)

        link_to_user = None
        if user_options:
            user_label = st.selectbox(
                "Select user",
                ["(No linked user)"] + list(user_options.keys()),
            )
            if user_label != "(No linked user)":
                link_to_user = user_options[user_label]

        submit_new = st.form_submit_button("Add Resource")

        if submit_new:
            if not full_name:
                st.error("Full name is required.")
            else:
                if link_to_user is None:
                    run_execute(
                        """
                        INSERT INTO public.resource_pool (full_name, role, skillset, department, is_active)
                        VALUES (:n, :r, :s, :d, :a)
                        """,
                        {
                            "n": full_name,
                            "r": role_title,
                            "s": skillset,
                            "d": department,
                            "a": is_active,
                        },
                    )
                else:
                    run_execute(
                        """
                        INSERT INTO public.resource_pool (full_name, role, skillset, department, is_active, user_id)
                        VALUES (:n, :r, :s, :d, :a, :uid)
                        """,
                        {
                            "n": full_name,
                            "r": role_title,
                            "s": skillset,
                            "d": department,
                            "a": is_active,
                            "uid": link_to_user,
                        },
                    )

                st.success("✅ Resource added successfully.")
                st.rerun()

# ============================================================
# TAB 4: EDIT / DELETE / ACTIVE-TOGGLE (unchanged; legacy skillset remains)
# ============================================================
with tab_edit_delete:
    st.markdown(
        """
<div class='section-header'>
    <h3>✏️ Edit / 🗑️ Delete / 🔁 Activate–Deactivate</h3>
</div>
""",
        unsafe_allow_html=True,
    )

    if resource_df.empty:
        st.info("No resources to edit or delete.")
    else:
        st.markdown(
            """
<div class='step-header'>
    <h4>✏️ Edit Resource</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        resource_options = {
            f"{row.full_name} (#{row.resource_id})": row.resource_id
            for _, row in resource_df.iterrows()
        }

        sel_label = st.selectbox("Select a resource to edit", list(resource_options.keys()))
        sel_id = resource_options[sel_label]

        rec = run_query("SELECT * FROM public.resource_pool WHERE resource_id = :id", {"id": sel_id})
        if rec is not None and not rec.empty:
            rec = rec.iloc[0]

            with st.form("edit_resource_form"):
                full_name = st.text_input("Full Name", rec.get("full_name") or "")
                role_title = st.text_input("Role / Job Title", rec.get("role") or "")
                skillset = st.text_input("Skillset (legacy comma-separated)", rec.get("skillset") or "")
                department = st.text_input("Department", rec.get("department") or "")
                is_active = st.checkbox("Active", value=bool(rec.get("is_active")))

                current_user_id = rec.get("user_id")
                existing_linked_ids = (
                    resource_df["user_id"].dropna().unique().tolist()
                    if ("user_id" in resource_df.columns)
                    else []
                )
                if current_user_id in existing_linked_ids:
                    existing_linked_ids = [uid for uid in existing_linked_ids if uid != current_user_id]

                edit_user_options = build_user_options(exclude_user_ids=existing_linked_ids)

                user_select_labels = ["(No linked user)"] + list(edit_user_options.keys())
                default_index = 0

                if current_user_id and users_df is not None and not users_df.empty:
                    current_row = users_df[users_df["user_id"] == current_user_id]
                    if not current_row.empty:
                        row_u = current_row.iloc[0]
                        label_name = row_u["full_name"] or row_u["email"]
                        current_label = f"{label_name} <{row_u['email']}>"
                        if current_label not in edit_user_options:
                            edit_user_options[current_label] = current_user_id
                            user_select_labels.append(current_label)
                        default_index = user_select_labels.index(current_label)

                user_label_edit = st.selectbox(
                    "Linked user account",
                    user_select_labels,
                    index=default_index,
                )

                if user_label_edit == "(No linked user)":
                    edit_user_id = None
                else:
                    edit_user_id = edit_user_options.get(user_label_edit)

                submit_edit = st.form_submit_button("Save Changes")

            if submit_edit:
                run_execute(
                    """
                    UPDATE public.resource_pool
                    SET full_name = :n,
                        role = :r,
                        skillset = :s,
                        department = :d,
                        is_active = :a,
                        user_id = :uid
                    WHERE resource_id = :id
                    """,
                    {
                        "id": sel_id,
                        "n": full_name,
                        "r": role_title,
                        "s": skillset,
                        "d": department,
                        "a": is_active,
                        "uid": edit_user_id,
                    },
                )

                st.success("✅ Resource updated successfully.")
                st.rerun()

        st.markdown("---")

        st.markdown(
            """
<div class='step-header'>
    <h4>🔁 Activate / Deactivate Resource</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        toggle_options = {
            f"{row.full_name} (#{row.resource_id}) — "
            f"{'Active' if bool(row.is_active) else 'Inactive'}": row.resource_id
            for _, row in resource_df.iterrows()
        }

        toggle_label = st.selectbox(
            "Select resource to change status",
            list(toggle_options.keys()),
            key="toggle_select",
        )
        toggle_id = toggle_options[toggle_label]

        current_row = resource_df[resource_df["resource_id"] == toggle_id].iloc[0]
        current_status = bool(current_row["is_active"])

        st.info(
            f"Current status for **{current_row['full_name']}** is "
            f"**{'Active' if current_status else 'Inactive'}**."
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Mark as Active ✅", key="btn_mark_active"):
                if current_status:
                    st.warning("This resource is already active.")
                else:
                    run_execute(
                        "UPDATE public.resource_pool SET is_active = TRUE WHERE resource_id = :id",
                        {"id": toggle_id},
                    )
                    st.success("✅ Resource marked as Active.")
                    st.rerun()
        with col_b:
            if st.button("Mark as Inactive ⛔", key="btn_mark_inactive"):
                if not current_status:
                    st.warning("This resource is already inactive.")
                else:
                    run_execute(
                        "UPDATE public.resource_pool SET is_active = FALSE WHERE resource_id = :id",
                        {"id": toggle_id},
                    )
                    st.success("⛔ Resource marked as Inactive.")
                    st.rerun()

        st.markdown("---")

        st.markdown(
            """
<div class='step-header'>
    <h4>🗑️ Delete Resource</h4>
</div>
""",
            unsafe_allow_html=True,
        )

        del_options = {
            f"{row.full_name} (#{row.resource_id})": row.resource_id
            for _, row in resource_df.iterrows()
        }

        del_label = st.selectbox("Select resource to delete", list(del_options.keys()))
        del_id = del_options[del_label]

        linked_row = resource_df[resource_df["resource_id"] == del_id]
        linked_email = None
        if not linked_row.empty and "user_email" in linked_row.columns:
            linked_email = linked_row.iloc[0]["user_email"]

        if linked_email:
            st.warning(
                f"This resource is linked to user account: **{linked_email}**. "
                "Deleting it will remove their entry from the resource pool, but not the user account itself."
            )

        if st.button("Delete Resource", type="primary"):
            run_execute("DELETE FROM public.resource_pool WHERE resource_id = :id", {"id": del_id})
            st.warning(f"Resource '{del_label}' deleted from resource pool.")
            st.rerun()

st.markdown("<hr/>", unsafe_allow_html=True)
pmo_footer()
