"""Tests for SCA-06: Automated Test Runner for Regression Testing.

Tests the test discovery, single-skill filtering, CSV appending,
exit codes, and the regression runner.

Run: python -m pytest tests/test-runner/test_run_tests.py -v
"""

import sys
import csv
import subprocess
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = PROJECT_ROOT / 'tests'
sys.path.insert(0, str(PROJECT_ROOT))

RUN_TESTS = PROJECT_ROOT / 'scripts' / 'run_tests.py'
RUN_REGRESSION = PROJECT_ROOT / 'scripts' / 'run_regression.py'


# ── Helpers ───────────────────────────────────────────────────────

@pytest.fixture()
def tmp_fail_dir():
    """Create a temporary test dir with a failing test, clean up after."""
    fail_dir = TESTS_DIR / '_tmp_fail_test'
    fail_dir.mkdir(exist_ok=True)
    fail_test = fail_dir / 'test_temp_fail.py'
    fail_test.write_text(
        'def test_always_fails():\n    assert False, "intentional failure"\n',
        encoding='utf-8',
    )
    yield fail_dir
    # Cleanup
    if fail_test.exists():
        fail_test.unlink()
    # Remove __pycache__ if pytest created it
    cache_dir = fail_dir / '__pycache__'
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
    if fail_dir.exists():
        fail_dir.rmdir()


# ── Test 1: discovers all test dirs ──────────────────────────────

class TestDiscoversAllTestDirs:

    def test_discovers_all_test_dirs(self):
        """discover_test_dirs finds all test folders under tests/."""
        from scripts.run_tests import discover_test_dirs

        dirs = discover_test_dirs()

        # Known directories that contain test_*.py files
        expected_present = [
            'retry', 'security', 'ops', 'cx',
            'commercial', 'storage-interface', 'prompt-overrides',
            'file-classifier', 'correction-logger', 'qa-oversight',
            'output-format-matcher',
        ]
        for d in expected_present:
            assert d in dirs, f"Missing test dir: {d}"

        # Directories without test files should NOT appear
        for d in ['sample-contracts', 'sample-invoices']:
            assert d not in dirs, f"Unexpected test dir: {d} (has no test files)"

        # Must find at least 10 test directories
        assert len(dirs) >= 10


# ── Test 2: --skill flag filters tests ───────────────────────────

class TestSingleSkillFlag:

    def test_single_skill_flag(self, tmp_path):
        """--skill retry only runs retry tests."""
        csv_out = tmp_path / 'bench.csv'
        result = subprocess.run(
            [sys.executable, str(RUN_TESTS),
             '--skill', 'retry', '--csv-output', str(csv_out)],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        assert result.returncode == 0

        # Every row in the CSV should be for the 'retry' skill
        with open(csv_out, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) > 0, "CSV should have at least one data row"
        for row in rows:
            assert row['skill_name'] == 'retry', (
                f"Expected only 'retry' but got '{row['skill_name']}'"
            )


# ── Test 3: benchmark history is appended ────────────────────────

class TestBenchmarkHistoryAppended:

    def test_benchmark_history_appended(self, tmp_path):
        """Results are appended to CSV without overwriting previous data."""
        csv_out = tmp_path / 'bench.csv'

        # First run
        subprocess.run(
            [sys.executable, str(RUN_TESTS),
             '--skill', 'retry', '--csv-output', str(csv_out)],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        with open(csv_out, 'r', encoding='utf-8') as f:
            first_lines = f.readlines()
        first_data_count = len(first_lines) - 1  # minus header

        assert first_data_count > 0, "First run should produce data rows"

        # Second run — must append, not overwrite
        subprocess.run(
            [sys.executable, str(RUN_TESTS),
             '--skill', 'retry', '--csv-output', str(csv_out)],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        with open(csv_out, 'r', encoding='utf-8') as f:
            second_lines = f.readlines()
        second_data_count = len(second_lines) - 1  # still only 1 header

        assert second_data_count == first_data_count * 2, (
            f"Expected {first_data_count * 2} data rows after two runs, "
            f"got {second_data_count}"
        )


# ── Test 4: exit code 0 on all-pass ─────────────────────────────

class TestExitCodeZeroOnPass:

    def test_exit_code_zero_on_pass(self, tmp_path):
        """All tests passing returns exit code 0."""
        csv_out = tmp_path / 'bench.csv'
        result = subprocess.run(
            [sys.executable, str(RUN_TESTS),
             '--skill', 'retry', '--csv-output', str(csv_out)],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        assert result.returncode == 0


# ── Test 5: exit code 1 on fail ──────────────────────────────────

class TestExitCodeOneOnFail:

    def test_exit_code_one_on_fail(self, tmp_fail_dir, tmp_path):
        """Any test failure returns exit code 1."""
        csv_out = tmp_path / 'bench.csv'
        result = subprocess.run(
            [sys.executable, str(RUN_TESTS),
             '--skill', '_tmp_fail_test', '--csv-output', str(csv_out)],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        assert result.returncode == 1


# ── Test 6: regression runner returns CLEAR ──────────────────────

class TestRegressionRunnerReturnsClear:

    def test_regression_runner_returns_clear(self):
        """Passing tests return REGRESSION_CLEAR with exit code 0."""
        result = subprocess.run(
            [sys.executable, str(RUN_REGRESSION), '--skill', 'retry'],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        assert result.returncode == 0
        assert 'REGRESSION_CLEAR' in result.stdout


# ── Test 7: regression runner returns DETECTED ───────────────────

class TestRegressionRunnerReturnsDetected:

    def test_regression_runner_returns_detected(self, tmp_fail_dir):
        """Failing test returns REGRESSION_DETECTED with exit code 1."""
        result = subprocess.run(
            [sys.executable, str(RUN_REGRESSION),
             '--skill', '_tmp_fail_test'],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        assert result.returncode == 1
        assert 'REGRESSION_DETECTED' in result.stdout
