"""Skill 4: Correction Logger.

Captures every correction through two paths:
  - Auto-diff: detects changes between original output and final version
  - Manual notes: reads CORRECTION: entries from the tracking sheet

Categorises errors and builds the client-specific knowledge base that
feeds into QA (Skill 3) and Prompt Refiner (Skill 6).

Usage:
    # Auto-diff mode (after file completion)
    python scripts/skills/correction_logger.py auto <client_code> <file_id>

    # Manual notes mode (run daily)
    python scripts/skills/correction_logger.py manual <client_code>
"""

import os
import sys
import json
import argparse
import logging
import uuid
import difflib
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils import claude_client, drive_client, sheets_client
from scripts.utils.prompt_builder import load_base_prompt, load_client_config
from scripts.utils.client_guard import validate_client_operation

# Tracking sheet column indices (from sheets_client.TRACKING_HEADERS)
COL_FILE_NAME = 0
COL_STATUS = 4
COL_WORKFLOW = 5
COL_NOTES = 8

# Valid correction categories
CATEGORIES = [
    'numerical_error',
    'missing_data',
    'wrong_classification',
    'formatting_error',
    'tone_mismatch',
    'factual_error',
]

CATEGORISATION_PROMPT = None


def get_categorisation_prompt():
    global CATEGORISATION_PROMPT
    if CATEGORISATION_PROMPT is None:
        CATEGORISATION_PROMPT = load_base_prompt('correction-logger.txt')
    return CATEGORISATION_PROMPT


def load_corrections(client_code):
    """Load existing corrections.json from client's 07-LEARNING on Drive."""
    config = load_client_config(client_code)
    if not config:
        return {'corrections': []}
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return {'corrections': []}
    # SEC-02: Validate client boundary
    validate_client_operation(client_code, learning_folder)
    data = drive_client.download_json(learning_folder, 'corrections.json')
    return data if data else {'corrections': []}


def save_corrections(client_code, corrections_data):
    """Save corrections.json to client's 07-LEARNING on Drive."""
    config = load_client_config(client_code)
    if not config:
        return
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return
    # SEC-02: Validate client boundary
    validate_client_operation(client_code, learning_folder)
    drive_client.upload_or_update_json(
        learning_folder, 'corrections.json', corrections_data
    )


def diff_json(original, final):
    """Compare two JSON objects field-by-field.

    Returns list of dicts with field, original_value, corrected_value.
    """
    changes = []

    if isinstance(original, dict) and isinstance(final, dict):
        all_keys = set(list(original.keys()) + list(final.keys()))
        for key in sorted(all_keys):
            orig_val = original.get(key)
            final_val = final.get(key)
            if orig_val != final_val:
                # Recurse for nested dicts
                if isinstance(orig_val, dict) and isinstance(final_val, dict):
                    sub_changes = diff_json(orig_val, final_val)
                    for sc in sub_changes:
                        sc['field'] = f"{key}.{sc['field']}"
                        changes.append(sc)
                else:
                    changes.append({
                        'field': key,
                        'original_value': _safe_str(orig_val),
                        'corrected_value': _safe_str(final_val),
                    })
    elif isinstance(original, list) and isinstance(final, list):
        for i, (o, f) in enumerate(zip(original, final)):
            if o != f:
                changes.append({
                    'field': f'[{i}]',
                    'original_value': _safe_str(o),
                    'corrected_value': _safe_str(f),
                })
        # Handle length differences
        if len(final) > len(original):
            for i in range(len(original), len(final)):
                changes.append({
                    'field': f'[{i}]',
                    'original_value': None,
                    'corrected_value': _safe_str(final[i]),
                })
        elif len(original) > len(final):
            for i in range(len(final), len(original)):
                changes.append({
                    'field': f'[{i}]',
                    'original_value': _safe_str(original[i]),
                    'corrected_value': None,
                })
    else:
        if original != final:
            changes.append({
                'field': '_root',
                'original_value': _safe_str(original),
                'corrected_value': _safe_str(final),
            })

    return changes


def diff_text(original_text, final_text):
    """Compare two text documents using unified diff.

    Returns a summary string of changes.
    """
    orig_lines = original_text.splitlines(keepends=True)
    final_lines = final_text.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        orig_lines, final_lines,
        fromfile='original', tofile='corrected', n=2
    ))

    if not diff:
        return None

    return ''.join(diff)


def categorise_changes(changes_description, workflow_name, client_code):
    """Send changes to Sonnet for categorisation.

    Args:
        changes_description: String describing the changes (diff or field list).
        workflow_name: The workflow that produced the output.
        client_code: Client code for cost tracking.

    Returns:
        List of correction dicts ready to append.
    """
    system_prompt = get_categorisation_prompt()
    prompt = (
        f"Workflow: {workflow_name}\n\n"
        f"Changes detected:\n{changes_description}\n\n"
        f"Categorise each change and return the result."
    )

    result = claude_client.send_message_json(
        prompt=prompt,
        system_prompt=system_prompt,
        model_tier='MODEL_STANDARD',
        max_tokens=2000,
        client_code=client_code,
        workflow='correction-logger',
    )

    # Normalise response — expect list of corrections
    corrections = result if isinstance(result, list) else result.get('corrections', [result])

    # Validate and enrich each correction
    validated = []
    for corr in corrections:
        entry = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'workflow': workflow_name,
            'category': _validate_category(corr.get('category', 'factual_error')),
            'field': corr.get('field', 'unknown'),
            'original_value': corr.get('original_value'),
            'corrected_value': corr.get('corrected_value'),
            'cause': corr.get('cause', ''),
            'source': corr.get('source', 'auto-diff'),
            'promoted_to': None,
        }
        validated.append(entry)

    return validated


def _validate_category(category):
    """Ensure category is one of the valid values."""
    if category in CATEGORIES:
        return category
    # Fuzzy match
    category_lower = category.lower().replace(' ', '_').replace('-', '_')
    for valid in CATEGORIES:
        if valid in category_lower or category_lower in valid:
            return valid
    return 'factual_error'


def _safe_str(val):
    """Convert value to string safely for storage."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return str(val)
    return str(val)


def read_file_content(filepath):
    """Read file content, handling JSON, text, and docx."""
    ext = Path(filepath).suffix.lower()

    if ext == '.json':
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    if ext == '.docx':
        try:
            from docx import Document
            doc = Document(filepath)
            return '\n'.join(p.text for p in doc.paragraphs)
        except ImportError:
            pass

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        with open(filepath, 'rb') as f:
            return f.read().decode('utf-8', errors='replace')


# ── Auto-Diff Mode ──────────────────────────────────────────────────

def run_auto_diff(client_code, file_id):
    """Auto-diff mode: compare original output with final version.

    Downloads both versions from Drive (02-PROCESSING vs 03-COMPLETED),
    diffs them, categorises changes, and appends to corrections.json.
    """
    config = load_client_config(client_code)
    if not config:
        log.error(f"Client config not found for: {client_code}")
        return []

    # Get file metadata
    try:
        file_meta = drive_client.get_file_metadata(file_id)
    except Exception as e:
        log.error(f"Could not get file metadata: {e}")
        return []

    file_name = file_meta.get('name', 'unknown')
    log.info(f"Auto-diff for: {file_name}")

    # Find the original version in 02-PROCESSING
    processing_folder = config.get('folders', {}).get('processing')
    completed_folder = config.get('folders', {}).get('completed')

    if not processing_folder or not completed_folder:
        log.error("Missing processing or completed folder in config")
        return []

    # SEC-02: Validate client boundary
    validate_client_operation(client_code, processing_folder)
    validate_client_operation(client_code, completed_folder)

    # Download both versions
    import shutil as _shutil
    import uuid as _uuid
    tmpdir = os.path.join(
        os.environ.get('TEMP', '/tmp'), 'ictus-flow-processing',
        f'correction-diff-{_uuid.uuid4().hex[:8]}',
    )
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # The file_id should be the completed version
        completed_path = os.path.join(tmpdir, f'completed_{file_name}')
        drive_client.download_file(file_id, completed_path)

        # Find original in processing folder
        original_file = drive_client.find_file_by_name(processing_folder, file_name)
        if not original_file:
            log.info(f"No original found in processing folder — file is new, no diff needed")
            return []

        original_path = os.path.join(tmpdir, f'original_{file_name}')
        drive_client.download_file(original_file['id'], original_path)

        # Read and compare
        original_content = read_file_content(original_path)
        final_content = read_file_content(completed_path)

        # Diff based on type
        ext = Path(file_name).suffix.lower()
        if ext == '.json' and isinstance(original_content, dict) and isinstance(final_content, dict):
            changes = diff_json(original_content, final_content)
            if not changes:
                log.info("No changes detected — no corrections to log")
                return []
            changes_desc = json.dumps(changes, indent=2)
        else:
            orig_text = original_content if isinstance(original_content, str) else json.dumps(original_content)
            final_text = final_content if isinstance(final_content, str) else json.dumps(final_content)
            diff_result = diff_text(orig_text, final_text)
            if not diff_result:
                log.info("No changes detected — no corrections to log")
                return []
            changes_desc = diff_result
    finally:
        _shutil.rmtree(tmpdir, ignore_errors=True)

    # Determine workflow from tracking sheet
    workflow_name = _get_workflow_from_sheet(client_code, file_name)

    # Categorise via Sonnet
    new_corrections = categorise_changes(changes_desc, workflow_name, client_code)

    if not new_corrections:
        log.info("No corrections categorised")
        return []

    # Append to corrections.json
    corrections_data = load_corrections(client_code)
    corrections_data['corrections'].extend(new_corrections)
    save_corrections(client_code, corrections_data)

    log.info(f"Logged {len(new_corrections)} correction(s) for {file_name}")

    # Print summary
    _print_corrections_summary(new_corrections, file_name)

    return new_corrections


# ── Manual Notes Mode ───────────────────────────────────────────────

def run_manual_notes(client_code):
    """Manual notes mode: read CORRECTION: entries from tracking sheet.

    Finds Notes column entries starting with 'CORRECTION:', categorises
    them, and appends to corrections.json.
    """
    config = load_client_config(client_code)
    if not config:
        log.error(f"Client config not found for: {client_code}")
        return []

    sheet_id = config.get('tracking_sheet_id')
    if not sheet_id:
        log.error("No tracking_sheet_id configured")
        return []

    # Read tracking sheet
    rows = sheets_client.read_sheet(sheet_id, 'Tracking!A:J')
    if not rows or len(rows) < 2:
        log.info("Tracking sheet empty or header-only")
        return []

    headers = rows[0]
    all_new_corrections = []

    for row_idx, row in enumerate(rows[1:], start=2):
        # Ensure row has enough columns
        if len(row) <= COL_NOTES:
            continue

        notes = row[COL_NOTES].strip()
        if not notes.upper().startswith('CORRECTION:'):
            continue

        # Check if already processed
        if notes.endswith('[LOGGED]'):
            continue

        correction_text = notes[len('CORRECTION:'):].strip()
        file_name = row[COL_FILE_NAME] if len(row) > COL_FILE_NAME else 'unknown'
        workflow = row[COL_WORKFLOW] if len(row) > COL_WORKFLOW else 'unknown'

        log.info(f"Processing correction note for {file_name}: {correction_text[:60]}...")

        # Categorise via Sonnet
        new_corrections = categorise_changes(
            correction_text, workflow, client_code
        )

        # Set source to manual
        for corr in new_corrections:
            corr['source'] = 'manual'

        all_new_corrections.extend(new_corrections)

        # Mark as processed in the sheet
        try:
            sheets_client.update_row_field(
                sheet_id, row_idx, COL_NOTES, f"{notes} [LOGGED]"
            )
        except Exception as e:
            log.warning(f"Could not mark row {row_idx} as logged: {e}")

    if not all_new_corrections:
        log.info("No new correction notes found")
        return []

    # Append to corrections.json
    corrections_data = load_corrections(client_code)
    corrections_data['corrections'].extend(all_new_corrections)
    save_corrections(client_code, corrections_data)

    log.info(f"Logged {len(all_new_corrections)} correction(s) from manual notes")
    _print_corrections_summary(all_new_corrections, 'manual notes')

    return all_new_corrections


def _get_workflow_from_sheet(client_code, file_name):
    """Look up the workflow name for a file from the tracking sheet."""
    config = load_client_config(client_code)
    if not config:
        return 'unknown'
    sheet_id = config.get('tracking_sheet_id')
    if not sheet_id:
        return 'unknown'
    try:
        row_num, row_data = sheets_client.find_row_by_value(
            sheet_id, COL_FILE_NAME, file_name
        )
        if row_data and len(row_data) > COL_WORKFLOW:
            return row_data[COL_WORKFLOW]
    except Exception:
        pass
    return 'unknown'


def _print_corrections_summary(corrections, source_label):
    """Print a summary of logged corrections."""
    print(f"\n{'='*50}")
    print(f"Corrections Logged — {source_label}")
    print(f"{'='*50}")
    for c in corrections:
        print(f"  [{c['category']}] {c['field']}: "
              f"{c['original_value']} -> {c['corrected_value']}")
        if c.get('cause'):
            print(f"    Cause: {c['cause']}")
    print(f"Total: {len(corrections)}")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description='Skill 4: Correction Logger')
    sub = parser.add_subparsers(dest='mode', required=True)

    auto_parser = sub.add_parser('auto', help='Auto-diff mode')
    auto_parser.add_argument('client_code', help='Client code (e.g. GILM)')
    auto_parser.add_argument('file_id', help='Drive file ID of completed file')

    manual_parser = sub.add_parser('manual', help='Manual notes mode')
    manual_parser.add_argument('client_code', help='Client code (e.g. GILM)')

    args = parser.parse_args()

    if args.mode == 'auto':
        run_auto_diff(args.client_code, args.file_id)
    elif args.mode == 'manual':
        run_manual_notes(args.client_code)


if __name__ == '__main__':
    main()
