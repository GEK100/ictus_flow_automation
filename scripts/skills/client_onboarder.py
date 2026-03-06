"""Skill 8: Client Onboarder.

One command, full onboarding: Drive folders, brand profiling,
tone fingerprinting, config, tracking sheet, welcome email.

Usage:
    python scripts/skills/client_onboarder.py "Client Name" client@email.com [--code XXXX] [--samples /path/to/docs]
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

from scripts.utils import drive_client, sheets_client, resend_client


# Drive folder structure per client
FOLDER_STRUCTURE = [
    ('01-DROP FILES HERE', 'inbox'),
    ('02-PROCESSING', 'processing'),
    ('03-COMPLETED', 'completed'),
    ('04-ARCHIVE', 'archive'),
    ('05-BRAND-ASSETS', 'brand_assets'),
    ('06-TEMPLATES', 'templates'),
    ('07-LEARNING', 'learning'),
]

# Empty learning files with valid schemas
EMPTY_CORRECTIONS = {'corrections': [], 'last_updated': None}
EMPTY_QA_STATS = {'workflows': {}}
EMPTY_OUTPUT_FORMATS = {'formats': {}, 'generated_at': None}


def generate_client_code(client_name):
    """Auto-generate a 4-char client code from the name."""
    words = client_name.upper().split()
    if len(words) >= 2:
        return (words[0][:2] + words[1][:2])[:4]
    return words[0][:4]


def create_drive_folders(client_name):
    """Create the full Drive folder structure.

    Returns dict mapping config keys to folder IDs.
    """
    root_name = f"{client_name} — Ictus Flow"
    log.info(f"Creating Drive folder: {root_name}")
    root_id = drive_client.create_folder(root_name)

    folder_ids = {'root': root_id}
    for folder_name, config_key in FOLDER_STRUCTURE:
        log.info(f"  Creating subfolder: {folder_name}")
        folder_id = drive_client.create_folder(folder_name, root_id)
        folder_ids[config_key] = folder_id

    # OPS-01: Create _FAILED subfolder inside 02-PROCESSING
    log.info("  Creating subfolder: 02-PROCESSING/_FAILED")
    failed_id = drive_client.create_folder('_FAILED', folder_ids['processing'])
    folder_ids['failed'] = failed_id

    return folder_ids


def share_with_client(folder_ids, client_email):
    """Share root folder with client and service account."""
    log.info(f"Sharing folder with {client_email}")
    try:
        drive_client.share_folder(folder_ids['root'], client_email, role='writer')
    except Exception as e:
        log.error(f"Failed to share with {client_email}: {e}")
        return False
    return True


def upload_sample_docs(folder_ids, samples_folder):
    """Upload sample documents to 05-BRAND-ASSETS."""
    if not samples_folder or not os.path.exists(samples_folder):
        log.info("No sample documents to upload")
        return 0

    count = 0
    for filename in os.listdir(samples_folder):
        filepath = os.path.join(samples_folder, filename)
        if os.path.isfile(filepath):
            log.info(f"  Uploading: {filename}")
            drive_client.upload_file(filepath, folder_ids['brand_assets'])
            count += 1

    log.info(f"Uploaded {count} sample documents")
    return count


def init_learning_files(folder_ids):
    """Create empty learning files with valid schemas in 07-LEARNING."""
    learning_id = folder_ids['learning']
    drive_client.upload_or_update_json(learning_id, 'corrections.json', EMPTY_CORRECTIONS)
    drive_client.upload_or_update_json(learning_id, 'qa-stats.json', EMPTY_QA_STATS)
    drive_client.upload_or_update_json(learning_id, 'output-formats.json', EMPTY_OUTPUT_FORMATS)
    log.info("Initialised empty learning files in 07-LEARNING")


def create_tracking_sheet(client_name):
    """Create Google Sheet for tracking. Returns sheet ID."""
    title = f"{client_name} — Ictus Flow Tracking"
    log.info(f"Creating tracking sheet: {title}")
    sheet_id = sheets_client.create_spreadsheet(
        title=title,
        sheet_name='Tracking',
        headers=sheets_client.TRACKING_HEADERS,
    )

    # OPS-01: Add conditional formatting so FAILED rows are visually obvious
    try:
        sheets_client.add_failed_row_formatting(sheet_id)
        log.info("Added FAILED row conditional formatting")
    except Exception as e:
        log.warning(f"Could not add FAILED formatting (non-fatal): {e}")

    return sheet_id


def write_client_config(
    client_name, client_code, client_email, folder_ids,
    sheet_id, brand_generated=False, tone_generated=False,
):
    """Write the client config JSON file."""
    config = {
        'client_name': client_name,
        'client_code': client_code,
        'contact_name': '',
        'contact_email': client_email,
        'intake_email': f"{client_code.lower()}@ictusflow.com",
        'folders': folder_ids,
        'active_workflows': ['invoice_processing'],
        'tracking_sheet_id': sheet_id,
        'brand': {
            'profile_generated': brand_generated,
            'primary_color': '',
            'secondary_color': '',
            'font': '',
        },
        'tone': {
            'profile_generated': tone_generated,
            'formality': None,
        },
        'qa': {
            'graduated_workflows': [],
        },
    }

    config_path = PROJECT_ROOT / 'config' / 'clients' / f'{client_code.lower()}.json'
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

    log.info(f"Client config saved: {config_path}")
    return config


def send_welcome_email(client_name, client_email):
    """Send welcome email to client."""
    html = f"""
    <h2>Welcome to Ictus Flow</h2>
    <p>Hi,</p>
    <p>Your Ictus Flow workspace for <strong>{client_name}</strong> is ready.</p>
    <p><strong>How it works:</strong></p>
    <ol>
        <li>Drop files into the <strong>01-DROP FILES HERE</strong> folder in Google Drive</li>
        <li>We'll automatically classify and process your documents</li>
        <li>Find completed work in the <strong>03-COMPLETED</strong> folder</li>
        <li>You'll receive email notifications when work is done</li>
    </ol>
    <p><strong>Getting started:</strong></p>
    <ul>
        <li>Upload any brand assets (logos, letterheads) to <strong>05-BRAND-ASSETS</strong></li>
        <li>Upload any existing templates to <strong>06-TEMPLATES</strong></li>
    </ul>
    <p>Any questions? Just reply to this email.</p>
    <p>Best regards,<br>Gareth Kerr<br>Ictus Flow</p>
    """
    try:
        resend_client.send_email(client_email, f"Welcome to Ictus Flow — {client_name}", html)
        log.info(f"Welcome email sent to {client_email}")
        return True
    except Exception as e:
        log.error(f"Failed to send welcome email: {e}")
        return False


def onboard_client(client_name, client_email, client_code=None, samples_folder=None):
    """Full onboarding sequence.

    Returns dict with summary of what was created.
    """
    if not client_code:
        client_code = generate_client_code(client_name)
    client_code = client_code.upper()

    log.info(f"\n{'='*50}")
    log.info(f"Onboarding: {client_name} ({client_code})")
    log.info(f"{'='*50}\n")

    errors = []
    summary = {
        'client_name': client_name,
        'client_code': client_code,
        'client_email': client_email,
    }

    # Step 1: Create Drive folders
    try:
        folder_ids = create_drive_folders(client_name)
        summary['folders_created'] = True
    except Exception as e:
        log.error(f"Drive folder creation failed: {e}")
        errors.append(f"Drive folders: {e}")
        return {'errors': errors}

    # Step 2: Share with client
    shared = share_with_client(folder_ids, client_email)
    if not shared:
        errors.append(f"Sharing failed for {client_email}")

    # Step 3: Upload sample docs
    sample_count = 0
    if samples_folder:
        try:
            sample_count = upload_sample_docs(folder_ids, samples_folder)
        except Exception as e:
            errors.append(f"Sample upload: {e}")
    summary['samples_uploaded'] = sample_count

    # Step 4: Run Brand Profiler (if samples exist)
    brand_generated = False
    if sample_count > 0:
        try:
            from scripts.skills.brand_profiler import run_brand_profiler
            # Need to write config first so brand profiler can read it
            sheet_id = 'PENDING'
            write_client_config(
                client_name, client_code, client_email,
                folder_ids, sheet_id,
            )
            profile = run_brand_profiler(client_code)
            brand_generated = profile is not None
        except Exception as e:
            log.warning(f"Brand profiling failed (non-fatal): {e}")
            errors.append(f"Brand profiler: {e}")
    else:
        # Create empty brand profile with all gaps
        empty_brand = {
            'colours': {'primary': None, 'secondary': None, 'accent': None},
            'fonts': {'primary': None, 'secondary': None},
            'layout': {'date_format': None, 'reference_pattern': None, 'logo_position': None},
            'gaps': ['All fields — no brand documents provided'],
            'source_doc_count': 0, 'generated_at': datetime.now().isoformat(),
        }
        drive_client.upload_or_update_json(folder_ids['learning'], 'brand-profile.json', empty_brand)

    summary['brand_generated'] = brand_generated

    # Step 5: Run Tone Fingerprinter (if samples exist)
    tone_generated = False
    if sample_count > 0:
        try:
            from scripts.skills.tone_fingerprinter import run_tone_fingerprinter
            profile = run_tone_fingerprinter(client_code)
            tone_generated = profile is not None
        except Exception as e:
            log.warning(f"Tone fingerprinting failed (non-fatal): {e}")
            errors.append(f"Tone fingerprinter: {e}")
    else:
        empty_tone = {
            'formality': None, 'sentence_length': None, 'vocabulary_complexity': None,
            'salutation': None, 'signoff': None, 'voice': None, 'jargon_level': None,
            'characteristic_phrases': [], 'anti_patterns': [],
            'source_doc_count': 0, 'generated_at': datetime.now().isoformat(),
        }
        drive_client.upload_or_update_json(folder_ids['learning'], 'tone-profile.json', empty_tone)

    summary['tone_generated'] = tone_generated

    # Step 6: Initialise learning files
    try:
        init_learning_files(folder_ids)
    except Exception as e:
        errors.append(f"Learning files: {e}")

    # Step 7: Create tracking sheet
    try:
        sheet_id = create_tracking_sheet(client_name)
        summary['tracking_sheet_id'] = sheet_id
    except Exception as e:
        log.error(f"Tracking sheet creation failed: {e}")
        errors.append(f"Tracking sheet: {e}")
        sheet_id = ''

    # Step 8: Write final client config (with real sheet ID)
    try:
        write_client_config(
            client_name, client_code, client_email,
            folder_ids, sheet_id,
            brand_generated=brand_generated,
            tone_generated=tone_generated,
        )
    except Exception as e:
        errors.append(f"Client config: {e}")

    # Step 9: Send welcome email
    email_sent = send_welcome_email(client_name, client_email)
    summary['welcome_email_sent'] = email_sent

    summary['errors'] = errors

    # Print final summary
    print(f"\n{'='*60}")
    print(f"ONBOARDING COMPLETE — {client_name} ({client_code})")
    print(f"{'='*60}")
    print(f"Drive folders:    Created")
    print(f"Shared with:      {client_email} {'(OK)' if shared else '(FAILED)'}")
    print(f"Samples uploaded: {sample_count}")
    print(f"Brand profile:    {'Generated' if brand_generated else 'Empty (gaps flagged)'}")
    print(f"Tone profile:     {'Generated' if tone_generated else 'Empty'}")
    print(f"Tracking sheet:   {sheet_id or 'FAILED'}")
    print(f"Welcome email:    {'Sent' if email_sent else 'Failed'}")
    if errors:
        print(f"\nErrors (non-fatal):")
        for err in errors:
            print(f"  - {err}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(description='Skill 8: Client Onboarder')
    parser.add_argument('client_name', help='Client name (e.g. "Gilmartins Property Maintenance")')
    parser.add_argument('client_email', help='Client contact email')
    parser.add_argument('--code', default=None, help='Client code (auto-generated if not provided)')
    parser.add_argument('--samples', default=None, help='Local folder with sample documents')
    args = parser.parse_args()

    onboard_client(
        client_name=args.client_name,
        client_email=args.client_email,
        client_code=args.code,
        samples_folder=args.samples,
    )


if __name__ == '__main__':
    main()
