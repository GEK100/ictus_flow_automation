"""COM-01: Value Tracking From First Document.

Tracks the value delivered by each processed file — minutes saved,
monetary value, API cost, and net value — so we can demonstrate ROI
to clients from day one.

Usage:
    from scripts.utils.value_tracker import log_value, get_client_summary
    log_value('GILM', 'invoice_001.pdf', 'INVOICE', 0.004)
    summary = get_client_summary('GILM')
"""

import csv
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VALUE_CSV = PROJECT_ROOT / 'logs' / 'value_tracking.csv'

_HEADERS = [
    'timestamp', 'client_code', 'file_name', 'classification',
    'minutes_saved', 'value_gbp', 'api_cost', 'net_value',
]

# Estimated manual processing time in minutes per document type
BENCHMARK_TIMES = {
    'INVOICE': 15,
    'LETTER': 20,
    'CONTRACT': 45,
    'TENDER': 120,
    'RAMS': 90,
    'CIS': 30,
    'PAYMENT_CERT': 40,
    'CREDIT_CONTROL': 15,
    'QUOTE': 25,
    'BLOG': 60,
    'PROGRESS_REPORT': 45,
    'COMPLIANCE': 20,
}

DEFAULT_MINUTES = 10

# Baseline hourly rate (GBP) for value calculation
ASSUMED_HOURLY_RATE = 15.00


def _ensure_csv():
    """Create the CSV with headers if it doesn't exist."""
    os.makedirs(VALUE_CSV.parent, exist_ok=True)
    if not VALUE_CSV.exists():
        with open(VALUE_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(_HEADERS)


def log_value(client_code, file_name, classification, api_cost):
    """Log the value delivered by processing a single file.

    Args:
        client_code: Client identifier (e.g. 'GILM').
        file_name: Name of the processed file.
        classification: Document type (e.g. 'INVOICE').
        api_cost: API cost in GBP for processing this file.
    """
    minutes_saved = BENCHMARK_TIMES.get(classification, DEFAULT_MINUTES)
    value_gbp = round((minutes_saved / 60) * ASSUMED_HOURLY_RATE, 4)
    net_value = round(value_gbp - api_cost, 4)

    _ensure_csv()
    with open(VALUE_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            client_code,
            file_name,
            classification,
            minutes_saved,
            f'{value_gbp:.4f}',
            f'{api_cost:.4f}',
            f'{net_value:.4f}',
        ])


def _read_rows():
    """Read all data rows from the CSV. Returns list of dicts."""
    if not VALUE_CSV.exists():
        return []
    with open(VALUE_CSV, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def _filter_rows(rows, client_code=None, month=None):
    """Filter rows by client and/or month (YYYY-MM format)."""
    filtered = rows
    if client_code:
        filtered = [r for r in filtered if r['client_code'] == client_code]
    if month:
        filtered = [r for r in filtered if r['timestamp'][:7] == month]
    return filtered


def _summarise(rows):
    """Aggregate a list of row dicts into a summary dict."""
    total_files = len(rows)
    total_minutes = sum(int(r['minutes_saved']) for r in rows)
    total_value = sum(float(r['value_gbp']) for r in rows)
    total_cost = sum(float(r['api_cost']) for r in rows)
    net = round(total_value - total_cost, 4)

    return {
        'total_files': total_files,
        'total_minutes_saved': total_minutes,
        'total_hours_saved': round(total_minutes / 60, 2),
        'total_value_gbp': round(total_value, 4),
        'total_api_cost': round(total_cost, 4),
        'net_value': net,
    }


def get_client_summary(client_code, month=None):
    """Get value summary for a single client.

    Args:
        client_code: Client identifier.
        month: Optional YYYY-MM string to filter by month.

    Returns dict with total_files, total_minutes_saved,
    total_hours_saved, total_value_gbp, total_api_cost, net_value.
    """
    rows = _read_rows()
    filtered = _filter_rows(rows, client_code=client_code, month=month)
    return _summarise(filtered)


def get_all_clients_summary(month=None):
    """Get value summary across all clients.

    Args:
        month: Optional YYYY-MM string to filter by month.

    Returns dict with the same keys as get_client_summary.
    """
    rows = _read_rows()
    filtered = _filter_rows(rows, month=month)
    return _summarise(filtered)
