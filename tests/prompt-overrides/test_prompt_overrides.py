"""Tests for SCA-03: Client-Specific Prompt Overrides.

Tests the 5-layer prompt assembly with Layer 0 client overrides,
using temporary prompt files and mocked client configs.
Drive-dependent layers (3, 4) are mocked to avoid API calls.

Run: python -m pytest tests/utils/test_prompt_overrides.py -v
"""

import sys
import os
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.prompt_builder import (
    build_prompt,
    load_base_prompt,
    load_client_override_prompt,
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def prompts_dir(tmp_path, monkeypatch):
    """Set up a temporary prompts directory with default and override files.

    Mocks Drive-dependent functions (layers 3-4) so tests run without
    Google API credentials.
    """
    # Create prompts/ with a default base prompt
    prompts = tmp_path / 'prompts'
    prompts.mkdir()
    (prompts / 'invoice-processor.txt').write_text(
        'You are an invoice processor. Extract all fields.',
        encoding='utf-8',
    )
    (prompts / 'letter-drafter.txt').write_text(
        'You are a letter drafter. Write professional letters.',
        encoding='utf-8',
    )

    # Create prompts/client_overrides/ with an override
    overrides = prompts / 'client_overrides'
    overrides.mkdir()
    (overrides / 'invoice-processor-property.txt').write_text(
        'You are an invoice processor for property management. '
        'Focus on rent invoices, service charges, and ground rent.',
        encoding='utf-8',
    )

    # Create config/clients/ with test client configs
    config_dir = tmp_path / 'config' / 'clients'
    config_dir.mkdir(parents=True)

    # Client WITH override
    (config_dir / 'prop.json').write_text(json.dumps({
        'client_name': 'Property Co',
        'client_code': 'PROP',
        'folders': {'learning': 'fake-id'},
        'prompt_overrides': {
            'invoice-processor': 'invoice-processor-property.txt',
        },
    }), encoding='utf-8')

    # Client WITHOUT override (empty dict)
    (config_dir / 'gilm.json').write_text(json.dumps({
        'client_name': 'Gilmartins',
        'client_code': 'GILM',
        'folders': {'learning': 'fake-id'},
        'prompt_overrides': {},
    }), encoding='utf-8')

    # Client with override referencing a MISSING file
    (config_dir / 'badc.json').write_text(json.dumps({
        'client_name': 'Bad Config',
        'client_code': 'BADC',
        'folders': {'learning': 'fake-id'},
        'prompt_overrides': {
            'invoice-processor': 'does-not-exist.txt',
        },
    }), encoding='utf-8')

    # Create empty learning/ dirs so Layer 2 doesn't fail
    (tmp_path / 'learning' / 'industry' / 'construction').mkdir(parents=True)

    # Point PROJECT_ROOT at our temp dir
    monkeypatch.setattr(
        'scripts.utils.prompt_builder.PROJECT_ROOT',
        str(tmp_path),
    )

    # Mock Drive-dependent functions so we don't hit Google APIs
    monkeypatch.setattr(
        'scripts.utils.prompt_builder.load_client_corrections',
        lambda client_code: [],
    )
    monkeypatch.setattr(
        'scripts.utils.prompt_builder.load_brand_profile',
        lambda client_code: None,
    )
    monkeypatch.setattr(
        'scripts.utils.prompt_builder.load_tone_profile',
        lambda client_code: None,
    )

    return tmp_path


# ── Test 1: Default prompt used when no override ──────────────────

class TestDefaultPromptUsedWhenNoOverride:

    def test_default_prompt_used_when_no_override(self, prompts_dir):
        """Client with empty prompt_overrides gets the standard Layer 1 prompt."""
        prompt = build_prompt(
            prompt_filename='invoice-processor.txt',
            client_code='GILM',
            workflow='invoice-processor',
        )

        assert 'You are an invoice processor. Extract all fields.' in prompt
        assert 'property management' not in prompt


# ── Test 2: Override replaces default ─────────────────────────────

class TestOverrideReplacesDefault:

    def test_override_replaces_default(self, prompts_dir):
        """Client with prompt_overrides gets the custom base prompt."""
        prompt = build_prompt(
            prompt_filename='invoice-processor.txt',
            client_code='PROP',
            workflow='invoice-processor',
        )

        assert 'property management' in prompt
        assert 'rent invoices' in prompt
        # The default Layer 1 text should NOT be present
        assert 'Extract all fields' not in prompt


# ── Test 3: Corrections still apply on override ──────────────────

class TestCorrectionsStillApplyOnOverride:

    def test_corrections_still_apply_on_override(self, prompts_dir):
        """Layers 2-4 are still applied on top of a Layer 0 override."""
        # Add industry corrections so Layer 2 has content
        corrections_dir = prompts_dir / 'learning' / 'industry' / 'construction'
        corrections_file = corrections_dir / 'corrections.json'
        corrections_file.write_text(json.dumps({
            'corrections': [{
                'workflow': 'invoice-processor',
                'category': 'numerical_error',
                'field': 'vat_amount',
                'cause': 'VAT was miscalculated',
                'original_value': '200',
                'corrected_value': '250',
            }],
        }), encoding='utf-8')

        prompt = build_prompt(
            prompt_filename='invoice-processor.txt',
            client_code='PROP',
            workflow='invoice-processor',
        )

        # Layer 0 override is the base
        assert 'property management' in prompt
        # Layer 2 corrections are appended
        assert 'LEARNED CORRECTIONS' in prompt
        assert 'vat_amount' in prompt


# ── Test 4: Missing override file raises clear error ──────────────

class TestMissingOverrideFileRaises:

    def test_missing_override_file_raises(self, prompts_dir):
        """Config referencing a non-existent override file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            build_prompt(
                prompt_filename='invoice-processor.txt',
                client_code='BADC',
                workflow='invoice-processor',
            )

        assert 'does-not-exist.txt' in str(exc_info.value)
        assert 'BADC' in str(exc_info.value)


# ── Test 5: Empty overrides dict uses all defaults ────────────────

class TestEmptyOverridesDict:

    def test_empty_overrides_dict(self, prompts_dir):
        """Client with prompt_overrides: {} uses default for every workflow."""
        prompt = build_prompt(
            prompt_filename='letter-drafter.txt',
            client_code='GILM',
            workflow='letter-drafter',
        )

        assert 'You are a letter drafter' in prompt

    def test_override_only_for_configured_workflow(self, prompts_dir):
        """PROP has an override for invoice-processor but not letter-drafter."""
        prompt = build_prompt(
            prompt_filename='letter-drafter.txt',
            client_code='PROP',
            workflow='letter-drafter',
        )

        # Gets the default letter-drafter prompt, not an override
        assert 'You are a letter drafter' in prompt
        assert 'property management' not in prompt
