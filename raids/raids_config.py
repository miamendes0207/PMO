# ============================================================
# raids_config.py — ScopeSight v4 (Unified RAID Architecture)
# Central configuration for RAID definitions + branding colours
#
# FIXES vs v3:
# - RAIDS_CONFIG column definitions now include mitigation, scoring,
#   and dual-owner columns that match the actual DB schema
# - Added get_columns_for_project() — builds a dynamic column list
#   from a project's enabled_optional_fields + custom_fields so that
#   Excel exporters and governance pack builders respect the per-project
#   RAIDs designer configuration rather than a fixed static list
# - owner_col split into owner_plen_col / owner_client_col to match DB
# ============================================================

from __future__ import annotations
from typing import Any

# ------------------------------------------------------------
# BRAND COLOURS (used across tables, governance packs, slides)
# ------------------------------------------------------------
BRAND_COLOURS = {
    "header_blue":   "#002060",
    "header_red":    "#9E1B32",
    "header_green":  "#007A33",
    "header_orange": "#C65D00",
}

# ------------------------------------------------------------
# RAID TYPE DEFINITIONS (DB-aligned)
#
# These are the *full* possible column sets for each RAID type —
# every column that could appear given any combination of optional
# fields.  Consumers should NOT slice this directly; instead call
# get_columns_for_project() which filters to the enabled fields for
# a specific project.
#
# Column name  → DB field mapping is in COLUMN_TO_DB_FIELD below.
# ------------------------------------------------------------

RAIDS_CONFIG: dict[str, dict[str, Any]] = {
    "Risks": {
        "sheet_name":   "Risks",
        "type_value":   "Risk",          # matches raids.raid_type / raids.type
        # Full possible column list (order matters for display)
        "columns": [
            "Risk ID",
            "Title",
            "Description",
            "Classification",            # internal_external
            "Probability",               # optional
            "Severity",                  # optional
            "Risk Score",                # optional (computed: prob × sev)
            "Plenitude Owner",           # optional
            "Client Owner",              # optional
            "Status",
            "Mitigation Plan",           # always-on
            "Mitigation Status",         # always-on
            "Date Raised",               # optional
            "Planned Closure",           # optional
            "Next Review",               # optional
            "Date Closed",
            "Related Reference",         # optional
            "Comments",                  # optional
        ],
        # Field name aliases used in code
        "id_col":              "Risk ID",
        "title_col":           "Title",
        "text_col":            "Description",
        "classification_col":  "Classification",
        "probability_col":     "Probability",
        "severity_col":        "Severity",
        "score_col":           "Risk Score",
        "owner_plen_col":      "Plenitude Owner",
        "owner_client_col":    "Client Owner",
        "status_col":          "Status",
        "mitigation_col":      "Mitigation Plan",
        "mitigation_status_col":"Mitigation Status",
        "date_raised_col":     "Date Raised",
        "date_target_col":     "Planned Closure",
        "next_review_col":     "Next Review",
        "date_closed_col":     "Date Closed",
        "related_col":         "Related Reference",
        "comments_col":        "Comments",
    },

    "Assumptions": {
        "sheet_name":   "Assumptions",
        "type_value":   "Assumption",
        "columns": [
            "Assumption ID",
            "Title",
            "Description",
            "Classification",
            "Plenitude Owner",
            "Client Owner",
            "Status",
            "Mitigation Plan",
            "Mitigation Status",
            "Date Raised",
            "Planned Closure",
            "Next Review",
            "Date Closed",
            "Related Reference",
            "Comments",
        ],
        "id_col":              "Assumption ID",
        "title_col":           "Title",
        "text_col":            "Description",
        "classification_col":  "Classification",
        "owner_plen_col":      "Plenitude Owner",
        "owner_client_col":    "Client Owner",
        "status_col":          "Status",
        "mitigation_col":      "Mitigation Plan",
        "mitigation_status_col":"Mitigation Status",
        "date_raised_col":     "Date Raised",
        "date_target_col":     "Planned Closure",
        "next_review_col":     "Next Review",
        "date_closed_col":     "Date Closed",
        "related_col":         "Related Reference",
        "comments_col":        "Comments",
    },

    "Issues": {
        "sheet_name":   "Issues",
        "type_value":   "Issue",
        "columns": [
            "Issue ID",
            "Title",
            "Description",
            "Classification",
            "Plenitude Owner",
            "Client Owner",
            "Status",
            "Mitigation Plan",
            "Mitigation Status",
            "Date Raised",
            "Planned Closure",
            "Next Review",
            "Date Closed",
            "Related Reference",
            "Comments",
        ],
        "id_col":              "Issue ID",
        "title_col":           "Title",
        "text_col":            "Description",
        "classification_col":  "Classification",
        "owner_plen_col":      "Plenitude Owner",
        "owner_client_col":    "Client Owner",
        "status_col":          "Status",
        "mitigation_col":      "Mitigation Plan",
        "mitigation_status_col":"Mitigation Status",
        "date_raised_col":     "Date Raised",
        "date_target_col":     "Planned Closure",
        "next_review_col":     "Next Review",
        "date_closed_col":     "Date Closed",
        "related_col":         "Related Reference",
        "comments_col":        "Comments",
    },

    "Dependencies": {
        "sheet_name":   "Dependencies",
        "type_value":   "Dependency",
        "columns": [
            "Dependency ID",
            "Title",
            "Description",
            "Classification",
            "Plenitude Owner",
            "Client Owner",
            "Status",
            "Mitigation Plan",
            "Mitigation Status",
            "Date Raised",
            "Target Date",
            "Next Review",
            "Date Closed",
            "Related Reference",
            "Comments",
        ],
        "id_col":              "Dependency ID",
        "title_col":           "Title",
        "text_col":            "Description",
        "classification_col":  "Classification",
        "owner_plen_col":      "Plenitude Owner",
        "owner_client_col":    "Client Owner",
        "status_col":          "Status",
        "mitigation_col":      "Mitigation Plan",
        "mitigation_status_col":"Mitigation Status",
        "date_raised_col":     "Date Raised",
        "date_target_col":     "Target Date",
        "next_review_col":     "Next Review",
        "date_closed_col":     "Date Closed",
        "related_col":         "Related Reference",
        "comments_col":        "Comments",
    },
}


# ------------------------------------------------------------
# DB FIELD → DISPLAY COLUMN NAME  (used by dynamic builder)
# Maps enabled_optional_fields keys → the column label string
# used in RAIDS_CONFIG so we can filter the full column list.
# ------------------------------------------------------------
_DB_FIELD_TO_COLUMN: dict[str, str] = {
    "probability":       "Probability",
    "severity":          "Severity",
    # score is derived; include it whenever both prob + sev are enabled
    "owner_plen":        "Plenitude Owner",
    "owner_client":      "Client Owner",
    "mitigation_plan":   "Mitigation Plan",
    "mitigation_status": "Mitigation Status",
    "date_raised":       "Date Raised",
    "planned_close":     "Planned Closure",
    "next_review":       "Next Review",
    "related_issue":     "Related Reference",
    "comments":          "Comments",
    # classification and date_closed are always shown
}

# Columns always shown regardless of optional config
_ALWAYS_ON_COLUMNS = {
    "Classification",
    "Status",
    "Date Closed",
    "Mitigation Plan",
    "Mitigation Status",
}


# ------------------------------------------------------------
# DISPLAY COLUMN → DB FIELD  (inverse map for data binding)
# ------------------------------------------------------------
COLUMN_TO_DB_FIELD: dict[str, str] = {
    # IDs / core
    "Risk ID":          "raid_id",
    "Assumption ID":    "raid_id",
    "Issue ID":         "raid_id",
    "Dependency ID":    "raid_id",
    "Title":            "title",
    "Description":      "description",
    "Classification":   "internal_external",
    # Scoring
    "Probability":      "probability",
    "Severity":         "severity",
    "Risk Score":       "revised_score",
    # Owners
    "Plenitude Owner":  "owner_plen",
    "Client Owner":     "owner_client",
    # Status + mitigation
    "Status":           "status",
    "Mitigation Plan":  "mitigation_plan",
    "Mitigation Status":"mitigation_status",
    # Dates
    "Date Raised":      "date_raised",
    "Planned Closure":  "planned_close",
    "Target Date":      "planned_close",
    "Next Review":      "next_review",
    "Date Closed":      "date_closed",
    # Other
    "Related Reference":"related_issue",
    "Comments":         "comments",
}


# ------------------------------------------------------------
# PUBLIC API
# ------------------------------------------------------------

def get_columns_for_project(
    raid_type_key: str,
    enabled_optional: set[str],
    custom_fields: list[dict] | None = None,
) -> list[str]:
    """
    Returns the ordered display column list for a specific RAID type,
    filtered to the fields enabled for this project.

    Parameters
    ----------
    raid_type_key : str
        One of "Risks", "Assumptions", "Issues", "Dependencies"
    enabled_optional : set[str]
        The set of enabled_optional_fields from the project's raids_config
        (e.g. {"probability", "severity", "owner_plen", "mitigation_plan", ...})
    custom_fields : list[dict] | None
        The project's custom_fields list; each dict has at least "label".

    Returns
    -------
    list[str]
        Ordered column name list ready for use in DataFrame / Excel / PPTX.
    """
    cfg = RAIDS_CONFIG.get(raid_type_key)
    if not cfg:
        return []

    full_columns = cfg["columns"]

    # Columns to include: always-on + those whose DB field is enabled
    enabled_display = set(_ALWAYS_ON_COLUMNS)
    for db_field, display_col in _DB_FIELD_TO_COLUMN.items():
        if db_field in enabled_optional:
            enabled_display.add(display_col)

    # Include "Risk Score" only when both probability AND severity are enabled
    # (it's a derived column, not a separate DB field)
    if "probability" in enabled_optional and "severity" in enabled_optional:
        enabled_display.add("Risk Score")
    else:
        enabled_display.discard("Risk Score")

    # Filter full list while preserving order
    id_col = cfg["id_col"]
    title_col = cfg["title_col"]
    text_col = cfg["text_col"]

    result = []
    for col in full_columns:
        # ID, Title, Description are always included
        if col in (id_col, title_col, text_col):
            result.append(col)
        elif col in enabled_display:
            result.append(col)

    # Append custom field labels at the end
    for cf in (custom_fields or []):
        label = (cf.get("label") or "").strip()
        if label:
            result.append(label)

    return result


def get_db_fields_for_project(
    raid_type_key: str,
    enabled_optional: set[str],
    custom_fields: list[dict] | None = None,
) -> list[tuple[str, str]]:
    """
    Returns a list of (display_column_name, db_field_name) tuples for
    the enabled columns of a project, in display order.

    Custom fields use their key as the db_field_name (stored in
    the raids.custom_fields JSONB column).
    """
    display_cols = get_columns_for_project(raid_type_key, enabled_optional, custom_fields)

    result = []
    for col in display_cols:
        db_field = COLUMN_TO_DB_FIELD.get(col)
        if db_field:
            result.append((col, db_field))
        else:
            # Could be a custom field label
            for cf in (custom_fields or []):
                if (cf.get("label") or "").strip() == col:
                    result.append((col, f"custom:{cf.get('key', col)}"))
                    break

    return result