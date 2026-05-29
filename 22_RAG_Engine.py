# ============================================================
# pages/22_⚙️_RAG_Engine.py — ScopeSight RAG Engine Admin
# ============================================================
#
# Features:
#   • Run RAG for a single project or all live projects
#   • View dimension breakdown with score bars
#   • Configure weights + thresholds per project
#   • History chart of RAG snapshots over time
#   • Manual override UI
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import pandas as pd
import streamlit as st

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav
from modules.rag_engine import RagEngine, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS

st.set_page_config(page_title="⚙️ RAG Engine", page_icon="⚙️", layout="wide")

require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="⚙️ RAG Engine")
render_sidebar()

# ── Styles ────────────────────────────────────────────────────
st.markdown("""
<style>
header[data-testid="stHeader"] { height:0 !important; visibility:hidden !important; }

.page-title  { font-size:2rem; font-weight:950; color:#0f172a; margin:0 0 .2rem 0; }
.page-sub    { color:#64748b; font-size:.95rem; margin:0 0 1.5rem 0; }

.panel { background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:1.2rem 1.4rem; margin-bottom:1rem; }

.rag-badge { display:inline-block; padding:.3rem .9rem; border-radius:999px;
             font-weight:900; font-size:1rem; border:1px solid transparent; }
.rag-green  { background:#dcfce7; color:#166534; border-color:#bbf7d0; }
.rag-amber  { background:#fef3c7; color:#92400e; border-color:#fde68a; }
.rag-red    { background:#fee2e2; color:#991b1b; border-color:#fecaca; }
.rag-none   { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }

.dim-label  { font-size:.78rem; font-weight:900; text-transform:uppercase;
              letter-spacing:.8px; color:#64748b; margin-bottom:.2rem; }
.dim-score  { font-size:1.6rem; font-weight:950; color:#0f172a; }
.dim-tag    { font-size:.8rem; font-weight:700; color:#475569; margin-top:.1rem; }

.driver-item { background:#f8fafc; border-left:3px solid #e2e8f0; padding:.4rem .7rem;
               margin-bottom:.35rem; border-radius:0 6px 6px 0; font-size:.9rem; color:#334155; }
.driver-risk       { border-color:#ef4444; }
.driver-actions    { border-color:#f59e0b; }
.driver-schedule   { border-color:#3b82f6; }
.driver-budget     { border-color:#8b5cf6; }
.driver-governance { border-color:#10b981; }

.score-bar-wrap { background:#f1f5f9; border-radius:999px; height:8px; margin-top:.4rem; }
.score-bar-fill { height:8px; border-radius:999px; transition:width .4s ease; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────
engine = RagEngine(run_query)

RAG_COLOUR = {"green": "rag-green", "amber": "rag-amber", "red": "rag-red"}
DIM_COLOUR = {
    "risk": "#ef4444", "actions": "#f59e0b", "schedule": "#3b82f6",
    "budget": "#8b5cf6", "governance": "#10b981",
}
DIM_ICON = {"risk": "🔴", "actions": "📝", "schedule": "📅", "budget": "💰", "governance": "📋"}


def _rag_badge(rag: str) -> str:
    cls = RAG_COLOUR.get((rag or "").lower(), "rag-none")
    return f"<span class='rag-badge {cls}'>{(rag or '—').title()}</span>"


def _score_bar(score: float, colour: str) -> str:
    pct = max(0, min(100, score))
    return f"""
    <div class="score-bar-wrap">
      <div class="score-bar-fill" style="width:{pct}%;background:{colour}"></div>
    </div>"""


def _load_projects() -> pd.DataFrame:
    df = run_query(
        """
        SELECT p.project_id, p.project_name, c.client_name,
               p.rag_status, p.health_score, p.status
        FROM public.projects p
        LEFT JOIN public.client_scaffold c ON c.id = p.client_id
        WHERE LOWER(COALESCE(p.status,'open')) NOT IN
              ('closed','completed','rejected','cancelled','canceled','archived')
        ORDER BY c.client_name, p.project_name
        """,
        {},
    )
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _load_latest_snapshot(project_id: int) -> dict | None:
    df = run_query(
        """
        SELECT overall_rag, overall_score, dimension_json, drivers_json, as_of, computed_by
        FROM public.project_rag_snapshot
        WHERE project_id = :pid
        ORDER BY as_of DESC
        LIMIT 1
        """,
        {"pid": project_id},
    )
    if df is None or df.empty:
        return None
    row = df.iloc[0]
    try:
        dims    = json.loads(row["dimension_json"]) if isinstance(row["dimension_json"], str) else dict(row["dimension_json"] or {})
        drivers = json.loads(row["drivers_json"])   if isinstance(row["drivers_json"],   str) else list(row["drivers_json"]   or [])
    except Exception:
        dims, drivers = {}, []
    return {
        "overall_rag":   row["overall_rag"],
        "overall_score": row["overall_score"],
        "dimensions":    dims,
        "drivers":       drivers,
        "as_of":         row["as_of"],
        "computed_by":   row["computed_by"],
    }


def _load_snapshot_history(project_id: int) -> pd.DataFrame:
    df = run_query(
        """
        SELECT as_of, overall_rag, overall_score
        FROM public.project_rag_snapshot
        WHERE project_id = :pid
        ORDER BY as_of DESC
        LIMIT 30
        """,
        {"pid": project_id},
    )
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _load_config(project_id: int) -> dict:
    df = run_query(
        """
        SELECT weights_json, thresholds_json
        FROM public.project_rag_config
        WHERE project_id = :pid
        ORDER BY updated_at DESC LIMIT 1
        """,
        {"pid": project_id},
    )
    if df is None or df.empty:
        return {"weights": DEFAULT_WEIGHTS.copy(), "thresholds": DEFAULT_THRESHOLDS.copy()}
    row = df.iloc[0]
    try:
        w = json.loads(row["weights_json"]) if isinstance(row["weights_json"], str) else dict(row["weights_json"] or {})
    except Exception:
        w = DEFAULT_WEIGHTS.copy()
    try:
        t = json.loads(row["thresholds_json"]) if isinstance(row["thresholds_json"], str) else dict(row["thresholds_json"] or {})
    except Exception:
        t = DEFAULT_THRESHOLDS.copy()
    return {"weights": w, "thresholds": t}


def _save_config(project_id: int, weights: dict, thresholds: dict, actor: str) -> bool:
    from modules.db import get_engine
    import sqlalchemy as sa
    sql = sa.text("""
        INSERT INTO public.project_rag_config
            (project_id, weights_json, thresholds_json, updated_at, updated_by)
        VALUES (:pid, :w::jsonb, :t::jsonb, now(), :actor)
        ON CONFLICT DO NOTHING
    """)
    # Upsert pattern: delete existing then insert
    del_sql = sa.text("DELETE FROM public.project_rag_config WHERE project_id = :pid")
    try:
        eng = get_engine()
        with eng.begin() as conn:
            conn.execute(del_sql, {"pid": project_id})
            conn.execute(sql, {
                "pid":   project_id,
                "w":     json.dumps(weights),
                "t":     json.dumps(thresholds),
                "actor": actor,
            })
        return True
    except Exception as e:
        st.error(f"Failed to save config: {e}")
        return False


def _save_override(project_id: int, rag: str, reason: str, actor: str, expires_days: int | None) -> bool:
    from modules.db import get_engine
    import sqlalchemy as sa
    # Deactivate existing overrides first
    deact = sa.text("UPDATE public.project_rag_override SET is_active=FALSE WHERE project_id=:pid")
    expires_expr = f"now() + interval '{expires_days} days'" if expires_days else "NULL"
    ins = sa.text(f"""
        INSERT INTO public.project_rag_override
            (project_id, override_rag, override_reason, set_by, set_at, expires_at, is_active)
        VALUES (:pid, :rag, :reason, :actor, now(), {expires_expr}, TRUE)
    """)
    try:
        eng = get_engine()
        with eng.begin() as conn:
            conn.execute(deact, {"pid": project_id})
            conn.execute(ins, {"pid": project_id, "rag": rag.lower(), "reason": reason, "actor": actor})
        return True
    except Exception as e:
        st.error(f"Failed to save override: {e}")
        return False


def _clear_override(project_id: int) -> bool:
    from modules.db import get_engine
    import sqlalchemy as sa
    sql = sa.text("UPDATE public.project_rag_override SET is_active=FALSE WHERE project_id=:pid")
    try:
        eng = get_engine()
        with eng.begin() as conn:
            conn.execute(sql, {"pid": project_id})
        return True
    except Exception as e:
        st.error(f"Failed to clear override: {e}")
        return False


def _render_result(result: dict):
    """Render a freshly-computed RAG result."""
    rag   = result["overall_rag"]
    score = result["overall_score"]
    dims  = result.get("dimension_detail", result.get("dimensions", {}))

    st.markdown(
        f"<div style='margin:.5rem 0 1rem'>"
        f"Overall RAG: {_rag_badge(rag)}&nbsp;&nbsp;"
        f"<span style='font-size:1.5rem;font-weight:950;color:#0f172a'>{score}</span>"
        f"<span style='color:#94a3b8;font-size:.9rem'>/100</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Dimension cards
    cols = st.columns(5)
    for i, (dim, data) in enumerate(dims.items()):
        sc = data.get("score", 0) if isinstance(data, dict) else 0
        lb = data.get("label", "")  if isinstance(data, dict) else str(data)
        colour = DIM_COLOUR.get(dim, "#64748b")
        with cols[i]:
            st.markdown(
                f"<div class='dim-label'>{DIM_ICON.get(dim,'')} {dim.title()}</div>"
                f"<div class='dim-score' style='color:{colour}'>{sc}</div>"
                f"<div class='dim-tag'>{lb}</div>"
                f"{_score_bar(sc, colour)}",
                unsafe_allow_html=True,
            )

    # Drivers
    if result.get("drivers"):
        st.markdown("<div style='margin-top:1rem'><strong>Key drivers:</strong></div>", unsafe_allow_html=True)
        for d in result["drivers"]:
            dim_cls = f"driver-{d.get('dimension','')}" if isinstance(d, dict) else ""
            msg = d.get("message", str(d)) if isinstance(d, dict) else str(d)
            dim = d.get("dimension", "") if isinstance(d, dict) else ""
            icon = DIM_ICON.get(dim, "•")
            st.markdown(
                f"<div class='driver-item {dim_cls}'>{icon} {msg}</div>",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<div class='page-title'>⚙️ RAG Engine</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='page-sub'>Compute, configure and monitor project RAG scores from live data</div>",
    unsafe_allow_html=True,
)

email = (st.session_state.get("email") or "system").strip().lower()
projects_df = _load_projects()

if projects_df.empty:
    st.warning("No live projects found.")
    pmo_footer()
    st.stop()

projects_df["label"] = projects_df.apply(
    lambda r: f"{r.get('client_name','?')} — {r.get('project_name','?')}", axis=1
)
project_map = {row["label"]: int(row["project_id"]) for _, row in projects_df.iterrows()}

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_compute, tab_all, tab_config, tab_override, tab_history = st.tabs([
    "🔬 Compute Single",
    "🚀 Run All Projects",
    "⚖️ Configure Weights",
    "🔒 Manual Override",
    "📈 Snapshot History",
])

# ── Tab 1: Compute single project ─────────────────────────────
with tab_compute:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 🔬 Compute RAG for a project")

    sel_label  = st.selectbox("Select project", list(project_map.keys()), key="compute_proj")
    project_id = project_map[sel_label]

    c1, c2 = st.columns([3, 1])
    with c1:
        save_snapshot = st.checkbox("Save snapshot to database", value=True)
    with c2:
        run_btn = st.button("▶ Compute RAG", use_container_width=True, type="primary")

    # Show latest stored snapshot
    latest = _load_latest_snapshot(project_id)
    if latest:
        st.markdown(
            f"<div style='color:#64748b;font-size:.85rem;margin:.3rem 0'>Last snapshot: "
            f"{latest['as_of']} | {_rag_badge(latest['overall_rag'])} "
            f"score {latest['overall_score']}</div>",
            unsafe_allow_html=True,
        )

    if run_btn:
        with st.spinner("Computing RAG..."):
            try:
                if save_snapshot:
                    result = engine.compute_and_store(project_id, actor=email)
                    st.success("✅ RAG computed and snapshot saved.")
                else:
                    result = engine.compute(project_id, actor=email)
                    st.info("Preview only — not saved.")
                st.cache_data.clear()
                _render_result(result)
            except Exception as e:
                st.error(f"RAG engine error: {e}")
    elif latest:
        st.markdown("**Latest stored result:**")
        _render_result({
            "overall_rag":      latest["overall_rag"],
            "overall_score":    latest["overall_score"],
            "dimension_detail": latest["dimensions"],
            "drivers":          latest["drivers"],
        })

    st.markdown("</div>", unsafe_allow_html=True)

# ── Tab 2: Run all projects ────────────────────────────────────
with tab_all:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 🚀 Compute RAG for all live projects")
    st.markdown(
        "Computes and saves a RAG snapshot for every live/approved project. "
        "Also updates `projects.rag_status` and `projects.health_score` immediately."
    )

    n_projects = len(projects_df)
    st.metric("Live projects to process", n_projects)

    if st.button(f"▶ Run RAG Engine for all {n_projects} projects", type="primary", use_container_width=True):
        progress = st.progress(0, text="Starting...")
        results_log = []

        for i, row in projects_df.iterrows():
            pid   = int(row["project_id"])
            pname = row.get("project_name", str(pid))
            progress.progress((list(projects_df.index).index(i) + 1) / n_projects, text=f"Processing: {pname}")
            try:
                r = engine.compute_and_store(pid, actor=email)
                results_log.append({
                    "project":  pname,
                    "rag":      r["overall_rag"].title(),
                    "score":    r["overall_score"],
                    "status":   "✅",
                })
            except Exception as e:
                results_log.append({"project": pname, "rag": "—", "score": "—", "status": f"❌ {e}"})

        progress.empty()
        st.cache_data.clear()

        results_df = pd.DataFrame(results_log)
        st.success(f"Done. Processed {len(results_df)} projects.")
        st.dataframe(results_df, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── Tab 3: Configure weights ───────────────────────────────────
with tab_config:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### ⚖️ Configure weights & thresholds")
    st.markdown("Weights must sum to 100. Thresholds define green/amber/red boundaries.")

    sel_label_c  = st.selectbox("Project", list(project_map.keys()), key="config_proj")
    project_id_c = project_map[sel_label_c]
    cfg          = _load_config(project_id_c)
    w            = cfg["weights"]
    t            = cfg["thresholds"]

    st.markdown("**Dimension weights (must total 100):**")
    wc1, wc2, wc3, wc4, wc5 = st.columns(5)
    w_risk       = wc1.number_input("🔴 Risk",       0, 100, int(w.get("risk",       25)), key="w_risk")
    w_actions    = wc2.number_input("📝 Actions",    0, 100, int(w.get("actions",    25)), key="w_actions")
    w_schedule   = wc3.number_input("📅 Schedule",   0, 100, int(w.get("schedule",   25)), key="w_schedule")
    w_budget     = wc4.number_input("💰 Budget",     0, 100, int(w.get("budget",     15)), key="w_budget")
    w_governance = wc5.number_input("📋 Governance", 0, 100, int(w.get("governance", 10)), key="w_governance")

    total_w = w_risk + w_actions + w_schedule + w_budget + w_governance
    if total_w != 100:
        st.warning(f"Weights total {total_w} — must equal 100.")

    st.markdown("**RAG thresholds:**")
    tc1, tc2 = st.columns(2)
    green_min = tc1.number_input("Green minimum score (≥)", 0, 100, int(t.get("green_min", 70)), key="t_green")
    amber_min = tc2.number_input("Amber minimum score (≥)", 0, 100, int(t.get("amber_min", 40)), key="t_amber")

    if green_min <= amber_min:
        st.warning("Green threshold must be higher than Amber threshold.")

    col_save, col_preview = st.columns(2)
    with col_save:
        if st.button("💾 Save config", disabled=(total_w != 100 or green_min <= amber_min), use_container_width=True):
            new_w = {"risk": w_risk, "actions": w_actions, "schedule": w_schedule, "budget": w_budget, "governance": w_governance}
            new_t = {"green_min": green_min, "amber_min": amber_min}
            if _save_config(project_id_c, new_w, new_t, email):
                st.success("Config saved.")
                st.cache_data.clear()

    with col_preview:
        if st.button("🔬 Preview with new config", disabled=(total_w != 100), use_container_width=True):
            with st.spinner("Computing preview..."):
                try:
                    # Temporarily patch config
                    prev_result = engine.compute(project_id_c, actor=email)
                    st.markdown("**Preview result (not saved):**")
                    _render_result(prev_result)
                except Exception as e:
                    st.error(f"Preview error: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# ── Tab 4: Manual override ─────────────────────────────────────
with tab_override:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 🔒 Manual RAG override")
    st.markdown(
        "Overrides take priority over all computed RAG. "
        "Use when exec has agreed a temporary position that data doesn't yet reflect."
    )

    sel_label_o  = st.selectbox("Project", list(project_map.keys()), key="override_proj")
    project_id_o = project_map[sel_label_o]

    # Show active override
    ov_df = run_query(
        """
        SELECT override_rag, override_reason, set_by, set_at, expires_at
        FROM public.project_rag_override
        WHERE project_id = :pid AND is_active = TRUE
          AND (expires_at IS NULL OR expires_at > now())
        LIMIT 1
        """,
        {"pid": project_id_o},
    )

    if ov_df is not None and not ov_df.empty:
        ov = ov_df.iloc[0]
        st.info(
            f"**Active override:** {_rag_badge(ov['override_rag'])}  "
            f"Set by {ov['set_by']} on {ov['set_at']}  "
            f"| Expires: {ov['expires_at'] or 'Never'}  "
            f"| Reason: {ov['override_reason']}",
            icon="🔒",
        )
        if st.button("🗑 Clear override (revert to computed RAG)", type="secondary"):
            if _clear_override(project_id_o):
                st.success("Override cleared.")
                st.cache_data.clear()
                st.rerun()
    else:
        st.markdown("No active override — computed RAG is in effect.")

    st.markdown("---")
    st.markdown("**Set new override:**")
    ov_rag    = st.selectbox("Override RAG", ["Green", "Amber", "Red"], key="ov_rag")
    ov_reason = st.text_area("Reason (required)", key="ov_reason", placeholder="e.g. Recovery plan agreed by steering group on 01/03/2026")
    ov_expire = st.number_input("Expires in (days, 0 = never)", 0, 365, 14, key="ov_expire")

    if st.button("🔒 Apply override", type="primary", disabled=not ov_reason.strip()):
        expire_days = int(ov_expire) if ov_expire > 0 else None
        if _save_override(project_id_o, ov_rag, ov_reason, email, expire_days):
            st.success(f"Override applied: {ov_rag}")
            st.cache_data.clear()
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ── Tab 5: History ─────────────────────────────────────────────
with tab_history:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("### 📈 RAG snapshot history")

    sel_label_h  = st.selectbox("Project", list(project_map.keys()), key="history_proj")
    project_id_h = project_map[sel_label_h]
    hist_df      = _load_snapshot_history(project_id_h)

    if hist_df is None or hist_df.empty:
        st.info("No snapshots yet — run the RAG engine to generate history.")
    else:
        hist_df["as_of"] = pd.to_datetime(hist_df["as_of"], errors="coerce")
        hist_df = hist_df.sort_values("as_of")

        # Score over time chart
        try:
            import altair as alt
            chart_df = hist_df[["as_of", "overall_score", "overall_rag"]].copy()
            chart_df["overall_score"] = pd.to_numeric(chart_df["overall_score"], errors="coerce")

            colour_scale = alt.Scale(
                domain=["green", "amber", "red"],
                range=["#22c55e", "#f59e0b", "#ef4444"],
            )
            line = alt.Chart(chart_df).mark_line(strokeWidth=2.5).encode(
                x=alt.X("as_of:T", title="Snapshot date"),
                y=alt.Y("overall_score:Q", title="Score", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("overall_rag:N", scale=colour_scale, legend=alt.Legend(title="RAG")),
                tooltip=["as_of:T", "overall_score:Q", "overall_rag:N"],
            )
            points = line.mark_point(size=60, filled=True).encode(
                color=alt.Color("overall_rag:N", scale=colour_scale),
            )
            st.altair_chart((line + points).properties(height=260), use_container_width=True)
        except ImportError:
            st.line_chart(hist_df.set_index("as_of")["overall_score"])

        # Reference lines
        st.markdown(
            "<div style='font-size:.82rem;color:#64748b'>Reference: "
            "<span style='color:#22c55e;font-weight:700'>Green ≥ 70</span> &nbsp; "
            "<span style='color:#f59e0b;font-weight:700'>Amber ≥ 40</span> &nbsp; "
            "<span style='color:#ef4444;font-weight:700'>Red &lt; 40</span></div>",
            unsafe_allow_html=True,
        )

        st.markdown("<br/>**Raw snapshot log:**", unsafe_allow_html=True)
        display_hist = hist_df[["as_of", "overall_rag", "overall_score"]].copy()
        display_hist.columns = ["Snapshot Date", "RAG", "Score"]
        display_hist = display_hist.sort_values("Snapshot Date", ascending=False)
        st.dataframe(display_hist, use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)

pmo_footer()