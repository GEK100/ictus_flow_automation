"""Tests for OPS-01: Failed File Handling.

Tests the handle_failure() function in drive_watcher.py,
the route_file() function in processor.py, and the
add_failed_row_formatting() function in sheets_client.py.

All Drive/Sheets/Resend calls are mocked — no real API calls.
"""

import importlib
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on the path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CLIENT = {
    'client_name': 'Test Client',
    'client_code': 'TEST',
    'contact_email': 'client@example.com',
    'tracking_sheet_id': 'SHEET_123',
    'folders': {
        'root': 'ROOT_ID',
        'inbox': 'INBOX_ID',
        'processing': 'PROC_ID',
        'completed': 'COMP_ID',
        'failed': 'FAILED_ID',
    },
}

SAMPLE_CLIENT_NO_FAILED = {
    'client_name': 'Legacy Client',
    'client_code': 'LGCY',
    'contact_email': 'legacy@example.com',
    'tracking_sheet_id': 'SHEET_456',
    'folders': {
        'root': 'ROOT_ID',
        'inbox': 'INBOX_ID',
        'processing': 'PROC_ID',
        'completed': 'COMP_ID',
    },
}

SAMPLE_FILE = {'id': 'FILE_001', 'name': 'invoice_test.pdf'}


def _import_handle_failure():
    """Import handle_failure from drive_watcher without triggering module-level code.

    drive_watcher.py has module-level code (API clients, file loads) that
    would fail in tests. We mock those out before importing.
    """
    # Remove cached module if any
    for mod_name in list(sys.modules.keys()):
        if 'drive_watcher' in mod_name:
            del sys.modules[mod_name]

    with patch.dict(os.environ, {
        'GOOGLE_SERVICE_ACCOUNT_JSON': 'fake.json',
        'MODEL_CLASSIFIER': 'claude-3-haiku-20240307',
    }):
        with patch('google.oauth2.service_account.Credentials.from_service_account_file'):
            with patch('googleapiclient.discovery.build'):
                with patch('anthropic.Anthropic'):
                    with patch('builtins.open', MagicMock()):
                        with patch('glob.glob', return_value=[]):
                            with patch('scripts.utils.client_guard.validate_client_operation'):
                                import scripts.drive_watcher as dw
                                return dw.handle_failure


# ---------------------------------------------------------------------------
# handle_failure tests
# ---------------------------------------------------------------------------

class TestHandleFailure:
    """Tests for drive_watcher.handle_failure()."""

    @patch('scripts.utils.resend_client.send_admin_notification')
    @patch('scripts.utils.sheets_client.append_row')
    @patch('scripts.utils.sheets_client.update_row_field')
    @patch('scripts.utils.sheets_client.find_row_by_value', return_value=(3, ['invoice_test.pdf']))
    @patch('scripts.utils.drive_client.move_file')
    def test_handle_failure_moves_file(
        self, mock_move, mock_find, mock_update, mock_append, mock_email
    ):
        handle_failure = _import_handle_failure()
        handle_failure(SAMPLE_CLIENT, SAMPLE_FILE, 'Test error', 'INBOX_ID')

        mock_move.assert_called_once_with(
            'FILE_001', 'INBOX_ID', 'FAILED_ID', client_code='TEST'
        )

    @patch('scripts.utils.resend_client.send_admin_notification')
    @patch('scripts.utils.sheets_client.append_row')
    @patch('scripts.utils.sheets_client.update_row_field')
    @patch('scripts.utils.sheets_client.find_row_by_value', return_value=(3, ['invoice_test.pdf']))
    @patch('scripts.utils.drive_client.move_file')
    def test_handle_failure_updates_tracking_sheet(
        self, mock_move, mock_find, mock_update, mock_append, mock_email
    ):
        handle_failure = _import_handle_failure()
        handle_failure(SAMPLE_CLIENT, SAMPLE_FILE, 'Classification failed', 'INBOX_ID')

        mock_find.assert_called_once_with('SHEET_123', 0, 'invoice_test.pdf')
        # Status (col 4) = 'FAILED'
        mock_update.assert_any_call('SHEET_123', 3, 4, 'FAILED')
        # Notes (col 8) = error message
        mock_update.assert_any_call('SHEET_123', 3, 8, 'Classification failed')
        # Should NOT append a new row since the file was found
        mock_append.assert_not_called()

    @patch('scripts.utils.resend_client.send_admin_notification')
    @patch('scripts.utils.sheets_client.append_row')
    @patch('scripts.utils.sheets_client.update_row_field')
    @patch('scripts.utils.sheets_client.find_row_by_value', return_value=(3, ['invoice_test.pdf']))
    @patch('scripts.utils.drive_client.move_file')
    def test_handle_failure_sends_alert_email(
        self, mock_move, mock_find, mock_update, mock_append, mock_email
    ):
        handle_failure = _import_handle_failure()
        handle_failure(SAMPLE_CLIENT, SAMPLE_FILE, 'OCR failed', 'INBOX_ID')

        mock_email.assert_called_once()
        subject = mock_email.call_args[0][0]
        body = mock_email.call_args[0][1]
        assert 'FAILED' in subject
        assert 'invoice_test.pdf' in subject
        assert 'TEST' in subject
        assert 'OCR failed' in body
        assert 'Test Client' in body

    @patch('scripts.utils.resend_client.send_admin_notification')
    @patch('scripts.utils.sheets_client.append_row')
    @patch('scripts.utils.sheets_client.update_row_field')
    @patch('scripts.utils.sheets_client.find_row_by_value', return_value=(3, ['invoice_test.pdf']))
    @patch('scripts.utils.drive_client.move_file')
    def test_handle_failure_no_failed_folder(
        self, mock_move, mock_find, mock_update, mock_append, mock_email
    ):
        """When 'failed' key is missing from folders, file is NOT moved but sheet+email still fire."""
        handle_failure = _import_handle_failure()
        handle_failure(SAMPLE_CLIENT_NO_FAILED, SAMPLE_FILE, 'Error msg', 'INBOX_ID')

        # move_file should NOT be called
        mock_move.assert_not_called()
        # But sheet and email should still work
        mock_find.assert_called_once()
        mock_update.assert_called()
        mock_email.assert_called_once()

    @patch('scripts.utils.resend_client.send_admin_notification')
    @patch('scripts.utils.sheets_client.append_row')
    @patch('scripts.utils.sheets_client.update_row_field')
    @patch('scripts.utils.sheets_client.find_row_by_value', return_value=(None, None))
    @patch('scripts.utils.drive_client.move_file')
    def test_handle_failure_file_not_in_sheet(
        self, mock_move, mock_find, mock_update, mock_append, mock_email
    ):
        """When file has no tracking row yet, a new FAILED row is appended."""
        handle_failure = _import_handle_failure()
        handle_failure(SAMPLE_CLIENT, SAMPLE_FILE, 'Early failure', 'INBOX_ID')

        mock_find.assert_called_once()
        # update_row_field should NOT be called (no row to update)
        mock_update.assert_not_called()
        # append_row SHOULD be called with FAILED status
        mock_append.assert_called_once()
        row_data = mock_append.call_args[0][1]
        assert row_data[0] == 'invoice_test.pdf'  # File Name
        assert row_data[4] == 'FAILED'              # Status
        assert row_data[8] == 'Early failure'        # Notes


# ---------------------------------------------------------------------------
# processor.route_file tests
# ---------------------------------------------------------------------------

class TestRouteFile:
    """Tests for processor.route_file()."""

    def test_route_file_unknown_classification(self):
        from scripts.processor import route_file

        with pytest.raises(ValueError, match="No handler for classification 'unknown_type'"):
            route_file('/tmp/test.pdf', 'unknown_type', SAMPLE_CLIENT)

    def test_route_file_valid_classification(self):
        from scripts.processor import route_file

        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_import.return_value = mock_module

            route_file('/tmp/test.pdf', 'invoice', SAMPLE_CLIENT)

            mock_import.assert_called_once_with('scripts.handlers.invoice_handler')
            mock_module.process.assert_called_once_with('/tmp/test.pdf', SAMPLE_CLIENT)

    def test_route_file_case_insensitive(self):
        from scripts.processor import route_file

        with patch('importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_import.return_value = mock_module

            route_file('/tmp/test.pdf', '  Invoice  ', SAMPLE_CLIENT)

            mock_import.assert_called_once_with('scripts.handlers.invoice_handler')

    def test_handler_map_covers_all_handlers(self):
        """Verify HANDLER_MAP covers all 12 handler files."""
        from scripts.processor import HANDLER_MAP

        expected = {
            'invoice', 'letter', 'contract', 'tender', 'rams', 'cis',
            'payment_cert', 'credit_control', 'quote', 'blog',
            'progress_report', 'compliance',
        }
        assert set(HANDLER_MAP.keys()) == expected


# ---------------------------------------------------------------------------
# add_failed_row_formatting tests
# ---------------------------------------------------------------------------

class TestFailedRowFormatting:
    """Tests for sheets_client.add_failed_row_formatting()."""

    @patch('scripts.utils.sheets_client._get_service')
    def test_add_failed_row_formatting(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # Mock the get() call that fetches sheet metadata
        mock_service.spreadsheets().get().execute.return_value = {
            'sheets': [{'properties': {'sheetId': 0}}]
        }

        from scripts.utils.sheets_client import add_failed_row_formatting
        add_failed_row_formatting('SHEET_123')

        # Verify batchUpdate was called
        mock_service.spreadsheets().batchUpdate.assert_called_once()
        call_kwargs = mock_service.spreadsheets().batchUpdate.call_args
        body = call_kwargs[1]['body'] if 'body' in call_kwargs[1] else call_kwargs[0][0]
        requests = body['requests']
        assert len(requests) == 1

        rule = requests[0]['addConditionalFormatRule']['rule']
        # Check the formula references FAILED
        condition = rule['booleanRule']['condition']
        assert condition['type'] == 'CUSTOM_FORMULA'
        assert 'FAILED' in condition['values'][0]['userEnteredValue']

        # Check the format has a reddish background and bold text
        fmt = rule['booleanRule']['format']
        assert fmt['backgroundColor']['red'] == 1.0
        assert fmt['textFormat']['bold'] is True
