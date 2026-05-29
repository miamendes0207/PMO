# modules/action_config.py

ACTION_SHEET_NAME = "Actions"

# Column order for the Actions sheet
ACTION_COLUMNS = [
    "A ID",
    "Title",
    "Description",
    "Owner",
    "Due Date",
    "Status",
    "Priority",
    "Source",
    "Date Created",
    "Last Updated",
    "Comments",
    "Client",
]

STATUS_OPTIONS = ["Open", "In Progress", "Blocked", "Closed"]
PRIORITY_OPTIONS = ["High", "Medium", "Low"]
SOURCE_OPTIONS = ["Manual", "NFR", "Weekly NFR", "RAID", "Other"]
