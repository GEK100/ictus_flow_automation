# utils/cost_logger.py
#
# Canonical cost logger for all Anthropic API calls.
# Writes to logs/api_costs.csv (project-root-relative).

import csv
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
COST_CSV = PROJECT_ROOT / 'logs' / 'api_costs.csv'

_HEADERS = [
    'timestamp', 'client_code', 'workflow', 'model',
    'input_tokens', 'output_tokens', 'estimated_cost',
]

# Per-million-token pricing for models in use
MODEL_PRICING = {
    'claude-haiku-4-5-20251001':
        {'input': 0.80, 'output': 4.00},
    'claude-sonnet-4-5-20250929':
        {'input': 3.00, 'output': 15.00},
    'claude-opus-4-6':
        {'input': 15.00, 'output': 75.00},
}

# Default pricing for unknown models (Sonnet-tier)
_DEFAULT_PRICING = {'input': 3.00, 'output': 15.00}


def _ensure_csv():
    """Create the CSV with headers if it doesn't exist."""
    os.makedirs(COST_CSV.parent, exist_ok=True)
    if not COST_CSV.exists():
        with open(COST_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(_HEADERS)


def estimate_cost(model, input_tokens, output_tokens):
    """Calculate estimated cost in USD for a single API call.

    Exposed so credit_monitor can reuse the same pricing logic.
    """
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return ((input_tokens * pricing['input']
             + output_tokens * pricing['output'])
            / 1_000_000)


def log_api_call(client_code, workflow, model,
                 input_tokens, output_tokens):
    """Log an API call with token usage and estimated cost.

    Appends a row to logs/api_costs.csv. Creates the file
    with headers if it doesn't exist yet.
    """
    cost = estimate_cost(model, input_tokens, output_tokens)

    _ensure_csv()
    with open(COST_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            client_code, workflow, model,
            input_tokens, output_tokens,
            f'{cost:.6f}',
        ])
