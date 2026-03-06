"""Client boundary enforcement for Ictus Flow.

Prevents cross-client data leakage by validating that every Drive
operation targets a folder belonging to the requesting client.

SEC-02: Client Data Isolation Enforcement.
"""

import os
import sys
import inspect
import logging
from datetime import datetime
from pathlib import Path
from functools import wraps

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Security logger — writes to logs/security.log
_security_logger = None


def _get_security_logger():
    """Lazy-init the security file logger."""
    global _security_logger
    if _security_logger is not None:
        return _security_logger

    _security_logger = logging.getLogger('ictus.security')
    _security_logger.setLevel(logging.WARNING)

    # Avoid duplicate handlers on re-import
    if not _security_logger.handlers:
        log_dir = PROJECT_ROOT / 'logs'
        log_dir.mkdir(exist_ok=True)
        handler = logging.FileHandler(log_dir / 'security.log', encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        _security_logger.addHandler(handler)

    return _security_logger


class ClientBoundaryError(Exception):
    """Raised when a Drive operation targets a folder outside the client's boundary."""

    def __init__(self, client_code, target_folder_id, message=None):
        self.client_code = client_code
        self.target_folder_id = target_folder_id
        if message is None:
            message = (
                f"CLIENT BOUNDARY VIOLATION: client '{client_code}' "
                f"attempted to access folder '{target_folder_id}' "
                f"which is not in their folder list."
            )
        super().__init__(message)


def _get_caller_info():
    """Walk the stack to find the calling script (skip client_guard and drive_client frames)."""
    skip_modules = {'client_guard', 'drive_client'}
    for frame_info in inspect.stack()[2:]:
        module_name = Path(frame_info.filename).stem
        if module_name not in skip_modules:
            return f"{Path(frame_info.filename).name}:{frame_info.lineno}"
    return 'unknown'


def validate_client_operation(client_code, target_folder_id):
    """Validate that target_folder_id belongs to the given client.

    Args:
        client_code: Client code (e.g. 'GILM').
        target_folder_id: Google Drive folder ID being accessed.

    Raises:
        ClientBoundaryError: If the folder does not belong to the client.
        ClientBoundaryError: If the client config cannot be loaded.
    """
    # Import here to avoid circular imports
    from scripts.utils.prompt_builder import load_client_config

    config = load_client_config(client_code)
    if config is None:
        caller = _get_caller_info()
        _log_violation(client_code, target_folder_id, caller, reason='CONFIG_NOT_FOUND')
        raise ClientBoundaryError(
            client_code, target_folder_id,
            f"CLIENT BOUNDARY ERROR: config not found for client '{client_code}'. "
            f"Cannot validate folder access — blocking operation."
        )

    # Collect all folder IDs from the client config
    folders = config.get('folders', {})
    allowed_ids = set(folders.values())

    if target_folder_id not in allowed_ids:
        caller = _get_caller_info()
        _log_violation(client_code, target_folder_id, caller)
        raise ClientBoundaryError(client_code, target_folder_id)


def _log_violation(client_code, target_folder_id, caller, reason='BOUNDARY_VIOLATION'):
    """Write a violation entry to logs/security.log."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"{timestamp} | {reason} | {client_code} | {target_folder_id} | {caller}"

    logger = _get_security_logger()
    logger.warning(entry)

    # Also print to stderr for immediate visibility
    print(f"SECURITY: {entry}", file=sys.stderr)


def enforce_client_boundary(func):
    """Decorator that validates client_code against folder_id before execution.

    The wrapped function MUST accept 'client_code' and 'folder_id' as
    keyword arguments (or positional args in those positions).
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Try to extract client_code and folder_id from kwargs first
        client_code = kwargs.get('client_code')
        folder_id = kwargs.get('folder_id')

        # Fall back to positional args via inspect
        if client_code is None or folder_id is None:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            for i, (param_name, arg_val) in enumerate(zip(params, args)):
                if param_name == 'client_code' and client_code is None:
                    client_code = arg_val
                elif param_name == 'folder_id' and folder_id is None:
                    folder_id = arg_val

        if client_code and folder_id:
            validate_client_operation(client_code, folder_id)

        return func(*args, **kwargs)

    return wrapper
