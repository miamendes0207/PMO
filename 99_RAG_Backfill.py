import streamlit as st
from modules.db import run_query, run_execute
from modules.project_health import compute_and_snapshot

st.title("🧱 RAG Backfill")

if st.button("Run Backfill"):
    df = run_query(
        """
        SELECT DISTINCT project_id
        FROM public.projects
        WHERE project_id IS NOT NULL
        """,
        {},
    )

    if df is None or df.empty:
        st.warning("No projects found.")
        st.stop()

    pids = df["project_id"].dropna().astype(int).tolist()

    ok, fail = 0, 0
    for pid in pids:
        try:
            compute_and_snapshot(
                pid,
                run_query,
                run_execute,
                computed_by="backfill",
                only_if_changed=False,
            )
            ok += 1
        except Exception as e:
            fail += 1
            st.write(f"❌ {pid}: {e}")

    st.success(f"Done. Snapshotted: {ok}, Failed: {fail}")