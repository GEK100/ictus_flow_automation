"""SCA-07: Automated Backup of Client Configs to Google Drive.

Bundles client configs, workflow routing rules, prompt files, and
pending-promotions.json into a single timestamped JSON file and
uploads it to a dedicated backup folder on Drive.

Retention: keeps the last 30 backups and deletes older ones.

Never backs up secrets (.env, service-account.json, etc.).
"""

import json
from datetime import datetime
from pathlib import Path

from scripts.utils import drive_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Configurable paths (monkeypatched in tests) ──────────────────
CLIENTS_DIR = PROJECT_ROOT / 'config' / 'clients'
WORKFLOWS_DIR = PROJECT_ROOT / 'config' / 'workflows'
PROMPTS_DIR = PROJECT_ROOT / 'prompts'
PENDING_PROMOTIONS = PROJECT_ROOT / 'pending-promotions.json'

BACKUP_FOLDER_NAME = 'Ictus Flow System Backups'
MAX_BACKUPS = 30


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════


def ensure_backup_folder():
    """Check if the backup folder exists on Drive; create it if not.

    The folder is owned by the service account and sits at its Drive root.

    Returns:
        str: The backup folder's Drive ID.
    """
    existing = drive_client.find_file_by_name('root', BACKUP_FOLDER_NAME)
    if existing:
        return existing['id']
    return drive_client.create_folder(BACKUP_FOLDER_NAME)


def backup_configs():
    """Bundle all configs and prompts into a single JSON and upload to Drive.

    Returns:
        dict with keys: file_id, filename, configs_count, prompts_count.
    """
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    date_str = datetime.now().strftime('%Y-%m-%d')

    configs = _collect_client_configs()
    prompts = _collect_prompts()

    backup = {
        'backup_date': timestamp,
        'configs': configs,
        'routing_rules': _collect_routing_rules(),
        'prompts': prompts,
        'pending_promotions': _collect_pending_promotions(),
    }

    folder_id = ensure_backup_folder()
    filename = f'backup_{date_str}.json'
    content = json.dumps(backup, indent=2)
    file_id = drive_client.upload_bytes(content, folder_id, filename)

    # Retention: keep last MAX_BACKUPS
    _enforce_retention(folder_id)

    return {
        'file_id': file_id,
        'filename': filename,
        'configs_count': len(configs),
        'prompts_count': len(prompts),
    }


def restore_configs(backup_date=None):
    """Download a backup and write configs back to disk.

    Args:
        backup_date: Date string 'YYYY-MM-DD'.  If None, uses most recent.

    Returns:
        dict with keys: restored_configs, backup_date.

    Raises:
        FileNotFoundError: If the requested backup (or any backup) is missing.
    """
    folder_id = ensure_backup_folder()

    if backup_date:
        filename = f'backup_{backup_date}.json'
        file_info = drive_client.find_file_by_name(folder_id, filename)
        if not file_info:
            raise FileNotFoundError(f"Backup not found: {filename}")
    else:
        files = drive_client.list_files(folder_id)
        backups = _filter_backup_files(files)
        if not backups:
            raise FileNotFoundError("No backups found")
        backups.sort(key=lambda f: f['name'], reverse=True)
        file_info = backups[0]

    raw = drive_client.download_file_bytes(file_info['id'])
    backup = json.loads(raw.decode('utf-8'))

    restored = []

    # Client configs
    CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
    for code, config in backup.get('configs', {}).items():
        path = CLIENTS_DIR / f'{code.lower()}.json'
        _write_json(path, config)
        restored.append(code)

    # Routing rules
    if backup.get('routing_rules'):
        WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(WORKFLOWS_DIR / 'routing-rules.json', backup['routing_rules'])

    # Prompts
    for rel_path, content in backup.get('prompts', {}).items():
        path = PROMPTS_DIR / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    # Pending promotions
    if backup.get('pending_promotions'):
        _write_json(PENDING_PROMOTIONS, backup['pending_promotions'])

    print(f"Restored {len(restored)} client configs from {backup['backup_date']}")
    return {
        'restored_configs': restored,
        'backup_date': backup['backup_date'],
    }


def list_backups():
    """List all available backups with dates and metadata.

    Returns:
        list[dict]: Sorted newest-first, each with filename, date, file_id, size.
    """
    folder_id = ensure_backup_folder()
    files = drive_client.list_files(folder_id)
    backups = _filter_backup_files(files)
    backups.sort(key=lambda f: f['name'], reverse=True)

    results = []
    for f in backups:
        date_str = f['name'].replace('backup_', '').replace('.json', '')
        results.append({
            'filename': f['name'],
            'date': date_str,
            'file_id': f['id'],
            'size': f.get('size', 'unknown'),
        })
    return results


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════


def _collect_client_configs():
    """Read all client configs (excluding _template.json)."""
    configs = {}
    if not CLIENTS_DIR.exists():
        return configs
    for path in sorted(CLIENTS_DIR.glob('*.json')):
        if '_template' in path.name:
            continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        client_code = data.get('client_code', path.stem.upper())
        configs[client_code] = data
    return configs


def _collect_prompts():
    """Read all prompt .txt files (including client_overrides/)."""
    prompts = {}
    if not PROMPTS_DIR.exists():
        return prompts
    for path in sorted(PROMPTS_DIR.rglob('*.txt')):
        rel = str(path.relative_to(PROMPTS_DIR)).replace('\\', '/')
        prompts[rel] = path.read_text(encoding='utf-8')
    return prompts


def _collect_routing_rules():
    """Read routing rules config if present."""
    path = WORKFLOWS_DIR / 'routing-rules.json'
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def _collect_pending_promotions():
    """Read pending-promotions.json if present."""
    if PENDING_PROMOTIONS.exists():
        with open(PENDING_PROMOTIONS, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def _filter_backup_files(files):
    """Keep only backup_*.json files from a file listing."""
    return [
        f for f in files
        if f['name'].startswith('backup_') and f['name'].endswith('.json')
    ]


def _enforce_retention(folder_id):
    """Delete backups beyond MAX_BACKUPS (oldest first)."""
    files = drive_client.list_files(folder_id)
    backups = _filter_backup_files(files)
    backups.sort(key=lambda f: f['name'])  # oldest first

    if len(backups) > MAX_BACKUPS:
        to_delete = backups[:len(backups) - MAX_BACKUPS]
        for f in to_delete:
            drive_client.delete_file(f['id'])
            print(f"  Deleted old backup: {f['name']}")


def _write_json(path, data):
    """Write a dict as pretty-printed JSON."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
