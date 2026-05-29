# ============================================================
# client_scaffolder.py — ScopeSight v2.0
# Build backend client/project folder from pending config
#
# FIXES vs v1.0:
# - Import corrected: notifications_utils (not notification_utils)
# - scaffold_client no longer overwrites raids_config.json with the
#   static tier template — custom raids_config from the project designer
#   is passed through and written to the project config file
# - ensure_project_folder() added: called by Project_Setup_Approval on
#   approval; writes a project-scoped folder with the live raids_config
# - config.json now always contains the raids_config so the filesystem
#   reflects what was designed in Project Configuration
# - scaffold_client is kept for client-level folder creation (no project
#   assumed at that stage); project folders are created separately via
#   ensure_project_folder()
# ============================================================

from __future__ import annotations

import json
import shutil
import datetime as dt
from pathlib import Path
from typing import Any

from .log_utils import log_event
from .notifications_utils import send_notification   # ← fixed module name

# Root paths
CLIENTS_ROOT  = Path("modules/clients")
PENDING_DIR   = CLIENTS_ROOT / "pending"
TEMPLATES_DIR = CLIENTS_ROOT / "templates"


# ============================================================
# LOW-LEVEL UTILS
# ============================================================

def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, default=str)


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)


def ensure_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)


# ============================================================
# CLIENT-LEVEL SCAFFOLDER
# Called when a new *client* is approved (not a project).
# Creates the shared client folder and copies tier templates,
# but does NOT write a raids_config — that is project-scoped.
# ============================================================

def scaffold_client(pending_file: Path) -> dict:
    """
    Reads a pending client JSON, creates the client folder structure,
    copies tier template files, and archives the pending request.

    Note: raids_config is NOT copied from the tier template here.
    It is project-specific and is written per-project by
    ensure_project_folder() when a project is approved.
    """
    pending = load_json(pending_file)

    client_name = pending["folder_name"]
    tier        = pending["tier"]

    if tier not in ("tier_1", "tier_2"):
        raise ValueError(f"Invalid tier '{tier}' in pending config: {pending_file.name}")

    template_path = TEMPLATES_DIR / tier
    if not template_path.exists():
        raise FileNotFoundError(f"Tier template folder not found: {template_path}")

    # ── Create client folder structure ─────────────────────────────────
    client_root = CLIENTS_ROOT / client_name
    for sub in ("logs", "glossary", "scripts", "templates", "projects"):
        ensure_folder(client_root / sub)

    # ── Copy tier template configs (excluding raids_config — project-scoped) ──
    for cfg_name in ["actions_config.json", "nfr_config.json", "settings.json"]:
        src = template_path / cfg_name
        dst = client_root / cfg_name
        if src.exists():
            copy_file(src, dst)

    # ── Copy governance template PPTX if present ───────────────────────
    gov_src = template_path / "gov_pack_template.pptx"
    gov_dst = client_root / "templates" / "gov_pack_template.pptx"
    if gov_src.exists():
        copy_file(gov_src, gov_dst)

    # ── Write client-level config.json ─────────────────────────────────
    final_config = {
        "client_name":    pending["client_name"],
        "folder_name":    client_name,
        "client_code":    pending["client_code"],
        "description":    pending.get("description", ""),
        "tier":           tier,
        "brand_primary":  pending.get("brand_primary", "#142D53"),
        "brand_secondary":pending.get("brand_secondary", "#1E74BB"),
        "access_list":    pending.get("access_list", []),
        "submitted_by":   pending.get("submitted_by", ""),
        "submitted_on":   pending.get("submitted_on", ""),
        "status":         "awaiting_approval",
        "created_on":     dt.datetime.utcnow().isoformat(),
    }
    save_json(client_root / "config.json", final_config)

    # ── Archive the pending request ─────────────────────────────────────
    archive_dir  = CLIENTS_ROOT / "pending_archive"
    ensure_folder(archive_dir)
    archived_path = archive_dir / pending_file.name
    shutil.move(str(pending_file), str(archived_path))

    # ── Log + notify ────────────────────────────────────────────────────
    log_event("client_scaffolded", {
        "client": pending["client_name"],
        "folder": client_name,
        "tier":   tier,
        "path":   str(client_root),
    })
    send_notification("client_scaffolded", {
        "client": pending["client_name"],
        "folder": client_name,
        "tier":   tier,
        "path":   str(client_root),
    })

    return {
        "client":           client_name,
        "tier":             tier,
        "path":             str(client_root),
        "pending_archived": str(archived_path),
    }


# ============================================================
# PROJECT-LEVEL FOLDER CREATOR
# Called by Project_Setup_Approval.py on project approval.
# Writes a project subfolder containing the live raids_config
# so the filesystem always reflects what was designed.
# ============================================================

def ensure_project_folder(
    client_code: str,
    project_code: str,
    metadata: dict,
    settings: dict,
) -> Path:
    """
    Creates (or updates) a project subfolder under the client folder.

    Parameters
    ----------
    client_code : str
        Short code for the client, used as the folder name segment.
    project_code : str
        Short code for the project (e.g. "DIGIP").
    metadata : dict
        Project identifiers (project_id, project_name, approved_by, etc.)
    settings : dict
        Full settings payload from the approval flow.  Must contain
        "raids_config" so the project folder stays in sync with the DB.

    Returns
    -------
    Path
        The project root folder path.
    """
    client_folder  = CLIENTS_ROOT / client_code.lower()
    projects_dir   = client_folder / "projects"
    project_root   = projects_dir / project_code.lower()

    for sub in ("logs", "exports", "files"):
        ensure_folder(project_root / sub)

    # ── Write raids_config.json from the live designer config ──────────
    raids_cfg = settings.get("raids_config") or {}
    if raids_cfg:
        save_json(project_root / "raids_config.json", raids_cfg)
    else:
        # Fall back to a minimal default so consumers never get FileNotFoundError
        default_raids = {
            "enabled_optional_fields": [
                "mitigation_plan", "mitigation_status",
                "owner_plen", "planned_close", "probability", "severity", "date_raised",
            ],
            "custom_fields": [],
            "rules": {"require_mitigation_for": ["Risk", "Issue"]},
        }
        save_json(project_root / "raids_config.json", default_raids)

    # ── Write project config.json (full settings snapshot) ─────────────
    project_config = {
        **metadata,
        "settings": settings,
        "created_on": dt.datetime.utcnow().isoformat(),
    }
    save_json(project_root / "config.json", project_config)

    log_event("project_folder_created", {
        "client_code":   client_code,
        "project_code":  project_code,
        "path":          str(project_root),
        "raids_config":  bool(raids_cfg),
    })

    return project_root


def delete_project_folder(client_code: str, project_code: str) -> bool:
    """
    Removes a project subfolder entirely.  Returns True if deleted,
    False if it did not exist (safe to call on missing paths).
    """
    project_root = CLIENTS_ROOT / client_code.lower() / "projects" / project_code.lower()
    if project_root.exists():
        shutil.rmtree(project_root)
        log_event("project_folder_deleted", {
            "client_code":  client_code,
            "project_code": project_code,
            "path":         str(project_root),
        })
        return True
    return False


# ============================================================
# BATCH SCAFFOLDER  (admin / CLI use)
# ============================================================

def scaffold_all_pending() -> list[dict]:
    """Scaffolds all clients in the pending folder."""
    results = []
    for file in PENDING_DIR.glob("*.json"):
        try:
            result = scaffold_client(file)
            results.append({"file": file.name, "result": result})
        except Exception as e:
            results.append({"file": file.name, "error": str(e)})
    return results


if __name__ == "__main__":
    print("Running scaffolder on all pending clients...")
    for item in scaffold_all_pending():
        print(item)