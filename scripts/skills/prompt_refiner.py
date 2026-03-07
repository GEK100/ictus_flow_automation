"""Skill 6 — Prompt Refiner (Stub).

Scale-phase skill for automated prompt improvement.  Currently implements
only the regression-check integration (SCA-06).  The full prompt refinement
logic (pattern detection, amendment generation, A/B testing) will be added
when Skill 6 is built.

Regression flow:
  1. Back up the current prompt file
  2. Apply the proposed amendment
  3. Run regression tests via run_regression.py
  4. If REGRESSION_DETECTED -> rollback from backup, log failure
  5. If REGRESSION_CLEAR    -> keep change, log success
"""

import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_regression_check(skill_name, prompt_file_path=None):
    """Run regression tests for a skill after a prompt change.

    Args:
        skill_name: Test directory name (e.g. 'invoice-processing').
        prompt_file_path: Path to the prompt file that was changed
                          (optional — logged for traceability).

    Returns:
        bool: True if regression clear (all tests pass), False if detected.
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / 'scripts' / 'run_regression.py'),
        '--skill', skill_name,
    ]
    if prompt_file_path:
        cmd.extend(['--prompt-file', str(prompt_file_path)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode == 0


def apply_prompt_amendment(prompt_path, new_content, skill_name):
    """Apply a prompt change with automatic regression rollback.

    Args:
        prompt_path: Path to the prompt file to amend.
        new_content: The new prompt content to write.
        skill_name: Skill name for regression testing (maps to tests/[skill_name]/).

    Returns:
        dict with keys:
            success (bool): Whether the amendment was kept.
            message (str): Human-readable outcome.
    """
    prompt_path = Path(prompt_path)
    backup_path = prompt_path.with_suffix('.txt.bak')

    # 1. Backup current prompt
    if prompt_path.exists():
        shutil.copy2(prompt_path, backup_path)

    # 2. Apply amendment
    with open(prompt_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    # 3. Run regression check
    regression_clear = run_regression_check(skill_name, prompt_path)

    if not regression_clear:
        # 4a. Rollback from backup
        if backup_path.exists():
            shutil.copy2(backup_path, prompt_path)
            backup_path.unlink()
        return {
            'success': False,
            'message': (
                f'REGRESSION_DETECTED for {skill_name} — '
                f'prompt rolled back to previous version.'
            ),
        }

    # 4b. Keep change, remove backup
    if backup_path.exists():
        backup_path.unlink()
    return {
        'success': True,
        'message': (
            f'REGRESSION_CLEAR for {skill_name} — '
            f'prompt amendment applied successfully.'
        ),
    }
