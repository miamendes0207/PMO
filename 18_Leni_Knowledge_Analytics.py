# ============================================================
# 💡 Leni Analytics Dashboard — ScopeSight v1.4
# Admin-only analytics on Leni usage across the platform (DB-powered)
#
# DATA SOURCES:
# - public.leni_interactions
# - public.leni_knowledge
# - public.leni_pending
# - public.leni_classification_rules
# ============================================================

import os
from collections import Counter

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from auth.login import require_login
from modules.db import run_query
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# ---------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# ---------------------------------------------------------
st.set_page_config(
    page_title="💡 Leni Analytics",
    page_icon="💡",
    layout="wide",
)

# ---------------------------------------------------------
# DEV MODE OVERRIDE BOOTSTRAP
# ---------------------------------------------------------
query = st.query_params

if "dev" in query and query["dev"] == "1":
    st.session_state["force_dev_mode"] = True

if st.session_state.get("email") == "developer@scopesight.local":
    st.session_state["force_dev_mode"] = True
    st.session_state["role"] = "admin"

if os.getenv("SCOPESIGHT_MODE") == "dev":
    st.session_state["force_dev_mode"] = True

# ---------------------------------------------------------
# REQUIRE LOGIN + THEME
# ---------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="💡 Leni Analytics (Database)")
render_sidebar()

# ---------------------------------------------------------
# STYLES
# ---------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

/* Shared visual language (admin pages) */
.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.75rem 0 1rem 0;
}
.section-header h3 { color: white; margin: 0; font-size: 1.2rem; font-weight: 700; }

.step-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1.25rem 0 1rem 0;
}
.step-header h4 { color: #0077be; margin: 0; font-size: 1.05rem; font-weight: 700; }

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0 1.25rem 0;
}

.metric-card {
    background: #f0f9ff;
    border: 2px solid #bae6fd;
    border-radius: 10px;
    padding: 1.1rem;
    text-align: center;
    margin: 0.35rem 0;
}
.metric-value { font-size: 1.8rem; font-weight: 800; color: #0077be; margin: 0.35rem 0; }
.metric-label { color: #0369a1; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }

.small-note { color: #64748b; font-size: 0.9rem; font-style: italic; margin: 0.4rem 0; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# ROLE GUARD
# ---------------------------------------------------------
role = (st.session_state.get("role", "user") or "user").strip().lower()
if role != "admin":
    st.error("🚫 You do not have permission to access Leni Analytics.")
    pmo_footer()
    st.stop()

# ============================================================
# HELPERS
# ============================================================
def safe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df if df is not None else pd.DataFrame()

def cap_labels(labels, max_len=24):
    out = []
    for x in labels:
        s = str(x)
        out.append(s if len(s) <= max_len else s[: max_len - 1] + "…")
    return out

@st.cache_data(show_spinner=False, ttl=60)
def load_distinct_filters():
    users = safe_df(run_query("SELECT DISTINCT email FROM public.leni_interactions WHERE email IS NOT NULL AND email <> '' ORDER BY email"))
    clients = safe_df(run_query("SELECT DISTINCT client FROM public.leni_interactions WHERE client IS NOT NULL AND client <> '' ORDER BY client"))
    roles = safe_df(run_query("SELECT DISTINCT role FROM public.leni_interactions WHERE role IS NOT NULL AND role <> '' ORDER BY role"))
    modules = safe_df(run_query("SELECT DISTINCT module FROM public.leni_interactions WHERE module IS NOT NULL AND module <> '' ORDER BY module"))
    cats = safe_df(run_query("SELECT DISTINCT category FROM public.leni_interactions WHERE category IS NOT NULL AND category <> '' ORDER BY category"))
    return users, clients, roles, modules, cats

@st.cache_data(show_spinner=False, ttl=60)
def load_interactions(date_from, date_to, users=None, clients=None, roles=None, modules=None, cats=None):
    where = ["timestamp >= :d1", "timestamp <= :d2"]
    params = {"d1": date_from, "d2": date_to}

    if users:
        where.append("email = ANY(:users)")
        params["users"] = users
    if clients:
        where.append("client = ANY(:clients)")
        params["clients"] = clients
    if roles:
        where.append("role = ANY(:roles)")
        params["roles"] = roles
    if modules:
        where.append("module = ANY(:modules)")
        params["modules"] = modules
    if cats:
        where.append("category = ANY(:cats)")
        params["cats"] = cats

    sql = f"""
    SELECT
        id, email, client, role,
        question, answer,
        category, module,
        detected_keywords,
        timestamp,
        latency_ms,
        tokens_in,
        tokens_out
    FROM public.leni_interactions
    WHERE {' AND '.join(where)}
    ORDER BY timestamp DESC
    """
    return safe_df(run_query(sql, params))

@st.cache_data(show_spinner=False, ttl=120)
def load_kb_stats():
    kb = safe_df(run_query("SELECT COUNT(*)::int AS n FROM public.leni_knowledge WHERE is_active = TRUE"))
    pending = safe_df(run_query("SELECT COUNT(*)::int AS n FROM public.leni_pending"))
    rules = safe_df(run_query("SELECT COUNT(*)::int AS n FROM public.leni_classification_rules"))

    kb_growth = safe_df(run_query("""
        SELECT DATE(created_at) AS day, COUNT(*)::int AS added
        FROM public.leni_knowledge
        WHERE created_at IS NOT NULL
        GROUP BY DATE(created_at)
        ORDER BY day
    """))

    pending_growth = safe_df(run_query("""
        SELECT DATE(created_at) AS day, COUNT(*)::int AS added
        FROM public.leni_pending
        WHERE created_at IS NOT NULL
        GROUP BY DATE(created_at)
        ORDER BY day
    """))
    return kb, pending, rules, kb_growth, pending_growth

# ============================================================
# FILTERS (GLOBAL — affect all tabs)
# ============================================================
st.markdown(
    """
    <div class='step-header'>
        <h4>🔎 Global Filters</h4>
    </div>
    """,
    unsafe_allow_html=True,
)

bounds = safe_df(run_query("SELECT MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts FROM public.leni_interactions"))
if bounds.empty or bounds.iloc[0]["min_ts"] is None:
    st.warning("No rows found in public.leni_interactions yet.")
    pmo_footer()
    st.stop()

min_ts = pd.to_datetime(bounds.iloc[0]["min_ts"])
max_ts = pd.to_datetime(bounds.iloc[0]["max_ts"])

c1, c2 = st.columns(2)
with c1:
    date_from = st.date_input("From", value=min_ts.date(), min_value=min_ts.date(), max_value=max_ts.date())
with c2:
    date_to = st.date_input("To", value=max_ts.date(), min_value=min_ts.date(), max_value=max_ts.date())

users_df, clients_df, roles_df, modules_df, cats_df = load_distinct_filters()

colA, colB, colC, colD, colE = st.columns(5)

with colA:
    all_users = users_df["email"].tolist() if not users_df.empty else []
    selected_users = st.multiselect("User (email)", options=all_users, default=all_users)

with colB:
    all_clients = clients_df["client"].tolist() if not clients_df.empty else []
    selected_clients = st.multiselect("Client", options=all_clients, default=all_clients)

with colC:
    all_roles = roles_df["role"].tolist() if not roles_df.empty else []
    selected_roles = st.multiselect("Role", options=all_roles, default=all_roles)

with colD:
    all_modules = modules_df["module"].tolist() if not modules_df.empty else []
    selected_modules = st.multiselect("Module", options=all_modules, default=all_modules)

with colE:
    all_cats = cats_df["category"].tolist() if not cats_df.empty else []
    selected_cats = st.multiselect("Category", options=all_cats, default=all_cats)

# Convert dates to timestamps for SQL
d1 = pd.Timestamp(date_from)
d2 = pd.Timestamp(date_to) + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)

df = load_interactions(
    d1.to_pydatetime(),
    d2.to_pydatetime(),
    users=selected_users or None,
    clients=selected_clients or None,
    roles=selected_roles or None,
    modules=selected_modules or None,
    cats=selected_cats or None,
)

if df.empty:
    st.info("No interactions match the selected filters.")
    pmo_footer()
    st.stop()

for c in ["latency_ms", "tokens_in", "tokens_out"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

df["timestamp"] = pd.to_datetime(df["timestamp"])
df["day"] = df["timestamp"].dt.date
df["has_answer"] = df["answer"].fillna("").astype(str).str.len().gt(0)

# ============================================================
# TABS
# ============================================================
tab_snapshot, tab_daily, tab_modules, tab_clients, tab_terms, tab_kb, tab_users, tab_table = st.tabs(
    [
        "📌 Snapshot",
        "📅 Daily Trends",
        "🧩 Modules & Categories",
        "🏢 Clients",
        "🔍 Top Terms",
        "📚 Knowledge Base",
        "👤 Users",
        "📋 Raw Data",
    ]
)

# ============================================================
# TAB 1 — SNAPSHOT (LANDING)
# ============================================================
with tab_snapshot:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📌 Snapshot</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    total_interactions = int(len(df))
    active_users = int(df["email"].nunique()) if "email" in df.columns else 0
    active_days = int(df["day"].nunique())
    avg_latency = float(df["latency_ms"].replace(0, pd.NA).dropna().mean() or 0)
    p95_latency = float(df["latency_ms"].replace(0, pd.NA).dropna().quantile(0.95) or 0)
    tok_in = int(df["tokens_in"].sum())
    tok_out = int(df["tokens_out"].sum())
    answer_rate = float(df["has_answer"].mean() * 100)

    top_module = "—"
    if "module" in df.columns and df["module"].fillna("").astype(str).str.len().gt(0).any():
        top_module = df["module"].value_counts().index[0]

    top_client = "—"
    if "client" in df.columns and df["client"].fillna("").astype(str).str.len().gt(0).any():
        top_client = df["client"].value_counts().index[0]

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Interactions</div><div class='metric-value'>{total_interactions}</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Active Users</div><div class='metric-value'>{active_users}</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Active Days</div><div class='metric-value'>{active_days}</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Avg Latency (ms)</div><div class='metric-value'>{avg_latency:.0f}</div></div>", unsafe_allow_html=True)
    with m5:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>P95 Latency (ms)</div><div class='metric-value'>{p95_latency:.0f}</div></div>", unsafe_allow_html=True)
    with m6:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Answer Rate</div><div class='metric-value'>{answer_rate:.0f}%</div></div>", unsafe_allow_html=True)

    st.markdown(
        f"<p class='small-note'>Top module: <b>{top_module}</b> • Top client: <b>{top_client}</b> • Tokens: <b>{tok_in:,}</b> in / <b>{tok_out:,}</b> out</p>",
        unsafe_allow_html=True,
    )

    st.download_button(
        "⬇️ Export filtered interactions (CSV)",
        data=df.drop(columns=["day"]).to_csv(index=False).encode("utf-8"),
        file_name="leni_interactions_filtered.csv",
        mime="text/csv",
    )

# ============================================================
# TAB 2 — DAILY TRENDS
# ============================================================
with tab_daily:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📅 Daily Usage Trends</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    daily = df.groupby("day").size().sort_index()

    fig, ax = plt.subplots(figsize=(9, 3.2))
    daily.plot(kind="bar", ax=ax)
    ax.set_ylabel("Interactions")
    ax.set_title("Daily Leni Usage (Filtered)", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig)

# ============================================================
# TAB 3 — MODULES & CATEGORIES
# ============================================================
with tab_modules:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🧩 Module & Category Distribution</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cL, cR = st.columns(2)

    with cL:
        if "module" in df.columns and df["module"].fillna("").astype(str).str.len().gt(0).any():
            mod_counts = df["module"].value_counts().head(20)
            fig2, ax2 = plt.subplots(figsize=(9, 3.2))
            ax2.bar(cap_labels(mod_counts.index.tolist()), mod_counts.values)
            ax2.set_ylabel("Count")
            ax2.set_title("Top Modules (Top 20)", fontsize=12)
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig2)
        else:
            st.info("Module not logged.")

    with cR:
        if "category" in df.columns and df["category"].fillna("").astype(str).str.len().gt(0).any():
            cat_counts = df["category"].value_counts().head(20)
            figc, axc = plt.subplots(figsize=(9, 3.2))
            axc.bar(cap_labels(cat_counts.index.tolist()), cat_counts.values)
            axc.set_ylabel("Count")
            axc.set_title("Top Categories (Top 20)", fontsize=12)
            plt.xticks(rotation=45, ha="right")
            st.pyplot(figc)
        else:
            st.info("Category not logged.")

# ============================================================
# TAB 4 — CLIENTS
# ============================================================
with tab_clients:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🏢 Client Interaction Volume</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "client" in df.columns and df["client"].fillna("").astype(str).str.len().gt(0).any():
        client_counts = df["client"].value_counts().head(25)
        fig3, ax3 = plt.subplots(figsize=(9, 3.2))
        ax3.bar(cap_labels(client_counts.index.tolist()), client_counts.values)
        ax3.set_ylabel("Interactions")
        ax3.set_title("Client Breakdown (Top 25)", fontsize=12)
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig3)
    else:
        st.info("Client context missing from interactions.")

# ============================================================
# TAB 5 — TOP TERMS
# ============================================================
with tab_terms:
    st.markdown(
        """
        <div class='section-header'>
            <h3>🔍 Most Common PMO Terms</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "question" in df.columns and df["question"].fillna("").astype(str).str.len().gt(0).any():
        questions = df["question"].dropna().astype(str)
        words = " ".join(questions).lower().split()
        words = [w.strip(".,!?()[]{}:;\"'") for w in words if len(w) > 3]
        common = Counter(words)
        top_words = dict(common.most_common(12))

        if top_words:
            fig4, ax4 = plt.subplots(figsize=(9, 4))
            ax4.barh(list(top_words.keys()), list(top_words.values()))
            ax4.invert_yaxis()
            ax4.set_title("Top Queried Terms (Filtered)", fontsize=12)
            st.pyplot(fig4)
        else:
            st.info("No frequent terms detected.")
    else:
        st.info("Question text not available.")

# ============================================================
# TAB 6 — KNOWLEDGE BASE
# ============================================================
with tab_kb:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📚 Knowledge Base & Pending Suggestions</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kb, pending, rules, kb_growth, pending_growth = load_kb_stats()

    kb_n = int(kb.iloc[0]["n"]) if not kb.empty else 0
    pending_n = int(pending.iloc[0]["n"]) if not pending.empty else 0
    rules_n = int(rules.iloc[0]["n"]) if not rules.empty else 0

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Active KB Entries</div><div class='metric-value'>{kb_n}</div></div>", unsafe_allow_html=True)
    with k2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Pending Suggestions</div><div class='metric-value'>{pending_n}</div></div>", unsafe_allow_html=True)
    with k3:
        st.markdown(f"<div class='metric-card'><div class='metric-card'><div class='metric-label'>Classification Rules</div><div class='metric-value'>{rules_n}</div></div></div>", unsafe_allow_html=True)

    cG1, cG2 = st.columns(2)
    with cG1:
        if not kb_growth.empty:
            figk, axk = plt.subplots(figsize=(9, 3.2))
            axk.plot(kb_growth["day"].astype(str), kb_growth["added"], marker="o")
            axk.set_title("KB Entries Added Per Day", fontsize=12)
            axk.set_ylabel("Entries Added")
            plt.xticks(rotation=45, ha="right")
            st.pyplot(figk)
        else:
            st.info("No KB growth data.")

    with cG2:
        if not pending_growth.empty:
            figp, axp = plt.subplots(figsize=(9, 3.2))
            axp.plot(pending_growth["day"].astype(str), pending_growth["added"], marker="o")
            axp.set_title("Pending Suggestions Added Per Day", fontsize=12)
            axp.set_ylabel("Suggestions Added")
            plt.xticks(rotation=45, ha="right")
            st.pyplot(figp)
        else:
            st.info("No pending growth data.")

# ============================================================
# TAB 7 — USERS
# ============================================================
with tab_users:
    st.markdown(
        """
        <div class='section-header'>
            <h3>👤 User-Level Insights</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "email" not in df.columns or not df["email"].fillna("").astype(str).str.len().gt(0).any():
        st.info("Email not logged in interactions — cannot show user analytics.")
    else:
        st.caption("Analyse usage patterns, module adoption, and workload across individual users.")

        user_counts = df["email"].value_counts().head(15)
        fig_u, ax_u = plt.subplots(figsize=(9, 3.2))
        ax_u.bar(cap_labels(user_counts.index.tolist(), 28), user_counts.values)
        ax_u.set_ylabel("Interactions")
        ax_u.set_title("Most Active Users (Top 15)", fontsize=12)
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig_u)

        users = sorted(df["email"].dropna().unique().tolist())
        selected_user = st.selectbox("Select a user for drill-down", users, key="leni_ua_user")

        udf = df[df["email"] == selected_user].copy()

        st.markdown(
            """
            <div class='step-header'>
                <h4>🧩 Module Usage For Selected User</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if "module" in udf.columns and udf["module"].fillna("").astype(str).str.len().gt(0).any():
            mc = udf["module"].value_counts().head(20)
            fig_mu, ax_mu = plt.subplots(figsize=(9, 3.2))
            ax_mu.bar(cap_labels(mc.index.tolist()), mc.values)
            ax_mu.set_ylabel("Count")
            ax_mu.set_title(f"Modules — {selected_user}", fontsize=12)
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig_mu)
        else:
            st.info("Module not logged for this user.")

        st.markdown(
            """
            <div class='step-header'>
                <h4>🏢 Client Usage For Selected User</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if "client" in udf.columns and udf["client"].fillna("").astype(str).str.len().gt(0).any():
            cc = udf["client"].value_counts().head(20)
            fig_cu, ax_cu = plt.subplots(figsize=(9, 3.2))
            ax_cu.bar(cap_labels(cc.index.tolist()), cc.values)
            ax_cu.set_ylabel("Interactions")
            ax_cu.set_title(f"Clients — {selected_user}", fontsize=12)
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig_cu)
        else:
            st.info("Client not logged for this user.")

        st.markdown(
            """
            <div class='step-header'>
                <h4>📈 User Activity Timeline</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        udf["day"] = udf["timestamp"].dt.date
        tl = udf.groupby("day").size().sort_index()
        fig_t, ax_t = plt.subplots(figsize=(9, 3.2))
        tl.plot(marker="o", ax=ax_t)
        ax_t.set_ylabel("Interactions")
        ax_t.set_title(f"Usage Timeline — {selected_user}", fontsize=12)
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig_t)

        st.markdown(
            """
            <div class='step-header'>
                <h4>⚠️ Potential Difficulty Signals</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if "question" in df.columns and df["question"].fillna("").astype(str).str.len().gt(0).any():
            def detect_repeats(texts):
                tokens = " ".join(texts).lower().split()
                c = Counter([w.strip(".,!?()[]{}:;\"'") for w in tokens if len(w) > 4])
                return {k: v for k, v in c.items() if v >= 4}

            texts = udf["question"].dropna().astype(str).tolist()
            reps = detect_repeats(texts)

            if reps:
                st.warning("Repeated terms may indicate confusion, retries, or unclear guidance.")
                st.json({selected_user: reps})
            else:
                st.success("No strong repeat-pattern signals detected for this user in the filtered window.")
        else:
            st.info("Question text not available in interactions.")

# ============================================================
# TAB 8 — RAW DATA TABLE
# ============================================================
with tab_table:
    st.markdown(
        """
        <div class='section-header'>
            <h3>📋 Raw Interactions</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    show_cols = [
        "timestamp", "email", "client", "role", "module", "category",
        "latency_ms", "tokens_in", "tokens_out", "question", "answer"
    ]
    show_cols = [c for c in show_cols if c in df.columns]

    st.dataframe(
        df[show_cols].sort_values("timestamp", ascending=False),
        use_container_width=True,
        height=600,
        hide_index=True,
    )

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
pmo_footer()
