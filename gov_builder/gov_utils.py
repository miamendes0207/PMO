# modules/gov_utils.py

from pathlib import Path
from typing import Dict, List
import json
import datetime as dt

import pandas as pd

from modules.raids.raids_config import RAIDS_CONFIG
from modules.action_manager.action_utils import load_client_actions


# -------------------------
# 1. Load RAIDS data
# -------------------------

def load_client_raids_data(client: str) -> Dict[str, pd.DataFrame]:
    """
    Load RAIDS workbook for a client, returning a dict:
    {
        "Risks": df_risks,
        "Assumptions": df_ass,
        "Issues": df_issues,
        "Dependencies": df_deps
    }
    """
    path = Path("data/raids") / f"{client.replace(' ', '_')}_RAIDS.xlsx"
    if not path.exists():
        # Return empty frames for each section
        return {section: pd.DataFrame() for section in RAIDS_CONFIG.keys()}

    xls = pd.ExcelFile(path)
    data: Dict[str, pd.DataFrame] = {}

    for section, cfg in RAIDS_CONFIG.items():
        sheet = cfg["sheet_name"]
        try:
            df = pd.read_excel(xls, sheet_name=sheet)
        except Exception:
            df = pd.DataFrame()
        data[section] = df

    return data


# -------------------------
# 2. Extract RAID snippets
# -------------------------

def extract_raid_snippets(raids_data: Dict[str, pd.DataFrame]) -> List[str]:
    """
    Build short text snippets from RAIDS data for governance summaries.
    e.g. "Risk: [Risk Description] (Status: Open)"
    """
    snippets: List[str] = []

    for section, df in raids_data.items():
        if df.empty:
            continue

        cfg = RAIDS_CONFIG[section]
        text_col = cfg["text_col"]
        comments_col = cfg.get("comments_col")
        status_col = cfg.get("status_col", "Status")
        title_col = cfg.get("title_col")

        for _, row in df.iterrows():
            text_val = row.get(text_col, "")
            if not isinstance(text_val, str) or not text_val.strip():
                continue

            status_val = row.get(status_col, "")
            title_val = row.get(title_col, "")

            prefix = section[:-1]  # "Risk", "Issue", etc.
            if isinstance(title_val, str) and title_val.strip():
                snippet = f"{prefix}: {title_val} – {text_val}"
            else:
                snippet = f"{prefix}: {text_val}"

            if isinstance(status_val, str) and status_val.strip():
                snippet += f" (Status: {status_val})"

            snippets.append(snippet)

            if comments_col:
                comments_val = row.get(comments_col, "")
                if isinstance(comments_val, str) and comments_val.strip():
                    snippets.append(f"{prefix} Comment: {comments_val}")

    return snippets


# -------------------------
# 3. Extract ACTION snippets
# -------------------------

def extract_action_snippets(client: str) -> List[str]:
    """
    Build action snippets from the Action Manager workbook.
    """
    df = load_client_actions(client)
    if df.empty:
        return []

    snippets: List[str] = []

    for _, row in df.iterrows():
        title = row.get("Title", "")
        desc = row.get("Description", "")
        status = row.get("Status", "")
        owner = row.get("Owner", "")
        due = row.get("Due Date", "")

        if not isinstance(title, str) or not title.strip():
            continue

        snippet = f"Action: {title}"
        if isinstance(desc, str) and desc.strip():
            snippet += f" – {desc}"

        extra_bits = []
        if isinstance(status, str) and status.strip():
            extra_bits.append(f"Status: {status}")
        if isinstance(owner, str) and owner.strip():
            extra_bits.append(f"Owner: {owner}")
        if isinstance(due, (str, dt.date)) and str(due).strip():
            extra_bits.append(f"Due: {due}")

        if extra_bits:
            snippet += f" ({'; '.join(extra_bits)})"

        snippets.append(snippet)

    return snippets


# -------------------------
# 4. Load Weekly NFR JSON for a client & period
# -------------------------

def load_weekly_nfr_json(client: str, period_start: dt.date, period_end: dt.date) -> List[dict]:
    """
    Load Weekly NFR JSON files for a client whose week_commencing
    falls inside [period_start, period_end].
    """
    base = Path("data/nfr_json") / client.replace(" ", "_")
    if not base.exists():
        return []

    items: List[dict] = []

    for file in base.glob("weekly_nfr_*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        wc_str = data.get("week_commencing")
        if not wc_str:
            continue

        try:
            wc = dt.date.fromisoformat(wc_str)
        except Exception:
            continue

        if period_start <= wc <= period_end:
            items.append(data)

    return items


# -------------------------
# 5. Extract NFR snippets for Governance Pack
# -------------------------

def extract_nfr_snippets(client: str, period_start: dt.date, period_end: dt.date) -> List[str]:
    """
    Build text snippets from Weekly NFR JSON for this client, using only
    weeks whose 'week_commencing' date sits in [period_start, period_end].
    """
    data_items = load_weekly_nfr_json(client, period_start, period_end)
    snippets: List[str] = []

    for entry in data_items:
        # Objectives
        objectives = entry.get("objectives")
        if isinstance(objectives, str) and objectives.strip():
            snippets.append(f"Objective: {objectives}")

        # Discussion sections: list of [subhead, bullets]
        for sub, bullets in entry.get("discussion_sections", []):
            if sub and isinstance(sub, str):
                for b in bullets or []:
                    if isinstance(b, str) and b.strip():
                        snippets.append(f"Discussion – {sub}: {b}")

        # Actions from Weekly NFR
        for a in entry.get("actions", []):
            title = a.get("Title", "")
            detail = a.get("Detail", "")
            if isinstance(title, str) and title.strip():
                snippet = f"NFR Action: {title}"
                if isinstance(detail, str) and detail.strip():
                    snippet += f" – {detail}"
                snippets.append(snippet)

    return snippets
