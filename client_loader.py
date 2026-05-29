import importlib
import importlib.util
import os
import json
from pathlib import Path
import re
from typing import Dict, List, Optional

from modules.db import run_query

BASE_PATH = Path("clients")


# ============================================================
# Exceptions
# ============================================================
class ClientLoaderError(Exception):
    pass


class ClientNotFoundError(ClientLoaderError):
    pass


class ClientConfigError(ClientLoaderError):
    pass


# ============================================================
# Sanitisation Helpers
# ============================================================
def sanitize(name: str) -> str:
    """Folder-safe version"""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return cleaned.lower()


def normalize(name: str) -> str:
    """Used for fuzzy matching"""
    return re.sub(r"[^A-Za-z0-9]", "", name).lower()


# ============================================================
# DEFAULT CONFIG (SAFE FALLBACK)
# ============================================================
DEFAULT_CONFIG = {
    "raids_config": {},
    "actions_config": {},
    "settings": {},
    "nfr_config": {
        "sections": ["Objectives", "Attendees", "Discussion", "Actions"],
        "include_summary": True,
        "format": "standard",
    },
}


def merge_with_defaults(db_row: Dict) -> Dict:
    """Merge DB configs with fallback defaults."""
    return {
        "client_name": db_row["client_name"],
        "raids_config": db_row.get("raids_config") or DEFAULT_CONFIG["raids_config"],
        "actions_config": db_row.get("actions_config") or DEFAULT_CONFIG["actions_config"],
        "settings": db_row.get("settings") or DEFAULT_CONFIG["settings"],
        "nfr_config": db_row.get("nfr_config") or DEFAULT_CONFIG["nfr_config"],
    }


# ============================================================
# DB CLIENTS
# ============================================================
def list_clients_from_db() -> List[Dict]:
    df = run_query("""
        SELECT 
            id AS client_id,
            client_code,
            client_name,
            tier,
            status,
            raids_config,
            actions_config,
            nfr_config,
            settings
        FROM client_scaffold
        WHERE status = 'approved'
        ORDER BY client_name;
    """)
    return df.to_dict("records") if df is not None and not df.empty else []


def try_load_from_db(client_name_or_code: str) -> Optional[Dict]:
    """Returns DB config if match found, else None."""

    if not client_name_or_code:
        return None

    norm = normalize(client_name_or_code)
    raw = client_name_or_code.lower()

    rows = list_clients_from_db()

    # 1. Exact client_code match
    for row in rows:
        code = (row.get("client_code") or "").lower()
        if code == raw:
            return merge_with_defaults(row)

    # 2. Exact client_name match
    for row in rows:
        name = (row.get("client_name") or "").lower()
        if name == raw:
            return merge_with_defaults(row)

    # 3. Fuzzy name match
    for row in rows:
        if normalize(row.get("client_name", "")) == norm:
            return merge_with_defaults(row)

    return None


# ============================================================
# FILESYSTEM CLIENTS
# ============================================================
def list_available_clients() -> List[str]:
    if not BASE_PATH.exists():
        return []
    return sorted([f.name for f in BASE_PATH.iterdir() if f.is_dir()])


def resolve_client_folder(name: str) -> Optional[Path]:
    """Filesystem resolution with sanitisation + fuzzy matching."""
    folders = list_available_clients()
    raw = name.lower()
    norm = normalize(name)
    sani = sanitize(name)

    # Exact match
    for f in folders:
        if f.lower() == raw:
            return BASE_PATH / f

    # Sanitised match
    for f in folders:
        if f.lower() == sani:
            return BASE_PATH / f

    # Fuzzy match
    for f in folders:
        if normalize(f) == norm:
            return BASE_PATH / f

    return None


# ============================================================
# CONFIG LOADER (DB FIRST → FS FALLBACK → DEFAULTS)
# ============================================================
def load_client_config(client_name_or_code: str) -> Dict:
    """
    1. Try DB (preferred)
    2. Try filesystem JSON
    3. Try filesystem legacy Python module
    4. Return DEFAULT_CONFIG always (never crash)
    """

    # 1️⃣ Try database
    db_cfg = try_load_from_db(client_name_or_code)
    if db_cfg:
        return db_cfg

    # 2️⃣ Try filesystem folders
    folder = resolve_client_folder(client_name_or_code)
    if folder:
        json_path = folder / "client_config.json"

        # JSON config
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if isinstance(cfg, dict):
                        return cfg
            except Exception as e:
                raise ClientConfigError(f"Failed to load config JSON: {e}")

        # Legacy python module
        mod_name = f"{folder.name}_profile"
        try:
            module = load_client_module(folder.name, mod_name)
            if hasattr(module, "CLIENT_PROFILE") and isinstance(module.CLIENT_PROFILE, dict):
                return module.CLIENT_PROFILE
        except Exception:
            pass

    # 3️⃣ Nothing found → use fallback instead of crashing
    return {
        "client_name": client_name_or_code,
        **DEFAULT_CONFIG,
        "warning": f"Client '{client_name_or_code}' not found. Using fallback config."
    }


# ============================================================
# MODULE LOADER
# ============================================================
def load_client_module(client_folder_name: str, module_name: str):
    folder = BASE_PATH / client_folder_name
    py = folder / f"{module_name}.py"

    # New FS loader
    if py.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                f"{client_folder_name}.{module_name}", py
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore
            return module
        except Exception as e:
            raise ClientLoaderError(f"Failed to import module {py}: {e}")

    # Legacy loader
    legacy_path = f"modules.clients.{client_folder_name}.{module_name}"
    try:
        return importlib.import_module(legacy_path)
    except Exception:
        raise ClientNotFoundError(f"Module not found: {legacy_path}")


# ============================================================
# MULTI-MODULE CLIENT LOADER
# ============================================================
def load_client(client_name_or_code: str, *modules: str) -> Dict:
    cfg = load_client_config(client_name_or_code)

    out = {"config": cfg}

    # Load modules if requested
    folder = resolve_client_folder(client_name_or_code)
    if folder:
        for m in modules:
            out[m] = load_client_module(folder.name, m)

    return out


# ============================================================
# DISPLAY MAPPING
# ============================================================
def get_all_clients_display() -> Dict[str, str]:
    """DB preferred, FS fallback."""
    db = list_clients_from_db()
    if db:
        return {row["client_code"]: row["client_name"] for row in db}

    # FS fallback
    mapping = {}
    for f in list_available_clients():
        mapping[f] = f  # until FS configs deprecated
    return mapping
