"""Tests for OPS-02: API Credit Monitoring and Circuit Breaker.

Tests the credit_monitor module and the updated cost_logger.
All tests use tmp_path with sample CSV data — no real API calls.
"""

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on the path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADERS = [
    'timestamp', 'client_code', 'workflow', 'model',
    'input_tokens', 'output_tokens', 'estimated_cost',
]


def _write_sample_csv(csv_path, rows):
    """Write a sample cost CSV with headers and given rows."""
    os.makedirs(csv_path.parent, exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for row in rows:
            writer.writerow(row)


def _current_month():
    return datetime.now().strftime('%Y-%m')


# ---------------------------------------------------------------------------
# cost_logger tests
# ---------------------------------------------------------------------------

class TestCostLogger:
    """Tests for utils/cost_logger.py."""

    def test_ensure_csv_creates_file_with_headers(self, tmp_path):
        """CSV is created with headers when it doesn't exist."""
        csv_path = tmp_path / 'logs' / 'api_costs.csv'

        with patch('utils.cost_logger.COST_CSV', csv_path):
            from utils.cost_logger import _ensure_csv
            _ensure_csv()

        assert csv_path.exists()
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == HEADERS

    def test_log_api_call_appends_row(self, tmp_path):
        """log_api_call appends a row with correct cost calculation."""
        csv_path = tmp_path / 'logs' / 'api_costs.csv'

        with patch('utils.cost_logger.COST_CSV', csv_path):
            from utils.cost_logger import log_api_call
            log_api_call('TEST', 'classification',
                         'claude-haiku-4-5-20251001', 1000, 500)

        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)

        assert row[1] == 'TEST'
        assert row[2] == 'classification'
        assert row[3] == 'claude-haiku-4-5-20251001'
        assert row[4] == '1000'
        assert row[5] == '500'
        # Cost: (1000 * 0.80 + 500 * 4.00) / 1_000_000 = 0.002800
        assert float(row[6]) == pytest.approx(0.002800, abs=1e-6)


# ---------------------------------------------------------------------------
# credit_monitor tests
# ---------------------------------------------------------------------------

class TestGetMonthlySpend:
    """Tests for credit_monitor.get_monthly_spend()."""

    def test_get_monthly_spend_filters_by_month(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        _write_sample_csv(csv_path, [
            [f'{current}-01T10:00:00', 'TEST', 'classify', 'haiku', 100, 50, '0.010000'],
            [f'{current}-15T10:00:00', 'TEST', 'invoice', 'sonnet', 200, 100, '0.020000'],
            ['2025-01-01T10:00:00', 'OLD', 'classify', 'haiku', 100, 50, '0.500000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path):
            from scripts.utils.credit_monitor import get_monthly_spend
            spend = get_monthly_spend(current)

        assert spend == pytest.approx(0.03, abs=1e-6)

    def test_get_monthly_spend_empty_csv(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        _write_sample_csv(csv_path, [])  # header only, no data rows

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path):
            from scripts.utils.credit_monitor import get_monthly_spend
            spend = get_monthly_spend()

        assert spend == 0.0

    def test_get_monthly_spend_no_file(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'nonexistent.csv'

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path):
            from scripts.utils.credit_monitor import get_monthly_spend
            spend = get_monthly_spend()

        assert spend == 0.0


class TestGetRemainingCredit:
    """Tests for credit_monitor.get_remaining_credit()."""

    def test_get_remaining_credit_never_negative(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        # Spend more than budget
        _write_sample_csv(csv_path, [
            [f'{current}-01T10:00:00', 'TEST', 'tender', 'opus', 100000, 50000, '60.000000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path), \
             patch('scripts.utils.credit_monitor.MONTHLY_BUDGET', 50.00):
            from scripts.utils.credit_monitor import get_remaining_credit
            remaining = get_remaining_credit()

        assert remaining == 0.0


class TestAverageCostPerFile:
    """Tests for credit_monitor.get_average_cost_per_file()."""

    def test_average_cost_calculation(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        _write_sample_csv(csv_path, [
            ['2026-03-01T10:00:00', 'A', 'classify', 'haiku', 100, 50, '0.010000'],
            ['2026-03-01T10:01:00', 'A', 'invoice', 'sonnet', 200, 100, '0.020000'],
            ['2026-03-02T10:00:00', 'B', 'classify', 'haiku', 100, 50, '0.010000'],
            ['2026-03-02T10:01:00', 'B', 'letter', 'sonnet', 300, 200, '0.040000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path):
            from scripts.utils.credit_monitor import get_average_cost_per_file
            avg = get_average_cost_per_file()

        # Total: 0.08, Count: 4, Average: 0.02
        assert avg == pytest.approx(0.02, abs=1e-6)

    def test_average_cost_no_data_returns_default(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'nonexistent.csv'

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path):
            from scripts.utils.credit_monitor import get_average_cost_per_file
            avg = get_average_cost_per_file()

        assert avg == 0.05  # DEFAULT_COST_PER_FILE


class TestCanProcessBatch:
    """Tests for credit_monitor.can_process_batch()."""

    def test_can_process_batch_sufficient(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        # Spend $2 total from 100 small calls → avg $0.02/file
        # Remaining: $48. Batch of 10 × $0.02 = $0.20. $48 - $0.20 = $47.80 >> $5 threshold
        rows = [
            [f'{current}-01T10:{i:02d}:00', 'TEST', 'classify', 'haiku', 100, 50, '0.020000']
            for i in range(100)
        ]
        _write_sample_csv(csv_path, rows)

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path), \
             patch('scripts.utils.credit_monitor.MONTHLY_BUDGET', 50.00):
            from scripts.utils.credit_monitor import can_process_batch
            result = can_process_batch(10)

        assert result is True

    def test_can_process_batch_insufficient(self, tmp_path):
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        # Spend $46 of $50 budget — only $4 left, below $5 threshold
        _write_sample_csv(csv_path, [
            [f'{current}-01T10:00:00', 'TEST', 'tender', 'opus', 100000, 50000, '46.000000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path), \
             patch('scripts.utils.credit_monitor.MONTHLY_BUDGET', 50.00):
            from scripts.utils.credit_monitor import can_process_batch
            result = can_process_batch(10)

        assert result is False


class TestCheckAndWarn:
    """Tests for credit_monitor.check_and_warn()."""

    @patch('scripts.utils.credit_monitor.send_low_credit_warning')
    def test_warning_threshold_sends_email(self, mock_warn, tmp_path):
        """Between WARNING and CREDIT thresholds: sends email, returns True."""
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        # Spend $43 of $50 → $7 remaining (below $10 WARNING, above $5 CREDIT)
        _write_sample_csv(csv_path, [
            [f'{current}-01T10:00:00', 'TEST', 'classify', 'haiku', 1000, 500, '43.000000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path), \
             patch('scripts.utils.credit_monitor.MONTHLY_BUDGET', 50.00):
            from scripts.utils.credit_monitor import check_and_warn
            result = check_and_warn()

        assert result is True
        mock_warn.assert_called_once()
        # Verify it was called with WARNING type
        assert mock_warn.call_args[0][1] == 'WARNING'

    @patch('scripts.utils.credit_monitor.send_low_credit_warning')
    def test_credit_threshold_sends_email_and_pauses(self, mock_warn, tmp_path):
        """Below CREDIT threshold: sends email, returns False."""
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        # Spend $47 of $50 → $3 remaining (below $5 CREDIT threshold)
        _write_sample_csv(csv_path, [
            [f'{current}-01T10:00:00', 'TEST', 'classify', 'haiku', 1000, 500, '47.000000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path), \
             patch('scripts.utils.credit_monitor.MONTHLY_BUDGET', 50.00):
            from scripts.utils.credit_monitor import check_and_warn
            result = check_and_warn()

        assert result is False
        mock_warn.assert_called_once()
        assert mock_warn.call_args[0][1] == 'PAUSED'

    @patch('scripts.utils.credit_monitor.send_low_credit_warning')
    def test_above_warning_no_email(self, mock_warn, tmp_path):
        """Above WARNING threshold: no email, returns True."""
        csv_path = tmp_path / 'logs' / 'api_costs.csv'
        current = _current_month()
        # Spend $10 of $50 → $40 remaining (well above thresholds)
        _write_sample_csv(csv_path, [
            [f'{current}-01T10:00:00', 'TEST', 'classify', 'haiku', 1000, 500, '10.000000'],
        ])

        with patch('scripts.utils.credit_monitor.COST_CSV', csv_path), \
             patch('scripts.utils.credit_monitor.MONTHLY_BUDGET', 50.00):
            from scripts.utils.credit_monitor import check_and_warn
            result = check_and_warn()

        assert result is True
        mock_warn.assert_not_called()
