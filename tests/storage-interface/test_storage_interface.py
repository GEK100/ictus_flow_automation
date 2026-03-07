"""Tests for SCA-05: Abstract Storage Layer for OneDrive Support.

Tests the StorageClient ABC, GoogleDriveClient class, OneDrive stub,
storage factory, template config, and drive_watcher integration.

Run: python -m pytest tests/storage-interface/test_storage_interface.py -v
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from abc import ABC

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.storage_interface import StorageClient
from scripts.utils.drive_client import GoogleDriveClient
from scripts.utils.onedrive_client import OneDriveClient
from scripts.utils.storage_factory import get_storage_client


# ── Test 1: StorageClient cannot be instantiated directly ─────────

class TestStorageClientIsAbstract:

    def test_storage_client_is_abstract(self):
        """StorageClient is an ABC — instantiation raises TypeError."""
        assert issubclass(StorageClient, ABC)
        with pytest.raises(TypeError):
            StorageClient()


# ── Test 2: GoogleDriveClient is a StorageClient ─────────────────

class TestGoogleDriveClientIsStorageClient:

    def test_google_drive_client_is_storage_client(self):
        """GoogleDriveClient inherits from StorageClient."""
        assert issubclass(GoogleDriveClient, StorageClient)
        client = GoogleDriveClient()
        assert isinstance(client, StorageClient)


# ── Test 3: OneDriveClient raises NotImplementedError ────────────

class TestOneDriveClientRaisesNotImplemented:

    def test_onedrive_list_files_raises(self):
        """Every OneDriveClient method raises NotImplementedError."""
        client = OneDriveClient()
        assert isinstance(client, StorageClient)

        with pytest.raises(NotImplementedError):
            client.list_files('folder123')

    def test_onedrive_download_file_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.download_file('file123', '/tmp/out.pdf')

    def test_onedrive_upload_file_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.upload_file('/tmp/in.pdf', 'folder123')

    def test_onedrive_move_file_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.move_file('file123', 'from_folder', 'to_folder')

    def test_onedrive_create_folder_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.create_folder('New Folder')

    def test_onedrive_download_json_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.download_json('folder123', 'data.json')

    def test_onedrive_upload_or_update_json_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.upload_or_update_json('folder123', 'data.json', {'key': 'value'})

    def test_onedrive_find_file_by_name_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.find_file_by_name('folder123', 'test.pdf')

    def test_onedrive_download_file_bytes_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.download_file_bytes('file123')

    def test_onedrive_upload_bytes_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.upload_bytes(b'data', 'folder123', 'test.bin')

    def test_onedrive_get_file_metadata_raises(self):
        client = OneDriveClient()
        with pytest.raises(NotImplementedError):
            client.get_file_metadata('file123')


# ── Test 4: Factory returns GoogleDriveClient for platform=google ─

class TestFactoryReturnsGoogleForGoogle:

    def test_factory_google_explicit(self):
        """get_storage_client({'platform': 'google'}) -> GoogleDriveClient."""
        client = get_storage_client({'platform': 'google'})
        assert isinstance(client, GoogleDriveClient)

    def test_factory_google_default(self):
        """get_storage_client({}) defaults to GoogleDriveClient."""
        client = get_storage_client({})
        assert isinstance(client, GoogleDriveClient)

    def test_factory_none_defaults_to_google(self):
        """get_storage_client(None) defaults to GoogleDriveClient."""
        client = get_storage_client(None)
        assert isinstance(client, GoogleDriveClient)


# ── Test 5: Factory returns OneDriveClient for platform=onedrive ──

class TestFactoryReturnsOneDriveForOneDrive:

    def test_factory_onedrive(self):
        """get_storage_client({'platform': 'onedrive'}) -> OneDriveClient."""
        client = get_storage_client({'platform': 'onedrive'})
        assert isinstance(client, OneDriveClient)


# ── Test 6: Factory raises ValueError for unknown platform ────────

class TestFactoryRaisesForUnknownPlatform:

    def test_factory_unknown_raises(self):
        """get_storage_client({'platform': 'dropbox'}) -> ValueError."""
        with pytest.raises(ValueError, match='Unsupported storage platform'):
            get_storage_client({'platform': 'dropbox'})


# ── Test 7: Client template includes platform field ───────────────

class TestTemplateIncludesPlatform:

    def test_template_has_platform_google(self):
        """config/clients/_template.json has 'platform': 'google'."""
        template_path = PROJECT_ROOT / 'config' / 'clients' / '_template.json'
        with open(template_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        assert 'platform' in config, "Template missing 'platform' field"
        assert config['platform'] == 'google'
