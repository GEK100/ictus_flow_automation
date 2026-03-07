"""5-layer prompt assembly for Ictus Flow.

Layers:
  0. (Optional) Client-specific base prompt override from
     prompts/client_overrides/[filename]. Configured via prompt_overrides
     in the client config. Replaces Layer 1 when present.
  1. Default base prompt from prompts/[workflow].txt
     (skipped if Layer 0 exists)
  2. Industry corrections from learning/industry/[vertical]/corrections.json
  3. Client corrections from client's 07-LEARNING/corrections.json on Drive
  4. Brand + tone from client's brand-profile.json and tone-profile.json
     (output workflows only)
"""

import os
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Workflows that produce client-facing output (need brand/tone layer)
OUTPUT_WORKFLOWS = {
    'letter-drafter', 'credit-control', 'quote-generator',
    'blog-writer', 'progress-report', 'payment-cert',
}


def load_base_prompt(prompt_filename):
    """Layer 1: Load base prompt from prompts/ directory."""
    path = os.path.join(PROJECT_ROOT, 'prompts', prompt_filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Base prompt not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def load_client_override_prompt(client_code, workflow_name):
    """Layer 0: Load client-specific base prompt override.

    Checks the client config for prompt_overrides[workflow_name].
    If found, loads the override file from prompts/client_overrides/.

    Args:
        client_code: Client code (e.g. 'GILM').
        workflow_name: Workflow name (e.g. 'invoice-processor').

    Returns:
        Override prompt string, or None if no override configured.

    Raises:
        FileNotFoundError: If the override file is referenced but missing.
    """
    config = load_client_config(client_code)
    if not config:
        return None

    overrides = config.get('prompt_overrides', {})
    if not overrides or workflow_name not in overrides:
        return None

    override_filename = overrides[workflow_name]
    path = os.path.join(PROJECT_ROOT, 'prompts', 'client_overrides', override_filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Client prompt override not found: {path} "
            f"(referenced by {client_code} for workflow '{workflow_name}')"
        )
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def load_industry_corrections(industry='construction'):
    """Layer 2: Load industry-level corrections from local learning/."""
    path = os.path.join(
        PROJECT_ROOT, 'learning', 'industry', industry, 'corrections.json'
    )
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('corrections', [])


def load_client_config(client_code):
    """Load a client config from config/clients/."""
    for variant in [client_code.lower(), client_code]:
        path = os.path.join(PROJECT_ROOT, 'config', 'clients', f'{variant}.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None


def load_client_corrections(client_code):
    """Layer 3: Load client-specific corrections from Drive."""
    from scripts.utils.drive_client import download_json
    config = load_client_config(client_code)
    if not config:
        return []
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return []
    data = download_json(learning_folder, 'corrections.json')
    return data.get('corrections', []) if data else []


def load_brand_profile(client_code):
    """Layer 4a: Load brand profile from Drive."""
    from scripts.utils.drive_client import download_json
    config = load_client_config(client_code)
    if not config:
        return None
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return None
    return download_json(learning_folder, 'brand-profile.json')


def load_tone_profile(client_code):
    """Layer 4b: Load tone profile from Drive."""
    from scripts.utils.drive_client import download_json
    config = load_client_config(client_code)
    if not config:
        return None
    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        return None
    return download_json(learning_folder, 'tone-profile.json')


def _format_corrections(corrections, workflow=None):
    """Format corrections into a prompt section."""
    if workflow:
        corrections = [c for c in corrections if c.get('workflow') == workflow]
    if not corrections:
        return ''

    lines = ['\n# LEARNED CORRECTIONS',
             'Apply these corrections based on past errors:\n']
    for c in corrections:
        lines.append(
            f"- {c.get('category', 'unknown')}: "
            f"Field '{c.get('field', '?')}' — {c.get('cause', 'no cause recorded')}. "
            f"Corrected: {c.get('original_value', '?')} -> {c.get('corrected_value', '?')}"
        )
    return '\n'.join(lines)


def _format_brand(brand_profile):
    """Format brand profile into a prompt section."""
    if not brand_profile:
        return ''
    lines = ['\n# CLIENT BRAND PROFILE',
             'Match these brand standards in your output:\n']
    colours = brand_profile.get('colours', {})
    if colours:
        lines.append(f"- Primary colour: {colours.get('primary', 'unknown')}")
        lines.append(f"- Secondary colour: {colours.get('secondary', 'unknown')}")
    fonts = brand_profile.get('fonts', {})
    if fonts:
        lines.append(f"- Primary font: {fonts.get('primary', 'unknown')}")
    layout = brand_profile.get('layout', {})
    if layout:
        lines.append(f"- Date format: {layout.get('date_format', 'DD/MM/YYYY')}")
        if layout.get('reference_pattern'):
            lines.append(f"- Reference pattern: {layout['reference_pattern']}")
    return '\n'.join(lines)


def _format_tone(tone_profile):
    """Format tone profile into a prompt section."""
    if not tone_profile:
        return ''
    lines = ['\n# CLIENT TONE PROFILE',
             'Match this communication style:\n']
    lines.append(f"- Formality: {tone_profile.get('formality', 3)}/5")
    lines.append(f"- Sentence length: {tone_profile.get('sentence_length', 'medium')}")
    lines.append(f"- Vocabulary: {tone_profile.get('vocabulary_complexity', 'plain')}")
    lines.append(f"- Salutation: {tone_profile.get('salutation', 'Hi')}")
    lines.append(f"- Sign-off: {tone_profile.get('signoff', 'Kind regards')}")
    lines.append(f"- Voice: {tone_profile.get('voice', 'active')}")
    phrases = tone_profile.get('characteristic_phrases', [])
    if phrases:
        lines.append(f"- Characteristic phrases: {', '.join(phrases)}")
    anti = tone_profile.get('anti_patterns', [])
    if anti:
        lines.append(f"- NEVER use: {', '.join(anti)}")
    return '\n'.join(lines)


def build_prompt(
    prompt_filename,
    client_code=None,
    workflow=None,
    industry='construction',
    include_brand_tone=None,
):
    """Assemble a full 5-layer prompt.

    Args:
        prompt_filename: Base prompt file (e.g. 'invoice-processor.txt').
        client_code: Client code for layers 0, 3-4 (e.g. 'GILM'). None = layers 1-2 only.
        workflow: Workflow name for filtering corrections and Layer 0 lookup.
        industry: Industry vertical for layer 2 corrections.
        include_brand_tone: Include brand/tone (layer 4). None = auto-detect.

    Returns:
        Assembled prompt string.
    """
    # Layer 0: Client-specific base prompt override (replaces Layer 1 if present)
    override = None
    if client_code and workflow:
        override = load_client_override_prompt(client_code, workflow)

    # Layer 1: Default base (skipped if Layer 0 exists)
    if override is not None:
        prompt = override
    else:
        prompt = load_base_prompt(prompt_filename)

    # Layer 2: Industry corrections
    industry_corrections = load_industry_corrections(industry)
    prompt += _format_corrections(industry_corrections, workflow)

    if client_code:
        # Layer 3: Client corrections
        client_corrections = load_client_corrections(client_code)
        if client_corrections:
            prompt += '\n\n# CLIENT-SPECIFIC CORRECTIONS'
            prompt += _format_corrections(client_corrections, workflow)

        # Layer 4: Brand + tone (output workflows only)
        if include_brand_tone is None:
            workflow_name = prompt_filename.replace('.txt', '')
            include_brand_tone = workflow_name in OUTPUT_WORKFLOWS

        if include_brand_tone:
            prompt += _format_brand(load_brand_profile(client_code))
            prompt += _format_tone(load_tone_profile(client_code))

    return prompt
