# utils/cost_logger.py

import csv
from datetime import datetime

def log_api_call(client_code, workflow, model,
                 input_tokens, output_tokens):
    # Calculate cost
    costs = {
        'claude-haiku-4-5-20251001':
            {'input': 0.80, 'output': 4.00},  # per million
        'claude-sonnet-4-5-20250929':
            {'input': 3.00, 'output': 15.00},
        'claude-opus-4-6':
            {'input': 15.00, 'output': 75.00},
    }
    model_cost = costs.get(model,
        {'input': 3.00, 'output': 15.00})
    cost = ((input_tokens * model_cost['input']
            + output_tokens * model_cost['output'])
            / 1_000_000)

    # Append to log
    with open('api_cost_log.csv', 'a') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            client_code, workflow, model,
            input_tokens, output_tokens,
            f'{cost:.6f}'
        ])
