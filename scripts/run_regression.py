"""SCA-06: Regression Runner for Skill 6 (Prompt Refiner).

Runs tests for a specific skill and returns a clear pass/fail result
suitable for automated rollback decisions.

Usage:
    python scripts/run_regression.py --skill invoice-processing
    python scripts/run_regression.py --skill retry --prompt-file prompts/retry.txt

Exit codes:
    0 — REGRESSION_CLEAR  (all tests passed)
    1 — REGRESSION_DETECTED (at least one test failed)
"""

import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_tests import run_tests


def main():
    parser = argparse.ArgumentParser(
        description='Ictus Flow Regression Runner')
    parser.add_argument('--skill', type=str, required=True,
                        help='Skill name to test (e.g. retry)')
    parser.add_argument('--prompt-file', type=str, default=None,
                        help='Path to the prompt file being tested (informational)')
    args = parser.parse_args()

    print(f"Running regression tests for skill: {args.skill}")
    if args.prompt_file:
        print(f"Prompt file: {args.prompt_file}")

    exit_code, results = run_tests(skill=args.skill)

    passed = sum(1 for r in results if r['outcome'] == 'passed')
    failed = sum(1 for r in results if r['outcome'] != 'passed')

    print(f"\nResults: {passed} passed, {failed} failed")

    if exit_code != 0 or failed > 0:
        print('REGRESSION_DETECTED')
        sys.exit(1)
    else:
        print('REGRESSION_CLEAR')
        sys.exit(0)


if __name__ == '__main__':
    main()
