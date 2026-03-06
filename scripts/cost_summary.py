# scripts/cost_summary.py
# Run: python scripts/cost_summary.py [YYYY-MM]
#
# Expected monthly costs per client (estimate)
#
# Invoice processing:  50 invoices x ~$0.02    = $1.00
# Classification:      100 files x ~$0.001     = $0.10
# Correspondence:      10 letters x ~$0.02     = $0.20
# Credit control:      1 run x ~$0.05          = $0.05
# CIS return:          1 run x ~$0.03          = $0.03
# Contract review:     1 contract x ~$0.50     = $0.50
# Tender response:     1 tender x ~$5.00       = $5.00
#
# TOTAL: approximately $2-8/month for standard client
# (excluding tender responses)
#
# At £295/month tier: 98%+ gross margin on API costs

import csv, sys, os
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Use the same CSV location as cost_logger.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
COST_CSV = PROJECT_ROOT / 'logs' / 'api_costs.csv'

# Default to current month if not specified
if len(sys.argv) > 1:
    target_month = sys.argv[1]  # e.g. "2026-03"
else:
    target_month = datetime.now().strftime('%Y-%m')

# Read CSV log
# Columns: timestamp, client_code, workflow, model,
#           input_tokens, output_tokens, cost
data = defaultdict(lambda: {
    'workflows': defaultdict(lambda: {
        'calls': 0, 'input_tokens': 0,
        'output_tokens': 0, 'cost': 0.0
    }),
    'total_calls': 0,
    'total_cost': 0.0
})

try:
    with open(COST_CSV) as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header row
        for row in reader:
            if len(row) < 7:
                continue
            timestamp, client, workflow, model, \
                inp, out, cost = row
            if not timestamp.startswith(target_month):
                continue

            entry = data[client]
            wf = entry['workflows'][workflow]
            wf['calls'] += 1
            wf['input_tokens'] += int(inp)
            wf['output_tokens'] += int(out)
            wf['cost'] += float(cost)
            entry['total_calls'] += 1
            entry['total_cost'] += float(cost)
except FileNotFoundError:
    print(f"No {COST_CSV} found. "
          "Run some workflows first.")
    sys.exit(1)

if not data:
    print(f"No API calls found for {target_month}")
    sys.exit(0)

# Print summary
print(f"\n{'='*55}")
print(f"  API COST SUMMARY — {target_month}")
print(f"{'='*55}")

grand_total = 0.0
grand_calls = 0

for client in sorted(data.keys()):
    entry = data[client]
    grand_total += entry['total_cost']
    grand_calls += entry['total_calls']

    print(f"\n  {client}")
    print(f"  {'-'*50}")

    for wf_name in sorted(entry['workflows'].keys()):
        wf = entry['workflows'][wf_name]
        print(f"    {wf_name:<25} "
              f"{wf['calls']:>4} calls  "
              f"${wf['cost']:.4f}")

    print(f"  {'':>25} {'—'*22}")
    print(f"    {'SUBTOTAL':<25} "
          f"{entry['total_calls']:>4} calls  "
          f"${entry['total_cost']:.4f}")

print(f"\n{'='*55}")
print(f"  GRAND TOTAL: {grand_calls} calls  "
      f"${grand_total:.4f}")
print(f"{'='*55}\n")
