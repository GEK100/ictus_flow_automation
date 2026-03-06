"""Tests for SEC-02: Client Data Isolation Enforcement.

Tests the client_guard module to ensure cross-client data leakage is blocked.
Run: python -m pytest tests/security/test_client_boundary.py -v
"""

import sys
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

TEST_DIR = Path(__file__).parent
PROJECT_ROOT = TEST_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.client_guard import (
    validate_client_operation,
    enforce_client_boundary,
    ClientBoundaryError,
)


# ── Mock client configs ────────────────────────────────────────────

CLIENT_A_CONFIG = {
    'client_name': 'Alpha Corp',
    'client_code': 'ALPH',
    'contact_email': 'alpha@example.com',
    'folders': {
        'root': 'folder_A_root',
        'inbox': 'folder_A_inbox',
        'processing': 'folder_A_processing',
        'completed': 'folder_A_completed',
        'archive': 'folder_A_archive',
        'brand_assets': 'folder_A_brand',
        'templates': 'folder_A_templates',
        'learning': 'folder_A_learning',
    },
    'tracking_sheet_id': 'sheet_A',
}

CLIENT_B_CONFIG = {
    'client_name': 'Bravo Ltd',
    'client_code': 'BRAV',
    'contact_email': 'bravo@example.com',
    'folders': {
        'root': 'folder_B_root',
        'inbox': 'folder_B_inbox',
        'processing': 'folder_B_processing',
        'completed': 'folder_B_completed',
        'archive': 'folder_B_archive',
        'brand_assets': 'folder_B_brand',
        'templates': 'folder_B_templates',
        'learning': 'folder_B_learning',
    },
    'tracking_sheet_id': 'sheet_B',
}


def mock_load_client_config(client_code):
    """Mock config loader that returns test configs."""
    configs = {
        'ALPH': CLIENT_A_CONFIG,
        'alph': CLIENT_A_CONFIG,
        'BRAV': CLIENT_B_CONFIG,
        'brav': CLIENT_B_CONFIG,
    }
    return configs.get(client_code)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_config_loader():
    """Patch load_client_config for all tests in this module."""
    with patch(
        'scripts.utils.client_guard.validate_client_operation.__module__',
        create=True,
    ):
        pass
    with patch(
        'scripts.utils.prompt_builder.load_client_config',
        side_effect=mock_load_client_config,
    ):
        yield


@pytest.fixture
def security_log_path(tmp_path):
    """Redirect security log to a temp directory."""
    import logging
    import scripts.utils.client_guard as guard

    log_dir = tmp_path / 'logs'
    log_dir.mkdir()
    log_file = log_dir / 'security.log'

    # Clear any existing logger handlers and reset
    logger = logging.getLogger('ictus.security')
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    guard._security_logger = None

    original_root = guard.PROJECT_ROOT
    guard.PROJECT_ROOT = tmp_path

    yield log_file

    # Restore — close handlers, reset logger
    logger = logging.getLogger('ictus.security')
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    guard.PROJECT_ROOT = original_root
    guard._security_logger = None


# ── Test: Cross-client boundary violation ───────────────────────────

class TestClientBoundaryViolation:

    def test_cross_client_write_raises_error(self):
        """CLIENT_A code + CLIENT_B folder → ClientBoundaryError."""
        with pytest.raises(ClientBoundaryError) as exc_info:
            validate_client_operation('ALPH', 'folder_B_inbox')

        assert exc_info.value.client_code == 'ALPH'
        assert exc_info.value.target_folder_id == 'folder_B_inbox'
        assert 'BOUNDARY VIOLATION' in str(exc_info.value)

    def test_cross_client_reverse(self):
        """CLIENT_B code + CLIENT_A folder → ClientBoundaryError."""
        with pytest.raises(ClientBoundaryError):
            validate_client_operation('BRAV', 'folder_A_completed')

    def test_violation_logged_to_security_log(self, security_log_path):
        """Violation should be written to logs/security.log."""
        try:
            validate_client_operation('ALPH', 'folder_B_processing')
        except ClientBoundaryError:
            pass

        # Flush handlers
        import scripts.utils.client_guard as guard
        for handler in guard._get_security_logger().handlers:
            handler.flush()

        assert security_log_path.exists()
        log_content = security_log_path.read_text()
        assert 'ALPH' in log_content
        assert 'folder_B_processing' in log_content
        assert 'BOUNDARY_VIOLATION' in log_content

    def test_violation_log_contains_timestamp(self, security_log_path):
        """Log entry should contain a timestamp."""
        try:
            validate_client_operation('BRAV', 'folder_A_inbox')
        except ClientBoundaryError:
            pass

        import scripts.utils.client_guard as guard
        for handler in guard._get_security_logger().handlers:
            handler.flush()

        log_content = security_log_path.read_text()
        # Timestamp format: YYYY-MM-DD HH:MM:SS
        import re
        assert re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', log_content)


# ── Test: Valid same-client operations ──────────────────────────────

class TestValidSameClient:

    def test_same_client_inbox(self):
        """CLIENT_A code + CLIENT_A inbox folder → no exception."""
        validate_client_operation('ALPH', 'folder_A_inbox')

    def test_same_client_all_folders(self):
        """CLIENT_A code + each CLIENT_A folder → no exception."""
        for folder_id in CLIENT_A_CONFIG['folders'].values():
            validate_client_operation('ALPH', folder_id)

    def test_same_client_b(self):
        """CLIENT_B code + CLIENT_B folder → no exception."""
        validate_client_operation('BRAV', 'folder_B_learning')

    def test_completely_unknown_folder(self):
        """Known client + random folder ID → ClientBoundaryError."""
        with pytest.raises(ClientBoundaryError):
            validate_client_operation('ALPH', 'folder_UNKNOWN_xyz')


# ── Test: Unknown / missing client config ───────────────────────────

class TestMissingConfig:

    def test_unknown_client_raises_error(self):
        """Invalid client_code → ClientBoundaryError (not silent skip)."""
        with pytest.raises(ClientBoundaryError) as exc_info:
            validate_client_operation('NOPE', 'any_folder_id')

        assert 'CONFIG_NOT_FOUND' in str(exc_info.value) or 'config not found' in str(exc_info.value)

    def test_missing_config_raises_error(self):
        """Nonexistent client_code → error rather than silently skipping validation."""
        with pytest.raises(ClientBoundaryError) as exc_info:
            validate_client_operation('DOESNOTEXIST', 'folder_A_inbox')

        # Must not silently pass — must raise
        assert exc_info.value.client_code == 'DOESNOTEXIST'

    def test_missing_config_logged(self, security_log_path):
        """Missing config should be logged as a security event."""
        try:
            validate_client_operation('GHOST', 'some_folder')
        except ClientBoundaryError:
            pass

        import scripts.utils.client_guard as guard
        for handler in guard._get_security_logger().handlers:
            handler.flush()

        log_content = security_log_path.read_text()
        assert 'GHOST' in log_content
        assert 'CONFIG_NOT_FOUND' in log_content


# ── Test: Decorator ─────────────────────────────────────────────────

class TestDecorator:

    def test_decorator_blocks_violation(self):
        """@enforce_client_boundary raises on cross-boundary access."""

        @enforce_client_boundary
        def fake_upload(client_code, folder_id, data):
            return 'uploaded'

        with pytest.raises(ClientBoundaryError):
            fake_upload(client_code='ALPH', folder_id='folder_B_inbox', data='test')

    def test_decorator_allows_valid(self):
        """@enforce_client_boundary allows same-client access."""

        @enforce_client_boundary
        def fake_upload(client_code, folder_id, data):
            return 'uploaded'

        result = fake_upload(client_code='ALPH', folder_id='folder_A_inbox', data='test')
        assert result == 'uploaded'

    def test_decorator_positional_args(self):
        """Decorator works with positional arguments too."""

        @enforce_client_boundary
        def fake_upload(client_code, folder_id, data):
            return 'uploaded'

        result = fake_upload('ALPH', 'folder_A_completed', 'test')
        assert result == 'uploaded'

    def test_decorator_no_client_code_skips(self):
        """When client_code is None, validation is skipped (backward compat)."""

        @enforce_client_boundary
        def fake_upload(client_code, folder_id, data):
            return 'uploaded'

        result = fake_upload(client_code=None, folder_id='folder_B_inbox', data='test')
        assert result == 'uploaded'


# ── Test: Exception attributes ──────────────────────────────────────

class TestExceptionAttributes:

    def test_exception_has_client_code(self):
        """ClientBoundaryError stores client_code."""
        err = ClientBoundaryError('TEST', 'folder_123')
        assert err.client_code == 'TEST'

    def test_exception_has_folder_id(self):
        """ClientBoundaryError stores target_folder_id."""
        err = ClientBoundaryError('TEST', 'folder_123')
        assert err.target_folder_id == 'folder_123'

    def test_exception_message(self):
        """ClientBoundaryError has a descriptive message."""
        err = ClientBoundaryError('TEST', 'folder_123')
        assert 'TEST' in str(err)
        assert 'folder_123' in str(err)
        assert 'BOUNDARY VIOLATION' in str(err)

    def test_custom_message(self):
        """ClientBoundaryError accepts custom message."""
        err = ClientBoundaryError('X', 'Y', message='Custom error')
        assert str(err) == 'Custom error'
