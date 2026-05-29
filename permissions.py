# ============================================================
# modules/permissions.py — ScopeSight
# Helpers for user/client/project membership lookups
# ============================================================

from __future__ import annotations
from modules.db import run_query


def _get_users_columns() -> set[str]:
    df = run_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
        ORDER BY column_name
        """
    )
    if df is None or df.empty:
        return set()
    return set(df["column_name"].astype(str).tolist())


def _pick_first(existing: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in existing:
            return c
    return None


def get_project_member_emails(project_id: int) -> list[dict]:
    """
    Returns:
      [{"user_email": "...", "display_name": "..."}]

    Uses user_project_permissions (user_id, project_id) and joins to users.
    Detects whether users table uses 'user_email' or 'email' (etc).
    """
    if not project_id:
        return []

    cols = _get_users_columns()

    # Common variants we've seen in your codebase
    email_col = _pick_first(cols, ["user_email", "email"])
    name_col = _pick_first(cols, ["full_name", "name", "display_name"])

    if not email_col:
        # Can't build a meaningful dropdown without an email field
        return []

    # Build display_name expression safely
    if name_col:
        display_expr = f"COALESCE(u.{name_col}, u.{email_col})"
        order_expr = display_expr
    else:
        display_expr = f"u.{email_col}"
        order_expr = f"u.{email_col}"

    sql = f"""
        SELECT
            u.{email_col} AS user_email,
            {display_expr} AS display_name
        FROM public.user_project_permissions upp
        JOIN public.users u
          ON u.user_id = upp.user_id
        WHERE upp.project_id = :pid
        ORDER BY {order_expr}
    """

    df = run_query(sql, {"pid": int(project_id)})
    if df is None or df.empty:
        return []

    # normalize to expected keys
    out = df.to_dict(orient="records")
    # ensure strings + lower emails
    for r in out:
        if r.get("user_email"):
            r["user_email"] = str(r["user_email"]).strip().lower()
        if r.get("display_name"):
            r["display_name"] = str(r["display_name"]).strip()
    return out


def get_client_member_emails(client_id: int) -> list[dict]:
    """
    Fallback list:
      [{"user_email": "...", "display_name": "..."}]

    Uses user_client_permissions (user_id, client_id) join users.
    """
    if not client_id:
        return []

    cols = _get_users_columns()
    email_col = _pick_first(cols, ["user_email", "email"])
    name_col = _pick_first(cols, ["full_name", "name", "display_name"])

    if not email_col:
        return []

    if name_col:
        display_expr = f"COALESCE(u.{name_col}, u.{email_col})"
        order_expr = display_expr
    else:
        display_expr = f"u.{email_col}"
        order_expr = f"u.{email_col}"

    sql = f"""
        SELECT
            u.{email_col} AS user_email,
            {display_expr} AS display_name
        FROM public.user_client_permissions ucp
        JOIN public.users u
          ON u.user_id = ucp.user_id
        WHERE ucp.client_id = :cid
        ORDER BY {order_expr}
    """

    df = run_query(sql, {"cid": int(client_id)})
    if df is None or df.empty:
        return []

    out = df.to_dict(orient="records")
    for r in out:
        if r.get("user_email"):
            r["user_email"] = str(r["user_email"]).strip().lower()
        if r.get("display_name"):
            r["display_name"] = str(r["display_name"]).strip()
    return out
