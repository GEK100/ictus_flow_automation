"""SCA-06: Automated Test Runner for Regression Testing.

Discovers and runs all tests under tests/, produces a summary table,
and appends results to tests/benchmark-history.csv for historical tracking.

Usage:
    python scripts/run_tests.py                           # Run all tests
    python scripts/run_tests.py --skill retry             # Single skill
    python scripts/run_tests.py --verbose                 # Detailed output
    python scripts/run_tests.py --benchmark               # Tag as monthly benchmark
    python scripts/run_tests.py --csv-output /tmp/r.csv   # Override CSV path
"""

import sys
import csv
import argparse
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / 'tests'
BENCHMARK_CSV = TESTS_DIR / 'benchmark-history.csv'

BENCHMARK_HEADERS = [
    'date', 'skill_name', 'test_case', 'expected', 'actual',
    'pass_fail', 'duration_ms', 'notes',
]


# ═══════════════════════════════════════════════════════════════════
# Pytest plugin for result collection
# ═══════════════════════════════════════════════════════════════════


class ResultCollector:
    """Pytest plugin that collects per-test outcomes and durations."""

    def __init__(self):
        self.results = []

    def pytest_runtest_logreport(self, report):
        """Capture the result of each test's *call* phase."""
        if report.when == 'call':
            self.results.append({
                'nodeid': report.nodeid,
                'outcome': report.outcome,        # 'passed' | 'failed' | 'skipped'
                'duration_ms': round(report.duration * 1000, 1),
            })
        elif report.when == 'setup' and report.failed:
            # Setup failures mean the test body never ran
            self.results.append({
                'nodeid': report.nodeid,
                'outcome': 'failed',
                'duration_ms': round(report.duration * 1000, 1),
            })


# ═══════════════════════════════════════════════════════════════════
# Core functions (importable for testing)
# ═══════════════════════════════════════════════════════════════════


def discover_test_dirs(tests_dir=None):
    """Find all subdirectories under tests/ that contain test_*.py files.

    Returns:
        Sorted list of directory names relative to tests/.
    """
    if tests_dir is None:
        tests_dir = TESTS_DIR
    tests_dir = Path(tests_dir)

    dirs = set()
    for p in tests_dir.rglob('test_*.py'):
        rel = p.parent.relative_to(tests_dir)
        name = str(rel).replace('\\', '/')
        if name != '.':
            dirs.add(name)
    return sorted(dirs)


def run_tests(skill=None, verbose=False, tests_dir=None):
    """Run pytest programmatically and return (exit_code, results).

    Args:
        skill: Name of a single skill directory to test (e.g. 'retry').
        verbose: Enable verbose pytest output.
        tests_dir: Override test root directory (default: tests/).

    Returns:
        Tuple of (int_exit_code, list_of_result_dicts).
    """
    if tests_dir is None:
        tests_dir = TESTS_DIR
    tests_dir = Path(tests_dir)

    collector = ResultCollector()

    target = tests_dir
    if skill:
        target = tests_dir / skill
        if not target.exists():
            print(f"ERROR: Test directory not found: {target}")
            return 1, []

    args = [str(target), '--tb=short', '-p', 'no:cacheprovider']
    if verbose:
        args.append('-v')
    else:
        args.append('-q')

    exit_code = pytest.main(args, plugins=[collector])
    return int(exit_code), collector.results


def write_benchmark_csv(results, csv_path=None, notes=''):
    """Append test results to the benchmark CSV.

    Creates the file with headers if it doesn't exist or is empty.
    Never overwrites existing data.

    Args:
        results: List of result dicts from ResultCollector.
        csv_path: Override CSV file path.
        notes: Value for the notes column (e.g. 'monthly-benchmark').
    """
    if csv_path is None:
        csv_path = BENCHMARK_CSV
    csv_path = Path(csv_path)

    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(BENCHMARK_HEADERS)

        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        for r in results:
            # Extract skill name from nodeid:
            #   tests/retry/test_retry.py::TestClass::test_method → 'retry'
            parts = r['nodeid'].replace('\\', '/').split('/')
            skill_name = parts[1] if len(parts) > 1 else (parts[0] if parts else 'unknown')

            pass_fail = 'pass' if r['outcome'] == 'passed' else 'fail'

            writer.writerow([
                timestamp,
                skill_name,
                r['nodeid'],
                'pass',              # expected
                pass_fail,           # actual
                pass_fail,           # pass_fail
                r['duration_ms'],
                notes,
            ])


def print_summary(results):
    """Print a grouped summary table to stdout."""
    by_skill = {}
    for r in results:
        parts = r['nodeid'].replace('\\', '/').split('/')
        skill = parts[1] if len(parts) > 1 else (parts[0] if parts else 'unknown')
        if skill not in by_skill:
            by_skill[skill] = {'run': 0, 'passed': 0, 'failed': 0, 'time_ms': 0.0}
        by_skill[skill]['run'] += 1
        by_skill[skill]['time_ms'] += r['duration_ms']
        if r['outcome'] == 'passed':
            by_skill[skill]['passed'] += 1
        else:
            by_skill[skill]['failed'] += 1

    print('\n' + '=' * 70)
    print(f"{'Skill/Module':<30} {'Run':>5} {'Pass':>5} {'Fail':>5} {'Time':>10}")
    print('-' * 70)
    total_run = total_pass = total_fail = 0
    total_time = 0.0
    for skill in sorted(by_skill):
        s = by_skill[skill]
        total_run += s['run']
        total_pass += s['passed']
        total_fail += s['failed']
        total_time += s['time_ms']
        print(
            f"{skill:<30} {s['run']:>5} {s['passed']:>5} "
            f"{s['failed']:>5} {s['time_ms']:>8.1f}ms"
        )
    print('-' * 70)
    print(
        f"{'TOTAL':<30} {total_run:>5} {total_pass:>5} "
        f"{total_fail:>5} {total_time:>8.1f}ms"
    )
    print('=' * 70)


# ═══════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description='Ictus Flow Test Runner')
    parser.add_argument('--skill', type=str, default=None,
                        help='Run tests for a single skill (e.g. retry)')
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose pytest output')
    parser.add_argument('--benchmark', action='store_true',
                        help='Tag the run as a monthly benchmark in CSV')
    parser.add_argument('--csv-output', type=str, default=None,
                        help='Override CSV output path (for testing)')
    args = parser.parse_args()

    notes = 'monthly-benchmark' if args.benchmark else ''
    csv_path = args.csv_output

    exit_code, results = run_tests(skill=args.skill, verbose=args.verbose)
    print_summary(results)
    write_benchmark_csv(results, csv_path=csv_path, notes=notes)

    target_csv = csv_path or str(BENCHMARK_CSV)
    print(f"\nResults appended to {target_csv}")
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
