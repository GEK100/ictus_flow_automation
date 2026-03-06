"""Processor: Routes classified work to the correct handler.

After drive_watcher.py classifies a file and moves it to 02-PROCESSING,
this module dispatches it to the appropriate handler based on classification.

Errors are NOT caught here — they propagate up to drive_watcher.py's
per-file try/except where handle_failure() handles them uniformly.
"""

import importlib
import logging

log = logging.getLogger(__name__)

# Maps classification labels (from the classifier) to handler module paths.
# Each handler module must expose a process(file_path, client_config) function.
HANDLER_MAP = {
    'invoice': 'scripts.handlers.invoice_handler',
    'letter': 'scripts.handlers.letter_handler',
    'contract': 'scripts.handlers.contract_handler',
    'tender': 'scripts.handlers.tender_handler',
    'rams': 'scripts.handlers.rams_handler',
    'cis': 'scripts.handlers.cis_handler',
    'payment_cert': 'scripts.handlers.payment_cert_handler',
    'credit_control': 'scripts.handlers.credit_control_handler',
    'quote': 'scripts.handlers.quote_handler',
    'blog': 'scripts.handlers.blog_handler',
    'progress_report': 'scripts.handlers.progress_report_handler',
    'compliance': 'scripts.handlers.compliance_handler',
}


def route_file(file_path, classification, client_config):
    """Route a classified file to its handler for processing.

    Args:
        file_path: Local path to the downloaded file.
        classification: Classification label from the classifier (e.g. 'invoice').
        client_config: Full client config dict.

    Raises:
        ValueError: If no handler exists for the given classification.
        Any exception raised by the handler's process() function.
    """
    classification_key = classification.lower().strip()
    handler_path = HANDLER_MAP.get(classification_key)

    if not handler_path:
        raise ValueError(
            f"No handler for classification '{classification}'. "
            f"Valid types: {', '.join(sorted(HANDLER_MAP.keys()))}"
        )

    log.info(f"Routing '{classification}' to {handler_path}")
    module = importlib.import_module(handler_path)
    module.process(file_path, client_config)
