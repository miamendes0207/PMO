# modules/project_filesystem.py

from pathlib import Path
import json
import shutil

BASE_DIR = Path("clients")


def ensure_project_folder(
    client_code: str,
    project_code: str,
    metadata: dict | None = None,
    settings: dict | None = None,
):
    """
    Ensure folder:
        clients/<client_code>/projects/<project_code>/
    and write metadata + settings JSON.
    """
    if not client_code or not project_code:
        return

    client_dir = BASE_DIR / client_code
    project_dir = client_dir / "projects" / project_code

    project_dir.mkdir(parents=True, exist_ok=True)

    # metadata.json
    if metadata is not None:
        (project_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, default=str),
            encoding="utf-8",
        )

    # settings.json
    if settings is not None:
        (project_dir / "settings.json").write_text(
            json.dumps(settings, indent=2, default=str),
            encoding="utf-8",
        )

    # simple activity.log placeholder
    log_path = project_dir / "activity.log"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")


def delete_project_folder(client_code: str, project_code: str):
    """
    Delete:
        clients/<client_code>/projects/<project_code>/
    if it exists.
    """
    if not client_code or not project_code:
        return

    project_dir = BASE_DIR / client_code / "projects" / project_code
    if project_dir.exists():
        shutil.rmtree(project_dir)
