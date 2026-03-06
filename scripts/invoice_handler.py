# scripts/invoice_handler.py

import os, sys, json, base64
from anthropic import Anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.cost_logger import log_api_call
from scripts.utils.client_guard import validate_client_operation

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")
anthropic = Anthropic()

with open('prompts/invoice-processor.txt') as f:
    INVOICE_PROMPT = f.read()

def process_invoice(file_path, client_config):
    """Process a single invoice file."""

    # SEC-02: Validate client boundary before processing
    client_code = client_config.get('client_code', 'UNKNOWN')
    for folder_key in ('inbox', 'processing', 'completed'):
        folder_id = client_config.get('folders', {}).get(folder_key)
        if folder_id:
            validate_client_operation(client_code, folder_id)

    # Read file (handle PDF, image, etc)
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
        b64_data = base64.b64encode(
            file_bytes).decode('utf-8')

    # Determine media type
    ext = file_path.split('.')[-1].lower()
    media_types = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
    }
    media_type = media_types.get(ext, 'application/pdf')

    # Send to Sonnet
    model = os.getenv('MODEL_STANDARD')
    response = anthropic.messages.create(
        model=model,
        max_tokens=2000,
        system=INVOICE_PROMPT,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'document' if ext == 'pdf'
                          else 'image',
                 'source': {'type': 'base64',
                            'media_type': media_type,
                            'data': b64_data}},
                {'type': 'text',
                 'text': 'Extract all invoice data.'}
            ]
        }]
    )
    log_api_call(
        client_code=client_config.get('client_code', 'UNKNOWN'),
        workflow='invoice_processing',
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens
    )

    data = json.loads(response.content[0].text)

    # Duplicate check
    existing = get_existing_invoices(
        client_config['tracking_sheet_id'])
    for inv in existing:
        if (inv['supplier'] == data['supplier_name']
            and inv['number'] == data['invoice_number']):
            data['flags'].append('DUPLICATE DETECTED')

    # Append to invoice tracker sheet
    append_to_tracker(
        client_config['tracking_sheet_id'], data)

    # Rename and file the original document
    new_name = (
        f"{data['invoice_date']}_"
        f"{data['supplier_name']}_"
        f"{data['invoice_number']}_"
        f"{data['total_gross']}.{ext}"
    )
    rename_and_file(file_path, new_name,
                    client_config)

    return data
