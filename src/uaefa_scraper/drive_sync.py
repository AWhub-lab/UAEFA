"""Google Drive publishing and runtime download helpers.

The module intentionally reads credentials from environment variables or
Streamlit secrets. Credentials and downloaded data must never be committed.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveSyncError(RuntimeError):
    """Raised when Drive synchronization cannot be completed safely."""


@dataclass(frozen=True)
class DriveSettings:
    root_folder_id: str
    service_account_json: str


def settings_from_mapping(mapping: dict[str, Any] | None = None) -> DriveSettings | None:
    """Resolve settings from a mapping first, then environment variables."""
    mapping = mapping or {}
    root_folder_id = str(mapping.get("root_folder_id") or os.getenv("GOOGLE_DRIVE_ROOT_ID") or "").strip()
    service_account_json = mapping.get("service_account_json") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not root_folder_id or not service_account_json:
        return None
    if isinstance(service_account_json, dict):
        service_account_json = json.dumps(service_account_json)
    return DriveSettings(root_folder_id=root_folder_id, service_account_json=str(service_account_json))


def service_from_settings(settings: DriveSettings):
    """Build an authenticated Drive client only when a sync is requested."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - deployment configuration failure
        raise DriveSyncError("Google Drive dependencies are not installed.") from exc
    try:
        info = json.loads(settings.service_account_json)
        credentials = service_account.Credentials.from_service_account_info(info, scopes=[DRIVE_SCOPE])
    except (TypeError, ValueError) as exc:
        raise DriveSyncError("The Google service-account secret is not valid JSON.") from exc
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _escape_query(value: str) -> str:
    return value.replace("'", "\\'")


def list_children(service, parent_id: str) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{_escape_query(parent_id)}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            pageToken=page_token,
            pageSize=1000,
        ).execute()
        children.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return children


def find_child(service, parent_id: str, name: str, mime_type: str | None = None) -> dict[str, Any] | None:
    for child in list_children(service, parent_id):
        if child["name"] == name and (mime_type is None or child["mimeType"] == mime_type):
            return child
    return None


def ensure_folder(service, parent_id: str, name: str) -> str:
    existing = find_child(service, parent_id, name, FOLDER_MIME_TYPE)
    if existing:
        return existing["id"]
    created = service.files().create(
        body={"name": name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]},
        fields="id",
    ).execute()
    return created["id"]


def ensure_path(service, root_id: str, parts: list[str]) -> str:
    folder_id = root_id
    for part in parts:
        folder_id = ensure_folder(service, folder_id, part)
    return folder_id


def find_path(service, root_id: str, parts: list[str]) -> str | None:
    """Resolve an existing folder path without creating Drive content."""
    folder_id = root_id
    for part in parts:
        folder = find_child(service, folder_id, part, FOLDER_MIME_TYPE)
        if not folder:
            return None
        folder_id = folder["id"]
    return folder_id


def upload_file(service, parent_id: str, source: Path, name: str | None = None) -> str:
    """Create or replace one Drive file, keeping its folder identity stable."""
    from googleapiclient.http import MediaFileUpload

    name = name or source.name
    existing = find_child(service, parent_id, name)
    media = MediaFileUpload(str(source), resumable=True)
    if existing:
        updated = service.files().update(fileId=existing["id"], media_body=media, fields="id").execute()
        return updated["id"]
    created = service.files().create(
        body={"name": name, "parents": [parent_id]}, media_body=media, fields="id"
    ).execute()
    return created["id"]


def upload_bytes(service, parent_id: str, name: str, payload: bytes) -> str:
    from googleapiclient.http import MediaIoBaseUpload

    existing = find_child(service, parent_id, name)
    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json", resumable=True)
    if existing:
        return service.files().update(fileId=existing["id"], media_body=media, fields="id").execute()["id"]
    return service.files().create(
        body={"name": name, "parents": [parent_id]}, media_body=media, fields="id"
    ).execute()["id"]


def download_file(service, file_id: str, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with destination.open("wb") as handle:
        downloader = MediaIoBaseDownload(handle, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def remote_manifest(service, current_folder_id: str) -> dict[str, Any] | None:
    entry = find_child(service, current_folder_id, "app_manifest.json")
    if not entry:
        return None
    request = service.files().get_media(fileId=entry["id"])
    payload = request.execute()
    return json.loads(payload.decode("utf-8"))


def publish_tree(
    service,
    local_root: Path,
    remote_root_id: str,
    remote_prefix: str,
    previous_hashes: dict[str, str],
) -> tuple[list[dict[str, Any]], int, int]:
    """Upload changed files from a local tree and return manifest records."""
    records: list[dict[str, Any]] = []
    uploaded = 0
    skipped = 0
    for source in sorted(path for path in local_root.rglob("*") if path.is_file()):
        relative = source.relative_to(local_root)
        key = f"{remote_prefix}/{relative.as_posix()}"
        digest = sha256_file(source)
        records.append({"path": key, "sha256": digest, "bytes": source.stat().st_size})
        if previous_hashes.get(key) == digest:
            skipped += 1
            continue
        folder_id = ensure_path(service, remote_root_id, list(relative.parts[:-1]))
        upload_file(service, folder_id, source)
        uploaded += 1
    return records, uploaded, skipped


def download_tree(
    service,
    remote_root_id: str,
    local_root: Path,
    remote_prefix: str,
    remote_hashes: dict[str, str],
    local_hashes: dict[str, str],
) -> int:
    """Download only changed Drive files while preserving the local cache."""
    downloaded = 0
    for child in list_children(service, remote_root_id):
        target = local_root / child["name"]
        key = f"{remote_prefix}/{child['name']}"
        if child["mimeType"] == FOLDER_MIME_TYPE:
            downloaded += download_tree(
                service, child["id"], target, key, remote_hashes, local_hashes
            )
        else:
            if remote_hashes.get(key) == local_hashes.get(key) and target.exists():
                continue
            download_file(service, child["id"], target)
            downloaded += 1
    return downloaded


def publish_project_snapshot(project_root: Path, settings: DriveSettings, include_raw: bool = True) -> dict[str, Any]:
    """Publish local data incrementally to the agreed Drive folder structure."""
    service = service_from_settings(settings)
    processed_current = project_root / "data" / "processed" / "first_division_2026_2027" / "current"
    external = project_root / "data" / "external" / "besoccer" / "first_division_2026_2027"
    assets = project_root / "data" / "assets"
    raw = project_root / "data" / "raw" / "first_division_2026_2027"
    if not processed_current.exists():
        raise DriveSyncError(f"Processed data not found: {processed_current}")

    current_id = ensure_path(service, settings.root_folder_id, ["02_Processed data", "current"])
    previous = remote_manifest(service, current_id) or {}
    previous_hashes = {entry["path"]: entry["sha256"] for entry in previous.get("files", [])}
    files: list[dict[str, Any]] = []
    uploaded = skipped = 0
    for local_root, remote_parent, prefix in (
        (processed_current, ensure_path(service, current_id, ["tables"]), "tables"),
        (external, ensure_path(service, current_id, ["besoccer"]), "besoccer"),
        (assets / "first_division_2026_2027" / "clubs", ensure_path(service, settings.root_folder_id, ["03_Assets", "clubs"]), "assets/clubs"),
        (assets / "first_division_2026_2027" / "players", ensure_path(service, settings.root_folder_id, ["03_Assets", "players"]), "assets/players"),
        (assets / "brand", ensure_path(service, settings.root_folder_id, ["03_Assets", "brand"]), "assets/brand"),
    ):
        if not local_root.exists():
            continue
        records, added, unchanged = publish_tree(service, local_root, remote_parent, prefix, previous_hashes)
        files.extend(records)
        uploaded += added
        skipped += unchanged

    if include_raw and raw.exists():
        raw_id = ensure_path(service, settings.root_folder_id, ["01_Raw data", "API JSON snapshots", "2026_2027"])
        records, added, unchanged = publish_tree(service, raw, raw_id, "raw", previous_hashes)
        files.extend(records)
        uploaded += added
        skipped += unchanged

    manifest = {
        "schema_version": 1,
        "published_at": datetime.now(UTC).isoformat(),
        "season": "2026/2027",
        "files": files,
        "summary": {"uploaded": uploaded, "unchanged": skipped, "total": len(files)},
    }
    upload_bytes(service, current_id, "app_manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
    return manifest


def sync_runtime_snapshot(project_root: Path, settings: DriveSettings) -> dict[str, Any]:
    """Download processed data and visual assets required by the deployed app."""
    service = service_from_settings(settings)
    current_id = find_path(service, settings.root_folder_id, ["02_Processed data", "current"])
    if not current_id:
        raise DriveSyncError("The Drive processed-data folder does not exist.")
    manifest = remote_manifest(service, current_id)
    if not manifest:
        raise DriveSyncError("No published Drive manifest was found. Run publish_to_drive.py first.")

    marker = project_root / "data" / ".drive_manifest.json"
    try:
        local_manifest = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        local_manifest = {}
    remote_hashes = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    local_hashes = {entry["path"]: entry["sha256"] for entry in local_manifest.get("files", [])}

    tables = find_child(service, current_id, "tables", FOLDER_MIME_TYPE)
    besoccer = find_child(service, current_id, "besoccer", FOLDER_MIME_TYPE)
    if not tables or not besoccer:
        raise DriveSyncError("Drive current snapshot is incomplete.")
    data_root = project_root / "data"
    downloaded = download_tree(
        service, tables["id"], data_root / "processed" / "first_division_2026_2027" / "current",
        "tables", remote_hashes, local_hashes,
    )
    downloaded += download_tree(
        service, besoccer["id"], data_root / "external" / "besoccer" / "first_division_2026_2027",
        "besoccer", remote_hashes, local_hashes,
    )

    assets_root = find_path(service, settings.root_folder_id, ["03_Assets"])
    if not assets_root:
        raise DriveSyncError("The Drive assets folder does not exist.")
    for remote_name, local_name in (("clubs", "clubs"), ("players", "players"), ("brand", "brand")):
        source = find_child(service, assets_root, remote_name, FOLDER_MIME_TYPE)
        if source:
            target = (
                data_root / "assets" / "first_division_2026_2027" / local_name
                if local_name != "brand"
                else data_root / "assets" / "brand"
            )
            downloaded += download_tree(
                service, source["id"], target, f"assets/{local_name}", remote_hashes, local_hashes
            )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"downloaded": downloaded, "published_at": manifest.get("published_at")}
