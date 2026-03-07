# scripts/drive_watcher.py

import os, sys, json, time, glob, base64
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from anthropic import Anthropic
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.cost_logger import log_api_call
from scripts.utils.client_guard import validate_client_operation
from scripts.utils import drive_client, sheets_client, resend_client, credit_monitor
from scripts.utils.value_tracker import log_value as log_file_value
from scripts.utils.storage_factory import get_storage_client

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")
anthropic = Anthropic()

SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(
    os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'), scopes=SCOPES
)
drive = build('drive', 'v3', credentials=creds)
sheets = build('sheets', 'v4', credentials=creds)

# Load classifier prompt
with open('prompts/classifier.txt') as f:
    CLASSIFIER_PROMPT = f.read()

# Load client configs
clients = []
for f in glob.glob('config/clients/*.json'):
    if '_template' not in f:
        with open(f) as cf:
            clients.append(json.load(cf))

def get_new_files(folder_id):
    """List files in folder not yet processed."""
    results = drive.files().list(
        q=f"'{folder_id}' in parents",
        fields='files(id, name, mimeType, createdTime)',
        orderBy='createdTime'
    ).execute()
    return results.get('files', [])

def read_file_content(file_id, mime_type):
    """Get first ~500 words of file content."""
    # For PDFs: download and extract text
    # For images: send to Haiku as image
    # For docs: export as text
    # Implementation depends on mime type
    content = drive.files().get_media(
        fileId=file_id).execute()
    return content[:2000]  # First ~500 words

def classify_file(filename, content, client_code='UNKNOWN'):
    """Send to Haiku for classification."""
    model = os.getenv('MODEL_CLASSIFIER')
    response = anthropic.messages.create(
        model=model,
        max_tokens=200,
        system=CLASSIFIER_PROMPT,
        messages=[{
            'role': 'user',
            'content': f'Filename: {filename}\n\n'
                       f'Content:\n{content}'
        }]
    )
    log_api_call(
        client_code=client_code,
        workflow='classification',
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens
    )
    return json.loads(response.content[0].text)

def log_to_tracking_sheet(sheet_id, row_data):
    """Append a row to the client tracking sheet."""
    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range='Tracking!A:H',
        valueInputOption='USER_ENTERED',
        body={'values': [row_data]}
    ).execute()

def move_file(file_id, from_folder, to_folder):
    """Move file from INBOX to PROCESSING."""
    drive.files().update(
        fileId=file_id,
        addParents=to_folder,
        removeParents=from_folder
    ).execute()


def handle_failure(client, file_info, error_msg, current_folder_id):
    """OPS-01: Move file to _FAILED, update tracking sheet, send alert email.

    Args:
        client: Full client config dict.
        file_info: Drive file dict with 'id' and 'name'.
        error_msg: Human-readable error description.
        current_folder_id: Folder the file is currently in (inbox or processing).
    """
    client_code = client.get('client_code', 'UNKNOWN')
    client_name = client.get('client_name', 'Unknown Client')
    file_name = file_info['name']
    file_id = file_info['id']
    sheet_id = client.get('tracking_sheet_id', '')

    # 1. Move file to _FAILED folder (if configured)
    failed_folder = client.get('folders', {}).get('failed')
    if failed_folder:
        try:
            drive_client.move_file(
                file_id, current_folder_id, failed_folder,
                client_code=client_code,
            )
            print(f"  Moved {file_name} to _FAILED folder")
        except Exception as move_err:
            print(f"  WARNING: Could not move {file_name} to _FAILED: {move_err}")
    else:
        print(f"  WARNING: No _FAILED folder configured for {client_code} — "
              f"file stays in current folder")

    # 2. Update tracking sheet
    if sheet_id:
        try:
            row_num, _ = sheets_client.find_row_by_value(sheet_id, 0, file_name)
            if row_num:
                # Row exists — update Status and Notes
                sheets_client.update_row_field(sheet_id, row_num, 4, 'FAILED')
                sheets_client.update_row_field(sheet_id, row_num, 8, error_msg)
            else:
                # File failed before tracking entry was created — add new row
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                sheets_client.append_row(sheet_id, [
                    file_name,   # File Name
                    timestamp,   # Date Received
                    '',          # Classification
                    '',          # Confidence
                    'FAILED',    # Status
                    '',          # Workflow
                    '',          # QA Score
                    '',          # QA Status
                    error_msg,   # Notes
                    '',          # Completed Date
                ])
            print(f"  Tracking sheet updated with FAILED status")
        except Exception as sheet_err:
            print(f"  WARNING: Could not update tracking sheet: {sheet_err}")

    # 3. Send alert email to admin
    try:
        subject = f"[Ictus Flow] FAILED: {file_name} ({client_code})"
        body_html = f"""
        <h2>File Processing Failed</h2>
        <table>
            <tr><td><strong>Client:</strong></td><td>{client_name} ({client_code})</td></tr>
            <tr><td><strong>File:</strong></td><td>{file_name}</td></tr>
            <tr><td><strong>Error:</strong></td><td>{error_msg}</td></tr>
            <tr><td><strong>Time:</strong></td><td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
        </table>
        <p>The file has been moved to the <strong>_FAILED</strong> folder for manual review.</p>
        """
        resend_client.send_admin_notification(subject, body_html)
        print(f"  Alert email sent to admin")
    except Exception as email_err:
        print(f"  WARNING: Could not send alert email: {email_err}")


def run():
    """Main polling loop — watches inbox folders and processes new files."""
    while True:
        # OPS-02: Check credit before processing any files this cycle
        if not credit_monitor.check_and_warn():
            print("PAUSED — insufficient API credit. Skipping this cycle.")
            time.sleep(int(os.getenv('DRIVE_POLL_INTERVAL', 900)))
            continue

        for client in clients:
            client_code = client.get('client_code', 'UNKNOWN')
            inbox_id = client['folders']['inbox']
            processing_id = client['folders']['processing']

            # SCA-05: Obtain platform-aware storage client for this client
            storage = get_storage_client(client)

            # SEC-02: Validate client boundary before processing
            validate_client_operation(client_code, inbox_id)
            validate_client_operation(client_code, processing_id)

            new_files = get_new_files(inbox_id)

            # OPS-02: Check if we can afford this batch
            if new_files and not credit_monitor.can_process_batch(len(new_files)):
                print(f"  Skipping {client_code}: insufficient credit "
                      f"for {len(new_files)} files")
                continue

            for file in new_files:
                try:
                    print(f"New file: {file['name']}")
                    content = read_file_content(
                        file['id'], file['mimeType'])
                    result = classify_file(
                        file['name'], content,
                        client.get('client_code', 'UNKNOWN'))

                    # Log to tracking sheet
                    log_to_tracking_sheet(
                        client['tracking_sheet_id'],
                        [file['name'],
                         result['classification'],
                         result['confidence'],
                         result['summary'],
                         result['suggested_workflow'],
                         'NEW',  # Status
                         file['createdTime'],
                         '']  # Notes
                    )

                    # Move to PROCESSING
                    move_file(file['id'],
                              inbox_id, processing_id)

                    # COM-01: Log value delivered
                    try:
                        from utils.cost_logger import estimate_cost
                        model = os.getenv('MODEL_CLASSIFIER', '')
                        api_cost = estimate_cost(
                            model,
                            response.usage.input_tokens if 'response' in dir() else 0,
                            response.usage.output_tokens if 'response' in dir() else 0,
                        ) if model else 0.0
                        log_file_value(
                            client_code, file['name'],
                            result['classification'], api_cost,
                        )
                    except Exception as val_err:
                        print(f"  WARNING: Could not log value: {val_err}")

                    print(f"  -> {result['classification']}"
                          f" ({result['confidence']})")

                except Exception as e:
                    print(f"  ERROR processing {file['name']}: {e}")
                    handle_failure(client, file, str(e), inbox_id)

        time.sleep(int(os.getenv(
            'DRIVE_POLL_INTERVAL', 900)))


if __name__ == '__main__':
    run()
