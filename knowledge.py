# =====================================================================
# ScopeSight Knowledge Engine (DB-based)
# =====================================================================

from modules.db import run_query, run_execute


# ---------------------------------------------------------------------
# AUTO-CATEGORISATION
# ---------------------------------------------------------------------

def categorise_question(text: str) -> str:
    t = text.lower()

    if any(w in t for w in ["nfr", "non functional", "non-functional"]):
        return "NFR Generator"
    if any(w in t for w in ["consolidator", "merge nfr"]):
        return "NFR Consolidator (Coming Soon)"
    if any(w in t for w in ["raid", "risk", "issue", "dependency"]):
        return "RAID Manager"
    if any(w in t for w in ["action", "owner", "due date"]):
        return "Action Manager / Action Register"
    if any(w in t for w in ["template", "library", "upload template"]):
        return "Template Library"
    if any(w in t for w in ["governance", "rag", "milestones"]):
        return "Governance Dashboard"
    if any(w in t for w in ["exec", "portfolio"]):
        return "Exec Dashboard"
    if any(w in t for w in ["client setup", "scaffold", "tier"]):
        return "Client Setup & Scaffolding"
    if any(w in t for w in ["access", "role", "permission"]):
        return "User Access Manager"
    if any(w in t for w in ["submission", "submit document"]):
        return "Submission Tracker"
    if any(w in t for w in ["coming soon", "future tool"]):
        return "Coming Soon"

    return "Other"


# ---------------------------------------------------------------------
# LOAD KNOWLEDGE FROM THE DATABASE
# ---------------------------------------------------------------------

def load_knowledge():
    sql = """
        SELECT id, question, answer, category
        FROM knowledge_entries
        WHERE is_active = TRUE
        ORDER BY id ASC;
    """
    return run_query(sql)


# ---------------------------------------------------------------------
# ADD NEW KNOWLEDGE ENTRY (Admin or Auto-Approved)
# ---------------------------------------------------------------------

def add_knowledge(question: str, answer: str, category: str, created_by: str = "system"):
    sql = """
        INSERT INTO knowledge_entries (question, answer, category, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """
    return run_execute(sql, (question, answer, category, created_by))


# ---------------------------------------------------------------------
# STORE PENDING KNOWLEDGE (User contributions)
# ---------------------------------------------------------------------

def submit_pending_knowledge(question: str, answer: str, category: str, submitted_by: str):
    sql = """
        INSERT INTO knowledge_pending (submitted_question, submitted_answer, category, submitted_by)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """
    return run_execute(sql, (question, answer, category, submitted_by))


# ---------------------------------------------------------------------
# SAVE FEEDBACK (Thumbs up/down)
# ---------------------------------------------------------------------

def save_feedback(knowledge_id: int, rating: int, user_email: str, feedback_text: str = None):
    sql = """
        INSERT INTO knowledge_feedback (knowledge_id, rating, user_email, feedback_text)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """
    return run_execute(sql, (knowledge_id, rating, user_email, feedback_text))
