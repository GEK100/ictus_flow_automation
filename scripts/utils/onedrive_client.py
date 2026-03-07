"""SCA-05: OneDrive stub — placeholder for future implementation.

Every method raises NotImplementedError so the system fails fast if
a client config sets ``"platform": "onedrive"`` before the integration
is ready.
"""

from scripts.utils.storage_interface import StorageClient


class OneDriveClient(StorageClient):
    """OneDrive implementation of StorageClient (stub)."""

    _NOT_IMPL = 'OneDrive integration is not yet implemented.'

    # ── Read operations ───────────────────────────────────────────

    def list_files(self, folder_id, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def download_file(self, file_id, destination_path, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def download_file_bytes(self, file_id, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def find_file_by_name(self, folder_id, filename, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def download_json(self, folder_id, filename, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def get_file_metadata(self, file_id):
        raise NotImplementedError(self._NOT_IMPL)

    # ── Write operations ──────────────────────────────────────────

    def upload_file(self, local_path, folder_id, filename=None, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def upload_bytes(self, content, folder_id, filename, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def move_file(self, file_id, from_folder_id, to_folder_id, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def create_folder(self, name, parent_id=None, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)

    def upload_or_update_json(self, folder_id, filename, data, client_code=None):
        raise NotImplementedError(self._NOT_IMPL)
