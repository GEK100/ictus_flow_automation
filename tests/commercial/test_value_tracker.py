"""Tests for COM-01: Value Tracking From First Document.

Tests the value logging, client summaries, and monthly filtering
using a temporary CSV file.

Run: python -m pytest tests/commercial/test_value_tracker.py -v
"""

import sys
import csv
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.value_tracker import (
    log_value,
    get_client_summary,
    get_all_clients_summary,
    BENCHMARK_TIMES,
    DEFAULT_MINUTES,
    ASSUMED_HOURLY_RATE,
    VALUE_CSV,
    _HEADERS,
)


@pytest.fixture(autouse=True)
def use_tmp_csv(tmp_path, monkeypatch):
    """Redirect VALUE_CSV to a temp file for every test."""
    tmp_csv = tmp_path / 'value_tracking.csv'
    monkeypatch.setattr('scripts.utils.value_tracker.VALUE_CSV', tmp_csv)
    yield tmp_csv


# ── Test 1: log_value creates CSV with headers ───────────────────

class TestLogValueCreatesCsv:

    def test_log_value_creates_csv(self, use_tmp_csv):
        """First call creates file with correct headers."""
        assert not use_tmp_csv.exists()

        log_value('GILM', 'invoice_001.pdf', 'INVOICE', 0.004)

        assert use_tmp_csv.exists()

        with open(use_tmp_csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == _HEADERS

            data_row = next(reader)
            assert data_row[1] == 'GILM'
            assert data_row[2] == 'invoice_001.pdf'
            assert data_row[3] == 'INVOICE'


# ── Test 2: minutes saved correct ─────────────────────────────────

class TestMinutesSavedCorrect:

    def test_minutes_saved_correct(self, use_tmp_csv):
        """INVOICE logs 15 mins saved."""
        log_value('GILM', 'inv.pdf', 'INVOICE', 0.003)

        with open(use_tmp_csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)

        assert int(row['minutes_saved']) == 15
        expected_value = round((15 / 60) * ASSUMED_HOURLY_RATE, 4)
        assert float(row['value_gbp']) == expected_value

    def test_contract_minutes(self, use_tmp_csv):
        """CONTRACT logs 45 mins saved."""
        log_value('TEST', 'contract.pdf', 'CONTRACT', 0.01)

        with open(use_tmp_csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)

        assert int(row['minutes_saved']) == 45


# ── Test 3: client summary totals ─────────────────────────────────

class TestClientSummaryTotals:

    def test_client_summary_totals(self, use_tmp_csv):
        """Multiple files sum correctly."""
        log_value('GILM', 'inv1.pdf', 'INVOICE', 0.003)    # 15 mins
        log_value('GILM', 'letter.pdf', 'LETTER', 0.005)    # 20 mins
        log_value('GILM', 'inv2.pdf', 'INVOICE', 0.004)    # 15 mins
        log_value('OTHR', 'inv3.pdf', 'INVOICE', 0.003)    # different client

        summary = get_client_summary('GILM')

        assert summary['total_files'] == 3
        assert summary['total_minutes_saved'] == 50  # 15 + 20 + 15
        expected_value = round((50 / 60) * ASSUMED_HOURLY_RATE, 4)
        assert summary['total_value_gbp'] == expected_value
        assert summary['total_api_cost'] == round(0.003 + 0.005 + 0.004, 4)

    def test_all_clients_summary(self, use_tmp_csv):
        """get_all_clients_summary includes all clients."""
        log_value('GILM', 'inv1.pdf', 'INVOICE', 0.003)
        log_value('OTHR', 'inv2.pdf', 'INVOICE', 0.004)

        summary = get_all_clients_summary()

        assert summary['total_files'] == 2
        assert summary['total_minutes_saved'] == 30  # 15 + 15


# ── Test 4: monthly filter ────────────────────────────────────────

class TestMonthlyFilter:

    def test_monthly_filter(self, use_tmp_csv, monkeypatch):
        """Only returns current month data when filtered."""
        # Write rows with different month timestamps manually
        import scripts.utils.value_tracker as vt
        vt._ensure_csv()

        with open(use_tmp_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                '2026-03-01T10:00:00', 'GILM', 'march.pdf', 'INVOICE',
                15, '3.7500', '0.0030', '3.7470',
            ])
            writer.writerow([
                '2026-02-15T10:00:00', 'GILM', 'feb.pdf', 'LETTER',
                20, '5.0000', '0.0050', '4.9950',
            ])
            writer.writerow([
                '2026-03-05T10:00:00', 'GILM', 'march2.pdf', 'CIS',
                30, '7.5000', '0.0040', '7.4960',
            ])

        summary_march = get_client_summary('GILM', month='2026-03')
        assert summary_march['total_files'] == 2

        summary_feb = get_client_summary('GILM', month='2026-02')
        assert summary_feb['total_files'] == 1

        summary_all = get_client_summary('GILM')
        assert summary_all['total_files'] == 3


# ── Test 5: unknown classification defaults ───────────────────────

class TestUnknownClassificationDefaults:

    def test_unknown_classification_defaults(self, use_tmp_csv):
        """Unknown type uses 10 mins default."""
        log_value('GILM', 'weird.xyz', 'UNKNOWN_TYPE', 0.002)

        with open(use_tmp_csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)

        assert int(row['minutes_saved']) == DEFAULT_MINUTES
        expected_value = round((DEFAULT_MINUTES / 60) * ASSUMED_HOURLY_RATE, 4)
        assert float(row['value_gbp']) == expected_value

    def test_other_classification_defaults(self, use_tmp_csv):
        """OTHER classification also uses default."""
        log_value('GILM', 'misc.pdf', 'OTHER', 0.001)

        summary = get_client_summary('GILM')
        assert summary['total_minutes_saved'] == DEFAULT_MINUTES
