# scripts/drive_watcher.py

import os, sys, json, time, glob, base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from anthropic import Anthropic
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.cost_logger import log_api_call
from scripts.utils.client_guard import validate_client_operation

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

# Main loop
while True:
    for client in clients:
        client_code = client.get('client_code', 'UNKNOWN')
        inbox_id = client['folders']['inbox']
        processing_id = client['folders']['processing']

        # SEC-02: Validate client boundary before processing
        validate_client_operation(client_code, inbox_id)
        validate_client_operation(client_code, processing_id)

        new_files = get_new_files(inbox_id)

        for file in new_files:
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

            print(f"  -> {result['classification']}"
                  f" ({result['confidence']})")

    time.sleep(int(os.getenv(
        'DRIVE_POLL_INTERVAL', 900)))
