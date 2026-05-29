import os
import sys

# ----------------------------------------------------
# Force project root into Python path so modules import
# ----------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR))
PARENT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if PARENT_ROOT not in sys.path:
    sys.path.insert(0, PARENT_ROOT)

# ----------------------------------------------------
# Now imports will work correctly
# ----------------------------------------------------
from modules.db import run_query
from modules.client_filesystem import ensure_client_folder


def migrate_clients():
    print("🔍 Loading approved clients...")

    rows = run_query("""
        SELECT client_code 
        FROM client_scaffold
        WHERE status = 'approved'
    """)

    if rows is None or rows.empty:
        print("⚠️ No approved clients found.")
        return

    for _, row in rows.iterrows():
        code = row["client_code"]
        ensure_client_folder(code)
        print(f"📁 Ensured folder for: {code}")

    print("\n✅ Migration complete — all client folders created.")


if __name__ == "__main__":
    migrate_clients()
