"""Generate test fixture files for QA Oversight tests.

Run once to create test input/output pairs:
    python tests/qa-oversight/create_fixtures.py
"""

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent


def create_test_1_perfect_invoice():
    """Test 1: Perfect invoice extraction — all dimensions should PASS."""
    original = {
        'raw_text': (
            'INVOICE\n'
            'Invoice No: INV-2025-0042\n'
            'Date: 15/01/2025\n'
            'From: Acme Building Supplies Ltd\n'
            'To: Gilmartins Property Maintenance\n\n'
            'Description: 500 red bricks @ £0.80 each\n'
            'Net Amount: £400.00\n'
            'VAT (20%): £80.00\n'
            'Total: £480.00\n\n'
            'Payment Terms: 30 days\n'
            'Due Date: 14/02/2025\n'
        ),
    }

    output = {
        'invoice_number': 'INV-2025-0042',
        'date': '15/01/2025',
        'supplier': 'Acme Building Supplies Ltd',
        'client': 'Gilmartins Property Maintenance',
        'description': '500 red bricks @ £0.80 each',
        'net_amount': 400.00,
        'vat_rate': 0.20,
        'vat_amount': 80.00,
        'gross_amount': 480.00,
        'payment_terms': '30 days',
        'due_date': '14/02/2025',
    }

    _write_fixture('test_1_original.json', original)
    _write_fixture('test_1_output.json', output)
    _write_fixture('test_1_expected.json', {
        'expected_overall': 'PASS',
        'all_dimensions_pass': True,
    })


def create_test_2_wrong_vat():
    """Test 2: Wrong VAT calculation — internal consistency should FAIL."""
    original = {
        'raw_text': (
            'INVOICE INV-2025-0043\n'
            'Net: £1,000.00\nVAT (20%): £200.00\nTotal: £1,200.00\n'
        ),
    }

    output = {
        'invoice_number': 'INV-2025-0043',
        'net_amount': 1000.00,
        'vat_rate': 0.20,
        'vat_amount': 150.00,  # WRONG: should be 200
        'gross_amount': 1200.00,  # Doesn't match net + vat
    }

    _write_fixture('test_2_original.json', original)
    _write_fixture('test_2_output.json', output)
    _write_fixture('test_2_expected.json', {
        'expected_overall': 'FAIL',
        'expected_fail_dimensions': ['internal_consistency'],
    })


def create_test_3_missing_supplier():
    """Test 3: Missing supplier name — completeness should FAIL."""
    original = {
        'raw_text': (
            'INVOICE INV-2025-0044\n'
            'From: Quick Fix Plumbing Ltd\n'
            'Net: £500.00\nVAT: £100.00\nTotal: £600.00\n'
        ),
    }

    output = {
        'invoice_number': 'INV-2025-0044',
        # supplier MISSING
        'net_amount': 500.00,
        'vat_amount': 100.00,
        'gross_amount': 600.00,
    }

    _write_fixture('test_3_original.json', original)
    _write_fixture('test_3_output.json', output)
    _write_fixture('test_3_expected.json', {
        'expected_overall': 'FAIL',
        'expected_fail_dimensions': ['completeness'],
    })


def create_test_4_wrong_tone():
    """Test 4: Formal letter for informal client — tone should FLAG or FAIL."""
    original = {
        'raw_text': 'Hey mate, just dropping a note about the job on Monday. Cheers!',
    }

    output = {
        'letter_text': (
            'Dear Sir/Madam,\n\n'
            'I write to inform you regarding the forthcoming engagement '
            'scheduled for Monday. Please do not hesitate to contact me '
            'should you require further clarification.\n\n'
            'Yours faithfully,\nGareth Kerr'
        ),
    }

    _write_fixture('test_4_original.json', original)
    _write_fixture('test_4_output.json', output)
    _write_fixture('test_4_expected.json', {
        'expected_overall_in': ['FLAG', 'FAIL'],
        'expected_problem_dimensions': ['tone_match'],
    })


def create_test_5_wrong_date_format():
    """Test 5: MM/DD when profile says DD/MM — format should FLAG."""
    original = {
        'raw_text': 'Invoice dated 15/01/2025 for £200.00',
    }

    output = {
        'invoice_number': 'INV-001',
        'date': '01/15/2025',  # MM/DD format — WRONG
        'amount': 200.00,
    }

    _write_fixture('test_5_original.json', original)
    _write_fixture('test_5_output.json', output)
    _write_fixture('test_5_expected.json', {
        'expected_problem_dimensions': ['format_compliance'],
    })


def create_test_6_known_correction():
    """Test 6: Known correction pattern for supplier name — accuracy should FAIL."""
    original = {
        'raw_text': 'Invoice from Acme Building Supplies Ltd for £300.00',
    }

    output = {
        'supplier': 'ACME Building Supplies',  # Missing 'Ltd' — known correction
        'amount': 300.00,
    }

    corrections = [
        {
            'id': 'corr-001',
            'workflow': 'invoice-processor',
            'category': 'factual_error',
            'field': 'supplier',
            'original_value': 'ACME Building Supplies',
            'corrected_value': 'Acme Building Supplies Ltd',
            'cause': 'Dropped Ltd suffix from supplier name',
        },
    ]

    _write_fixture('test_6_original.json', original)
    _write_fixture('test_6_output.json', output)
    _write_fixture('test_6_corrections.json', corrections)
    _write_fixture('test_6_expected.json', {
        'expected_overall': 'FAIL',
        'expected_problem_dimensions': ['factual_accuracy'],
        'note': 'Known correction pattern repeated',
    })


def _write_fixture(filename, data):
    path = FIXTURE_DIR / filename
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Created: {path.name}")


if __name__ == '__main__':
    create_test_1_perfect_invoice()
    create_test_2_wrong_vat()
    create_test_3_missing_supplier()
    create_test_4_wrong_tone()
    create_test_5_wrong_date_format()
    create_test_6_known_correction()
    print("\nAll QA test fixtures created.")
