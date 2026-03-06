# scripts/notifier.py

import os, resend
from dotenv import load_dotenv

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")
resend.api_key = os.getenv('RESEND_API_KEY')

def notify_work_received(client_config, file_name,
                         classification):
    """Confirm receipt of work."""
    resend.Emails.send({
        'from': 'Ictus Flow <hello@ictusflow.com>',
        'to': client_config['contact_email'],
        'subject': f'Received: {file_name}',
        'html': f'''
            <p>Hi {client_config['contact_name']},</p>
            <p>We've received <strong>{file_name}
            </strong> and identified it as:
            <strong>{classification}</strong>.</p>
            <p>We'll process this and notify you when
            it's complete.</p>
            <p>Ictus Flow</p>
        '''
    })

def notify_work_complete(client_config, summary,
                         output_link):
    """Notify client that work is ready."""
    resend.Emails.send({
        'from': 'Ictus Flow <hello@ictusflow.com>',
        'to': client_config['contact_email'],
        'subject': f'Complete: {summary}',
        'html': f'''
            <p>Hi {client_config['contact_name']},</p>
            <p>Your work is complete:</p>
            <p><strong>{summary}</strong></p>
            <p>You can find the output in your
            Completed folder, or click here:
            <a href="{output_link}">View file</a></p>
            <p>Ictus Flow</p>
        '''
    })
