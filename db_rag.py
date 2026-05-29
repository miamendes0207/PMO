# modules/db_rag.py
from modules.db import run_query

def search_knowledge_library(query: str, limit: int = 5):
    """
    Simple RAG search over knowledge_library using ILIKE.
    Returns a pandas DataFrame.
    """
    sql = """
        SELECT id, question, answer, category, rating, created_at
        FROM knowledge_library
        WHERE question ILIKE :pattern
        ORDER BY created_at DESC
        LIMIT :limit;
    """
    params = {
        "pattern": f"%{query}%",
        "limit": limit,
    }
    return run_query(sql, params)
