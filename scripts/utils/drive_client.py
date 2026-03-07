"""Google Drive API wrapper for Ictus Flow.

SCA-05: Refactored as GoogleDriveClient(StorageClient).  Backward-compatible
module-level functions are preserved at the bottom so existing code that does
``from scripts.utils.drive_client import list_files`` continues to work.

SEC-02: All folder-based operations accept an optional client_code parameter.
When provided, the folder is validated against the client's config before the
Drive API call. This prevents cross-client data leakage.

Audit: When client_code is provided, every upload/download/move/delete is
logged to logs/audit.csv via audit_logger.log_access().
"""

import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaInMemoryUpload
from dotenv import load_dotenv
from scripts.utils.retry import retry_with_backoff
from scripts.utils.storage_interface import StorageClient

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

_service = None


def _get_service():
    global _service
    if _service is None:
        creds = service_account.Credentials.from_service_account_file(
            os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'), scopes=SCOPES
        )
        _service = build('drive', 'v3', credentials=creds)
    return _service


def _guard(client_code, folder_id):
    """Validate folder belongs to client. No-op if client_code is None."""
    if client_code and folder_id:
        from scripts.utils.client_guard import validate_client_operation
        validate_client_operation(client_code, folder_id)


def _audit(client_code, file_id, file_name, action):
    """Log a Drive operation to the audit trail. No-op if client_code is None."""
    if client_code:
        from scripts.utils.audit_logger import log_access
        log_access(client_code, file_id, file_name, action, 'drive_client')


# ═══════════════════════════════════════════════════════════════════
# Class-based implementation (SCA-05)
# ═══════════════════════════════════════════════════════════════════


class GoogleDriveClient(StorageClient):
    """Google Drive implementation of StorageClient."""

    # ── Read operations ───────────────────────────────────────────

    @retry_with_backoff()
    def list_files(self, folder_id, mime_type=None, client_code=None):
        """List files in a Drive folder.

        Returns list of dicts with id, name, mimeType, modifiedTime, size.
        """
        _guard(client_code, folder_id)

        service = _get_service()
        query = f"'{folder_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"

        results = []
        page_token = None
        while True:
            resp = service.files().list(
                q=query,
                fields='nextPageToken, files(id, name, mimeType, modifiedTime, size)',
                orderBy='createdTime',
                pageToken=page_token,
            ).execute()
            results.extend(resp.get('files', []))
            page_token = resp.get('nextPageToken')
            if not page_token:
                break
        return results

    @retry_with_backoff()
    def download_file(self, file_id, destination_path, client_code=None):
        """Download a file from Drive to a local path. Returns the path."""
        service = _get_service()
        request = service.files().get_media(fileId=file_id)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        with open(destination_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        _audit(client_code, file_id, os.path.basename(destination_path), 'READ')
        return destination_path

    @retry_with_backoff()
    def download_file_bytes(self, file_id, client_code=None):
        """Download a file from Drive and return bytes."""
        service = _get_service()
        request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)
        _audit(client_code, file_id, file_id, 'READ')
        return buffer.read()

    @retry_with_backoff()
    def export_file(self, file_id, mime_type='text/plain', client_code=None):
        """Export a Google Docs/Sheets/Slides file. Returns bytes.

        Google-specific — not part of StorageClient interface.
        """
        service = _get_service()
        result = service.files().export(fileId=file_id, mimeType=mime_type).execute()
        _audit(client_code, file_id, file_id, 'READ')
        return result

    @retry_with_backoff()
    def find_file_by_name(self, folder_id, filename, client_code=None):
        """Find a file by name in a folder. Returns file dict or None."""
        _guard(client_code, folder_id)

        service = _get_service()
        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        resp = service.files().list(q=query, fields='files(id, name)').execute()
        files = resp.get('files', [])
        return files[0] if files else None

    def download_json(self, folder_id, filename, client_code=None):
        """Download and parse a JSON file from a folder. Returns dict or None."""
        _guard(client_code, folder_id)

        existing = self.find_file_by_name(folder_id, filename)
        if not existing:
            return None
        content = self.download_file_bytes(existing['id'])
        _audit(client_code, existing['id'], filename, 'READ')
        return json.loads(content.decode('utf-8'))

    @retry_with_backoff()
    def get_file_metadata(self, file_id):
        """Get metadata for a file."""
        service = _get_service()
        return service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, modifiedTime, size, parents',
        ).execute()

    # ── Write operations ──────────────────────────────────────────

    @retry_with_backoff()
    def upload_file(self, local_path, folder_id, filename=None, mime_type=None, client_code=None):
        """Upload a local file to a Drive folder. Returns the file ID."""
        _guard(client_code, folder_id)

        service = _get_service()
        if filename is None:
            filename = os.path.basename(local_path)
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        result = service.files().create(
            body=file_metadata, media_body=media, fields='id'
        ).execute()
        _audit(client_code, result['id'], filename, 'WRITE')
        return result['id']

    @retry_with_backoff()
    def upload_bytes(self, content, folder_id, filename, mime_type='application/json', client_code=None):
        """Upload bytes/string content to a Drive folder. Returns file ID."""
        _guard(client_code, folder_id)

        service = _get_service()
        if isinstance(content, str):
            content = content.encode('utf-8')
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=True)
        result = service.files().create(
            body=file_metadata, media_body=media, fields='id'
        ).execute()
        _audit(client_code, result['id'], filename, 'WRITE')
        return result['id']

    @retry_with_backoff()
    def update_file(self, file_id, local_path, mime_type=None, client_code=None):
        """Update an existing file's content on Drive.

        Google-specific — not part of StorageClient interface.
        """
        service = _get_service()
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        service.files().update(fileId=file_id, media_body=media).execute()
        _audit(client_code, file_id, os.path.basename(local_path), 'WRITE')

    @retry_with_backoff()
    def update_file_bytes(self, file_id, content, mime_type='application/json', client_code=None):
        """Update an existing file's content with bytes/string.

        Google-specific — not part of StorageClient interface.
        """
        service = _get_service()
        if isinstance(content, str):
            content = content.encode('utf-8')
        media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=True)
        service.files().update(fileId=file_id, media_body=media).execute()
        _audit(client_code, file_id, file_id, 'WRITE')

    @retry_with_backoff()
    def move_file(self, file_id, from_folder_id, to_folder_id, client_code=None):
        """Move a file between folders."""
        _guard(client_code, from_folder_id)
        _guard(client_code, to_folder_id)

        service = _get_service()
        service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=from_folder_id,
        ).execute()
        _audit(client_code, file_id, file_id, 'MOVE')

    @retry_with_backoff()
    def create_folder(self, name, parent_folder_id=None, client_code=None):
        """Create a folder on Drive. Returns the folder ID."""
        if parent_folder_id:
            _guard(client_code, parent_folder_id)

        service = _get_service()
        metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_folder_id:
            metadata['parents'] = [parent_folder_id]
        result = service.files().create(body=metadata, fields='id').execute()
        _audit(client_code, result['id'], name, 'WRITE')
        return result['id']

    @retry_with_backoff()
    def share_folder(self, folder_id, email, role='writer'):
        """Share a folder with an email address.

        Google-specific — not part of StorageClient interface.
        """
        service = _get_service()
        permission = {'type': 'user', 'role': role, 'emailAddress': email}
        service.permissions().create(
            fileId=folder_id, body=permission, sendNotificationEmail=False
        ).execute()

    @retry_with_backoff()
    def delete_file(self, file_id, client_code=None):
        """Permanently delete a file from Drive.

        Google-specific — not part of StorageClient interface.
        Used by config_backup retention to remove old backups.
        """
        service = _get_service()
        service.files().delete(fileId=file_id).execute()
        _audit(client_code, file_id, file_id, 'DELETE')

    def upload_or_update_json(self, folder_id, filename, data, client_code=None):
        """Upload JSON to Drive, updating if it already exists. Returns file ID."""
        _guard(client_code, folder_id)

        content = json.dumps(data, indent=2)
        existing = self.find_file_by_name(folder_id, filename)
        if existing:
            self.update_file_bytes(existing['id'], content)
            _audit(client_code, existing['id'], filename, 'WRITE')
            return existing['id']
        file_id = self.upload_bytes(content, folder_id, filename)
        _audit(client_code, file_id, filename, 'WRITE')
        return file_id


# ═══════════════════════════════════════════════════════════════════
# Backward-compatible module-level functions
# ═══════════════════════════════════════════════════════════════════
# Every existing ``from scripts.utils.drive_client import X`` still works.

_default_client = GoogleDriveClient()


def list_files(folder_id, mime_type=None, client_code=None):
    return _default_client.list_files(folder_id, mime_type=mime_type, client_code=client_code)


def download_file(file_id, destination_path, client_code=None):
    return _default_client.download_file(file_id, destination_path, client_code=client_code)


def download_file_bytes(file_id, client_code=None):
    return _default_client.download_file_bytes(file_id, client_code=client_code)


def export_file(file_id, mime_type='text/plain', client_code=None):
    return _default_client.export_file(file_id, mime_type=mime_type, client_code=client_code)


def find_file_by_name(folder_id, filename, client_code=None):
    return _default_client.find_file_by_name(folder_id, filename, client_code=client_code)


def download_json(folder_id, filename, client_code=None):
    return _default_client.download_json(folder_id, filename, client_code=client_code)


def get_file_metadata(file_id):
    return _default_client.get_file_metadata(file_id)


def upload_file(local_path, folder_id, filename=None, mime_type=None, client_code=None):
    return _default_client.upload_file(local_path, folder_id, filename=filename, mime_type=mime_type, client_code=client_code)


def upload_bytes(content, folder_id, filename, mime_type='application/json', client_code=None):
    return _default_client.upload_bytes(content, folder_id, filename, mime_type=mime_type, client_code=client_code)


def update_file(file_id, local_path, mime_type=None, client_code=None):
    return _default_client.update_file(file_id, local_path, mime_type=mime_type, client_code=client_code)


def update_file_bytes(file_id, content, mime_type='application/json', client_code=None):
    return _default_client.update_file_bytes(file_id, content, mime_type=mime_type, client_code=client_code)


def move_file(file_id, from_folder_id, to_folder_id, client_code=None):
    return _default_client.move_file(file_id, from_folder_id, to_folder_id, client_code=client_code)


def create_folder(name, parent_folder_id=None, client_code=None):
    return _default_client.create_folder(name, parent_folder_id=parent_folder_id, client_code=client_code)


def share_folder(folder_id, email, role='writer'):
    return _default_client.share_folder(folder_id, email, role=role)


def delete_file(file_id, client_code=None):
    return _default_client.delete_file(file_id, client_code=client_code)


def upload_or_update_json(folder_id, filename, data, client_code=None):
    return _default_client.upload_or_update_json(folder_id, filename, data, client_code=client_code)
