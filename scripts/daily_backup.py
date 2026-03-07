"""Daily config backup — entry point for Windows Task Scheduler.

Schedule with:
  schtasks /create /tn "Ictus Flow Config Backup" ^
    /tr "C:\\Python313\\python.exe C:\\Users\\gk100\\Ictus Flow Automation\\ictus-flow-system\\scripts\\daily_backup.py" ^
    /sc daily /st 02:00

Run manually:
  python scripts/daily_backup.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.config_backup import backup_configs, list_backups


def main():
    print("Starting Ictus Flow config backup...")

    try:
        result = backup_configs()
        print(f"Backup complete:")
        print(f"  Configs backed up: {result['configs_count']}")
        print(f"  Prompts backed up: {result['prompts_count']}")
        print(f"  Backup file: {result['filename']}")

        # Show retention info
        backups = list_backups()
        if backups:
            print(f"  Total backups retained: {len(backups)}")
            print(f"  Oldest backup: {backups[-1]['date']}")

    except Exception as e:
        print(f"ERROR: Backup failed — {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
