"""Tests for Skill 4: Correction Logger.

Tests the local diff, categorisation validation, and text diff logic
without API/Drive calls.
Run: python -m pytest tests/correction-logger/test_correction_logger.py -v
"""

import sys
import json
import pytest
from pathlib import Path

TEST_DIR = Path(__file__).parent
PROJECT_ROOT = TEST_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.skills.correction_logger import (
    diff_json,
    diff_text,
    _validate_category,
    _safe_str,
    CATEGORIES,
)


# ── Fixtures ────────────────────────────────────────────────────────

def load_fixture(name):
    path = TEST_DIR / name
    with open(path, 'r') as f:
        return json.load(f)


def fixtures_exist():
    return (TEST_DIR / 'test_1_original.json').exists()


# ── Test 1: VAT change detected ────────────────────────────────────

@pytest.mark.skipif(not fixtures_exist(), reason="Run create_fixtures.py first")
class TestVatChange:

    def setup_method(self):
        self.original = load_fixture('test_1_original.json')
        self.final = load_fixture('test_1_final.json')
        self.expected = load_fixture('test_1_expected.json')

    def test_detects_changes(self):
        changes = diff_json(self.original, self.final)
        assert len(changes) == self.expected['changes_expected']

    def test_correct_fields_changed(self):
        changes = diff_json(self.original, self.final)
        fields = [c['field'] for c in changes]
        for expected_field in self.expected['fields']:
            assert expected_field in fields

    def test_original_values_captured(self):
        changes = diff_json(self.original, self.final)
        vat_change = next(c for c in changes if c['field'] == 'vat_amount')
        assert vat_change['original_value'] == '200.0'

    def test_corrected_values_captured(self):
        changes = diff_json(self.original, self.final)
        vat_change = next(c for c in changes if c['field'] == 'vat_amount')
        assert vat_change['corrected_value'] == '250.0'


# ── Test 2: No changes ─────────────────────────────────────────────

@pytest.mark.skipif(not fixtures_exist(), reason="Run create_fixtures.py first")
class TestNoChanges:

    def setup_method(self):
        self.original = load_fixture('test_2_original.json')
        self.final = load_fixture('test_2_final.json')

    def test_no_changes_detected(self):
        changes = diff_json(self.original, self.final)
        assert len(changes) == 0


# ── Test 4: Multiple field changes ──────────────────────────────────

@pytest.mark.skipif(not fixtures_exist(), reason="Run create_fixtures.py first")
class TestMultipleFields:

    def setup_method(self):
        self.original = load_fixture('test_4_original.json')
        self.final = load_fixture('test_4_final.json')
        self.expected = load_fixture('test_4_expected.json')

    def test_detects_all_changes(self):
        changes = diff_json(self.original, self.final)
        assert len(changes) == self.expected['changes_expected']

    def test_one_entry_per_field(self):
        changes = diff_json(self.original, self.final)
        fields = [c['field'] for c in changes]
        assert len(fields) == len(set(fields)), "Duplicate fields found"

    def test_all_expected_fields(self):
        changes = diff_json(self.original, self.final)
        fields = [c['field'] for c in changes]
        for expected_field in self.expected['fields']:
            assert expected_field in fields


# ── diff_json edge cases ────────────────────────────────────────────

class TestDiffJsonEdgeCases:

    def test_nested_dict_change(self):
        original = {'address': {'city': 'London', 'postcode': 'SW1A'}}
        final = {'address': {'city': 'Manchester', 'postcode': 'SW1A'}}
        changes = diff_json(original, final)
        assert len(changes) == 1
        assert changes[0]['field'] == 'address.city'

    def test_added_field(self):
        original = {'a': 1}
        final = {'a': 1, 'b': 2}
        changes = diff_json(original, final)
        assert len(changes) == 1
        assert changes[0]['field'] == 'b'
        assert changes[0]['original_value'] is None

    def test_removed_field(self):
        original = {'a': 1, 'b': 2}
        final = {'a': 1}
        changes = diff_json(original, final)
        assert len(changes) == 1
        assert changes[0]['field'] == 'b'
        assert changes[0]['corrected_value'] is None

    def test_list_change(self):
        original = [1, 2, 3]
        final = [1, 99, 3]
        changes = diff_json(original, final)
        assert len(changes) == 1
        assert changes[0]['field'] == '[1]'

    def test_list_length_increase(self):
        original = [1, 2]
        final = [1, 2, 3]
        changes = diff_json(original, final)
        assert len(changes) == 1
        assert changes[0]['corrected_value'] == '3'

    def test_empty_dicts(self):
        changes = diff_json({}, {})
        assert len(changes) == 0

    def test_identical_complex(self):
        data = {'a': 1, 'b': {'c': [1, 2, 3]}, 'd': 'hello'}
        changes = diff_json(data, data)
        assert len(changes) == 0


# ── diff_text tests ─────────────────────────────────────────────────

class TestDiffText:

    def test_no_changes(self):
        result = diff_text("hello world", "hello world")
        assert result is None

    def test_detects_change(self):
        result = diff_text("hello world", "hello earth")
        assert result is not None
        assert 'world' in result or 'earth' in result

    def test_multiline_diff(self):
        original = "line 1\nline 2\nline 3"
        final = "line 1\nline CHANGED\nline 3"
        result = diff_text(original, final)
        assert result is not None
        assert 'CHANGED' in result


# ── Category validation ─────────────────────────────────────────────

class TestValidateCategory:

    def test_valid_category(self):
        for cat in CATEGORIES:
            assert _validate_category(cat) == cat

    def test_fuzzy_match(self):
        assert _validate_category('numerical error') == 'numerical_error'
        assert _validate_category('missing-data') == 'missing_data'
        assert _validate_category('FORMATTING_ERROR') == 'formatting_error'

    def test_unknown_defaults(self):
        assert _validate_category('completely_random') == 'factual_error'


# ── _safe_str tests ─────────────────────────────────────────────────

class TestSafeStr:

    def test_none(self):
        assert _safe_str(None) is None

    def test_int(self):
        assert _safe_str(42) == '42'

    def test_float(self):
        assert _safe_str(3.14) == '3.14'

    def test_string(self):
        assert _safe_str('hello') == 'hello'
