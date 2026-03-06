"""OPS-02: API Credit Monitoring and Circuit Breaker.

Reads the cost log (logs/api_costs.csv) written by cost_logger.log_api_call(),
tracks monthly spend, and pauses processing when the budget is nearly exhausted.

Usage in drive_watcher.py:
    from scripts.utils import credit_monitor

    if not credit_monitor.check_and_warn():
        # Budget exhausted — skip this poll cycle
        continue

    if not credit_monitor.can_process_batch(len(new_files)):
        # Not enough credit for this batch — skip client
        continue
"""

import csv
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils import resend_client

# Budget and thresholds (USD)
MONTHLY_BUDGET = float(os.getenv('MONTHLY_API_BUDGET', '50.00'))
CREDIT_THRESHOLD = 5.00    # Stop processing if remaining < $5
WARNING_THRESHOLD = 10.00  # Send warning if remaining < $10

# Conservative default cost per file when no historical data exists.
# Based on cost_summary.py estimates: classification ~$0.001,
# plus downstream processing ~$0.02 = ~$0.05 conservative.
DEFAULT_COST_PER_FILE = 0.05

# Cost CSV written by utils/cost_logger.py
COST_CSV = PROJECT_ROOT / 'logs' / 'api_costs.csv'


def get_monthly_spend(month=None):
    """Sum estimated_cost from the cost log for a given month.

    Args:
        month: 'YYYY-MM' string. Defaults to current month.

    Returns:
        Total spend in USD for the month as a float.
    """
    if month is None:
        month = datetime.now().strftime('%Y-%m')

    total = 0.0
    if not COST_CSV.exists():
        return total

    with open(COST_CSV, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header row
        for row in reader:
            if len(row) < 7:
                continue
            timestamp = row[0]
            if timestamp.startswith(month):
                try:
                    total += float(row[6])  # estimated_cost column
                except (ValueError, IndexError):
                    continue
    return total


def get_remaining_credit():
    """Calculate remaining credit for the current month.

    Returns:
        MONTHLY_BUDGET minus current month's spend, clamped to >= 0.
    """
    remaining = MONTHLY_BUDGET - get_monthly_spend()
    return max(0.0, remaining)


def get_average_cost_per_file():
    """Calculate average cost per API call from historical data.

    Reads all rows in the cost log and divides total cost by number
    of calls. Returns DEFAULT_COST_PER_FILE if no data exists.
    """
    if not COST_CSV.exists():
        return DEFAULT_COST_PER_FILE

    total_cost = 0.0
    call_count = 0

    with open(COST_CSV, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header
        for row in reader:
            if len(row) < 7:
                continue
            try:
                total_cost += float(row[6])
                call_count += 1
            except (ValueError, IndexError):
                continue

    if call_count == 0:
        return DEFAULT_COST_PER_FILE

    return total_cost / call_count


def can_process_batch(file_count):
    """Estimate whether there's enough credit to process a batch.

    Args:
        file_count: Number of files to process.

    Returns:
        True if estimated remaining credit after the batch
        would still be >= CREDIT_THRESHOLD.
    """
    if file_count <= 0:
        return True

    avg_cost = get_average_cost_per_file()
    estimated_batch_cost = file_count * avg_cost
    remaining = get_remaining_credit()

    return (remaining - estimated_batch_cost) >= CREDIT_THRESHOLD


def send_low_credit_warning(remaining, threshold_type):
    """Send a low-credit alert email to the admin.

    Args:
        remaining: Current remaining credit in USD.
        threshold_type: 'WARNING' (still processing) or 'PAUSED' (stopped).
    """
    status = 'WARNING' if threshold_type == 'WARNING' else 'PAUSED'
    subject = f"[Ictus Flow] API Credit {status}: ${remaining:.2f} remaining"
    body_html = f"""
    <h2>API Credit {status}</h2>
    <table>
        <tr><td><strong>Remaining Credit:</strong></td><td>${remaining:.2f}</td></tr>
        <tr><td><strong>Monthly Budget:</strong></td><td>${MONTHLY_BUDGET:.2f}</td></tr>
        <tr><td><strong>Month:</strong></td><td>{datetime.now().strftime('%Y-%m')}</td></tr>
        <tr><td><strong>Status:</strong></td><td>{'Processing continues with caution' if status == 'WARNING' else 'Processing PAUSED until budget is topped up or new month starts'}</td></tr>
    </table>
    <p>{'Consider increasing MONTHLY_API_BUDGET in .env or reducing processing volume.' if status == 'WARNING' else 'All file processing has been paused. Increase MONTHLY_API_BUDGET in .env or wait for the new billing month.'}</p>
    """
    try:
        resend_client.send_admin_notification(subject, body_html)
    except Exception as e:
        print(f"  WARNING: Could not send credit alert email: {e}")


def check_and_warn():
    """Check credit level, send warnings if needed, return whether to proceed.

    Called at the top of each poll cycle in drive_watcher.run().

    Returns:
        True if processing should continue.
        False if processing should be paused (credit below CREDIT_THRESHOLD).
    """
    remaining = get_remaining_credit()

    if remaining < CREDIT_THRESHOLD:
        print(f"CREDIT MONITOR: ${remaining:.2f} remaining — below ${CREDIT_THRESHOLD:.2f} threshold. PAUSING.")
        send_low_credit_warning(remaining, 'PAUSED')
        return False

    if remaining < WARNING_THRESHOLD:
        print(f"CREDIT MONITOR: ${remaining:.2f} remaining — below ${WARNING_THRESHOLD:.2f} warning level.")
        send_low_credit_warning(remaining, 'WARNING')
        return True  # Continue processing but warn

    return True
