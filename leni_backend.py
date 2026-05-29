# ============================================================
# modules/leni_backend.py
# DB-backed engine for Leni (ScopeSight 1.0) — PATCHED
# ============================================================

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional, Tuple

import os
import streamlit as st
from openai import OpenAI

from modules.db import run_query, run_execute

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini"


# ============================================================
# OPENAI CLIENT
# ============================================================

def _get_openai_key() -> str | None:
    # Streamlit secrets first, then env
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY")


_api_key = _get_openai_key()
client = OpenAI(api_key=_api_key) if _api_key else None


def _has_openai() -> bool:
    return client is not None


# ============================================================
# EMBEDDING HELPERS
# ============================================================

def create_embedding(text: str) -> List[float]:
    """
    Create an embedding using OpenAI. Raises a clear error if API key missing.
    """
    if not _has_openai():
        raise RuntimeError("OPENAI_API_KEY not set (OpenAI client is None)")

    text = " ".join((text or "").split())
    if not text:
        return []

    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def _vector_literal(embedding: List[float]) -> str:
    """
    Formats embedding as a pgvector literal: [0.123,0.456,...]
    Avoids spaces + scientific formatting issues.
    """
    if not embedding:
        return "[]"
    return "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"


def store_embedding(knowledge_id: int, embedding: List[float]) -> None:
    """
    Stores embedding in public.leni_embeddings.
    Assumes leni_embeddings.embedding is a pgvector column.
    """
    emb_str = _vector_literal(embedding)

    sql = """
        INSERT INTO public.leni_embeddings (knowledge_id, embedding)
        VALUES (:kid, :emb::vector)
        ON CONFLICT (knowledge_id) DO UPDATE
        SET embedding = EXCLUDED.embedding
    """
    run_execute(sql, {"kid": int(knowledge_id), "emb": emb_str})


# ============================================================
# KNOWLEDGE BASE MANAGEMENT
# ============================================================

def add_knowledge_entry(
    question: str,
    answer: str,
    category: Optional[str] = None,
    client_name: Optional[str] = None,
    tags: Optional[str] = None,
    source: str = "manual",
    created_by: Optional[str] = None,
    auto_embed: bool = True,
) -> int:
    sql = """
        INSERT INTO public.leni_knowledge
            (question, answer, category, client, tags, source, created_by)
        VALUES (:q, :a, :cat, :client, :tags, :source, :created_by)
        RETURNING id
    """
    rows = run_query(
        sql,
        {
            "q": question,
            "a": answer,
            "cat": category,
            "client": client_name,
            "tags": tags,
            "source": source,
            "created_by": created_by,
        },
    )

    knowledge_id = int(rows.iloc[0]["id"]) if hasattr(rows, "iloc") else int(rows[0]["id"])

    if auto_embed:
        try:
            if _has_openai():
                emb = create_embedding((question or "") + "\n" + (answer or ""))
                store_embedding(knowledge_id, emb)
            else:
                logger.warning("Skipping embedding (no OPENAI_API_KEY) for KB entry %s", knowledge_id)
        except Exception:
            logger.exception("Embedding failed for KB entry %s", knowledge_id)

    return knowledge_id


def search_knowledge(query: str, k: int = 5, min_score: Optional[float] = None):
    """
    Semantic KB search using pgvector cosine distance (<=>).
    Safe: returns [] if OpenAI key missing or embedding fails.
    """
    if not _has_openai():
        # No embeddings possible without API key
        return []

    try:
        embedding = create_embedding(query)
    except Exception:
        logger.exception("create_embedding failed for query: %s", query)
        return []

    emb_str = _vector_literal(embedding)

    sql = """
        SELECT
            k.id,
            k.question,
            k.answer,
            k.category,
            k.client,
            k.tags,
            1 - (e.embedding <=> (:emb)::vector) AS score
        FROM public.leni_embeddings e
        JOIN public.leni_knowledge k ON k.id = e.knowledge_id
        WHERE k.is_active IS TRUE
        ORDER BY e.embedding <=> (:emb)::vector
        LIMIT :lim
    """

    rows = run_query(sql, {"emb": emb_str, "lim": int(k)})

    # run_query sometimes returns DataFrame in your codebase
    if hasattr(rows, "to_dict"):
        recs = rows.to_dict(orient="records")
    else:
        recs = rows or []

    if min_score is not None:
        recs = [
            r for r in recs
            if r.get("score") is not None and float(r["score"]) >= float(min_score)
        ]

    return recs


# ============================================================
# CLASSIFICATION RULES
# ============================================================

def _load_classification_rules() -> List[Dict[str, str]]:
    return [
        {"module": "RAID", "keywords": "risk, issue, dependency, assumption, blocker, mitigation"},
        {"module": "NFR", "keywords": "nfr, non functional, security, performance, availability, capacity"},
        {"module": "Governance", "keywords": "deck, governance, steercos, status report, rag"},
        {"module": "Templates", "keywords": "template, upload, download, document, library"},
        {"module": "Client", "keywords": "client, scaffold, setup, permissions, client id"},
        {"module": "Platform", "keywords": "dashboard, sidebar, page, navigation, login, logout"},
        {"module": "PMO", "keywords": "pmo, project, plan, delivery"},
    ]


def _fallback_categorise_question(question: str) -> str:
    q = (question or "").lower()
    if "template" in q:
        return "Templates"
    if "client" in q:
        return "Client"
    if "dashboard" in q or "page" in q:
        return "Platform"
    return "General"


def classify_question(question: str) -> Dict[str, Any]:
    text = (question or "").lower()
    rules = _load_classification_rules()

    best_module = None
    matched_keywords: List[str] = []

    for rule in rules:
        module = (rule.get("module") or "").strip()
        keywords_str = rule.get("keywords") or ""
        keyword_list = [k.strip().lower() for k in keywords_str.split(",") if k.strip()]
        hits = [kw for kw in keyword_list if kw in text]

        if hits and len(hits) > len(matched_keywords):
            matched_keywords = hits
            best_module = module

    if best_module is None:
        best_module = _fallback_categorise_question(question)

    return {"module": best_module, "category": best_module, "matched_keywords": matched_keywords}


# ============================================================
# AUTO-LEARNING
# ============================================================

def insert_pending_learning(
    question: str,
    answer: str,
    category: Optional[str] = None,
    client_name: Optional[str] = None,
    tags: Optional[str] = None,
    confidence: Optional[float] = None,
    flagged_reason: Optional[str] = None,
) -> int:
    sql = """
        INSERT INTO public.leni_pending
            (question, answer, category, client, tags, confidence, flagged_reason)
        VALUES (:q, :a, :cat, :client, :tags, :conf, :reason)
        RETURNING id
    """
    rows = run_query(
        sql,
        {
            "q": question,
            "a": answer,
            "cat": category,
            "client": client_name,
            "tags": tags,
            "conf": confidence,
            "reason": flagged_reason,
        },
    )
    return int(rows.iloc[0]["id"]) if hasattr(rows, "iloc") else int(rows[0]["id"])


# ============================================================
# INTERACTION LOGGING
# ============================================================

def log_interaction(
    email: str,
    client_name: Optional[str],
    role: Optional[str],
    question: str,
    answer: Optional[str],
    category: Optional[str],
    module: Optional[str],
    detected_keywords: Optional[List[str]] = None,
    latency_ms: Optional[int] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
):
    detected_str = ", ".join(detected_keywords) if detected_keywords else None

    sql = """
        INSERT INTO public.leni_interactions
            (timestamp, email, client, role, question, answer,
             category, module, detected_keywords,
             latency_ms, tokens_in, tokens_out)
        VALUES
            (NOW(), :email, :client, :role, :question, :answer,
             :category, :module, :detected_keywords,
             :latency_ms, :tokens_in, :tokens_out)
    """

    try:
        run_execute(
            sql,
            {
                "email": email,
                "client": client_name,
                "role": role,
                "question": question,
                "answer": answer,
                "category": category,
                "module": module,
                "detected_keywords": detected_str,
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            },
        )
    except Exception:
        logger.exception("Failed to log Leni interaction")


# ============================================================
# ANSWERING PIPELINE
# ============================================================

def answer_with_knowledge(
    email: str,
    client_name: Optional[str],
    role: Optional[str],
    question: str,
    *,
    top_k: int = 5,
) -> Tuple[str, Dict[str, Any]]:
    t0 = time.time()

    classification = classify_question(question)
    module = classification["module"]
    category = classification["category"]
    keywords = classification["matched_keywords"]

    # Semantic KB search (safe)
    kb_hits = search_knowledge(question, k=top_k, min_score=0.35)

    tokens_in = None
    tokens_out = None

    if kb_hits:
        best = kb_hits[0]
        answer_text = best.get("answer") or ""
        answer_source = "kb"
    else:
        # LLM fallback (safe)
        if not _has_openai():
            answer_text = (
                "I can’t access the AI service right now (missing API key) and "
                "I couldn’t find a matching answer in the knowledge bank."
            )
            answer_source = "fallback_no_key"
        else:
            prompt = (
                "You are Leni, the ScopeSight PMO assistant.\n\n"
                f"User question:\n{question}"
            )
            completion = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            answer_text = completion.choices[0].message.content or ""
            answer_source = "llm"

            usage = getattr(completion, "usage", None)
            if usage:
                tokens_in = getattr(usage, "prompt_tokens", None)
                tokens_out = getattr(usage, "completion_tokens", None)

    latency_ms = int((time.time() - t0) * 1000)

    log_interaction(
        email=email,
        client_name=client_name,
        role=role,
        question=question,
        answer=answer_text,
        category=category,
        module=module,
        detected_keywords=keywords,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )

    debug_info = {
        "classification": classification,
        "kb_hits": kb_hits,
        "answer_source": answer_source,
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "openai_key_loaded": bool(_api_key),
    }

    return answer_text, debug_info
