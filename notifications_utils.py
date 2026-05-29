# ============================================================
# modules/notifications_utils.py — ScopeSight v3.4
# Central Notification Utility (In-App)
# ============================================================

from __future__ import annotations

import datetime as dt
from typing import Optional

from modules.db import run_query, run_execute


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def _norm_email(email: str | None) -> str | None:
    """Normalise email for safe storage / comparison."""
    if not email:
        return None
    return email.strip().lower()


def _valid_severity(sev: str | None) -> str:
    """Ensure severity is valid."""
    if not sev:
        return "info"

    s = sev.lower().strip()
    if s not in ("info", "warning", "critical"):
        return "info"
    return s


# ------------------------------------------------------------
# CORE: SEND NOTIFICATION
# ------------------------------------------------------------

def send_notification(
    recipient_email: str,
    title: str,
    message: str,
    severity: str = "info",
    project_id: Optional[int] = None,
    client_id: Optional[int] = None,
    created_by: Optional[str] = None,
    dedupe_minutes: Optional[int] = None,
) -> bool:
    """
    Create an in-app notification.

    Parameters
    ----------
    recipient_email : str
    title : str
    message : str
    severity : str ('info', 'warning', 'critical')
    project_id : Optional[int]
    client_id : Optional[int]
    created_by : Optional[str]
    dedupe_minutes : Optional[int]
        If provided, prevents duplicate notifications
        with same title+recipient within this window.
    """

    try:
        recipient_email = _norm_email(recipient_email)
        created_by = _norm_email(created_by)
        severity = _valid_severity(severity)

        if not recipient_email or not title:
            return False

        # -----------------------------------------------------
        # Optional de-duplication
        # -----------------------------------------------------
        if dedupe_minutes:
            cutoff = dt.datetime.utcnow() - dt.timedelta(minutes=dedupe_minutes)

            existing = run_query(
                """
                SELECT id
                FROM inapp_notifications
                WHERE LOWER(recipient_email) = :email
                  AND LOWER(title) = LOWER(:title)
                  AND created_at >= :cutoff
                  AND dismissed_at IS NULL
                LIMIT 1
                """,
                {
                    "email": recipient_email,
                    "title": title,
                    "cutoff": cutoff,
                },
            )

            if existing is not None and not existing.empty:
                return False  # skip duplicate

        # -----------------------------------------------------
        # Insert notification
        # -----------------------------------------------------
        run_execute(
            """
            INSERT INTO inapp_notifications (
                recipient_email,
                title,
                message,
                severity,
                project_id,
                client_id,
                created_by,
                created_at
            )
            VALUES (
                :recipient_email,
                :title,
                :message,
                :severity,
                :project_id,
                :client_id,
                :created_by,
                NOW()
            )
            """,
            {
                "recipient_email": recipient_email,
                "title": title.strip(),
                "message": message.strip(),
                "severity": severity,
                "project_id": project_id,
                "client_id": client_id,
                "created_by": created_by,
            },
        )

        return True

    except Exception as e:
        print(f"⚠ Notification error: {e}")
        return False


# ------------------------------------------------------------
# FETCH NOTIFICATIONS
# ------------------------------------------------------------

def get_inapp_notifications(
    user_email: str,
    limit: int = 10,
):
    """
    Fetch active (non-dismissed) notifications for a user.
    """

    user_email = _norm_email(user_email)
    if not user_email:
        return None

    return run_query(
        """
        SELECT
            id,
            title,
            message,
            severity,
            project_id,
            client_id,
            created_by,
            created_at
        FROM inapp_notifications
        WHERE LOWER(recipient_email) = :email
          AND dismissed_at IS NULL
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {
            "email": user_email,
            "limit": limit,
        },
    )


# ------------------------------------------------------------
# DISMISS NOTIFICATION
# ------------------------------------------------------------

def dismiss_notification(notification_id: int) -> bool:
    """Soft dismiss a notification."""

    try:
        run_execute(
            """
            UPDATE inapp_notifications
            SET dismissed_at = NOW()
            WHERE id = :nid
            """,
            {"nid": notification_id},
        )
        return True
    except Exception as e:
        print(f"⚠ Dismiss error: {e}")
        return False


# ------------------------------------------------------------
# ADMIN / CLEANUP (Optional)
# ------------------------------------------------------------

def clear_old_notifications(days_old: int = 30) -> int:
    """
    Permanently delete dismissed notifications older than X days.
    Useful for housekeeping.
    """

    try:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=days_old)

        result = run_execute(
            """
            DELETE FROM inapp_notifications
            WHERE dismissed_at IS NOT NULL
              AND dismissed_at < :cutoff
            """,
            {"cutoff": cutoff},
        )

        return result or 0

    except Exception as e:
        print(f"⚠ Cleanup error: {e}")
        return 0
