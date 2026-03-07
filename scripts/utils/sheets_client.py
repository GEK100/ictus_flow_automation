"""Google Sheets API wrapper for Ictus Flow."""

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
from scripts.utils.retry import retry_with_backoff

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


@retry_with_backoff()
def read_sheet(sheet_id, range_name='Sheet1!A:Z'):
    """Read all values from a sheet range. Returns list of rows."""
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_name
    ).execute()
    return result.get('values', [])


@retry_with_backoff()
def append_row(sheet_id, row_data, range_name='Tracking!A:Z'):
    """Append a single row to the sheet."""
    service = _get_service()
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption='USER_ENTERED',
        body={'values': [row_data]},
    ).execute()


@retry_with_backoff()
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


@retry_with_backoff()
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
    'Client Review', 'Client Notes',
]


@retry_with_backoff()
def add_failed_row_formatting(sheet_id, sheet_name='Tracking'):
    """Add conditional formatting: rows where Status (col E) = 'FAILED' get red background.

    Uses the Sheets batchUpdate API to add a conditional format rule that
    highlights the entire row with a light-red background and bold text
    whenever the Status column contains 'FAILED'.
    """
    service = _get_service()

    # Get the sheet's internal numeric ID (different from spreadsheet ID)
    meta = service.spreadsheets().get(
        spreadsheetId=sheet_id, fields='sheets.properties'
    ).execute()
    sheet_gid = meta['sheets'][0]['properties']['sheetId']

    rule = {
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{
                    'sheetId': sheet_gid,
                    'startRowIndex': 1,       # skip header row
                    'startColumnIndex': 0,
                    'endColumnIndex': 12,      # columns A-L
                }],
                'booleanRule': {
                    'condition': {
                        'type': 'CUSTOM_FORMULA',
                        'values': [{'userEnteredValue': '=$E2="FAILED"'}],
                    },
                    'format': {
                        'backgroundColor': {
                            'red': 1.0,
                            'green': 0.8,
                            'blue': 0.8,
                        },
                        'textFormat': {'bold': True},
                    },
                },
            },
            'index': 0,
        }
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={'requests': [rule]},
    ).execute()


# Column index for Client Review (K = index 10)
COL_CLIENT_REVIEW = 10
COL_CLIENT_NOTES = 11

REVIEW_VALUES = ['Correct', 'Wrong', 'Needs Review', '']


@retry_with_backoff()
def add_review_dropdown(sheet_id, sheet_name='Tracking'):
    """Apply data validation dropdown to column K (Client Review).

    Restricts values to: Correct, Wrong, Needs Review, or blank.
    Applied from row 2 onwards (skipping header).
    """
    service = _get_service()

    meta = service.spreadsheets().get(
        spreadsheetId=sheet_id, fields='sheets.properties'
    ).execute()
    sheet_gid = meta['sheets'][0]['properties']['sheetId']

    request = {
        'setDataValidation': {
            'range': {
                'sheetId': sheet_gid,
                'startRowIndex': 1,
                'startColumnIndex': COL_CLIENT_REVIEW,
                'endColumnIndex': COL_CLIENT_REVIEW + 1,
            },
            'rule': {
                'condition': {
                    'type': 'ONE_OF_LIST',
                    'values': [{'userEnteredValue': v} for v in REVIEW_VALUES],
                },
                'showCustomUi': True,
                'strict': True,
            },
        }
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={'requests': [request]},
    ).execute()


@retry_with_backoff()
def add_review_conditional_formatting(sheet_id, sheet_name='Tracking'):
    """Add conditional formatting for Client Review column.

    - 'Wrong' rows get orange background
    - 'Needs Review' rows get yellow background
    """
    service = _get_service()

    meta = service.spreadsheets().get(
        spreadsheetId=sheet_id, fields='sheets.properties'
    ).execute()
    sheet_gid = meta['sheets'][0]['properties']['sheetId']

    range_def = {
        'sheetId': sheet_gid,
        'startRowIndex': 1,
        'startColumnIndex': 0,
        'endColumnIndex': 12,
    }

    wrong_rule = {
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [range_def],
                'booleanRule': {
                    'condition': {
                        'type': 'CUSTOM_FORMULA',
                        'values': [{'userEnteredValue': '=$K2="Wrong"'}],
                    },
                    'format': {
                        'backgroundColor': {
                            'red': 1.0,
                            'green': 0.6,
                            'blue': 0.0,
                        },
                    },
                },
            },
            'index': 0,
        }
    }

    needs_review_rule = {
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [range_def],
                'booleanRule': {
                    'condition': {
                        'type': 'CUSTOM_FORMULA',
                        'values': [{'userEnteredValue': '=$K2="Needs Review"'}],
                    },
                    'format': {
                        'backgroundColor': {
                            'red': 1.0,
                            'green': 1.0,
                            'blue': 0.0,
                        },
                    },
                },
            },
            'index': 1,
        }
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={'requests': [wrong_rule, needs_review_rule]},
    ).execute()


def get_flagged_rows(sheet_id, range_name='Tracking!A:L'):
    """Return all rows where Client Review (col K) is 'Wrong' or 'Needs Review'.

    Returns list of dicts with keys: row_number, row_data.
    row_number is 1-indexed (matching sheet row numbers).
    """
    rows = read_sheet(sheet_id, range_name)
    if not rows or len(rows) < 2:
        return []

    flagged = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) > COL_CLIENT_REVIEW:
            review_val = row[COL_CLIENT_REVIEW].strip()
            if review_val in ('Wrong', 'Needs Review'):
                flagged.append({'row_number': i, 'row_data': row})

    return flagged
