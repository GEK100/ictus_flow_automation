"""Tests for CX-04: Client Error Flagging on Tracking Sheet.

Tests the review dropdown validation, get_flagged_rows logic, and
correction_logger integration — all without API/Drive calls.

Run: python -m pytest tests/cx/test_client_flagging.py -v
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.sheets_client import (
    REVIEW_VALUES,
    COL_CLIENT_REVIEW,
    COL_CLIENT_NOTES,
    get_flagged_rows,
    TRACKING_HEADERS,
)


# ── Helpers ────────────────────────────────────────────────────────

def _make_row(file_name, status, workflow, notes='', review='', client_notes=''):
    """Build a tracking row with all 12 columns (A-L)."""
    return [
        file_name,        # A: File Name
        '2026-03-01',     # B: Date Received
        'invoice',        # C: Classification
        '0.95',           # D: Confidence
        status,           # E: Status
        workflow,          # F: Workflow
        '4.5',            # G: QA Score
        'PASS',           # H: QA Status
        notes,            # I: Notes
        '2026-03-02',     # J: Completed Date
        review,           # K: Client Review
        client_notes,     # L: Client Notes
    ]


HEADER_ROW = TRACKING_HEADERS


# ── Test 1: Review dropdown only allows valid values ──────────────

class TestReviewDropdownValues:

    def test_review_dropdown_values(self):
        """Data validation only allows the four values: Correct, Wrong, Needs Review, blank."""
        assert 'Correct' in REVIEW_VALUES
        assert 'Wrong' in REVIEW_VALUES
        assert 'Needs Review' in REVIEW_VALUES
        assert '' in REVIEW_VALUES
        assert len(REVIEW_VALUES) == 4

    def test_tracking_headers_include_review_columns(self):
        """Tracking headers include Client Review and Client Notes."""
        assert 'Client Review' in TRACKING_HEADERS
        assert 'Client Notes' in TRACKING_HEADERS
        assert TRACKING_HEADERS.index('Client Review') == COL_CLIENT_REVIEW
        assert TRACKING_HEADERS.index('Client Notes') == COL_CLIENT_NOTES


# ── Test 2: get_flagged_rows returns rows marked Wrong ────────────

class TestGetFlaggedRowsReturnsWrong:

    @patch('scripts.utils.sheets_client.read_sheet')
    def test_get_flagged_rows_returns_wrong(self, mock_read):
        wrong_row = _make_row('inv_001.pdf', 'COMPLETED', 'invoice', review='Wrong', client_notes='VAT is wrong')
        correct_row = _make_row('inv_002.pdf', 'COMPLETED', 'invoice', review='Correct')
        needs_review = _make_row('inv_003.pdf', 'COMPLETED', 'invoice', review='Needs Review', client_notes='Check totals')

        mock_read.return_value = [HEADER_ROW, wrong_row, correct_row, needs_review]

        flagged = get_flagged_rows('fake-sheet-id')

        assert len(flagged) == 2
        assert flagged[0]['row_number'] == 2
        assert flagged[0]['row_data'][COL_CLIENT_REVIEW] == 'Wrong'
        assert flagged[1]['row_number'] == 4
        assert flagged[1]['row_data'][COL_CLIENT_REVIEW] == 'Needs Review'


# ── Test 3: get_flagged_rows ignores Correct ──────────────────────

class TestGetFlaggedRowsIgnoresCorrect:

    @patch('scripts.utils.sheets_client.read_sheet')
    def test_get_flagged_rows_ignores_correct(self, mock_read):
        correct_row = _make_row('inv_001.pdf', 'COMPLETED', 'invoice', review='Correct')
        blank_row = _make_row('inv_002.pdf', 'COMPLETED', 'invoice', review='')
        logged_row = _make_row('inv_003.pdf', 'COMPLETED', 'invoice', review='Logged')

        mock_read.return_value = [HEADER_ROW, correct_row, blank_row, logged_row]

        flagged = get_flagged_rows('fake-sheet-id')

        assert len(flagged) == 0


# ── Test 4: Correction logger picks up flagged rows ───────────────

class TestCorrectionLoggerPicksUpFlags:

    @patch('scripts.skills.correction_logger.save_corrections')
    @patch('scripts.skills.correction_logger.load_corrections')
    @patch('scripts.skills.correction_logger.categorise_changes')
    @patch('scripts.skills.correction_logger.sheets_client')
    @patch('scripts.skills.correction_logger.load_client_config')
    def test_correction_logger_picks_up_flags(
        self, mock_config, mock_sheets, mock_categorise,
        mock_load_corr, mock_save_corr,
    ):
        from scripts.skills.correction_logger import run_manual_notes

        mock_config.return_value = {
            'tracking_sheet_id': 'sheet-123',
            'folders': {'learning': 'learn-folder-id'},
        }

        # No CORRECTION: notes, but one flagged row
        wrong_row = _make_row('inv_001.pdf', 'COMPLETED', 'invoice',
                              review='Wrong', client_notes='The total is incorrect')
        mock_sheets.read_sheet.return_value = [HEADER_ROW, wrong_row]
        mock_sheets.get_flagged_rows.return_value = [
            {'row_number': 2, 'row_data': wrong_row},
        ]

        mock_categorise.return_value = [{
            'id': 'test-id',
            'timestamp': '2026-03-07',
            'workflow': 'invoice',
            'category': 'numerical_error',
            'field': 'total',
            'original_value': '100',
            'corrected_value': '120',
            'cause': 'wrong calculation',
            'source': 'client-flag',
            'promoted_to': None,
        }]

        mock_load_corr.return_value = {'corrections': []}

        result = run_manual_notes('GILM')

        assert len(result) == 1
        assert result[0]['source'] == 'client-flag'
        mock_categorise.assert_called_once()
        mock_save_corr.assert_called_once()


# ── Test 5: Processed flag changes to Logged ──────────────────────

class TestProcessedFlagChangesToLogged:

    @patch('scripts.skills.correction_logger.save_corrections')
    @patch('scripts.skills.correction_logger.load_corrections')
    @patch('scripts.skills.correction_logger.categorise_changes')
    @patch('scripts.skills.correction_logger.sheets_client')
    @patch('scripts.skills.correction_logger.load_client_config')
    def test_processed_flag_changes_to_logged(
        self, mock_config, mock_sheets, mock_categorise,
        mock_load_corr, mock_save_corr,
    ):
        from scripts.skills.correction_logger import run_manual_notes, COL_CLIENT_REVIEW

        mock_config.return_value = {
            'tracking_sheet_id': 'sheet-123',
            'folders': {'learning': 'learn-folder-id'},
        }

        wrong_row = _make_row('inv_005.pdf', 'COMPLETED', 'invoice',
                              review='Wrong', client_notes='Date is wrong')
        mock_sheets.read_sheet.return_value = [HEADER_ROW, wrong_row]
        mock_sheets.get_flagged_rows.return_value = [
            {'row_number': 2, 'row_data': wrong_row},
        ]

        mock_categorise.return_value = [{
            'id': 'test-id-2',
            'timestamp': '2026-03-07',
            'workflow': 'invoice',
            'category': 'factual_error',
            'field': 'date',
            'original_value': '2026-01-01',
            'corrected_value': '2026-02-01',
            'cause': 'wrong date',
            'source': 'client-flag',
            'promoted_to': None,
        }]

        mock_load_corr.return_value = {'corrections': []}

        run_manual_notes('GILM')

        # Verify update_row_field was called with 'Logged' for the Client Review column
        mock_sheets.update_row_field.assert_any_call(
            'sheet-123', 2, COL_CLIENT_REVIEW, 'Logged'
        )
