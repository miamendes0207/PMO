# ============================================================
# modules/leni_logger.py — PATCHED (SQLAlchemy :params)
# DB-first interaction logging for Leni + JSONL fallback
# ============================================================

import os
import json
import datetime as dt
import logging

import streamlit as st

from modules.db import run_execute  # uses your existing db layer

logger = logging.getLogger(__name__)


def _now_iso():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def log_leni_interaction(
    *,
    event: str,                 # e.g. "ask", "answer", "kb_add", "kb_search"
    question: str | None = None,
    answer: str | None = None,
    category: str | None = None,  # module/page/category
    client: str | None = None,
    client_id: int | None = None,
    project: str | None = None,
    project_id: int | None = None,
    meta: dict | None = None,
) -> bool:
    """
    Logs a single Leni interaction.

    DB-first: inserts into public.leni_interactions if table exists.
    Fallback: appends to leni/data/leni_interactions.jsonl.

    Returns True if logged somewhere, else False.
    """

    email = (st.session_state.get("email") or "").strip().lower() or None
    user_id = st.session_state.get("user_id")

    payload = {
        "timestamp": _now_iso(),
        "event": event,
        "email": email,
        "user_id": user_id,
        "question": question,
        "answer": answer,
        "category": category,
        "client": client,
        "client_id": client_id,
        "project": project,
        "project_id": project_id,
        "meta": meta or {},
    }

    # -------------------------
    # 1) Try DB insert (preferred)
    # -------------------------
    try:
        run_execute(
            """
            INSERT INTO public.leni_interactions
            (ts_utc, event, email, user_id, question, answer, category,
             client, client_id, project, project_id, meta)
            VALUES
            (:ts, :event, :email, :user_id, :question, :answer, :category,
             :client, :client_id, :project, :project_id, (:meta)::jsonb)
            """,
            {
                "ts": payload["timestamp"],
                "event": payload["event"],
                "email": payload["email"],
                "user_id": payload["user_id"],
                "question": payload["question"],
                "answer": payload["answer"],
                "category": payload["category"],
                "client": payload["client"],
                "client_id": payload["client_id"],
                "project": payload["project"],
                "project_id": payload["project_id"],
                "meta": json.dumps(payload["meta"]),
            },
        )
        return True
    except Exception as e:
        # If table doesn't exist yet, or insert fails, fall back to file
        logger.warning("DB log failed, falling back to JSONL. Error=%s", type(e).__name__)

    # -------------------------
    # 2) JSONL fallback
    # -------------------------
    try:
        # project root: modules/ -> project root is one level up
        base_dir = os.path.dirname(os.path.dirname(__file__))
        log_path = os.path.join(base_dir, "leni", "data", "leni_interactions.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        return True
    except Exception as e:
        logger.exception("JSONL log failed. Error=%s", type(e).__name__)
        return False
