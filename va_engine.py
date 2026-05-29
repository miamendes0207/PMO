# ============================================================
# modules/va_engine.py — PATCHED
# High-level API for Leni (connects frontend → backend engine)
# ============================================================

from __future__ import annotations

from typing import Dict, Any, Optional, Tuple
import time
import re
import pandas as pd
import logging

from modules.db import run_query, run_execute

from modules.leni_backend import (
    answer_with_knowledge,
    insert_pending_learning,
    classify_question,
    log_interaction,  # keep this as primary analytics logger for now
)

logger = logging.getLogger(__name__)


# ============================================================
# INTERNAL: Normalisation helpers
# ============================================================

_ws_re = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """
    Normalise for robust matching:
    - lowercase
    - trim
    - collapse whitespace
    """
    return _ws_re.sub(" ", (text or "").strip().lower())


# ============================================================
# INTERNAL: KB search helpers (compatible with db.py)
# ============================================================

def _kb_search(
    user_question: str,
    limit: int = 5,
    *,
    client_name: Optional[str] = None,
    category: Optional[str] = None,
) -> pd.DataFrame:
    """
    KB lookup:
    1) exact match on normalized question (best)
    2) keyword match over tokens (safe)
    Returns a DataFrame (possibly empty).

    Notes:
    - Exact match must normalize DB field too (otherwise it never matches)
    - Optional filters are applied only if provided
    """
    q_norm = _normalize(user_question)

    where_filters = ["is_active = TRUE"]
    params: Dict[str, Any] = {"lim": int(limit), "q_norm": q_norm}

    if client_name:
        where_filters.append("LOWER(COALESCE(client,'')) = :client")
        params["client"] = client_name.strip().lower()

    if category:
        where_filters.append("LOWER(COALESCE(category,'')) = :category")
        params["category"] = category.strip().lower()

    where_base = " AND ".join(where_filters)

    # 1) Exact match (best) — normalize DB question too
    df_exact = run_query(
        f"""
        SELECT
            id, question, answer, category, client, tags, source, created_by,
            is_active, created_at
        FROM public.leni_knowledge
        WHERE {where_base}
          AND REGEXP_REPLACE(LOWER(TRIM(question)), '\\s+', ' ', 'g') = :q_norm
        ORDER BY created_at DESC
        LIMIT :lim
        """,
        params,
    )

    if df_exact is not None and not df_exact.empty:
        return df_exact

    # 2) Keyword match (safe tokens)
    stop = {
        "what", "does", "do", "how", "can", "could", "should", "would",
        "is", "are", "the", "a", "an", "to", "for", "of", "in", "on",
        "my", "your", "i", "we", "you", "and", "or", "with", "from",
        "about", "please", "help", "tell", "me"
    }

    tokens = [t for t in re.findall(r"[a-z0-9]+", q_norm) if len(t) >= 4 and t not in stop]
    tokens = tokens[:8]  # cap for safety

    if not tokens:
        # last resort: partial match of the whole string
        df_like = run_query(
            f"""
            SELECT
                id, question, answer, category, client, tags, source, created_by,
                is_active, created_at
            FROM public.leni_knowledge
            WHERE {where_base}
              AND (question ILIKE :q OR answer ILIKE :q)
            ORDER BY created_at DESC
            LIMIT :lim
            """,
            {**params, "q": f"%{q_norm}%"},
        )
        return df_like if df_like is not None else pd.DataFrame()

    conds = []
    params_kw: Dict[str, Any] = {"lim": int(limit)}
    # carry filters
    if client_name:
        params_kw["client"] = client_name.strip().lower()
    if category:
        params_kw["category"] = category.strip().lower()

    for i, tok in enumerate(tokens):
        key = f"t{i}"
        conds.append(f"(question ILIKE :{key} OR answer ILIKE :{key})")
        params_kw[key] = f"%{tok}%"

    where_or = " OR ".join(conds)

    df_kw = run_query(
        f"""
        SELECT
            id, question, answer, category, client, tags, source, created_by,
            is_active, created_at
        FROM public.leni_knowledge
        WHERE {where_base}
          AND ({where_or})
        ORDER BY created_at DESC
        LIMIT :lim
        """,
        params_kw,
    )
    return df_kw if df_kw is not None else pd.DataFrame()


def _kb_best_answer(
    user_question: str,
    *,
    client_name: Optional[str] = None,
    category: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Return (answer_text or None, debug_info).
    """
    df = _kb_search(user_question=user_question, limit=5, client_name=client_name, category=category)

    if df is not None and not df.empty:
        rows = df.to_dict(orient="records")
        best = rows[0]
        debug_info = {
            "source": "knowledge_bank",
            "kb_used": True,
            "kb_hits": [
                {
                    "id": r.get("id"),
                    "question": r.get("question"),
                    "answer": r.get("answer"),
                    "category": r.get("category"),
                    "client": r.get("client"),
                    "tags": r.get("tags"),
                    "created_at": str(r.get("created_at")) if r.get("created_at") else None,
                }
                for r in rows
            ],
        }
        return str(best.get("answer") or ""), debug_info

    return None, {"source": "knowledge_bank", "kb_used": False, "kb_hits": []}


# ============================================================
# 1️⃣ ANSWER A USER QUESTION (MAIN ENTRYPOINT)
# ============================================================

def answer_question(
    user_question: str,
    user_email: str,
    client_name: Optional[str] = None,
    user_role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Behaviour:
    - KB-first (guarantees we actually use the knowledge bank when it matches)
    - Then backend (semantic/LLM) if KB has no good hit
    - Logs ALL interactions (KB + backend) via leni_backend.log_interaction
    - Never crashes UI
    """
    start = time.time()
    user_question = (user_question or "").strip()

    # classify once (used for logging + optional KB filters)
    cls = classify_question(user_question)
    category = cls.get("category")
    module = cls.get("module")
    matched = cls.get("matched_keywords")

    # ---- 0) KB-FIRST ----
    kb_answer, kb_debug = _kb_best_answer(user_question, client_name=client_name, category=None)

    if kb_answer:
        kb_hits = kb_debug.get("kb_hits", [])
        knowledge_id = kb_hits[0]["id"] if kb_hits else None
        latency_ms = int((time.time() - start) * 1000)

        log_interaction(
            email=user_email,
            client_name=client_name,
            role=user_role,
            question=user_question,
            answer=kb_answer,
            category=category,
            module=module,
            detected_keywords=matched,
            latency_ms=latency_ms,
            tokens_in=None,
            tokens_out=None,
        )

        kb_debug["latency_ms"] = latency_ms

        return {
            "answer": kb_answer,
            "knowledge_id": knowledge_id,
            "debug": kb_debug,
        }

    # ---- 1) BACKEND (semantic + LLM) ----
    try:
        answer_text, debug_info = answer_with_knowledge(
            email=user_email,
            client_name=client_name,
            role=user_role,
            question=user_question,
        )

        # Only attach knowledge_id if backend actually returned kb hits
        kb_hits2 = debug_info.get("kb_hits", []) if isinstance(debug_info, dict) else []
        knowledge_id2 = kb_hits2[0].get("id") if kb_hits2 else None

        if isinstance(debug_info, dict):
            debug_info["latency_ms_total"] = int((time.time() - start) * 1000)

        return {
            "answer": answer_text,
            "knowledge_id": knowledge_id2,
            "debug": debug_info,
        }

    except Exception as e:
        logger.exception("va_engine backend failed")

        # ---- 2) Final fallback: KB again (never crash UI) ----
        kb_answer2, kb_debug2 = _kb_best_answer(user_question, client_name=client_name)
        latency_ms = int((time.time() - start) * 1000)

        if kb_answer2:
            kb_hits2 = kb_debug2.get("kb_hits", [])
            knowledge_id2 = kb_hits2[0]["id"] if kb_hits2 else None
            kb_debug2["primary_error_type"] = type(e).__name__
            kb_debug2["latency_ms"] = latency_ms

            log_interaction(
                email=user_email,
                client_name=client_name,
                role=user_role,
                question=user_question,
                answer=kb_answer2,
                category=category,
                module=module,
                detected_keywords=matched,
                latency_ms=latency_ms,
                tokens_in=None,
                tokens_out=None,
            )

            return {
                "answer": kb_answer2,
                "knowledge_id": knowledge_id2,
                "debug": kb_debug2,
            }

        # nothing worked
        return {
            "answer": (
                "I’m having trouble answering right now. The AI service may be unavailable and "
                "I couldn’t find a matching answer in the knowledge bank."
            ),
            "knowledge_id": None,
            "debug": {
                "source": "fallback",
                "primary_error_type": type(e).__name__,
                "latency_ms": latency_ms,
                "kb_hits": [],
            },
        }


## ============================================================
# 2️⃣ RECORD FEEDBACK (THUMBS UP / DOWN)
# ============================================================

import sqlalchemy as sa

def _ensure_leni_feedback_table() -> None:
    """
    Self-heal: create the feedback table + indexes if missing.
    Safe to run multiple times.
    """
    run_execute("""
    CREATE TABLE IF NOT EXISTS public.leni_feedback (
        feedback_id   BIGSERIAL PRIMARY KEY,
        knowledge_id  INTEGER NOT NULL,
        rating        SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
        user_email    TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- 1 vote per user per knowledge item (enables UPSERT)
    CREATE UNIQUE INDEX IF NOT EXISTS ux_leni_feedback_kid_email
        ON public.leni_feedback (knowledge_id, user_email);

    CREATE INDEX IF NOT EXISTS ix_leni_feedback_created_at
        ON public.leni_feedback (created_at);

    CREATE INDEX IF NOT EXISTS ix_leni_feedback_knowledge_id
        ON public.leni_feedback (knowledge_id);
    """)


def record_feedback(
    knowledge_id: int,
    rating: int,
    user_email: str,
) -> None:
    """
    Writes thumbs up/down feedback.
    - Auto-creates the table if it doesn't exist (prevents UI crash).
    - Upserts so repeated votes update instead of duplicate rows.
    """
    sql = """
        INSERT INTO public.leni_feedback (knowledge_id, rating, user_email, created_at)
        VALUES (:kid, :rating, :email, NOW())
        ON CONFLICT (knowledge_id, user_email)
        DO UPDATE SET
            rating = EXCLUDED.rating,
            created_at = NOW()
    """

    params = {"kid": int(knowledge_id), "rating": int(rating), "email": user_email}

    try:
        run_execute(sql, params)
    except sa.exc.ProgrammingError as e:
        # psycopg2 UndefinedTable is wrapped by SQLAlchemy
        if "UndefinedTable" in str(e) or "does not exist" in str(e):
            _ensure_leni_feedback_table()
            run_execute(sql, params)  # retry once
        else:
            raise


# ============================================================
# 3️⃣ HANDLE USER-CORRECTED ANSWERS (THUMBS DOWN)
# ============================================================

def suggest_new_knowledge(
    question: str,
    answer: str,
    user_email: str
) -> int:
    classification = classify_question(question)

    pending_id = insert_pending_learning(
        question=question,
        answer=answer,
        category=classification.get("category"),
        client_name=None,
        tags=None,
        confidence=0.5,
        flagged_reason=f"user correction by {user_email}",
    )
    return int(pending_id)
