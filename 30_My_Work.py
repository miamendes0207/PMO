# ============================================================
# 30_My_Work.py — ScopeSight v3.5 (IMPROVED UX)
# My Work - Personal task management and tracking
# ============================================================

import datetime as dt
import streamlit as st
import pandas as pd

from auth.login import require_login
from modules.db import run_query, run_execute
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="🧩 My Work",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# BOOTSTRAP
# ============================================================
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🧩 My Work")
render_sidebar()

TODAY = dt.date.today()
user_id = st.session_state.get("user_id")
role = st.session_state.get("role")
email = (st.session_state.get("email") or "").strip().lower()

if not user_id:
    st.error("❌ No user session found. Please log in again.")
    st.stop()

user_id = int(user_id)

# ============================================================
# CONSTANTS
# ============================================================
STATUS_OPTIONS = ["open", "in_progress", "blocked", "closed"]
PRIORITY_OPTIONS = ["low", "medium", "high", "critical"]
TYPE_OPTIONS = ["action", "raid", "task"]

# ============================================================
# ENHANCED STYLES
# ============================================================
st.markdown("""
<style>
header[data-testid="stHeader"] { height: 0 !important; visibility: hidden !important; }

.page-title { 
    font-size: 2rem; font-weight: 800; color: #0f172a; 
    margin: 0 0 0.5rem 0; line-height: 1.2;
}
.page-sub { 
    color: #64748b; font-size: 1rem; margin-bottom: 2rem; 
}

/* Metrics */
.metric-tile {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid #e2e8f0; 
    border-radius: 12px;
    padding: 1.25rem 1.5rem; 
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: all 0.2s ease;
}
.metric-tile:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transform: translateY(-2px);
}
.metric-tile .val { 
    font-size: 2.25rem; font-weight: 800; line-height: 1.1; 
}
.metric-tile .lbl {
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.8px; color: #64748b; margin-top: 0.4rem;
}
.val-blue { color: #2563eb; }
.val-red { color: #dc2626; }
.val-amber { color: #d97706; }
.val-green { color: #16a34a; }

/* Section Headers */
.section-header {
    font-size: 0.75rem; 
    font-weight: 700; 
    text-transform: uppercase; 
    letter-spacing: 1.2px;
    color: #94a3b8; 
    margin: 2rem 0 1rem 0; 
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

/* Work Item Cards */
.wi-card {
    background: white; 
    border: 1px solid #e2e8f0; 
    border-left: 4px solid #cbd5e1;
    border-radius: 10px; 
    padding: 1.25rem 1.5rem; 
    margin-bottom: 1rem;
    transition: all 0.2s ease;
}
.wi-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    border-left-width: 6px;
}
.wi-card.p-critical { border-left-color: #dc2626; }
.wi-card.p-high { border-left-color: #f97316; }
.wi-card.p-medium { border-left-color: #eab308; }
.wi-card.p-low { border-left-color: #94a3b8; }
.wi-card.overdue { 
    background: linear-gradient(135deg, #fff7f7 0%, #ffffff 100%);
    border: 1px solid #fecaca;
}

.wi-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
}

.wi-title { 
    font-size: 1.1rem; 
    font-weight: 700; 
    color: #0f172a; 
    margin: 0;
    flex: 1;
}

.wi-badges {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.wi-meta { 
    font-size: 0.85rem; 
    color: #64748b; 
    display: flex; 
    flex-wrap: wrap; 
    gap: 1rem; 
    margin: 0.75rem 0;
    padding: 0.5rem 0;
    border-top: 1px solid #f1f5f9;
}

.wi-meta-item {
    display: flex;
    align-items: center;
    gap: 0.35rem;
}

.wi-desc { 
    font-size: 0.9rem; 
    color: #475569; 
    background: #f8fafc; 
    border-radius: 6px; 
    padding: 0.75rem 1rem;
    margin: 0.75rem 0;
    line-height: 1.5;
}

.wi-section {
    margin-top: 1.25rem;
    padding-top: 1rem;
    border-top: 1px solid #f1f5f9;
}

.wi-section-title {
    font-size: 0.7rem; 
    font-weight: 700; 
    text-transform: uppercase; 
    letter-spacing: 0.8px;
    color: #94a3b8; 
    margin-bottom: 0.75rem;
}

/* Badges */
.badge {
    display: inline-flex; 
    align-items: center; 
    gap: 0.25rem;
    padding: 0.25rem 0.75rem; 
    border-radius: 999px;
    font-size: 0.75rem; 
    font-weight: 600;
    white-space: nowrap;
}
.b-open { background: #dbeafe; color: #1e40af; }
.b-in_progress { background: #fef3c7; color: #92400e; }
.b-blocked { background: #fee2e2; color: #991b1b; }
.b-completed { background: #dcfce7; color: #166534; }
.b-closed { background: #f1f5f9; color: #475569; }
.b-action { background: #ede9fe; color: #5b21b6; }
.b-raid { background: #fce7f3; color: #9d174d; }
.b-task { background: #e0f2fe; color: #0c4a6e; }
.b-overdue { background: #fee2e2; color: #991b1b; font-weight: 700; }

/* Subtasks */
.subtask-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: #f8fafc;
    border-radius: 6px;
    margin-bottom: 0.5rem;
    transition: background 0.2s ease;
}
.subtask-item:hover {
    background: #f1f5f9;
}
.subtask-icon { font-size: 1.1rem; }
.subtask-title { flex: 1; font-size: 0.9rem; color: #334155; }
.subtask-due { font-size: 0.8rem; color: #94a3b8; }

/* Notes */
.note-card {
    background: #f8fafc; 
    border-left: 3px solid #cbd5e1;
    border-radius: 6px;
    padding: 0.85rem 1rem; 
    margin-bottom: 0.75rem; 
    font-size: 0.9rem; 
    color: #334155;
}
.note-card.private { border-left-color: #94a3b8; }
.note-card.shared { border-left-color: #3b82f6; }
.note-meta { 
    font-size: 0.75rem; 
    color: #94a3b8; 
    margin-top: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* Filter Bar */
.filter-bar {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
}

/* Quick Actions */
.quick-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
}

/* Buttons */
div.stButton > button { 
    font-weight: 600 !important; 
    border-radius: 8px !important; 
    transition: all 0.2s ease !important;
    border: 1px solid #e2e8f0 !important;
}
div.stButton > button:hover { 
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
}

/* Expander Styling */
.streamlit-expanderHeader {
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    border-radius: 8px !important;
}

label { font-weight: 600 !important; font-size: 0.85rem !important; }

/* Empty State */
.empty-state {
    text-align: center;
    padding: 3rem 2rem;
    color: #94a3b8;
}
.empty-state-icon { font-size: 3rem; margin-bottom: 1rem; }
.empty-state-text { font-size: 1.1rem; font-weight: 600; }
.empty-state-sub { font-size: 0.9rem; margin-top: 0.5rem; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def safe_df(x) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def safe_date(v):
    try:
        if v is None or (hasattr(pd, "isna") and pd.isna(v)):
            return None
        if isinstance(v, dt.datetime):
            return v.date()
        if isinstance(v, dt.date):
            return v
        return pd.to_datetime(v).date()
    except Exception:
        return None


def fmt_date(d) -> str:
    if not d:
        return "No due date"
    delta = (d - TODAY).days
    if delta < 0:
        return f"⚠️ Overdue by {-delta}d"
    if delta == 0:
        return "📅 Due today"
    if delta <= 3:
        return f"⏰ Due in {delta}d"
    return f"{d.day} {d.strftime('%b %Y')}"


def badge(text: str, cls: str) -> str:
    return f'<span class="badge {cls}">{text}</span>'


def to_source_status(item_type: str, status: str) -> str:
        mapping = {
            "open": "Open",
            "in_progress": "In Progress",
            "blocked": "Blocked",
            "closed": "Closed",
        }
        # legacy safeguard
        if (status or "").lower() == "completed":
            return "Closed"
        return mapping.get((status or "open").lower(), "Open")

def from_source_status(src_status: str) -> str:
        s = (src_status or "").strip().lower()

        # normalise any variants to our internal set
        if s in ("open", "in_progress", "blocked", "closed"):
            return s

        if s in ("in progress", "in-progress"):
            return "in_progress"

        # legacy / synonyms -> closed
        if s in ("done", "complete", "completed", "closed"):
            return "closed"

        if s in ("blocked", "stuck"):
            return "blocked"

        return "open"


def ensure_work_item_assignee(work_item_id: int):
    run_execute("""
        INSERT INTO public.work_item_assignees (work_item_id, user_id, role, assigned_at)
        SELECT :wid, :uid, 'owner', NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM public.work_item_assignees
            WHERE work_item_id = :wid AND user_id = :uid
        )
    """, {"wid": int(work_item_id), "uid": user_id})


# ============================================================
# ASSIGNMENT LOGIC
# ============================================================
def get_assigned_action_ids() -> list[int]:
    if not email:
        em = ""
        local = ""
    else:
        em = email.strip().lower()
        local = em.split("@")[0].strip().lower()

    df = safe_df(run_query("""
        SELECT DISTINCT action_id
        FROM public.actions
        WHERE
              COALESCE(owner_user_id, -1) = :uid
           OR LOWER(COALESCE(owner,'')) = :em
           OR LOWER(COALESCE(owner,'')) ILIKE :p
    """, {
        "uid": int(user_id),
        "em": em,
        "p": f"%{local}%"
    }))

    return [int(x) for x in df["action_id"].tolist()] if not df.empty else []


def get_assigned_raid_ids():
    if not email:
        local = ""
    else:
        local = email.split("@")[0].strip().lower()

    df = safe_df(run_query("""
        SELECT raid_id
        FROM public.raids
        WHERE LOWER(COALESCE(owner_plen,'')) ILIKE :p 
           OR LOWER(COALESCE(owner_client,'')) ILIKE :p
    """, {"p": f"%{local}%"}))
    return df["raid_id"].astype(int).tolist() if not df.empty else []


# ============================================================
# UPSERT LOGIC
# ============================================================
def upsert_work_item_from_action(action_id: int):
    df = safe_df(run_query("""
        SELECT
            action_id, client_id, project_id,
            title, detail, comments,
            status, priority,
            due_date, date_raised, actual_close_date
        FROM public.actions
        WHERE action_id = :id
        LIMIT 1
    """, {"id": int(action_id)}))
    if df.empty:
        return

    r = df.iloc[0].to_dict()
    title = (r.get("title") or f"Action #{action_id}").strip()
    desc = (r.get("detail") or "").strip()
    comm = (r.get("comments") or "").strip()
    stt = from_source_status(r.get("status") or "Open")
    pr = str(r.get("priority") or "medium").strip().lower()
    if pr not in PRIORITY_OPTIONS:
        pr = "medium"
    due = safe_date(r.get("due_date"))
    raised = safe_date(r.get("date_raised")) or TODAY
    closed = safe_date(r.get("actual_close_date"))
    cid = r.get("client_id")
    pid = r.get("project_id")

    run_execute("""
        UPDATE public.work_items
        SET
            client_id = :cid, project_id = :pid, title = :t, description = :d,
            comments = :c, status = :st, priority = :p, due_date = :due,
            date_raised = :raised, actual_close_date = :closed, updated_at = NOW()
        WHERE item_type = 'action' AND source_id = :sid
    """, {
        "sid": int(action_id), "cid": int(cid) if cid is not None else None,
        "pid": int(pid) if pid is not None else None, "t": title, "d": desc,
        "c": comm, "st": stt, "p": pr, "due": due, "raised": raised, "closed": closed,
    })

    run_execute("""
        INSERT INTO public.work_items
            (item_type, source_id, client_id, project_id, title, description, comments,
             status, priority, due_date, date_raised, actual_close_date,
             created_by, created_at, updated_at)
        SELECT
            'action', :sid, :cid, :pid, :t, :d, :c, :st, :p, :due, :raised, :closed,
            :uid, NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM public.work_items WHERE item_type = 'action' AND source_id = :sid
        )
    """, {
        "sid": int(action_id), "cid": int(cid) if cid is not None else None,
        "pid": int(pid) if pid is not None else None, "t": title, "d": desc,
        "c": comm, "st": stt, "p": pr, "due": due, "raised": raised, "closed": closed,
        "uid": user_id,
    })

    wi = safe_df(run_query("""
        SELECT work_item_id FROM public.work_items
        WHERE item_type = 'action' AND source_id = :sid LIMIT 1
    """, {"sid": int(action_id)}))
    if not wi.empty:
        ensure_work_item_assignee(int(wi.iloc[0]["work_item_id"]))


def upsert_work_item_from_raid(raid_id: int):
    df = safe_df(run_query("""
        SELECT
            raid_id, client_id, project_id, title, description, comments,
            status, planned_close, date_raised, date_closed, owner_plen, owner_client
        FROM public.raids
        WHERE raid_id = :id
        LIMIT 1
    """, {"id": int(raid_id)}))
    if df.empty:
        return

    r = df.iloc[0].to_dict()
    title = (r.get("title") or f"RAID #{raid_id}").strip()
    desc = (r.get("description") or "").strip()
    comm = (r.get("comments") or "").strip()
    stt = from_source_status(r.get("status") or "Open")
    pr = "high" if stt == "blocked" else "medium"
    due = safe_date(r.get("planned_close"))
    raised = safe_date(r.get("date_raised")) or TODAY
    closed = safe_date(r.get("date_closed"))
    cid = r.get("client_id")
    pid = r.get("project_id")

    run_execute("""
        UPDATE public.work_items
        SET
            client_id = :cid, project_id = :pid, title = :t, description = :d,
            comments = :c, status = :st, priority = :p, due_date = :due,
            date_raised = :raised, actual_close_date = :closed, updated_at = NOW()
        WHERE item_type = 'raid' AND source_id = :sid
    """, {
        "sid": int(raid_id), "cid": int(cid) if cid is not None else None,
        "pid": int(pid) if pid is not None else None, "t": title, "d": desc,
        "c": comm, "st": stt, "p": pr, "due": due, "raised": raised, "closed": closed,
    })

    run_execute("""
        INSERT INTO public.work_items
            (item_type, source_id, client_id, project_id, title, description, comments,
             status, priority, due_date, date_raised, actual_close_date,
             created_by, created_at, updated_at)
        SELECT
            'raid', :sid, :cid, :pid, :t, :d, :c, :st, :p, :due, :raised, :closed,
            :uid, NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM public.work_items WHERE item_type = 'raid' AND source_id = :sid
        )
    """, {
        "sid": int(raid_id), "cid": int(cid) if cid is not None else None,
        "pid": int(pid) if pid is not None else None, "t": title, "d": desc,
        "c": comm, "st": stt, "p": pr, "due": due, "raised": raised, "closed": closed,
        "uid": user_id,
    })

    wi = safe_df(run_query("""
        SELECT work_item_id FROM public.work_items
        WHERE item_type = 'raid' AND source_id = :sid LIMIT 1
    """, {"sid": int(raid_id)}))
    if not wi.empty:
        ensure_work_item_assignee(int(wi.iloc[0]["work_item_id"]))


def sync_assigned_raids_and_actions():
    a_ids = get_assigned_action_ids()
    r_ids = get_assigned_raid_ids()
    for aid in a_ids:
        upsert_work_item_from_action(aid)
    for rid in r_ids:
        upsert_work_item_from_raid(rid)


# Initial sync
if "mw_synced_sources" not in st.session_state:
    try:
        sync_assigned_raids_and_actions()
    except Exception as e:
        st.error(f"❌ Sync failed: {e}")
    st.session_state["mw_synced_sources"] = True


# ============================================================
# DATA QUERIES
# ============================================================
def fetch_my_work(
        *,
        status_filter=None,
        type_filter=None,
        project_id=None,
        priority_filter=None,
        search_text=None,
        only_assigned=True,
        include_completed=False,
) -> pd.DataFrame:

    params = {"uid": user_id}
    join_sql, where = "", []

    if only_assigned:
        join_sql = "JOIN public.work_item_assignees wia ON wia.work_item_id = wi.work_item_id"
        where.append("wia.user_id = :uid")

    if type_filter:
        params["types"] = list(type_filter)
        where.append("wi.item_type = ANY(CAST(:types AS text[]))")

    if status_filter:
        params["statuses"] = list(status_filter)
        where.append("wi.status = ANY(CAST(:statuses AS text[]))")
    elif not include_completed:
        # hide closed (and legacy completed)
        where.append("wi.status NOT IN ('closed','completed')")

    if priority_filter:
        params["priorities"] = list(priority_filter)
        where.append("wi.priority = ANY(CAST(:priorities AS text[]))")

    if project_id:
        params["pid"] = int(project_id)
        where.append("wi.project_id = :pid")

    if search_text:
        params["search"] = f"%{search_text.lower()}%"
        where.append("(LOWER(wi.title) LIKE :search OR LOWER(wi.description) LIKE :search)")

    where_sql = " AND ".join(where) if where else "TRUE"

    sql = f"""
    SELECT
        wi.work_item_id, wi.item_type, wi.source_id, wi.client_id, wi.project_id,
        wi.title, wi.description, wi.comments, wi.status, wi.priority,
        wi.due_date, wi.date_raised, wi.actual_close_date, wi.updated_at
    FROM public.work_items wi
    {join_sql}
    WHERE {where_sql}
    ORDER BY
        (wi.due_date IS NULL) ASC,
        wi.due_date ASC,
        CASE wi.priority
            WHEN 'critical' THEN 0
            WHEN 'high' THEN 1
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 3
            ELSE 9
        END ASC,
        wi.updated_at DESC
    """

    return safe_df(run_query(sql, params))

def fetch_projects_for_user() -> pd.DataFrame:
    try:
        return safe_df(run_query(
            "SELECT project_id, project_name FROM public.projects ORDER BY project_name", {}
        ))
    except Exception:
        return pd.DataFrame(columns=["project_id", "project_name"])


def fetch_subtasks(work_item_id: int) -> pd.DataFrame:
    return safe_df(run_query("""
        SELECT subtask_id, title, status, due_date, sort_order
        FROM public.work_subtasks
        WHERE work_item_id = :wid
        ORDER BY sort_order ASC, (due_date IS NULL) ASC, due_date ASC, subtask_id ASC
    """, {"wid": int(work_item_id)}))


def fetch_notes(work_item_id: int) -> pd.DataFrame:
    return safe_df(run_query("""
        SELECT note_id, author_id, note_text, visibility, created_at
        FROM public.work_notes
        WHERE work_item_id = :wid
          AND (visibility = 'shared' OR (visibility = 'private' AND author_id = :uid))
        ORDER BY created_at DESC
    """, {"wid": int(work_item_id), "uid": user_id}))


# ============================================================
# MUTATIONS
# ============================================================
def update_work_item_status(work_item_id: int, item_type: str, source_id: int, new_status: str):
    new_status = (new_status or "open").lower().strip()

    # normalise legacy
    if new_status == "completed":
        new_status = "closed"

    if new_status not in STATUS_OPTIONS:
        st.error("❌ Invalid status.")
        return

    run_execute(
        "UPDATE public.work_items SET status = :s, updated_at = NOW() WHERE work_item_id = :wid",
        {"s": new_status, "wid": int(work_item_id)},
    )

    try:
        src = to_source_status(item_type, new_status)
        if item_type == "action":
            run_execute(
                "UPDATE public.actions SET status = :s, updated_at = NOW() WHERE action_id = :sid",
                {"s": src, "sid": int(source_id)},
            )
        elif item_type == "raid":
            run_execute(
                "UPDATE public.raids SET status = :s, updated_at = NOW() WHERE raid_id = :sid",
                {"s": src, "sid": int(source_id)},
            )
    except Exception:
        pass



def update_subtask_status(subtask_id: int, new_status: str):
    new_status = (new_status or "open").lower().strip()
    if new_status not in STATUS_OPTIONS:
        return
    run_execute(
        "UPDATE public.work_subtasks SET status = :s, updated_at = NOW() WHERE subtask_id = :sid",
        {"s": new_status, "sid": int(subtask_id)},
    )


def add_subtask(work_item_id: int, title: str, due_date: dt.date | None):
    title = (title or "").strip()
    if not title:
        st.warning("⚠️ Subtask title is required.")
        return
    run_execute("""
        INSERT INTO public.work_subtasks
            (work_item_id, title, status, due_date, sort_order, created_by, created_at, updated_at)
        VALUES (:wid, :t, 'open', :d, 0, :uid, NOW(), NOW())
    """, {"wid": int(work_item_id), "t": title, "d": due_date, "uid": user_id})


def add_note(work_item_id: int, note_text: str, visibility: str):
    note_text = (note_text or "").strip()
    visibility = (visibility or "private").lower().strip()
    if not note_text:
        st.warning("⚠️ Note text is required.")
        return
    if visibility not in ("private", "shared"):
        st.error("❌ Invalid visibility.")
        return
    run_execute("""
        INSERT INTO public.work_notes
            (work_item_id, author_id, note_text, visibility, created_at, updated_at)
        VALUES (:wid, :uid, :txt, :vis, NOW(), NOW())
    """, {"wid": int(work_item_id), "uid": user_id, "txt": note_text, "vis": visibility})


# ============================================================
# IMPROVED WORK ITEM RENDERER
# ============================================================
def render_work_item_in_expander(row, key_prefix: str):
    wid = int(row["work_item_id"])
    item_type = str(row["item_type"])
    source_id = int(row["source_id"])
    title = str(row["title"])
    status = (row.get("status") or "open").lower()
    priority = (row.get("priority") or "medium").lower()
    due = safe_date(row.get("due_date"))
    description = (row.get("description") or "").strip()
    comments = (row.get("comments") or "").strip()

    is_overdue = due and due < TODAY and status not in ("completed", "closed")

    # Build expander title
    status_icon = {
        "open": "⬜",
        "in_progress": "🔄",
        "blocked": "🚫",
        "closed": "🔒"
    }.get(status, "⬜")

    priority_icon = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢"
    }.get(priority, "🟡")

    type_emoji = {
        "action": "⚡",
        "raid": "⚠️",
        "task": "📋"
    }.get(item_type, "📋")

    due_text = f" · {fmt_date(due)}" if due else ""

    expander_title = f"{status_icon} {priority_icon} {type_emoji} **{title}**{due_text}"

    with st.expander(expander_title, expanded=False):
        # Badges and metadata
        badges_html = f"""
        <div class="wi-badges">
            {badge(status.replace("_", " ").title(), f"b-{status}")}
            {badge(item_type.upper(), f"b-{item_type}")}
            {badge(priority.upper(), f"b-{priority.replace('_', ' ')}")}
            {badge("OVERDUE", "b-overdue") if is_overdue else ""}
        </div>
        """
        st.markdown(badges_html, unsafe_allow_html=True)

        # Description
        if description:
            st.markdown(f'<div class="wi-desc">📄 {description}</div>', unsafe_allow_html=True)
        if comments:
            st.markdown(f'<div class="wi-desc">💬 {comments}</div>', unsafe_allow_html=True)

        # Quick actions
        st.markdown("<div class='wi-section-title'>⚡ Quick Actions</div>", unsafe_allow_html=True)

        qa1, qa2, qa3, qa4 = st.columns(4)

        with qa1:
            if st.button("🔒 Close Task", key=f"{key_prefix}_close_{wid}", use_container_width=True):
                update_work_item_status(wid, item_type, source_id, "closed")
                st.toast("🔒 Marked closed!")
                st.rerun()

        with qa2:
            if st.button("🔄 In Progress", key=f"{key_prefix}_progress_{wid}", use_container_width=True):
                update_work_item_status(wid, item_type, source_id, "in_progress")
                st.toast("🔄 Marked in progress!")
                st.rerun()

        with qa3:
            if st.button("🚫 Block", key=f"{key_prefix}_block_{wid}", use_container_width=True):
                update_work_item_status(wid, item_type, source_id, "blocked")
                st.toast("🚫 Marked blocked!")
                st.rerun()

        with qa4:
            new_status = st.selectbox(
                "Change status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                key=f"{key_prefix}_status_{wid}",
            )

        if new_status != status:
            if st.button("💾 Save Status", key=f"{key_prefix}_save_{wid}"):
                update_work_item_status(wid, item_type, source_id, new_status)
                st.toast("💾 Status updated!")
                st.rerun()

        # Subtasks section
        st.markdown("<div class='wi-section'><div class='wi-section-title'>🔸 Subtasks</div></div>",
                    unsafe_allow_html=True)

        sub_df = fetch_subtasks(wid)

        if not sub_df.empty:
            for _, sr in sub_df.iterrows():
                sid = int(sr["subtask_id"])
                stt = (sr.get("status") or "open").lower()
                s_title = sr.get("title", "")
                s_due = safe_date(sr.get("due_date"))

                icon = "🔒" if stt == "closed" else ("🚫" if stt == "blocked" else "⬜")

                sc1, sc2 = st.columns([3, 1])
                with sc1:
                    due_str = f" · {fmt_date(s_due)}" if s_due else ""
                    st.markdown(f"{icon} **{s_title}**{due_str}")
                with sc2:
                    new_s = st.selectbox(
                        "Status",
                        STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(stt) if stt in STATUS_OPTIONS else 0,
                        key=f"{key_prefix}_sub_st_{sid}",
                        label_visibility="collapsed"
                    )
                    if new_s != stt:
                        if st.button("Save", key=f"{key_prefix}_sub_sv_{sid}", use_container_width=True):
                            update_subtask_status(sid, new_s)
                            st.toast("✅ Subtask updated!")
                            st.rerun()
        else:
            st.caption("No subtasks yet")

        # Add subtask
        st.markdown("**➕ Add Subtask**")
        nc1, nc2, nc3 = st.columns([2, 1.5, 1])
        with nc1:
            new_title = st.text_input(
                "Title",
                placeholder="Subtask title",
                key=f"{key_prefix}_sub_t_{wid}",
                label_visibility="collapsed"
            )
        with nc2:
            new_due = safe_date(st.date_input(
                "Due date",
                value=None,
                key=f"{key_prefix}_sub_d_{wid}",
                label_visibility="collapsed"
            ))
        with nc3:
            if st.button("Add", key=f"{key_prefix}_sub_add_{wid}", use_container_width=True):
                add_subtask(wid, new_title, new_due)
                st.toast("✅ Subtask added!")
                st.rerun()

        # Notes section
        st.markdown("<div class='wi-section'><div class='wi-section-title'>📝 Notes</div></div>", unsafe_allow_html=True)

        notes_df = fetch_notes(wid)

        if not notes_df.empty:
            for _, nr in notes_df.iterrows():
                vis = (nr.get("visibility") or "private").lower()
                txt = (nr.get("note_text") or "").strip()
                icon = "🔒" if vis == "private" else "👥"
                try:
                    ts = pd.to_datetime(nr.get("created_at")).strftime("%d %b %Y, %H:%M")
                except Exception:
                    ts = ""

                st.markdown(f"""
                <div class="note-card {vis}">
                    {icon} {txt}
                    <div class="note-meta">{ts} · {vis.title()}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No notes yet")

        # Add note
        st.markdown("**➕ Add Note**")
        nv1, nv2 = st.columns([3, 1])
        with nv1:
            note_text = st.text_area(
                "Note",
                height=80,
                placeholder="Add a note...",
                key=f"{key_prefix}_note_t_{wid}",
                label_visibility="collapsed"
            )
        with nv2:
            visibility = st.radio(
                "Visibility",
                ["private", "shared"],
                format_func=lambda x: "🔒 Private" if x == "private" else "👥 Shared",
                key=f"{key_prefix}_note_v_{wid}",
                label_visibility="collapsed"
            )
            if st.button("Add Note", key=f"{key_prefix}_note_add_{wid}", use_container_width=True):
                add_note(wid, note_text, visibility)
                st.toast("✅ Note added!")
                st.rerun()

# ============================================================
# METRICS DASHBOARD
# ============================================================
df_metrics = fetch_my_work(
    status_filter=["open", "in_progress", "blocked"],
    type_filter=TYPE_OPTIONS,
    only_assigned=True,
    include_completed=True,
)

active_count = blocked_count = overdue_count = due7_count = 0
if not df_metrics.empty:
    for _, rr in df_metrics.iterrows():
        stt = (rr.get("status") or "").lower()
        dd = safe_date(rr.get("due_date"))
        if stt in ("open", "in_progress"):
            active_count += 1
        if stt == "blocked":
            blocked_count += 1
        if dd and stt not in ("completed", "closed"):
            if dd < TODAY:
                overdue_count += 1
            elif dd <= TODAY + dt.timedelta(days=7):
                due7_count += 1

mc1, mc2, mc3, mc4 = st.columns(4)
with mc1:
    st.markdown(
        f"<div class='metric-tile'><div class='val val-blue'>{active_count}</div><div class='lbl'>Active Tasks</div></div>",
        unsafe_allow_html=True)
with mc2:
    st.markdown(
        f"<div class='metric-tile'><div class='val val-red'>{blocked_count}</div><div class='lbl'>Blocked</div></div>",
        unsafe_allow_html=True)
with mc3:
    st.markdown(
        f"<div class='metric-tile'><div class='val val-amber'>{overdue_count}</div><div class='lbl'>Overdue</div></div>",
        unsafe_allow_html=True)
with mc4:
    st.markdown(
        f"<div class='metric-tile'><div class='val val-green'>{due7_count}</div><div class='lbl'>Due Soon</div></div>",
        unsafe_allow_html=True)

# ============================================================
# ENHANCED FILTERS
# ============================================================
st.markdown("<div class='section-header'>🔍 Filters & Search</div>", unsafe_allow_html=True)

with st.container():
    st.markdown("<div class='filter-bar'>", unsafe_allow_html=True)

    # Row 1: Search and sync
    f_row1_c1, f_row1_c2 = st.columns([3, 1])

    with f_row1_c1:
        search_text = st.text_input(
            "🔍 Search tasks",
            placeholder="Search by title or description...",
            key="search_input",
            label_visibility="collapsed"
        )

    with f_row1_c2:
        if st.button("🔄 Sync Now", use_container_width=True, key="sync_btn"):
            try:
                sync_assigned_raids_and_actions()
                st.toast("✅ Synced successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Sync failed: {e}")

    # Row 2: Filters
    f_row2_c1, f_row2_c2, f_row2_c3, f_row2_c4 = st.columns(4)

    projects_df = fetch_projects_for_user()
    project_map = {"All Projects": None}
    if not projects_df.empty:
        for _, r in projects_df.iterrows():
            project_map[str(r["project_name"])] = int(r["project_id"])

    with f_row2_c1:
        project_choice = st.selectbox(
            "📁 Project",
            list(project_map.keys()),
            index=0,
            key="filter_project"
        )

    with f_row2_c2:
        type_choice = st.multiselect(
            "📋 Type",
            TYPE_OPTIONS,
            default=TYPE_OPTIONS,
            key="filter_type"
        )

    with f_row2_c3:
        status_choice = st.multiselect(
            "📊 Status",
            STATUS_OPTIONS,
            default=["open", "in_progress", "blocked"],
            key="filter_status"
        )

    with f_row2_c4:
        priority_choice = st.multiselect(
            "⚡ Priority",
            PRIORITY_OPTIONS,
            default=PRIORITY_OPTIONS,
            key="filter_priority"
        )

    # Row 3: Toggles
    f_row3_c1, f_row3_c2, f_row3_c3 = st.columns([1, 1, 2])

    with f_row3_c1:
        only_assigned = st.toggle("👤 My Tasks Only", value=True, key="filter_assigned")

    with f_row3_c2:
        show_completed = st.toggle("🔒 Show Closed", value=False, key="filter_completed")

    st.markdown("</div>", unsafe_allow_html=True)

selected_project_id = project_map.get(project_choice)

# ============================================================
# WORK ITEMS VIEW
# ============================================================
st.markdown("<div class='section-header'>📋 My Tasks</div>", unsafe_allow_html=True)

# Fetch filtered data
df_filtered = fetch_my_work(
    status_filter=status_choice if status_choice else None,
    type_filter=type_choice if type_choice else None,
    priority_filter=priority_choice if priority_choice else None,
    project_id=selected_project_id,
    search_text=search_text if search_text else None,
    only_assigned=only_assigned,
    include_completed=show_completed,
)

if df_filtered.empty:
    st.markdown("""
    <div class='empty-state'>
        <div class='empty-state-icon'>📭</div>
        <div class='empty-state-text'>No tasks found</div>
        <div class='empty-state-sub'>Try adjusting your filters or search criteria</div>
    </div>
    """, unsafe_allow_html=True)
else:
    # Show count
    st.caption(f"Showing **{len(df_filtered)}** task{'s' if len(df_filtered) != 1 else ''}")

    # Render each task in an expander
    for idx, row in df_filtered.iterrows():
        render_work_item_in_expander(row, key_prefix=f"task_{idx}")

# ============================================================
# FOOTER
# ============================================================
st.markdown("<div style='margin: 3rem 0 1.5rem 0;'></div>", unsafe_allow_html=True)
pmo_footer()