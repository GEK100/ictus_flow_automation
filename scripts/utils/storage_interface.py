"""SCA-05: Abstract storage interface for Ictus Flow.

Defines StorageClient — a base class that both GoogleDriveClient and
OneDriveClient implement.  Any code that needs file operations should depend
on this interface so the underlying platform can be swapped per-client.
"""

from abc import ABC, abstractmethod


class StorageClient(ABC):
    """Platform-agnostic file-storage operations.

    Every concrete subclass must implement the abstract methods below.
    Signatures use generic names (folder_id, file_id) — each platform maps
    them to its own identifiers (Drive folder ID, OneDrive item ID, etc.).
    """

    # ── Read operations ───────────────────────────────────────────

    @abstractmethod
    def list_files(self, folder_id, client_code=None):
        """List files in a folder.

        Returns:
            list[dict]: Each dict has at least {id, name, mimeType}.
        """

    @abstractmethod
    def download_file(self, file_id, destination_path, client_code=None):
        """Download a file to a local path.

        Returns:
            str: The destination path.
        """

    @abstractmethod
    def download_file_bytes(self, file_id, client_code=None):
        """Download a file and return raw bytes.

        Returns:
            bytes
        """

    @abstractmethod
    def find_file_by_name(self, folder_id, filename, client_code=None):
        """Find a single file by exact name in a folder.

        Returns:
            dict or None: File dict with at least {id, name}, or None.
        """

    @abstractmethod
    def download_json(self, folder_id, filename, client_code=None):
        """Download and parse a JSON file from a folder.

        Returns:
            dict or None
        """

    @abstractmethod
    def get_file_metadata(self, file_id):
        """Get metadata for a file.

        Returns:
            dict: Platform-specific metadata dict.
        """

    # ── Write operations ──────────────────────────────────────────

    @abstractmethod
    def upload_file(self, local_path, folder_id, filename=None, client_code=None):
        """Upload a local file to a folder.

        Returns:
            str: The new file's ID.
        """

    @abstractmethod
    def upload_bytes(self, content, folder_id, filename, client_code=None):
        """Upload bytes/string content to a folder.

        Returns:
            str: The new file's ID.
        """

    @abstractmethod
    def move_file(self, file_id, from_folder_id, to_folder_id, client_code=None):
        """Move a file between folders.

        Returns:
            None
        """

    @abstractmethod
    def create_folder(self, name, parent_id=None, client_code=None):
        """Create a folder.

        Returns:
            str: The new folder's ID.
        """

    @abstractmethod
    def upload_or_update_json(self, folder_id, filename, data, client_code=None):
        """Upload JSON to storage, updating if it already exists.

        Returns:
            str: The file ID.
        """
