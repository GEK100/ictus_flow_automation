"""Tests for Skill 3: QA Oversight Agent.

Tests the local logic (thresholds, graduation, spot-check) without API calls.
Run: python -m pytest tests/qa-oversight/test_qa_oversight.py -v
"""

import sys
import json
import pytest
from pathlib import Path
from copy import deepcopy

TEST_DIR = Path(__file__).parent
PROJECT_ROOT = TEST_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.skills.qa_oversight import (
    apply_thresholds,
    update_graduation,
    should_run_qa,
    read_file_content,
    DIMENSIONS,
    PASS_THRESHOLD,
    FLAG_THRESHOLD,
    GRADUATION_THRESHOLD,
    SPOT_CHECK_FREQUENCY,
)


# ── apply_thresholds tests ──────────────────────────────────────────

class TestApplyThresholds:

    def test_all_pass(self):
        """Test 1: All dimensions >= 80 = overall PASS."""
        scores = {d: 90 for d in DIMENSIONS}
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'PASS'
        assert result['failed_dimensions'] == []
        assert result['flagged_dimensions'] == []

    def test_one_fail(self):
        """Test 2: One dimension < 60 = overall FAIL."""
        scores = {d: 90 for d in DIMENSIONS}
        scores['internal_consistency'] = 45
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'FAIL'
        assert 'internal_consistency' in result['failed_dimensions']

    def test_one_flag(self):
        """Test 4: One dimension 60-79 = overall FLAG."""
        scores = {d: 90 for d in DIMENSIONS}
        scores['tone_match'] = 65
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'FLAG'
        assert 'tone_match' in result['flagged_dimensions']

    def test_fail_beats_flag(self):
        """FAIL takes priority over FLAG."""
        scores = {d: 90 for d in DIMENSIONS}
        scores['completeness'] = 50  # FAIL
        scores['tone_match'] = 70    # FLAG
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'FAIL'
        assert 'completeness' in result['failed_dimensions']
        assert 'tone_match' in result['flagged_dimensions']

    def test_boundary_pass(self):
        """Exactly 80 = PASS."""
        scores = {d: 80 for d in DIMENSIONS}
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'PASS'

    def test_boundary_flag(self):
        """Exactly 60 = FLAG (not FAIL)."""
        scores = {d: 90 for d in DIMENSIONS}
        scores['format_compliance'] = 60
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'FLAG'
        assert result['dimensions']['format_compliance']['status'] == 'FLAG'

    def test_boundary_fail(self):
        """59 = FAIL."""
        scores = {d: 90 for d in DIMENSIONS}
        scores['factual_accuracy'] = 59
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'FAIL'
        assert result['dimensions']['factual_accuracy']['status'] == 'FAIL'

    def test_overall_score_average(self):
        """Overall score is the average of all dimensions."""
        scores = {'factual_accuracy': 100, 'completeness': 80,
                  'tone_match': 90, 'format_compliance': 70,
                  'internal_consistency': 60}
        result = apply_thresholds(scores)
        assert result['overall_score'] == 80.0

    def test_missing_dimension_defaults_zero(self):
        """Missing dimensions default to 0 (FAIL)."""
        scores = {}
        result = apply_thresholds(scores)
        assert result['overall_status'] == 'FAIL'
        assert len(result['failed_dimensions']) == 5


# ── Graduation tests ────────────────────────────────────────────────

class TestGraduation:

    def _empty_stats(self):
        return {'workflows': {}}

    def test_new_workflow_not_graduated(self):
        """New workflow starts as not graduated."""
        stats = self._empty_stats()
        stats = update_graduation('invoice-processor', 'PASS', stats, [])
        wf = stats['workflows']['invoice-processor']
        assert wf['graduated'] is False
        assert wf['total_checked'] == 1
        assert wf['consecutive_pass'] == 1

    def test_graduation_after_threshold(self):
        """Workflow graduates after N consecutive passes."""
        stats = self._empty_stats()
        stats['workflows']['invoice-processor'] = {
            'total_checked': 49,
            'consecutive_pass': 49,
            'graduated': False,
            'graduation_date': None,
            'spot_check_frequency': SPOT_CHECK_FREQUENCY,
            'last_fail': None,
        }
        stats = update_graduation('invoice-processor', 'PASS', stats, [])
        wf = stats['workflows']['invoice-processor']
        assert wf['graduated'] is True
        assert wf['graduation_date'] is not None
        assert wf['consecutive_pass'] == 50

    def test_fail_resets_streak(self):
        """A FAIL resets consecutive_pass to 0."""
        stats = self._empty_stats()
        stats['workflows']['invoice-processor'] = {
            'total_checked': 30,
            'consecutive_pass': 30,
            'graduated': False,
            'graduation_date': None,
            'spot_check_frequency': SPOT_CHECK_FREQUENCY,
            'last_fail': None,
        }
        stats = update_graduation('invoice-processor', 'FAIL', stats, [])
        wf = stats['workflows']['invoice-processor']
        assert wf['consecutive_pass'] == 0
        assert wf['last_fail'] is not None
        assert wf['graduated'] is False

    def test_fail_revokes_graduation(self):
        """A FAIL after graduation revokes it."""
        stats = self._empty_stats()
        stats['workflows']['invoice-processor'] = {
            'total_checked': 55,
            'consecutive_pass': 55,
            'graduated': True,
            'graduation_date': '2025-01-01T00:00:00',
            'spot_check_frequency': SPOT_CHECK_FREQUENCY,
            'last_fail': None,
        }
        stats = update_graduation('invoice-processor', 'FAIL', stats, [])
        wf = stats['workflows']['invoice-processor']
        assert wf['graduated'] is False
        assert wf['graduation_date'] is None

    def test_never_graduate_workflow(self):
        """Never-graduate workflows cannot graduate even with enough passes."""
        stats = self._empty_stats()
        stats['workflows']['RAMS'] = {
            'total_checked': 99,
            'consecutive_pass': 99,
            'graduated': False,
            'graduation_date': None,
            'spot_check_frequency': SPOT_CHECK_FREQUENCY,
            'last_fail': None,
        }
        stats = update_graduation('RAMS', 'PASS', stats, ['RAMS', 'CONTRACT'])
        wf = stats['workflows']['RAMS']
        assert wf['graduated'] is False
        assert wf['consecutive_pass'] == 100

    def test_flag_resets_streak(self):
        """A FLAG also resets the streak (only PASS counts)."""
        stats = self._empty_stats()
        stats['workflows']['invoice-processor'] = {
            'total_checked': 20,
            'consecutive_pass': 20,
            'graduated': False,
            'graduation_date': None,
            'spot_check_frequency': SPOT_CHECK_FREQUENCY,
            'last_fail': None,
        }
        stats = update_graduation('invoice-processor', 'FLAG', stats, [])
        wf = stats['workflows']['invoice-processor']
        assert wf['consecutive_pass'] == 0


# ── should_run_qa tests ─────────────────────────────────────────────

class TestShouldRunQA:

    def test_never_graduate_always_checks(self):
        stats = {'workflows': {'RAMS': {'graduated': True, 'total_checked': 100,
                                        'spot_check_frequency': 5}}}
        should, reason = should_run_qa('RAMS', stats, ['RAMS', 'CONTRACT'])
        assert should is True
        assert 'never-graduate' in reason

    def test_not_graduated_always_checks(self):
        stats = {'workflows': {}}
        should, reason = should_run_qa('invoice-processor', stats, [])
        assert should is True
        assert 'not yet graduated' in reason

    def test_graduated_spot_check_hit(self):
        """Graduated workflow checked on spot-check frequency."""
        stats = {'workflows': {'invoice-processor': {
            'graduated': True, 'total_checked': 54,
            'spot_check_frequency': 5,
        }}}
        # total_checked=54, next would be 55, (54+1) % 5 == 0 → check
        should, reason = should_run_qa('invoice-processor', stats, [])
        assert should is True
        assert 'spot check' in reason

    def test_graduated_spot_check_skip(self):
        """Graduated workflow skipped between spot checks."""
        stats = {'workflows': {'invoice-processor': {
            'graduated': True, 'total_checked': 51,
            'spot_check_frequency': 5,
        }}}
        # (51+1) % 5 == 2 → skip
        should, reason = should_run_qa('invoice-processor', stats, [])
        assert should is False
        assert 'skipping' in reason

    def test_case_insensitive_never_graduate(self):
        """Never-graduate matching is case-insensitive."""
        stats = {'workflows': {}}
        should, _ = should_run_qa('rams', stats, ['RAMS'])
        assert should is True


# ── File reading tests ──────────────────────────────────────────────

class TestReadFileContent:

    def test_read_json_fixture(self):
        fixture = TEST_DIR / 'test_1_original.json'
        if fixture.exists():
            content = read_file_content(str(fixture))
            assert 'INVOICE' in content or 'invoice' in content

    def test_read_text_file(self, tmp_path):
        f = tmp_path / 'test.txt'
        f.write_text('Hello world', encoding='utf-8')
        content = read_file_content(str(f))
        assert content == 'Hello world'

    def test_read_json_file(self, tmp_path):
        f = tmp_path / 'test.json'
        f.write_text('{"key": "value"}', encoding='utf-8')
        content = read_file_content(str(f))
        data = json.loads(content)
        assert data['key'] == 'value'
