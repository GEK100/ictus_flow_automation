"""Google Drive API wrapper for Ictus Flow."""

import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaInMemoryUpload
from dotenv import load_dotenv

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


def list_files(folder_id, mime_type=None):
    """List files in a Drive folder.

    Returns list of dicts with id, name, mimeType, modifiedTime, size.
    """
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


def download_file(file_id, destination_path):
    """Download a file from Drive to a local path. Returns the path."""
    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    with open(destination_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return destination_path


def download_file_bytes(file_id):
    """Download a file from Drive and return bytes."""
    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def export_file(file_id, mime_type='text/plain'):
    """Export a Google Docs/Sheets/Slides file. Returns bytes."""
    service = _get_service()
    return service.files().export(fileId=file_id, mimeType=mime_type).execute()


def upload_file(local_path, folder_id, filename=None, mime_type=None):
    """Upload a local file to a Drive folder. Returns the file ID."""
    service = _get_service()
    if filename is None:
        filename = os.path.basename(local_path)
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    result = service.files().create(
        body=file_metadata, media_body=media, fields='id'
    ).execute()
    return result['id']


def upload_bytes(content, folder_id, filename, mime_type='application/json'):
    """Upload bytes/string content to a Drive folder. Returns file ID."""
    service = _get_service()
    if isinstance(content, str):
        content = content.encode('utf-8')
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=True)
    result = service.files().create(
        body=file_metadata, media_body=media, fields='id'
    ).execute()
    return result['id']


def update_file(file_id, local_path, mime_type=None):
    """Update an existing file's content on Drive."""
    service = _get_service()
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()


def update_file_bytes(file_id, content, mime_type='application/json'):
    """Update an existing file's content with bytes/string."""
    service = _get_service()
    if isinstance(content, str):
        content = content.encode('utf-8')
    media = MediaInMemoryUpload(content, mimetype=mime_type, resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()


def move_file(file_id, from_folder_id, to_folder_id):
    """Move a file between folders."""
    service = _get_service()
    service.files().update(
        fileId=file_id,
        addParents=to_folder_id,
        removeParents=from_folder_id,
    ).execute()


def create_folder(name, parent_folder_id=None):
    """Create a folder on Drive. Returns the folder ID."""
    service = _get_service()
    metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_folder_id:
        metadata['parents'] = [parent_folder_id]
    result = service.files().create(body=metadata, fields='id').execute()
    return result['id']


def share_folder(folder_id, email, role='writer'):
    """Share a folder with an email address (reader/writer/owner)."""
    service = _get_service()
    permission = {'type': 'user', 'role': role, 'emailAddress': email}
    service.permissions().create(
        fileId=folder_id, body=permission, sendNotificationEmail=False
    ).execute()


def get_file_metadata(file_id):
    """Get metadata for a file."""
    service = _get_service()
    return service.files().get(
        fileId=file_id,
        fields='id, name, mimeType, modifiedTime, size, parents',
    ).execute()


def find_file_by_name(folder_id, filename):
    """Find a file by name in a folder. Returns file dict or None."""
    service = _get_service()
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    resp = service.files().list(q=query, fields='files(id, name)').execute()
    files = resp.get('files', [])
    return files[0] if files else None


def upload_or_update_json(folder_id, filename, data):
    """Upload JSON to Drive, updating if it already exists. Returns file ID."""
    content = json.dumps(data, indent=2)
    existing = find_file_by_name(folder_id, filename)
    if existing:
        update_file_bytes(existing['id'], content)
        return existing['id']
    return upload_bytes(content, folder_id, filename)


def download_json(folder_id, filename):
    """Download and parse a JSON file from a folder. Returns dict or None."""
    existing = find_file_by_name(folder_id, filename)
    if not existing:
        return None
    content = download_file_bytes(existing['id'])
    return json.loads(content.decode('utf-8'))
