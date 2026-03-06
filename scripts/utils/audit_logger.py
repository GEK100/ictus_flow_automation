"""Audit logger for Ictus Flow — append-only CSV access log.

Logs every file-level Drive operation (read, write, move, delete) to
logs/audit.csv.  Never edit or delete rows — this is an immutable trail.
"""

import csv
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT_CSV = PROJECT_ROOT / 'logs' / 'audit.csv'

VALID_ACTIONS = frozenset({
    'READ', 'WRITE', 'MOVE', 'DELETE',
    'CLASSIFY', 'PROCESS', 'QA_CHECK',
})

_HEADERS = ['timestamp', 'client_code', 'file_id', 'file_name', 'action', 'script_name']


def _ensure_csv():
    """Create the CSV with headers if it doesn't exist."""
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not AUDIT_CSV.exists():
        with open(AUDIT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(_HEADERS)


def log_access(client_code, file_id, file_name, action, script_name):
    """Append an audit row to logs/audit.csv.

    Args:
        client_code: Client identifier (e.g. 'GILM').
        file_id:     Google Drive file ID.
        file_name:   Human-readable filename.
        action:      One of READ, WRITE, MOVE, DELETE, CLASSIFY, PROCESS, QA_CHECK.
        script_name: Name of the calling script / module.

    Raises:
        ValueError: If action is not in the allowed set.
    """
    action = action.upper()
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"Invalid audit action '{action}'. "
            f"Must be one of: {', '.join(sorted(VALID_ACTIONS))}"
        )

    _ensure_csv()

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = [timestamp, client_code, file_id, file_name, action, script_name]

    with open(AUDIT_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(row)
