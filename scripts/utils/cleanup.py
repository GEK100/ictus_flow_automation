"""Daily cleanup safety net for Ictus Flow temp files.

Deletes everything inside the dedicated processing temp directory:
    %TEMP%/ictus-flow-processing   (Windows)
    /tmp/ictus-flow-processing      (Linux/Mac)

Designed to run via Windows Task Scheduler as a daily safety net.
Normal operation already cleans up via try/finally in each skill,
but this catches anything left behind by crashes or killed processes.

Schedule (Task Scheduler):
    Action:  python scripts/utils/cleanup.py
    Trigger: Daily at 02:00 (or any off-peak time)
"""

import os
import sys
import shutil
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

TEMP_BASE = os.path.join(os.environ.get('TEMP', '/tmp'), 'ictus-flow-processing')


def cleanup():
    """Delete everything inside the ictus-flow-processing temp directory."""
    if not os.path.exists(TEMP_BASE):
        log.info(f"Nothing to clean — {TEMP_BASE} does not exist")
        return 0

    removed = 0
    errors = 0

    for entry in os.listdir(TEMP_BASE):
        entry_path = os.path.join(TEMP_BASE, entry)
        try:
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
            else:
                os.remove(entry_path)
            removed += 1
        except Exception as e:
            log.warning(f"Could not remove {entry_path}: {e}")
            errors += 1

    log.info(
        f"Cleanup complete: {removed} items removed, "
        f"{errors} errors, directory: {TEMP_BASE}"
    )
    return removed


if __name__ == '__main__':
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Ictus Flow temp cleanup")
    count = cleanup()
    print(f"Removed {count} items from {TEMP_BASE}")
