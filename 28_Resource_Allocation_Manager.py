# ============================================================
# 28_Resource_Allocation_Manager.py — ScopeSight v3.4
# Admin / Exec Resource Allocation Editor + Capacity Management
# UPDATED: Skills Matrix filters + clean skill labels (no numeric prefixes)
# ============================================================

import streamlit as st
import pandas as pd
import datetime as dt
import re
import plotly.express as px

from auth.login import require_login
from modules.db import run_query, run_execute
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav


# ---------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="🧑‍🔧 Resource Allocation Manager",
    page_icon="🧑‍🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# BOOTSTRAP
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()

role = st.session_state.get("role")
email = (st.session_state.get("email") or "").strip().lower()

if role not in ("admin", "ceo", "exec"):
    st.error("You do not have permission to manage resource allocations.")
    st.stop()

set_pmo_theme("🧑‍🔧 Resource Allocation Manager")
render_sidebar()

# ---------------------------------------------------------
# GLOBAL STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] {
    height:0 !important;
    visibility:hidden !important;
}

/* Section header band */
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.5rem 0 1rem 0;
}
.section-header h3 {
    margin: 0;
    color: white;
    font-size: 1.2rem;
    font-weight: 600;
}

/* Info box */
.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin-bottom: 1.25rem;
}

/* Scrollable tables */
.table-container {
    max-height: 520px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e6f2ff;
}

h2, h3 { text-align:center !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def _clamp_int(v, lo=0, hi=100, default=0):
    try:
        v = int(v)
    except Exception:
        v = default
    return max(lo, min(hi, v))


def bind_percent_pair(num_key: str, slider_key: str, lo=0, hi=100):
    """
    Two-way sync between a number_input and slider using session_state keys.
    Returns: (num_to_slider_callback, slider_to_num_callback)
    """
    def _num_to_slider():
        st.session_state[slider_key] = _clamp_int(st.session_state.get(num_key, lo), lo, hi, lo)

    def _slider_to_num():
        st.session_state[num_key] = _clamp_int(st.session_state.get(slider_key, lo), lo, hi, lo)

    if num_key not in st.session_state and slider_key not in st.session_state:
        st.session_state[num_key] = lo
        st.session_state[slider_key] = lo
    elif num_key in st.session_state and slider_key not in st.session_state:
        _num_to_slider()
    elif slider_key in st.session_state and num_key not in st.session_state:
        _slider_to_num()
    else:
        _num_to_slider()

    return _num_to_slider, _slider_to_num


def _as_date(x):
    if x is None or pd.isna(x):
        return None
    if isinstance(x, dt.date):
        return x
    return pd.to_datetime(x).date()


def _overlap_days(a_start, a_end, r_start, r_end):
    """
    Inclusive overlap days between [a_start, a_end] and [r_start, r_end].
    a_end can be None -> treat as r_end.
    """
    if a_start is None:
        return 0
    a_start = _as_date(a_start)
    a_end = _as_date(a_end) or r_end
    r_start = _as_date(r_start)
    r_end = _as_date(r_end)

    if a_start is None or r_start is None or r_end is None:
        return 0

    start = max(a_start, r_start)
    end = min(a_end, r_end)
    if end < start:
        return 0
    return (end - start).days + 1


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


# --------------------------
# Skills matrix helpers
# --------------------------
def _clean_skill_label(name: str) -> str:
    """
    Remove numeric prefixes like:
    '01 - Foo', '1. Foo', '12) Foo', '3 - Foo', '01 Foo'
    """
    if name is None:
        return ""
    s = str(name).strip()
    s = re.sub(r"^\s*\d+\s*[-.)]\s*", "", s)
    s = re.sub(r"^\s*\d+\s+", "", s)
    return s.strip()


HAS_SKILLS = table_exists("skills") and table_exists("resource_skills")


def load_skills_with_display() -> pd.DataFrame:
    """
    Returns df with:
      - skill_name: original DB value (used in SQL)
      - display_name: cleaned label for UI (sorted alphabetically)
    Disambiguates display duplicates by appending the original.
    """
    if not HAS_SKILLS:
        return pd.DataFrame(columns=["skill_name", "display_name"])

    df = run_query("SELECT skill_name FROM public.skills ORDER BY skill_name")
    if df is None or df.empty:
        return pd.DataFrame(columns=["skill_name", "display_name"])

    out = df.copy()
    out["skill_name"] = out["skill_name"].astype(str)
    out["display_name"] = out["skill_name"].apply(_clean_skill_label)

    dup = out["display_name"].duplicated(keep=False)
    out.loc[dup, "display_name"] = out.loc[dup].apply(
        lambda r: f"{r['display_name']} ({r['skill_name']})",
        axis=1,
    )

    return out.sort_values("display_name", kind="stable").reset_index(drop=True)


SKILLS_DF = load_skills_with_display()

def _clean_skill_list_str(skill_csv: str) -> str:
    """
    Take a 'a, b, c' CSV string and return cleaned, deduped, alpha-sorted labels.
    """
    if not skill_csv:
        return ""
    parts = [p.strip() for p in str(skill_csv).split(",") if p.strip()]
    cleaned = {_clean_skill_label(p) for p in parts if _clean_skill_label(p)}
    return ", ".join(sorted(cleaned))


# ---------------------------------------------------------
# CLIENT SCOPE
# ---------------------------------------------------------
if role == "admin":
    clients = run_query(
        """
        SELECT id, client_name
        FROM client_scaffold
        ORDER BY client_name
        """
    )
else:
    clients = run_query(
        """
        SELECT c.id, c.client_name
        FROM user_client_permissions u
        JOIN client_scaffold c ON c.id = u.client_id
        WHERE LOWER(u.user_email) = :email
        ORDER BY c.client_name
        """,
        {"email": email},
    )

if clients is None or clients.empty:
    if role == "admin":
        st.error("No clients exist in the system yet.")
    else:
        st.warning(
            "You are not assigned to any clients.\n\n"
            "If this is unexpected, ask an administrator to assign you to a client."
        )
    st.stop()

client_map = dict(zip(clients.client_name, clients.id))
selected_client = st.selectbox("Select Client", clients.client_name.tolist())
client_id = int(client_map[selected_client])

st.markdown("<hr/>", unsafe_allow_html=True)

# ---------------------------------------------------------
# LOAD PROJECTS & RESOURCES
# ---------------------------------------------------------
projects = run_query(
    """
    SELECT project_id, project_name
    FROM projects
    WHERE client_id = :cid
    ORDER BY project_name
    """,
    {"cid": client_id},
)

resources = run_query(
    """
    SELECT resource_id, full_name, department, role
    FROM resource_pool
    WHERE is_active = TRUE
    ORDER BY full_name
    """
)

if projects is None or resources is None or projects.empty or resources.empty:
    st.info("Projects or resources missing.")
    st.stop()

proj_name_by_id = projects.set_index("project_id")["project_name"].to_dict()
res_name_by_id = resources.set_index("resource_id")["full_name"].to_dict()

# ---------------------------------------------------------
# Tabs
# ---------------------------------------------------------
tab_add, tab_current, tab_skills = st.tabs(
    ["➕ Add Allocation", "📋 Current Allocations", "🧠 Skills Matrix"]
)

# ---------------------------------------------------------
# TAB 1: ADD ALLOCATION
# ---------------------------------------------------------
with tab_add:
    st.markdown(
        """
        <div class='section-header'>
            <h3>➕ Add Allocation</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='info-box'>
            Select a <b>resource</b>, <b>project</b>, and set the
            <b>allocation percentage</b> with dates. Existing pairs
            of (resource, project) will be updated automatically.
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        resource_id = st.selectbox(
            "Resource",
            options=resources.resource_id.tolist(),
            format_func=lambda x: res_name_by_id.get(int(x), f"Resource {x}"),
            key="add_alloc_resource_id",
        )

    with c2:
        project_id = st.selectbox(
            "Project",
            options=projects.project_id.tolist(),
            format_func=lambda x: proj_name_by_id.get(int(x), f"Project {x}"),
            key="add_alloc_project_id",
        )

    num_to_slider, slider_to_num = bind_percent_pair("alloc_pct_num", "alloc_pct_slider", 1, 100)

    with c3:
        st.number_input(
            "Allocation %",
            min_value=1,
            max_value=100,
            step=1,
            key="alloc_pct_num",
            on_change=num_to_slider,
        )
        st.slider(
            "Allocation % (slider)",
            1,
            100,
            step=5,
            key="alloc_pct_slider",
            on_change=slider_to_num,
        )

    d1, d2 = st.columns(2)
    start_date = d1.date_input("Start Date", value=dt.date.today(), key="add_alloc_start")
    end_date = d2.date_input("End Date", value=dt.date.today(), key="add_alloc_end")

    st.markdown("")

    if st.button("💾 Save Allocation", use_container_width=True, type="primary", key="btn_save_allocation"):
        if end_date < start_date:
            st.error("End Date must be on/after Start Date.")
        else:
            try:
                run_execute(
                    """
                    INSERT INTO resource_allocation (
                        resource_id,
                        project_id,
                        client_id,
                        allocation_pct,
                        start_date,
                        end_date
                    )
                    VALUES (:r, :p, :c, :a, :s, :e)
                    ON CONFLICT (resource_id, project_id)
                    DO UPDATE SET
                        allocation_pct = EXCLUDED.allocation_pct,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        updated_at = NOW()
                    """,
                    {
                        "r": int(resource_id),
                        "p": int(project_id),
                        "c": int(client_id),
                        "a": int(st.session_state["alloc_pct_num"]),
                        "s": start_date,
                        "e": end_date,
                    },
                )
                st.success("Allocation saved.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ---------------------------------------------------------
# TAB 2: CURRENT ALLOCATIONS (strong skills column)
# ---------------------------------------------------------
with tab_current:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📋 Current Allocations</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if HAS_SKILLS:
        allocs = run_query(
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
                ra.allocation_id,
                ra.resource_id,
                rp.full_name AS resource,
                rp.department,
                rp.role,
                COALESCE(strong.strong_skills, '') AS strong_skills,
                ra.project_id,
                p.project_name,
                ra.allocation_pct,
                ra.start_date,
                ra.end_date
            FROM public.resource_allocation ra
            JOIN public.resource_pool rp ON ra.resource_id = rp.resource_id
            JOIN public.projects p ON ra.project_id = p.project_id
            LEFT JOIN strong ON strong.resource_id = rp.resource_id
            WHERE ra.client_id = :cid
            ORDER BY rp.full_name, p.project_name
            """,
            {"cid": client_id},
        )
    else:
        allocs = run_query(
            """
            SELECT
                ra.allocation_id,
                ra.resource_id,
                rp.full_name AS resource,
                rp.department,
                rp.role,
                ra.project_id,
                p.project_name,
                ra.allocation_pct,
                ra.start_date,
                ra.end_date
            FROM public.resource_allocation ra
            JOIN public.resource_pool rp ON ra.resource_id = rp.resource_id
            JOIN public.projects p ON ra.project_id = p.project_id
            WHERE ra.client_id = :cid
            ORDER BY rp.full_name, p.project_name
            """,
            {"cid": client_id},
        )

    if allocs is None or allocs.empty:
        st.info("No allocations for this client yet.")
    else:
        df = allocs.copy()
        df["start_date"] = df["start_date"].apply(_as_date)
        df["end_date"] = df["end_date"].apply(_as_date)

        if "strong_skills" in df.columns:
            df["strong_skills"] = df["strong_skills"].fillna("").astype(str).apply(_clean_skill_list_str)

        cols = ["resource", "department", "role"]
        if HAS_SKILLS and "strong_skills" in df.columns:
            cols.append("strong_skills")
        cols += ["project_name", "allocation_pct", "start_date", "end_date"]

        st.markdown('<div class="table-container">', unsafe_allow_html=True)
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        with st.expander("🗑️ Delete an allocation"):
            pick = st.selectbox(
                "Select allocation to delete",
                options=df["allocation_id"].tolist(),
                format_func=lambda aid: f"{df.set_index('allocation_id').loc[aid, 'resource']} — "
                                       f"{df.set_index('allocation_id').loc[aid, 'project_name']} "
                                       f"({int(df.set_index('allocation_id').loc[aid, 'allocation_pct'])}%)",
                key="delete_alloc_pick",
            )
            if st.button("Delete allocation", type="secondary", use_container_width=True, key="btn_delete_alloc"):
                try:
                    run_execute(
                        "DELETE FROM resource_allocation WHERE allocation_id = :aid",
                        {"aid": int(pick)},
                    )
                    st.success("Allocation deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# ---------------------------------------------------------
# TAB 3: SKILLS MATRIX (CLIENT-SCOPED HEATMAP)
# ---------------------------------------------------------
with tab_skills:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🧠 Skills Matrix</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not HAS_SKILLS:
        st.warning("Skills Matrix tables not found (skills/resource_skills).")
    else:
        st.markdown(
            """
            <div class='info-box'>
                Heatmap view of <b>skills coverage for resources allocated to this client</b>.
                Cells show the <b>skill rating (0–5)</b>. Skill labels are cleaned (numeric prefixes removed).
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --- Find resources in scope for this client ---
        in_scope = run_query(
            """
            SELECT DISTINCT ra.resource_id
            FROM public.resource_allocation ra
            WHERE ra.client_id = :cid
            """,
            {"cid": client_id},
        )

        in_ids = (
            in_scope["resource_id"].astype(int).tolist()
            if in_scope is not None and not in_scope.empty
            else []
        )

        if not in_ids:
            st.info("No allocated resources for this client yet — add allocations to see skills coverage.")
            st.stop()

        in_sql = f"({','.join(str(i) for i in in_ids)})"

        # --- Controls ---
        c1, c2, c3, c4 = st.columns([1.6, 1, 1.2, 1.2])

        with c1:
            view_mode = st.selectbox(
                "Heatmap view",
                ["All skills (may be large)", "Top skills by coverage"],
                index=1,
                key="skills_heatmap_view_mode",
            )

        with c2:
            min_rating = st.select_slider(
                "Min rating",
                options=[0, 1, 2, 3, 4, 5],
                value=3,
                key="skills_heatmap_min_rating",
            )

        with c3:
            top_n = st.number_input(
                "Top N skills",
                min_value=5,
                max_value=60,
                value=25,
                step=5,
                disabled=(view_mode != "Top skills by coverage"),
                key="skills_heatmap_top_n",
            )

        with c4:
            include_unrated = st.checkbox(
                "Show unrated as 0",
                value=True,
                key="skills_heatmap_include_unrated",
            )

        st.markdown("<hr/>", unsafe_allow_html=True)

        # --- Pull client-scoped skill ratings (resource_id in in_ids) ---
        raw = run_query(
            f"""
            SELECT
                rp.resource_id,
                rp.full_name AS resource,
                rp.department,
                rp.role,
                s.skill_name,
                rs.rating
            FROM public.resource_skills rs
            JOIN public.skills s ON s.skill_id = rs.skill_id
            JOIN public.resource_pool rp ON rp.resource_id = rs.resource_id
            WHERE rs.resource_id IN {in_sql}
            """,
        )

        if raw is None or raw.empty:
            st.info("No skills ratings found for the allocated resources in this client scope.")
            st.stop()

        raw = raw.copy()
        raw["skill_name"] = raw["skill_name"].astype(str)
        raw["skill"] = raw["skill_name"].apply(_clean_skill_label)
        raw["rating"] = pd.to_numeric(raw["rating"], errors="coerce").fillna(0).astype(int)

        # Disambiguate duplicates after cleaning (rare but possible)
        dup = raw["skill"].duplicated(keep=False)
        if dup.any():
            raw.loc[dup, "skill"] = raw.loc[dup].apply(
                lambda r: f"{r['skill']} ({r['skill_name']})",
                axis=1,
            )

        # Filter by min rating (note: for heatmap we still keep 0s if include_unrated)
        raw_f = raw[raw["rating"] >= int(min_rating)].copy()

        if raw_f.empty and not include_unrated:
            st.info("No skills meet the selected minimum rating in this client scope.")
            st.stop()

        # Determine which skills to show (top coverage or all)
        if view_mode == "Top skills by coverage":
            coverage = (
                raw_f.groupby("skill", dropna=False)["resource_id"]
                .nunique()
                .sort_values(ascending=False)
            )
            skills_keep = coverage.head(int(top_n)).index.tolist()
        else:
            skills_keep = sorted(raw["skill"].unique().tolist())

        # Build heatmap matrix: rows=resource, cols=skill, values=rating
        # If include_unrated=True, we create a full grid with zeros for missing ratings.
        resources_df = (
            raw[["resource_id", "resource", "department", "role"]]
            .drop_duplicates()
            .sort_values("resource", kind="stable")
        )

        # Create pivot from raw (not raw_f) so we can show 0 for missing if requested
        pivot_src = raw[raw["skill"].isin(skills_keep)].copy()
        matrix = pivot_src.pivot_table(
            index="resource",
            columns="skill",
            values="rating",
            aggfunc="max",
        )

        if include_unrated:
            # ensure all resources present
            all_resources = resources_df["resource"].tolist()
            matrix = matrix.reindex(index=all_resources)
            matrix = matrix.fillna(0)
        else:
            # only keep cells meeting min rating by blanking others
            matrix = matrix.fillna(0)
            matrix = matrix.where(matrix >= int(min_rating))

        # If matrix ends up empty after filtering, stop cleanly
        if matrix.shape[1] == 0 or matrix.shape[0] == 0:
            st.info("Nothing to display for the selected filters (try lowering Min rating or increasing Top N).")
            st.stop()

        st.markdown("#### 🔥 Client skills heatmap (Resource × Skill)")

        # Plotly heatmap (interactive)
        fig = px.imshow(
            matrix,
            aspect="auto",
            labels=dict(x="Skill", y="Resource", color="Rating"),
            zmin=0,
            zmax=5,
        )
        fig.update_layout(
            height=min(900, 140 + 22 * max(10, matrix.shape[0])),
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📌 Coverage summary (resources meeting threshold)", expanded=False):
            cov2 = (
                raw[raw["rating"] >= int(min_rating)]
                .groupby("skill")["resource_id"]
                .nunique()
                .reset_index(name="resources")
                .sort_values(["resources", "skill"], ascending=[False, True])
            )
            if view_mode == "Top skills by coverage":
                cov2 = cov2[cov2["skill"].isin(skills_keep)]

            if cov2.empty:
                st.info("No coverage found at this threshold.")
            else:
                st.dataframe(
                    cov2.rename(columns={"skill": "Skill", "resources": "Resources"}),
                    use_container_width=True,
                    hide_index=True,
                )

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
