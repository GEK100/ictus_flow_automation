"""Generate test fixture files for Correction Logger tests.

Run once:
    python tests/correction-logger/create_fixtures.py
"""

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent


def create_test_1_vat_change():
    """Test 1: VAT changed in output JSON — should log numerical_error."""
    original = {
        'invoice_number': 'INV-001',
        'net_amount': 1000.00,
        'vat_rate': 0.20,
        'vat_amount': 200.00,
        'gross_amount': 1200.00,
    }
    final = {
        'invoice_number': 'INV-001',
        'net_amount': 1000.00,
        'vat_rate': 0.20,
        'vat_amount': 250.00,   # Changed
        'gross_amount': 1250.00,  # Changed
    }

    _write('test_1_original.json', original)
    _write('test_1_final.json', final)
    _write('test_1_expected.json', {
        'changes_expected': 2,
        'fields': ['vat_amount', 'gross_amount'],
    })


def create_test_2_no_changes():
    """Test 2: No edits, move to COMPLETED — no correction should be logged."""
    data = {
        'invoice_number': 'INV-002',
        'supplier': 'Acme Ltd',
        'amount': 500.00,
    }

    _write('test_2_original.json', data)
    _write('test_2_final.json', data)
    _write('test_2_expected.json', {
        'changes_expected': 0,
    })


def create_test_3_manual_note():
    """Test 3: CORRECTION: note in tracking sheet — should categorise."""
    _write('test_3_sheet_rows.json', [
        ['File Name', 'Date Received', 'Classification', 'Confidence',
         'Status', 'Workflow', 'QA Score', 'QA Status', 'Notes', 'Completed Date'],
        ['invoice_001.pdf', '15/01/2025', 'INVOICE', '0.95',
         'COMPLETED', 'invoice-processor', '85', 'PASS',
         'CORRECTION: Supplier name should be "Acme Building Supplies Ltd" not "Acme Building"', ''],
        ['letter_001.docx', '16/01/2025', 'LETTER', '0.90',
         'COMPLETED', 'letter-drafter', '90', 'PASS', 'Looks good', ''],
    ])
    _write('test_3_expected.json', {
        'corrections_found': 1,
        'note': 'Only one row has CORRECTION: prefix',
    })


def create_test_4_multiple_fields():
    """Test 4: Three field changes at once — one entry per field."""
    original = {
        'invoice_number': 'INV-003',
        'supplier': 'Quick Fix',
        'date': '15/01/2025',
        'amount': 300.00,
    }
    final = {
        'invoice_number': 'INV-003',
        'supplier': 'Quick Fix Plumbing Ltd',  # Changed
        'date': '01/15/2025',                   # Changed format
        'amount': 350.00,                        # Changed
    }

    _write('test_4_original.json', original)
    _write('test_4_final.json', final)
    _write('test_4_expected.json', {
        'changes_expected': 3,
        'fields': ['supplier', 'date', 'amount'],
    })


def _write(filename, data):
    path = FIXTURE_DIR / filename
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Created: {filename}")


if __name__ == '__main__':
    create_test_1_vat_change()
    create_test_2_no_changes()
    create_test_3_manual_note()
    create_test_4_multiple_fields()
    print("\nAll Correction Logger fixtures created.")
