"""Tests for Skill 9: Output Format Matcher.

Tests the local extraction functions (no API/Drive calls).
Run: python -m pytest tests/output-format-matcher/test_output_format_matcher.py -v
"""

import os
import sys
import json
import pytest
from pathlib import Path

# Setup paths
TEST_DIR = Path(__file__).parent
PROJECT_ROOT = TEST_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.skills.output_format_matcher import (
    extract_spreadsheet_structure,
    extract_csv_structure,
    extract_docx_structure,
    _infer_column_type,
    _derive_format_key,
)


# ── Fixtures ────────────────────────────────────────────────────────

EXCEL_FIXTURE = TEST_DIR / 'test_a_invoice_tracker.xlsx'
DOCX_FIXTURE = TEST_DIR / 'test_b_letterhead.docx'
CSV_FIXTURE = TEST_DIR / 'test_c_timesheet.csv'


def fixtures_exist():
    return EXCEL_FIXTURE.exists() and DOCX_FIXTURE.exists() and CSV_FIXTURE.exists()


# ── Test A: Invoice Tracker Excel ───────────────────────────────────

@pytest.mark.skipif(not fixtures_exist(), reason="Run create_fixtures.py first")
class TestExcelExtraction:

    def setup_method(self):
        self.result = extract_spreadsheet_structure(str(EXCEL_FIXTURE))
        with open(TEST_DIR / 'test_a_expected.json') as f:
            self.expected = json.load(f)

    def test_type_is_spreadsheet(self):
        assert self.result['type'] == 'spreadsheet'

    def test_has_invoices_sheet(self):
        assert 'Invoices' in self.result['sheets']

    def test_column_count(self):
        columns = self.result['sheets']['Invoices']['columns']
        assert len(columns) == self.expected['expected_column_count']

    def test_column_names_match(self):
        columns = self.result['sheets']['Invoices']['columns']
        names = [c['name'] for c in columns]
        assert names == self.expected['expected_columns']

    def test_column_order_preserved(self):
        columns = self.result['sheets']['Invoices']['columns']
        positions = [c['position'] for c in columns]
        assert positions == list(range(1, len(columns) + 1))

    def test_date_format_captured(self):
        columns = self.result['sheets']['Invoices']['columns']
        date_col = next(c for c in columns if c['name'] == 'Date')
        assert 'format' in date_col

    def test_currency_format_captured(self):
        columns = self.result['sheets']['Invoices']['columns']
        net_col = next(c for c in columns if c['name'] == 'Net Amount')
        assert 'format' in net_col

    def test_formula_captured(self):
        columns = self.result['sheets']['Invoices']['columns']
        vat_col = next(c for c in columns if c['name'] == 'VAT Amount')
        assert 'formula_pattern' in vat_col

    def test_conditional_formatting_present(self):
        cf = self.result['sheets']['Invoices']['conditional_formatting']
        assert len(cf) > 0

    def test_frozen_panes(self):
        assert self.result['sheets']['Invoices']['frozen_panes'] is not None


# ── Test B: Word Letterhead ─────────────────────────────────────────

@pytest.mark.skipif(not fixtures_exist(), reason="Run create_fixtures.py first")
class TestDocxExtraction:

    def setup_method(self):
        self.result = extract_docx_structure(str(DOCX_FIXTURE))
        with open(TEST_DIR / 'test_b_expected.json') as f:
            self.expected = json.load(f)

    def test_type_is_document(self):
        assert self.result['type'] == 'document'

    def test_has_header(self):
        assert self.result['has_header'] == self.expected['expected_has_header']

    def test_has_footer(self):
        assert self.result['has_footer'] == self.expected['expected_has_footer']

    def test_has_sections(self):
        assert len(self.result['sections']) > 0

    def test_margins_present(self):
        section = self.result['sections'][0]
        margins = section['margins']
        assert all(v is not None for v in margins.values())

    def test_orientation(self):
        section = self.result['sections'][0]
        assert section['orientation'] == self.expected['expected_orientation']

    def test_styles_captured(self):
        assert len(self.result['styles']) > 0


# ── Test C: CSV Extraction ──────────────────────────────────────────

@pytest.mark.skipif(not fixtures_exist(), reason="Run create_fixtures.py first")
class TestCsvExtraction:

    def setup_method(self):
        self.result = extract_csv_structure(str(CSV_FIXTURE))
        with open(TEST_DIR / 'test_c_expected.json') as f:
            self.expected = json.load(f)

    def test_type_is_spreadsheet(self):
        assert self.result['type'] == 'spreadsheet'

    def test_column_count(self):
        columns = self.result['sheets']['Sheet1']['columns']
        assert len(columns) == self.expected['expected_column_count']

    def test_column_names(self):
        columns = self.result['sheets']['Sheet1']['columns']
        names = [c['name'] for c in columns]
        assert names == self.expected['expected_columns']


# ── Unit Tests ──────────────────────────────────────────────────────

class TestInferColumnType:

    def test_dates(self):
        assert _infer_column_type(['15/01/2025', '16/01/2025', '17/01/2025']) == 'date'

    def test_numbers(self):
        assert _infer_column_type(['8', '7.5', '10']) == 'number'

    def test_currency(self):
        assert _infer_column_type(['\u00a3100.00', '\u00a3200.50', '\u00a350.00']) == 'currency'

    def test_text(self):
        assert _infer_column_type(['John', 'Jane', 'Bob']) == 'text'

    def test_empty(self):
        assert _infer_column_type([]) == 'text'


class TestDeriveFormatKey:

    def test_simple(self):
        assert _derive_format_key('Invoice Tracker.xlsx') == 'invoice_tracker'

    def test_with_template_suffix(self):
        assert _derive_format_key('Monthly Report Template.xlsx') == 'monthly_report'

    def test_with_dashes(self):
        assert _derive_format_key('payment-cert-blank.docx') == 'payment_cert'

    def test_empty_after_strip(self):
        assert _derive_format_key('template.xlsx') == 'unnamed'
