"""Google Sheets API wrapper for Ictus Flow."""

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

_service = None


def _get_service():
    global _service
    if _service is None:
        creds = service_account.Credentials.from_service_account_file(
            os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'), scopes=SCOPES
        )
        _service = build('sheets', 'v4', credentials=creds)
    return _service


def read_sheet(sheet_id, range_name='Sheet1!A:Z'):
    """Read all values from a sheet range. Returns list of rows."""
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_name
    ).execute()
    return result.get('values', [])


def append_row(sheet_id, row_data, range_name='Tracking!A:Z'):
    """Append a single row to the sheet."""
    service = _get_service()
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption='USER_ENTERED',
        body={'values': [row_data]},
    ).execute()


def update_cell(sheet_id, cell_range, value):
    """Update a single cell or range.

    cell_range: e.g. 'Tracking!G5' or 'Tracking!F5:G5'
    """
    service = _get_service()
    body = {'values': [value if isinstance(value, list) else [value]]}
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=cell_range,
        valueInputOption='USER_ENTERED',
        body=body,
    ).execute()


def find_row_by_value(sheet_id, column_index, search_value,
                      range_name='Tracking!A:Z'):
    """Find the first row where column matches search_value.

    Returns (row_number_1indexed, row_data) or (None, None).
    """
    rows = read_sheet(sheet_id, range_name)
    for i, row in enumerate(rows):
        if len(row) > column_index and row[column_index] == search_value:
            return i + 1, row
    return None, None


def update_row_field(sheet_id, row_number, column_index, value,
                     sheet_name='Tracking'):
    """Update a specific field by row number and column index."""
    col_letter = chr(ord('A') + column_index)
    cell_range = f'{sheet_name}!{col_letter}{row_number}'
    update_cell(sheet_id, cell_range, value)


def create_spreadsheet(title, sheet_name='Tracking', headers=None):
    """Create a new Google Sheet. Returns the spreadsheet ID."""
    service = _get_service()
    body = {
        'properties': {'title': title},
        'sheets': [{'properties': {'title': sheet_name}}],
    }
    result = service.spreadsheets().create(body=body, fields='spreadsheetId').execute()
    sheet_id = result['spreadsheetId']

    if headers:
        append_row(sheet_id, headers, range_name=f'{sheet_name}!A:Z')

    return sheet_id


TRACKING_HEADERS = [
    'File Name', 'Date Received', 'Classification', 'Confidence',
    'Status', 'Workflow', 'QA Score', 'QA Status', 'Notes', 'Completed Date',
]
