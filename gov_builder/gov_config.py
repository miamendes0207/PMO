# modules/gov_config.py

from datetime import date

BRAND_COLOURS = {
    "navy": "#002060",
    "red": "#C00000",
    "light_grey": "#EDEDED",
}

# Which sections the user can toggle
DEFAULT_SECTIONS = {
    "exec_summary": True,
    "delivery_summary": True,
    "risks_issues": True,
    "actions_summary": True,
    "timeline": True,
    "raids_appendix": False,  # optional
}

# For now just hardcode; later you can load from a config / SharePoint
CLIENT_LIST = [
    "N Brown",
    "Client B",
    "Client C",
]


def default_reporting_period() -> tuple[date, date]:
    """Return this week's Monday–Friday as default period."""
    today = date.today()
    monday = today if today.weekday() == 0 else today.replace(
        day=today.day - today.weekday()
    )
    friday = monday.fromordinal(monday.toordinal() + 4)
    return monday, friday
