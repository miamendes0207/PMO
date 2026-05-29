# ============================================================
# modules/project_health.py
# Minimal RAG calculation + snapshot + effective RAG getter
# (Aligned to your schema + psycopg2 param style)
#
# INPUT TABLES:
#   - public.actions (project_id, status, due_date, ...)
#   - public.raids   (project_id, raid_type/type, status, planned_close, next_review, ...)
#
# OUTPUT TABLES (you already created):
#   - public.project_rag_snapshot
#   - public.project_rag_override
# ============================================================

import json

CLOSED_STATUSES_SQL = "('closed','done','complete','completed','resolved')"


def _safe_count(df, col="n") -> int:
    if df is None or getattr(df, "empty", True):
        return 0
    try:
        return int(df.iloc[0][col])
    except Exception:
        return 0


def _rag_from_score(score: int) -> str:
    # Simple thresholds (tweak anytime)
    if score >= 8:
        return "red"
    if score >= 4:
        return "amber"
    return "green"


def _fetch_action_counts(project_id: int, run_query) -> dict:
    overdue = run_query(
        f"""
        SELECT COUNT(*) AS n
        FROM public.actions
        WHERE project_id = %(pid)s
          AND COALESCE(LOWER(status),'open') NOT IN {CLOSED_STATUSES_SQL}
          AND due_date IS NOT NULL
          AND due_date < CURRENT_DATE
        """,
        {"pid": project_id},
    )

    upcoming_7d = run_query(
        f"""
        SELECT COUNT(*) AS n
        FROM public.actions
        WHERE project_id = %(pid)s
          AND COALESCE(LOWER(status),'open') NOT IN {CLOSED_STATUSES_SQL}
          AND due_date IS NOT NULL
          AND due_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '7 days')
        """,
        {"pid": project_id},
    )

    return {
        "overdue_actions": _safe_count(overdue),
        "upcoming_actions_7d": _safe_count(upcoming_7d),
    }


def _fetch_raid_overdue_counts(project_id: int, run_query) -> dict:
    # planned_close is your main "due" date; fallback to next_review
    overdue_issues = run_query(
        f"""
        SELECT COUNT(*) AS n
        FROM public.raids
        WHERE project_id = %(pid)s
          AND LOWER(COALESCE(raid_type, type, '')) = 'issue'
          AND COALESCE(LOWER(status),'open') NOT IN {CLOSED_STATUSES_SQL}
          AND COALESCE(planned_close, next_review) IS NOT NULL
          AND COALESCE(planned_close, next_review) < CURRENT_DATE
        """,
        {"pid": project_id},
    )

    overdue_risks = run_query(
        f"""
        SELECT COUNT(*) AS n
        FROM public.raids
        WHERE project_id = %(pid)s
          AND LOWER(COALESCE(raid_type, type, '')) = 'risk'
          AND COALESCE(LOWER(status),'open') NOT IN {CLOSED_STATUSES_SQL}
          AND COALESCE(planned_close, next_review) IS NOT NULL
          AND COALESCE(planned_close, next_review) < CURRENT_DATE
        """,
        {"pid": project_id},
    )

    return {
        "overdue_issues": _safe_count(overdue_issues),
        "overdue_risks": _safe_count(overdue_risks),
    }


def calculate_project_rag_details(project_id: int, run_query) -> dict:
    """
    Calculates score and rag based on existing actions/raids in DB.
    """
    a = _fetch_action_counts(project_id, run_query)
    r = _fetch_raid_overdue_counts(project_id, run_query)

    # Simple weighted score (tweak whenever)
    score = (
        a["overdue_actions"] * 1
        + a["upcoming_actions_7d"] * 1
        + r["overdue_issues"] * 3
        + r["overdue_risks"] * 2
    )

    rag = _rag_from_score(score)

    drivers = {
        "overdue_actions": a["overdue_actions"],
        "upcoming_actions_7d": a["upcoming_actions_7d"],
        "overdue_issues": r["overdue_issues"],
        "overdue_risks": r["overdue_risks"],
        "score": int(score),
    }

    return {"overall_rag": rag, "overall_score": int(score), "drivers": drivers}


def compute_and_snapshot(
    project_id: int,
    run_query,
    run_execute,
    *,
    computed_by: str = "system",
    only_if_changed: bool = True,
) -> dict:
    """
    Writes a snapshot row into public.project_rag_snapshot.
    """
    details = calculate_project_rag_details(project_id, run_query)

    if only_if_changed:
        prev = run_query(
            """
            SELECT overall_rag, overall_score
            FROM public.project_rag_snapshot
            WHERE project_id = %(pid)s
            ORDER BY as_of DESC
            LIMIT 1
            """,
            {"pid": project_id},
        )
        if prev is not None and not prev.empty:
            try:
                prev_rag = str(prev.iloc[0].get("overall_rag") or "")
                prev_score = int(prev.iloc[0].get("overall_score") or 0)
                if prev_rag == details["overall_rag"] and prev_score == details["overall_score"]:
                    return details
            except Exception:
                pass

    run_execute(
        """
        INSERT INTO public.project_rag_snapshot
            (project_id, overall_rag, overall_score, drivers_json, computed_by)
        VALUES
            (%(pid)s, %(rag)s, %(score)s, %(drivers)s::jsonb, %(by)s)
        """,
        {
            "pid": project_id,
            "rag": details["overall_rag"],
            "score": details["overall_score"],
            "drivers": json.dumps(details["drivers"]),
            "by": computed_by,
        },
    )

    return details


def get_effective_project_rag(project_id: int, run_query) -> dict:
    """
    Effective RAG = active override (if any) else latest snapshot.
    """
    df = run_query(
        """
        WITH ov AS (
          SELECT override_rag, override_reason, set_by, set_at, expires_at
          FROM public.project_rag_override
          WHERE project_id = %(pid)s
            AND is_active = TRUE
            AND (expires_at IS NULL OR expires_at > now())
          LIMIT 1
        ),
        sn AS (
          SELECT overall_rag, overall_score, as_of, drivers_json
          FROM public.project_rag_snapshot
          WHERE project_id = %(pid)s
          ORDER BY as_of DESC
          LIMIT 1
        )
        SELECT
          COALESCE(ov.override_rag, sn.overall_rag, 'green') AS effective_rag,
          COALESCE(sn.overall_score, 0) AS overall_score,
          sn.as_of,
          sn.drivers_json,
          (ov.override_rag IS NOT NULL) AS is_overridden,
          ov.override_reason,
          ov.set_by,
          ov.set_at,
          ov.expires_at
        FROM sn
        LEFT JOIN ov ON TRUE
        """,
        {"pid": project_id},
    )

    if df is None or df.empty:
        return {"effective_rag": "green", "overall_score": 0, "is_overridden": False}

    return df.iloc[0].to_dict()