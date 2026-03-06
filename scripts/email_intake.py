# scripts/email_intake.py
# Run on a schedule (cron) or as a persistent process

import os, base64, json, glob
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/drive'
]

# Load all client configs
clients = {}
for f in glob.glob('config/clients/*.json'):
    if '_template' not in f:
        with open(f) as cf:
            c = json.load(cf)
            if 'intake_email' in c:
                clients[c['intake_email']] = c

# For each unread email:
# 1. Check the To: address against client configs
# 2. Download attachments
# 3. Upload to correct client INBOX folder
# 4. Mark email as processed (add label)
# 5. Log to tracking sheet

# NOTE: For Gmail API with service account, you need
# domain-wide delegation enabled in Workspace Admin.
# Alternative: use OAuth2 with your personal account
# and refresh tokens. See Google's Gmail API quickstart.
