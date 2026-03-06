"""Skill 3: QA Oversight Agent.

Full oversight scoring on 5 dimensions: factual accuracy, completeness,
tone match, format compliance, internal consistency. Graduation logic:
full QA for first 50 docs per workflow, then 1-in-5 spot check.
High-value workflows (RAMS, contracts, tenders, payment certs) never graduate.

Usage:
    python scripts/skills/qa_oversight.py <client_code> <workflow> <original_path> <output_path>
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils import claude_client, drive_client, sheets_client
from scripts.utils.prompt_builder import (
    load_base_prompt, load_client_config,
    load_brand_profile, load_tone_profile,
)

# Tracking sheet column indices
COL_QA_SCORE = 6
COL_QA_STATUS = 7
COL_NOTES = 8

# QA thresholds
PASS_THRESHOLD = 80
FLAG_THRESHOLD = 60

DIMENSIONS = [
    'factual_accuracy',
    'completeness',
    'tone_match',
    'format_compliance',
    'internal_consistency',
]

# Graduation config
GRADUATION_THRESHOLD = 50  # consecutive passes needed
SPOT_CHECK_FREQUENCY = 5   # after graduation, check 1 in N


QA_PROMPT = None


def get_qa_prompt():
    global QA_PROMPT
    if QA_PROMPT is None:
        QA_PROMPT = load_base_prompt('qa-oversight.txt')
    return QA_PROMPT


def load_routing_rules():
    """Load routing rules including never_graduate_qa list."""
    path = PROJECT_ROOT / 'config' / 'workflows' / 'routing-rules.json'
    if not path.exists():
        return {'never_graduate_qa': []}
    with open(path, 'r') as f:
        return json.load(f)


def load_client_corrections(client_code):
    """Load corrections from client's 07-LEARNING on Drive."""
    config = load_client_config(client_code)
    if not config:
        return []
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return []
    data = drive_client.download_json(learning_folder, 'corrections.json')
    return data.get('corrections', []) if data else []


def load_qa_stats(client_code):
    """Load qa-stats.json from client's 07-LEARNING on Drive."""
    config = load_client_config(client_code)
    if not config:
        return {'workflows': {}}
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return {'workflows': {}}
    data = drive_client.download_json(learning_folder, 'qa-stats.json')
    return data if data else {'workflows': {}}


def save_qa_stats(client_code, stats):
    """Save qa-stats.json to client's 07-LEARNING on Drive."""
    config = load_client_config(client_code)
    if not config:
        return
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return
    drive_client.upload_or_update_json(learning_folder, 'qa-stats.json', stats)


def should_run_qa(workflow_name, qa_stats, never_graduate_list):
    """Determine if QA should run for this file based on graduation status.

    Returns:
        (should_check, reason): tuple of bool and explanation string.
    """
    # Never-graduate workflows always get checked
    if workflow_name.upper() in [w.upper() for w in never_graduate_list]:
        return True, 'never-graduate workflow'

    wf_stats = qa_stats.get('workflows', {}).get(workflow_name, {})

    if not wf_stats.get('graduated', False):
        return True, 'not yet graduated'

    # Graduated — apply spot check frequency
    total = wf_stats.get('total_checked', 0)
    frequency = wf_stats.get('spot_check_frequency', SPOT_CHECK_FREQUENCY)
    if (total + 1) % frequency == 0:
        return True, f'spot check (1 in {frequency})'

    return False, 'graduated — skipping'


def score_output(client_code, workflow_name, original_content, output_content):
    """Send original + output + client profiles to Sonnet for QA scoring.

    Returns dict with dimension scores and overall status.
    """
    system_prompt = get_qa_prompt()

    # Load client learning data
    brand_profile = load_brand_profile(client_code)
    tone_profile = load_tone_profile(client_code)
    corrections = load_client_corrections(client_code)

    # Filter corrections relevant to this workflow
    relevant_corrections = [
        c for c in corrections if c.get('workflow') == workflow_name
    ]

    # Build the QA request
    prompt_parts = [
        f"## Workflow: {workflow_name}\n",
        f"## Original Document\n{original_content[:8000]}\n",
        f"## Processed Output\n{output_content[:8000]}\n",
    ]

    if brand_profile:
        prompt_parts.append(
            f"## Brand Profile\n{json.dumps(brand_profile, indent=2)}\n"
        )

    if tone_profile:
        prompt_parts.append(
            f"## Tone Profile\n{json.dumps(tone_profile, indent=2)}\n"
        )

    if relevant_corrections:
        prompt_parts.append(
            f"## Known Correction Patterns for {workflow_name}\n"
            f"{json.dumps(relevant_corrections, indent=2)}\n"
        )

    prompt = '\n'.join(prompt_parts)

    result = claude_client.send_message_json(
        prompt=prompt,
        system_prompt=system_prompt,
        model_tier='MODEL_STANDARD',
        max_tokens=2000,
        client_code=client_code,
        workflow='qa-oversight',
    )

    return result


def apply_thresholds(scores):
    """Apply PASS/FLAG/FAIL thresholds to dimension scores.

    Args:
        scores: dict with dimension name -> score (0-100).

    Returns:
        dict with 'dimensions' (per-dimension status), 'overall_status',
        'overall_score', and 'failed_dimensions'.
    """
    dimensions = {}
    failed = []
    flagged = []

    for dim in DIMENSIONS:
        score = scores.get(dim, 0)
        if score >= PASS_THRESHOLD:
            status = 'PASS'
        elif score >= FLAG_THRESHOLD:
            status = 'FLAG'
            flagged.append(dim)
        else:
            status = 'FAIL'
            failed.append(dim)

        dimensions[dim] = {'score': score, 'status': status}

    # Overall = worst dimension
    if failed:
        overall = 'FAIL'
    elif flagged:
        overall = 'FLAG'
    else:
        overall = 'PASS'

    # Average score for display
    dim_scores = [dimensions[d]['score'] for d in DIMENSIONS]
    overall_score = round(sum(dim_scores) / len(dim_scores), 1) if dim_scores else 0

    return {
        'dimensions': dimensions,
        'overall_status': overall,
        'overall_score': overall_score,
        'failed_dimensions': failed,
        'flagged_dimensions': flagged,
    }


def update_graduation(workflow_name, overall_status, qa_stats, never_graduate_list):
    """Update graduation tracking in qa_stats.

    Returns updated qa_stats dict.
    """
    workflows = qa_stats.setdefault('workflows', {})
    wf = workflows.setdefault(workflow_name, {
        'total_checked': 0,
        'consecutive_pass': 0,
        'graduated': False,
        'graduation_date': None,
        'spot_check_frequency': SPOT_CHECK_FREQUENCY,
        'last_fail': None,
    })

    wf['total_checked'] += 1

    if overall_status == 'PASS':
        wf['consecutive_pass'] += 1
    else:
        wf['consecutive_pass'] = 0
        wf['last_fail'] = datetime.now().isoformat()
        # Any fail resets graduation
        if wf['graduated']:
            wf['graduated'] = False
            wf['graduation_date'] = None
            log.warning(f"Graduation REVOKED for {workflow_name} after FAIL")

    # Check graduation (never-graduate excluded)
    is_never_graduate = workflow_name.upper() in [w.upper() for w in never_graduate_list]
    if (not is_never_graduate
            and not wf['graduated']
            and wf['consecutive_pass'] >= GRADUATION_THRESHOLD):
        wf['graduated'] = True
        wf['graduation_date'] = datetime.now().isoformat()
        log.info(f"Workflow {workflow_name} GRADUATED after {GRADUATION_THRESHOLD} consecutive passes")

    return qa_stats


def update_tracking_sheet(client_code, file_name, overall_status, overall_score, notes=''):
    """Update the client's Google Sheet tracking row with QA results."""
    config = load_client_config(client_code)
    if not config:
        return
    sheet_id = config.get('tracking_sheet_id')
    if not sheet_id:
        log.warning("No tracking_sheet_id configured")
        return

    # Find the row for this file
    row_num, row_data = sheets_client.find_row_by_value(
        sheet_id, 0, file_name
    )
    if row_num is None:
        log.warning(f"File '{file_name}' not found in tracking sheet")
        return

    # Update QA Score and QA Status columns
    sheets_client.update_row_field(sheet_id, row_num, COL_QA_SCORE, overall_score)
    sheets_client.update_row_field(sheet_id, row_num, COL_QA_STATUS, overall_status)

    if notes:
        sheets_client.update_row_field(sheet_id, row_num, COL_NOTES, notes)


def read_file_content(filepath):
    """Read file content for QA comparison.

    Handles text, JSON, docx, and PDF files.
    """
    ext = Path(filepath).suffix.lower()

    if ext == '.json':
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return json.dumps(data, indent=2)

    if ext == '.docx':
        try:
            from docx import Document
            doc = Document(filepath)
            return '\n'.join(p.text for p in doc.paragraphs)
        except ImportError:
            log.warning("python-docx not available, reading as binary")

    if ext == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                text = ''
                for page in pdf.pages[:10]:
                    text += (page.extract_text() or '') + '\n'
                return text
        except ImportError:
            log.warning("pdfplumber not available for PDF reading")

    # Default: read as text
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        with open(filepath, 'rb') as f:
            return f.read(8000).decode('utf-8', errors='replace')


def run_qa(client_code, workflow_name, original_path, output_path, file_name=None):
    """Main QA function.

    Args:
        client_code: Client code (e.g. 'GILM').
        workflow_name: Workflow name (e.g. 'invoice-processor').
        original_path: Path to original input file.
        output_path: Path to processed output file.
        file_name: Filename for tracking sheet lookup (defaults to output filename).

    Returns:
        QA result dict or None if skipped.
    """
    if file_name is None:
        file_name = Path(output_path).name

    config = load_client_config(client_code)
    if not config:
        log.error(f"Client config not found for: {client_code}")
        return None

    # Load routing rules
    routing = load_routing_rules()
    never_graduate = routing.get('never_graduate_qa', [])

    # Load QA stats
    qa_stats = load_qa_stats(client_code)

    # Check if QA should run
    should_check, reason = should_run_qa(workflow_name, qa_stats, never_graduate)
    if not should_check:
        log.info(f"QA skipped for {file_name}: {reason}")
        return {'skipped': True, 'reason': reason}

    log.info(f"Running QA for {file_name} ({reason})")

    # Read file contents
    original_content = read_file_content(original_path)
    output_content = read_file_content(output_path)

    # Score via Sonnet
    raw_scores = score_output(
        client_code, workflow_name, original_content, output_content
    )

    # Apply thresholds
    result = apply_thresholds(raw_scores)
    result['workflow'] = workflow_name
    result['file_name'] = file_name
    result['timestamp'] = datetime.now().isoformat()
    result['qa_reason'] = reason

    # Collect notes from scoring
    notes_parts = []
    if raw_scores.get('notes'):
        notes_parts.append(raw_scores['notes'])
    if result['failed_dimensions']:
        notes_parts.append(f"FAILED: {', '.join(result['failed_dimensions'])}")
    if result['flagged_dimensions']:
        notes_parts.append(f"FLAGGED: {', '.join(result['flagged_dimensions'])}")
    notes = '; '.join(notes_parts)

    # Update graduation tracking
    qa_stats = update_graduation(
        workflow_name, result['overall_status'], qa_stats, never_graduate
    )
    save_qa_stats(client_code, qa_stats)

    # Update tracking sheet
    try:
        update_tracking_sheet(
            client_code, file_name, result['overall_status'],
            result['overall_score'], notes
        )
    except Exception as e:
        log.warning(f"Could not update tracking sheet: {e}")

    # Print summary
    print(f"\n{'='*50}")
    print(f"QA Result — {file_name}")
    print(f"{'='*50}")
    print(f"Workflow:  {workflow_name}")
    print(f"Overall:   {result['overall_status']} ({result['overall_score']})")
    for dim in DIMENSIONS:
        d = result['dimensions'][dim]
        print(f"  {dim:25s} {d['score']:5.0f}  {d['status']}")
    if notes:
        print(f"\nNotes: {notes}")

    wf_stats = qa_stats.get('workflows', {}).get(workflow_name, {})
    print(f"\nGraduation: {'YES' if wf_stats.get('graduated') else 'NO'} "
          f"(streak: {wf_stats.get('consecutive_pass', 0)}/{GRADUATION_THRESHOLD})")
    print(f"{'='*50}")

    return result


def main():
    parser = argparse.ArgumentParser(description='Skill 3: QA Oversight Agent')
    parser.add_argument('client_code', help='Client code (e.g. GILM)')
    parser.add_argument('workflow', help='Workflow name (e.g. invoice-processor)')
    parser.add_argument('original', help='Path to original input file')
    parser.add_argument('output', help='Path to processed output file')
    parser.add_argument('--file-name', help='Filename for tracking sheet (defaults to output filename)')
    args = parser.parse_args()

    run_qa(args.client_code, args.workflow, args.original, args.output, args.file_name)


if __name__ == '__main__':
    main()
