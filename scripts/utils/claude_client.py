"""Anthropic Claude API wrapper for Ictus Flow.

Provides model selection by tier and automatic cost tracking.

OPS-02: Every API call made through send_message() / send_message_json()
is automatically logged to logs/api_costs.csv via cost_logger.log_api_call().
The credit_monitor module reads this CSV to enforce budget limits.
Token counts come from the Anthropic response object (usage.input_tokens,
usage.output_tokens) — these are actual values, not estimates.
"""

import os
import sys
import json
import base64
from anthropic import Anthropic
from dotenv import load_dotenv
from scripts.utils.retry import retry_with_backoff

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

# Add project root for cost logger import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from utils.cost_logger import log_api_call

_client = None

MODEL_TIERS = {
    'MODEL_CLASSIFIER': os.getenv('MODEL_CLASSIFIER', 'claude-haiku-4-5-20251001'),
    'MODEL_STANDARD': os.getenv('MODEL_STANDARD', 'claude-sonnet-4-5-20250929'),
    'MODEL_COMPLEX': os.getenv('MODEL_COMPLEX', 'claude-opus-4-6'),
}


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def get_model(tier):
    """Resolve a model tier name to an actual model ID.

    Accepts 'MODEL_CLASSIFIER', 'MODEL_STANDARD', 'MODEL_COMPLEX',
    or a direct model ID string.
    """
    return MODEL_TIERS.get(tier, tier)


@retry_with_backoff()
def send_message(
    prompt,
    system_prompt=None,
    model_tier='MODEL_STANDARD',
    max_tokens=4096,
    client_code='SYSTEM',
    workflow='unknown',
    images=None,
):
    """Send a message to Claude and return the text response.

    Args:
        prompt: User message text.
        system_prompt: System prompt string.
        model_tier: 'MODEL_CLASSIFIER', 'MODEL_STANDARD', 'MODEL_COMPLEX',
                    or a direct model ID.
        max_tokens: Max output tokens.
        client_code: For cost tracking.
        workflow: For cost tracking.
        images: List of dicts with 'data' (base64 str) and 'media_type'.

    Returns:
        Response text string.
    """
    client = _get_client()
    model = get_model(model_tier)

    content = []
    if images:
        for img in images:
            content.append({
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': img['media_type'],
                    'data': img['data'],
                },
            })
    content.append({'type': 'text', 'text': prompt})

    kwargs = {
        'model': model,
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': content}],
    }
    if system_prompt:
        kwargs['system'] = system_prompt

    response = client.messages.create(**kwargs)

    log_api_call(
        client_code=client_code,
        workflow=workflow,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    return response.content[0].text


def send_message_json(
    prompt,
    system_prompt=None,
    model_tier='MODEL_STANDARD',
    max_tokens=4096,
    client_code='SYSTEM',
    workflow='unknown',
    images=None,
):
    """Send a message and parse the response as JSON.

    Returns parsed dict/list. Raises ValueError on parse failure.
    """
    text = send_message(
        prompt=prompt,
        system_prompt=system_prompt,
        model_tier=model_tier,
        max_tokens=max_tokens,
        client_code=client_code,
        workflow=workflow,
        images=images,
    )

    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        cleaned = '\n'.join(lines)

    return json.loads(cleaned)


def encode_image_file(filepath):
    """Read an image file and return a dict for the images parameter."""
    ext = os.path.splitext(filepath)[1].lower()
    media_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp',
    }
    media_type = media_types.get(ext, 'image/jpeg')

    with open(filepath, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')

    return {'data': data, 'media_type': media_type}


def encode_pdf_page_as_image(pdf_path, page_number=0):
    """Convert a PDF page to an image and return encoded dict.

    Requires pdf2image (and poppler on the system PATH).
    """
    from pdf2image import convert_from_path

    images = convert_from_path(
        pdf_path, first_page=page_number + 1,
        last_page=page_number + 1, dpi=200,
    )
    if not images:
        raise ValueError(f"Could not convert page {page_number} of {pdf_path}")

    import io
    buffer = io.BytesIO()
    images[0].save(buffer, format='PNG')
    data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return {'data': data, 'media_type': 'image/png'}
