# scripts/create_client.py
# Run: python scripts/create_client.py "Client Name" "client@email.com"

import sys, json, os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(
    os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'), scopes=SCOPES
)
drive = build('drive', 'v3', credentials=creds)

def create_folder(name, parent_id=None):
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        metadata['parents'] = [parent_id]
    folder = drive.files().create(
        body=metadata, fields='id'
    ).execute()
    return folder.get('id')

def share_folder(folder_id, email, role='writer'):
    drive.permissions().create(
        fileId=folder_id,
        body={'type': 'user', 'role': role, 'emailAddress': email},
        sendNotificationEmail=True
    ).execute()

client_name = sys.argv[1]
client_email = sys.argv[2]
code = client_name.upper()[:4].replace(' ', '')

# Create folder structure
root_id = create_folder(f'{client_name} - Ictus Flow')
folders = {}
for name in ['01-DROP FILES HERE', '02-PROCESSING',
             '03-COMPLETED', '04-ARCHIVE',
             '05-BRAND-ASSETS', '06-TEMPLATES']:
    folders[name] = create_folder(name, root_id)

# Share with client and service account
share_folder(root_id, client_email)

# Save config
config = {
    'client_name': client_name,
    'client_code': code,
    'contact_email': client_email,
    'folders': {
        'root': root_id,
        'inbox': folders['01-DROP FILES HERE'],
        'processing': folders['02-PROCESSING'],
        'completed': folders['03-COMPLETED'],
        'archive': folders['04-ARCHIVE'],
        'brand_assets': folders['05-BRAND-ASSETS'],
        'templates': folders['06-TEMPLATES']
    }
}
filepath = f'config/clients/{code.lower()}.json'
with open(filepath, 'w') as f:
    json.dump(config, f, indent=2)
print(f'Client created: {filepath}')
print(f'Root folder ID: {root_id}')
