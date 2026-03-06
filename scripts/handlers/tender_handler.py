"""Handler: Tender Compilation.

Routes classified tender documents through compilation and formatting.
"""

import os
import sys
import shutil
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.client_guard import validate_client_operation, ClientBoundaryError


def process(file_path, client_config):
    """Process a tender document.

    Args:
        file_path: Local path to the downloaded file.
        client_config: Full client config dict.

    Raises:
        ClientBoundaryError: If file's source folder doesn't match client.
    """
    client_code = client_config.get('client_code', 'UNKNOWN')

    # SEC-02: Validate client boundary before processing
    for folder_key in ('inbox', 'processing', 'completed'):
        folder_id = client_config.get('folders', {}).get(folder_key)
        if folder_id:
            validate_client_operation(client_code, folder_id)

    # Dedicated temp directory for local processing
    tmpdir = os.path.join(
        os.environ.get('TEMP', '/tmp'), 'ictus-flow-processing',
        f'tender-{uuid.uuid4().hex[:8]}',
    )
    os.makedirs(tmpdir, exist_ok=True)
    try:
        # TODO: Implement tender compilation pipeline
        pass
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
