"""SCA-05: Factory for obtaining the correct StorageClient per client.

Usage in any processing loop::

    from scripts.utils.storage_factory import get_storage_client

    storage = get_storage_client(client_config)
    files   = storage.list_files(inbox_folder_id)
"""

from scripts.utils.storage_interface import StorageClient


def get_storage_client(client_config=None):
    """Return the correct StorageClient for the given client config.

    Args:
        client_config: Client config dict (from config/clients/*.json).
                       If None or missing ``platform`` key, defaults to
                       ``"google"``.

    Returns:
        StorageClient: A GoogleDriveClient or OneDriveClient instance.

    Raises:
        ValueError: If ``platform`` is not a supported value.
    """
    platform = 'google'
    if client_config:
        platform = client_config.get('platform', 'google')

    if platform == 'google':
        from scripts.utils.drive_client import GoogleDriveClient
        return GoogleDriveClient()

    if platform == 'onedrive':
        from scripts.utils.onedrive_client import OneDriveClient
        return OneDriveClient()

    raise ValueError(
        f"Unsupported storage platform: '{platform}'. "
        f"Supported values: 'google', 'onedrive'."
    )
