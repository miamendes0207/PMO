# ============================================================
# modules/notifications_config.py — ScopeSight v5
# Canonical Notification Event Registry
# ============================================================

"""
Single source of truth for notification event types across ScopeSight.

Use this module for:
- Notifications Preferences UI (what users can toggle)
- emit_event() validation (prevent typos / drift)
- Consistent reporting & audit of notification history

Design notes:
- event_type values are stable identifiers (do not rename casually)
- display labels can change without breaking data
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# Group name -> list of (event_type, display_label)
EVENT_TYPES: Dict[str, List[Tuple[str, str]]] = {
    # --------------------------------------------------------
    # RAID
    # --------------------------------------------------------
    "RAID updates": [
        ("raid.created", "RAID added"),
        ("raid.updated", "RAID edited"),
        ("raid.closed", "RAID closed"),
        ("raid.reopened", "RAID reopened"),
    ],

    # --------------------------------------------------------
    # Actions
    # --------------------------------------------------------
    "Action updates": [
        ("action.created", "Action added"),
        ("action.updated", "Action edited"),
        ("action.closed", "Action closed"),
        ("action.reopened", "Action reopened"),
    ],

    # --------------------------------------------------------
    # Templates / Governance Packs / Content
    # --------------------------------------------------------
    "Templates": [
        ("template.created", "Template added"),
        ("template.updated", "Template edited"),
        ("template.deleted", "Template removed"),
    ],

    # --------------------------------------------------------
    # NFR / Meeting Intelligence
    # --------------------------------------------------------
    "NFR": [
        ("nfr.generated", "NFR generated"),
        ("nfr.updated", "NFR updated"),
    ],

    # --------------------------------------------------------
    # "My Work" (personal worklist items, tasks, focus items)
    # --------------------------------------------------------
    "My Work": [
        ("mywork.created", "My work item added"),
        ("mywork.updated", "My work item edited"),
        ("mywork.closed", "My work item closed"),
        ("mywork.reopened", "My work item reopened"),
    ],

    # --------------------------------------------------------
    # Access / Config / Governance Requests
    # --------------------------------------------------------
    "Requests": [
        ("access_request.created", "Access request submitted"),
        ("access_request.status_changed", "Access request status changed"),
        ("project_config.created", "Project config request submitted"),
        ("project_config.status_changed", "Project config request status changed"),
    ],

    # --------------------------------------------------------
    # Allocations / Assignments
    # --------------------------------------------------------
    "Allocations": [
        ("allocation.created", "New project allocation"),
        ("allocation.removed", "Project allocation removed"),
        ("allocation.updated", "Project allocation updated"),
    ],

    # --------------------------------------------------------
    # System / Audit / Admin (optional but useful)
    # --------------------------------------------------------
    "System": [
        ("project.created", "New project created"),
        ("project.updated", "Project updated"),
        ("project.status_changed", "Project status changed"),
    ],

    # --------------------------------------------------------
    # Time-driven reminders (overdue / due soon)
    # --------------------------------------------------------
    "Reminders": [
        ("raid.due_soon", "RAID due soon"),
        ("raid.overdue", "RAID overdue"),
        ("action.due_soon", "Action due soon"),
        ("action.overdue", "Action overdue"),
        ("deadline.due_soon", "Deadline due soon"),
        ("deadline.overdue", "Deadline overdue"),
    ],
}

# Flattened list of valid event_type keys
ALL_EVENT_TYPES: List[str] = [
    event_type
    for group_items in EVENT_TYPES.values()
    for (event_type, _label) in group_items
]

# Reverse lookup: event_type -> display label (handy for rendering)
EVENT_LABELS: Dict[str, str] = {
    event_type: label
    for group_items in EVENT_TYPES.values()
    for (event_type, label) in group_items
}

# Optional: severity defaults (used if emit_event doesn't specify)
# info | warning | critical
EVENT_SEVERITY_DEFAULTS: Dict[str, str] = {
    # RAID
    "raid.created": "info",
    "raid.updated": "info",
    "raid.closed": "info",
    "raid.reopened": "warning",

    # Actions
    "action.created": "info",
    "action.updated": "info",
    "action.closed": "info",
    "action.reopened": "warning",

    # Templates
    "template.created": "info",
    "template.updated": "info",
    "template.deleted": "warning",

    # NFR
    "nfr.generated": "info",
    "nfr.updated": "info",

    # My Work
    "mywork.created": "info",
    "mywork.updated": "info",
    "mywork.closed": "info",
    "mywork.reopened": "warning",

    # Requests
    "access_request.created": "info",
    "access_request.status_changed": "warning",
    "project_config.created": "info",
    "project_config.status_changed": "warning",

    # Allocations
    "allocation.created": "warning",
    "allocation.removed": "warning",
    "allocation.updated": "info",

    # System
    "project.created": "info",
    "project.updated": "info",
    "project.status_changed": "warning",

    # Reminders
    "raid.due_soon": "warning",
    "raid.overdue": "critical",
    "action.due_soon": "warning",
    "action.overdue": "critical",
    "deadline.due_soon": "warning",
    "deadline.overdue": "critical",
}

# Optional: categories for filtering / UI tagging (not required)
EVENT_CATEGORY: Dict[str, str] = {}
for group_name, group_items in EVENT_TYPES.items():
    for (event_type, _label) in group_items:
        EVENT_CATEGORY[event_type] = group_name


def is_valid_event_type(event_type: str) -> bool:
    """Quick validator to avoid typos when emitting events."""
    return event_type in EVENT_LABELS


def get_label(event_type: str) -> str:
    """Safe label lookup (falls back to event_type if not registered)."""
    return EVENT_LABELS.get(event_type, event_type)


def get_default_severity(event_type: str) -> str:
    """Returns default severity for an event type (falls back to 'info')."""
    return EVENT_SEVERITY_DEFAULTS.get(event_type, "info")
