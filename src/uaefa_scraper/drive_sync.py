"""Google Drive publishing and runtime download helpers.

The module intentionally reads credentials from environment variables or
Streamlit secrets. Credentials and downloaded data must never be committed.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveSyncError(RuntimeError):
    """Raised when Drive synchronization cannot be completed safely."""


def load_project_env(path: Path) -> None:
    """Load simple local KEY=VALUE entries without adding a runtime dependency.

    Deployment secrets still come from Streamlit. This helper exists solely for
    the local owner-side publisher and never logs the values it reads.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class DriveSettings:
    root_folder_id: str
    service_account_json: str


def build_drive_service(credentials):
    """Create a Drive client with bounded HTTP calls for unattended syncs."""
    try:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - dependency configuration failure
        raise DriveSyncError("Google Drive dependencies are not installed.") from exc
    http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=60))
    return build("drive", "v3", http=http, cache_discovery=False)


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
    except ImportError as exc:  # pragma: no cover - deployment configuration failure
        raise DriveSyncError("Google Drive dependencies are not installed.") from exc
    try:
        info = json.loads(settings.service_account_json)
        credentials = service_account.Credentials.from_service_account_info(info, scopes=[DRIVE_SCOPE])
    except (TypeError, ValueError) as exc:
        raise DriveSyncError("The Google service-account secret is not valid JSON.") from exc
    return build_drive_service(credentials)


def publisher_service_from_oauth(project_root: Path):
    """Authorize the local publisher with the owner's Drive account.

    Service accounts can read the shared project folder in production but do not
    have personal Drive storage quota. Publishing therefore uses a local OAuth
    client and stores its renewable token outside Git.
    """
    configured_path = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_PATH", "").strip()
    client_path = project_root / configured_path if configured_path else None
    if not client_path or not client_path.exists():
        candidates = sorted(project_root.glob("client_secret_*.json"))
        client_path = candidates[0] if len(candidates) == 1 else None
    if not client_path or not client_path.exists():
        raise DriveSyncError("OAuth client JSON not found. Download a Desktop OAuth credential first.")

    token_path = project_root / ".drive_oauth_token.json"
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover - local environment failure
        raise DriveSyncError("Google OAuth publishing dependencies are not installed.") from exc

    credentials = None
    if token_path.exists():
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), [DRIVE_SCOPE])
        except (OSError, ValueError):
            token_path.unlink(missing_ok=True)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_path), [DRIVE_SCOPE])
        credentials = flow.run_local_server(port=0)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    token_path.chmod(0o600)
    return build_drive_service(credentials)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_runtime_media_bundle(project_root: Path) -> Path:
    """Create a compact archive with the visual resources required at runtime."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency configuration failure
        raise DriveSyncError("Pillow is required to build the deployment media bundle.") from exc

    bundle_path = project_root / "tmp" / "uae_first_division_runtime_media.zip"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    club_root = project_root / "data" / "assets" / "first_division_2026_2027" / "clubs"
    player_root = project_root / "data" / "assets" / "first_division_2026_2027" / "players"
    club_archive_root = Path("data/assets/first_division_2026_2027/clubs")
    player_archive_root = Path("data/assets/first_division_2026_2027/players")
    report = project_root / "output" / "pdf" / "uae_first_division_category_board_report_en.pdf"
    brand = project_root / "data" / "assets" / "brand" / "al_wasl.png"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        # Crests are tiny and preserve their transparent source format.
        if club_root.exists():
            for source in sorted(path for path in club_root.rglob("*") if path.is_file()):
                archive.write(source, (club_archive_root / source.relative_to(club_root)).as_posix())
        # The local originals remain untouched. The hosted copy uses compact JPEG
        # portraits, while app.py transparently falls back from .png to .jpg.
        if player_root.exists():
            for source in sorted(path for path in player_root.rglob("*") if path.is_file()):
                with Image.open(source) as image:
                    image = image.convert("RGB")
                    image.thumbnail((300, 400), Image.Resampling.LANCZOS)
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)
                archive.writestr(
                    (player_archive_root / source.relative_to(player_root)).with_suffix(".jpg").as_posix(),
                    buffer.getvalue(),
                )
        if brand.exists():
            archive.write(brand, "data/assets/brand/al_wasl.png")
        if report.exists():
            archive.write(report, "output/pdf/uae_first_division_category_board_report_en.pdf")
    return bundle_path


def extract_runtime_media_bundle(bundle_path: Path, project_root: Path) -> None:
    """Extract our own runtime archive without allowing paths outside the project."""
    destination = project_root.resolve()
    with zipfile.ZipFile(bundle_path) as archive:
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            if destination not in target.parents and target != destination:
                raise DriveSyncError("Runtime media archive contains an invalid path.")
        archive.extractall(destination)


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
    # Individual tables and visual assets are compact. A direct upload avoids
    # resumable sessions lingering indefinitely on an interrupted connection.
    media = MediaFileUpload(str(source), resumable=False)
    if existing:
        updated = service.files().update(fileId=existing["id"], media_body=media, fields="id").execute(num_retries=3)
        return updated["id"]
    created = service.files().create(
        body={"name": name, "parents": [parent_id]}, media_body=media, fields="id"
    ).execute(num_retries=3)
    return created["id"]


def upload_bytes(service, parent_id: str, name: str, payload: bytes) -> str:
    from googleapiclient.http import MediaIoBaseUpload

    existing = find_child(service, parent_id, name)
    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json", resumable=False)
    if existing:
        return service.files().update(fileId=existing["id"], media_body=media, fields="id").execute(num_retries=3)["id"]
    return service.files().create(
        body={"name": name, "parents": [parent_id]}, media_body=media, fields="id"
    ).execute(num_retries=3)["id"]


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
    allowed_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Upload changed runtime files from a local tree and return manifest records."""
    records: list[dict[str, Any]] = []
    uploaded = 0
    skipped = 0
    sources = sorted(
        path for path in local_root.rglob("*")
        if path.is_file() and (
            allowed_paths is None or path.relative_to(local_root).as_posix() in allowed_paths
        )
    )
    for index, source in enumerate(sources, start=1):
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
        if index == 1 or index % 25 == 0 or index == len(sources):
            print(f"Drive publish · {remote_prefix}: {index}/{len(sources)} files", flush=True)
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


def publish_project_snapshot(
    project_root: Path,
    settings: DriveSettings,
    service=None,
) -> dict[str, Any]:
    """Publish only the files required by the deployed application."""
    service = service or service_from_settings(settings)
    processed_current = project_root / "data" / "processed" / "first_division_2026_2027" / "current"
    external = project_root / "data" / "external" / "besoccer" / "first_division_2026_2027"
    media_bundle = build_runtime_media_bundle(project_root)
    if not processed_current.exists():
        raise DriveSyncError(f"Processed data not found: {processed_current}")

    current_id = ensure_path(service, settings.root_folder_id, ["02_Processed data", "current"])
    previous = remote_manifest(service, current_id) or {}
    previous_hashes = {entry["path"]: entry["sha256"] for entry in previous.get("files", [])}
    files: list[dict[str, Any]] = []
    uploaded = skipped = 0
    for local_root, remote_parent, prefix, allowed_paths in (
        (processed_current, ensure_path(service, current_id, ["tables"]), "tables", None),
        (external, ensure_path(service, current_id, ["besoccer"]), "besoccer", {"player_profiles_validated.parquet", "teams.parquet"}),
        (media_bundle.parent, current_id, "runtime", {media_bundle.name}),
    ):
        if not local_root.exists():
            continue
        records, added, unchanged = publish_tree(
            service, local_root, remote_parent, prefix, previous_hashes, allowed_paths
        )
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

    media_bundle = find_child(service, current_id, "uae_first_division_runtime_media.zip")
    media_key = "runtime/uae_first_division_runtime_media.zip"
    local_bundle = project_root / "tmp" / "uae_first_division_runtime_media.zip"
    if not media_bundle:
        raise DriveSyncError("Drive runtime media bundle is missing.")
    if remote_hashes.get(media_key) != local_hashes.get(media_key) or not local_bundle.exists():
        download_file(service, media_bundle["id"], local_bundle)
        extract_runtime_media_bundle(local_bundle, project_root)
        downloaded += 1
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"downloaded": downloaded, "published_at": manifest.get("published_at")}


def sync_competition_snapshot(
    project_root: Path,
    settings: DriveSettings,
    directory: str,
) -> dict[str, Any]:
    """Download one competition published through the isolated Drive layout.

    New competitions never overwrite the established First Division snapshot.
    Each one has its own tables and optional media archive, allowing the hosted
    application to cache only the competition a scout opens.
    """
    service = service_from_settings(settings)
    tables_id = find_path(
        service,
        settings.root_folder_id,
        ["02_Processed data", "competitions", directory, "current", "tables"],
    )
    if not tables_id:
        raise DriveSyncError(f"No published snapshot found for {directory}.")

    marker = project_root / "data" / ".drive_competition_manifests" / f"{directory}.json"
    try:
        local_manifest = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        local_manifest = {}
    manifest_entry = find_child(service, tables_id, "drive_manifest.json")
    remote_manifest_data: dict[str, Any] = {}
    if manifest_entry:
        remote_manifest_data = json.loads(
            service.files().get_media(fileId=manifest_entry["id"]).execute().decode("utf-8")
        )
    remote_hashes = {
        entry["path"]: entry["sha256"] for entry in remote_manifest_data.get("files", [])
    }
    local_hashes = {entry["path"]: entry["sha256"] for entry in local_manifest.get("files", [])}
    # The manifest sits beside tables, not inside the local snapshot itself.
    downloaded = download_tree(
        service,
        tables_id,
        project_root / "data" / "processed" / directory / "current",
        "tables",
        remote_hashes,
        local_hashes,
    )

    media_folder = find_path(
        service, settings.root_folder_id, ["03_Assets", "competitions", directory]
    )
    if media_folder:
        bundle = find_child(service, media_folder, f"{directory}_media.zip")
        if bundle:
            local_bundle = project_root / "tmp" / f"{directory}_media.zip"
            # Media archives are immutable by hash in the publisher manifest.
            bundle_changed = remote_manifest_data.get("media_bundle", {}).get("sha256") != local_manifest.get("media_bundle", {}).get("sha256")
            if bundle_changed or not local_bundle.exists():
                download_file(service, bundle["id"], local_bundle)
                # Competition bundles are rooted at their asset directory
                # (clubs/, players/), unlike the legacy all-project archive.
                extract_runtime_media_bundle(
                    local_bundle, project_root / "data" / "assets" / directory
                )
                downloaded += 1

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(remote_manifest_data, indent=2), encoding="utf-8")
    return {"downloaded": downloaded, "published_at": remote_manifest_data.get("published_at")}
