"""Tests for SCA-07: Automated Backup of Client Configs.

All tests use mocked Drive client — no real API calls.

Run: python -m pytest tests/config-backup/test_config_backup.py -v
"""

import sys
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.utils.config_backup as cb


# ── Shared fixture ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_env(tmp_path, monkeypatch):
    """Create temp project structure and mock all Drive client calls."""
    # ── Directory layout ──
    clients_dir = tmp_path / 'config' / 'clients'
    clients_dir.mkdir(parents=True)

    workflows_dir = tmp_path / 'config' / 'workflows'
    workflows_dir.mkdir(parents=True)

    prompts_dir = tmp_path / 'prompts'
    prompts_dir.mkdir()
    overrides_dir = prompts_dir / 'client_overrides'
    overrides_dir.mkdir()

    pending_path = tmp_path / 'pending-promotions.json'

    # ── Monkeypatch module-level paths ──
    monkeypatch.setattr(cb, 'CLIENTS_DIR', clients_dir)
    monkeypatch.setattr(cb, 'WORKFLOWS_DIR', workflows_dir)
    monkeypatch.setattr(cb, 'PROMPTS_DIR', prompts_dir)
    monkeypatch.setattr(cb, 'PENDING_PROMOTIONS', pending_path)

    # ── Sample files ──
    _write(clients_dir / 'gilmartins.json', {
        'client_code': 'GILM',
        'client_name': 'Gilmartins',
        'folders': {'inbox': 'folder_inbox_1'},
    })
    _write(clients_dir / '_template.json', {
        'client_code': 'XXXX',
        'client_name': 'TEMPLATE — DO NOT EDIT',
    })
    _write(workflows_dir / 'routing-rules.json', {
        'classification_map': {'INVOICE': {'handler': 'invoice_handler'}},
    })
    (prompts_dir / 'invoice-processor.txt').write_text(
        'You are an invoice processor.', encoding='utf-8')
    (prompts_dir / 'classifier.txt').write_text(
        'Classify the document.', encoding='utf-8')
    (overrides_dir / 'custom-gilm-invoice.txt').write_text(
        'Custom GILM invoice prompt.', encoding='utf-8')
    _write(pending_path, {'pending': [], 'last_scan': None})

    # ── Mock Drive state ──
    mock = _MockDrive()

    from scripts.utils import drive_client as dc
    monkeypatch.setattr(dc, 'find_file_by_name', mock.find_file_by_name)
    monkeypatch.setattr(dc, 'create_folder', mock.create_folder)
    monkeypatch.setattr(dc, 'upload_bytes', mock.upload_bytes)
    monkeypatch.setattr(dc, 'list_files', mock.list_files)
    monkeypatch.setattr(dc, 'delete_file', mock.delete_file)
    monkeypatch.setattr(dc, 'download_file_bytes', mock.download_file_bytes)

    yield {
        'tmp_path': tmp_path,
        'clients_dir': clients_dir,
        'prompts_dir': prompts_dir,
        'workflows_dir': workflows_dir,
        'overrides_dir': overrides_dir,
        'pending_path': pending_path,
        'mock': mock,
    }


# ── Mock Drive client ───────────────────────────────────────────

class _MockDrive:
    """In-memory fake for the drive_client module-level functions."""

    BACKUP_FOLDER_ID = 'backup_folder_999'

    def __init__(self):
        self.uploaded = []      # list of {file_id, folder_id, filename, content}
        self.deleted = []       # list of file_ids
        self.files = []         # files visible in list_files

    def find_file_by_name(self, folder_id, filename, client_code=None):
        if filename == cb.BACKUP_FOLDER_NAME:
            return {'id': self.BACKUP_FOLDER_ID, 'name': filename}
        # Search uploaded files
        for u in self.uploaded:
            if u['filename'] == filename:
                return {'id': u['file_id'], 'name': filename}
        return None

    def create_folder(self, name, parent_folder_id=None, client_code=None):
        return f'folder_{name}'

    def upload_bytes(self, content, folder_id, filename,
                     mime_type='application/json', client_code=None):
        if isinstance(content, str):
            content = content.encode('utf-8')
        file_id = f'file_{filename}'
        entry = {
            'file_id': file_id,
            'folder_id': folder_id,
            'filename': filename,
            'content': content,
        }
        self.uploaded.append(entry)
        self.files.append({
            'id': file_id,
            'name': filename,
            'size': str(len(content)),
        })
        return file_id

    def list_files(self, folder_id, mime_type=None, client_code=None):
        return list(self.files)

    def delete_file(self, file_id, client_code=None):
        self.deleted.append(file_id)
        self.files = [f for f in self.files if f['id'] != file_id]

    def download_file_bytes(self, file_id, client_code=None):
        for u in self.uploaded:
            if u['file_id'] == file_id:
                return u['content']
        return b'{}'


def _write(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def _parse_uploaded_backup(mock):
    """Parse the JSON from the most recent upload."""
    assert mock.uploaded, "Nothing was uploaded"
    content = mock.uploaded[-1]['content']
    return json.loads(content.decode('utf-8'))


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════


# ── Test 1: backup creates correct JSON structure ────────────────

class TestBackupCreatesJson:

    def test_backup_creates_json(self, mock_env):
        """Backup JSON has backup_date, configs, routing_rules, prompts,
        and pending_promotions keys."""
        result = cb.backup_configs()
        assert result['configs_count'] == 1  # only GILM (template excluded)
        assert result['filename'].startswith('backup_')
        assert result['filename'].endswith('.json')

        backup = _parse_uploaded_backup(mock_env['mock'])
        assert 'backup_date' in backup
        assert 'configs' in backup
        assert 'routing_rules' in backup
        assert 'prompts' in backup
        assert 'pending_promotions' in backup


# ── Test 2: backup excludes _template.json ───────────────────────

class TestBackupExcludesTemplate:

    def test_backup_excludes_template(self, mock_env):
        """_template.json is not included in the configs dict."""
        cb.backup_configs()
        backup = _parse_uploaded_backup(mock_env['mock'])

        assert 'XXXX' not in backup['configs'], \
            "_template.json should not be backed up"
        assert 'GILM' in backup['configs'], \
            "Real client config should be backed up"


# ── Test 3: restore writes configs to disk ───────────────────────

class TestRestoreWritesConfigs:

    def test_restore_writes_configs(self, mock_env):
        """restore_configs writes client configs back to correct paths."""
        # Create a backup first
        cb.backup_configs()

        # Delete the original config file
        gilm_path = mock_env['clients_dir'] / 'gilmartins.json'
        gilm_path.unlink()
        assert not gilm_path.exists()

        # Restore
        result = cb.restore_configs()
        assert 'GILM' in result['restored_configs']

        # The file should exist again (written as gilm.json from client_code)
        restored_path = mock_env['clients_dir'] / 'gilm.json'
        assert restored_path.exists()

        with open(restored_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data['client_code'] == 'GILM'
        assert data['client_name'] == 'Gilmartins'


# ── Test 4: retention deletes old backups ────────────────────────

class TestRetentionDeletesOld:

    def test_retention_deletes_old(self, mock_env):
        """Backups older than the last MAX_BACKUPS are deleted."""
        mock = mock_env['mock']

        # Pre-populate with 33 existing backups
        for i in range(33):
            mock.files.append({
                'id': f'old_backup_{i:02d}',
                'name': f'backup_2026-01-{i + 1:02d}.json',
                'size': '1000',
            })

        # Run a new backup (adds 1 more → 34 total)
        cb.backup_configs()

        # Should have deleted 4 oldest (34 - 30 = 4)
        assert len(mock.deleted) == 4
        # Oldest ones should be deleted first
        assert 'old_backup_00' in mock.deleted
        assert 'old_backup_01' in mock.deleted
        assert 'old_backup_02' in mock.deleted
        assert 'old_backup_03' in mock.deleted


# ── Test 5: list_backups returns correct list ────────────────────

class TestListBackups:

    def test_list_backups(self, mock_env):
        """list_backups returns available backups sorted newest-first."""
        mock = mock_env['mock']

        # Add some backup files to the mock
        mock.files.extend([
            {'id': 'b1', 'name': 'backup_2026-03-01.json', 'size': '1000'},
            {'id': 'b2', 'name': 'backup_2026-03-05.json', 'size': '1200'},
            {'id': 'b3', 'name': 'backup_2026-02-28.json', 'size': '900'},
            # Non-backup file (should be filtered out)
            {'id': 'other', 'name': 'random.txt', 'size': '50'},
        ])

        backups = cb.list_backups()

        assert len(backups) == 3
        # Newest first
        assert backups[0]['date'] == '2026-03-05'
        assert backups[1]['date'] == '2026-03-01'
        assert backups[2]['date'] == '2026-02-28'
        # Each has required keys
        for b in backups:
            assert 'filename' in b
            assert 'date' in b
            assert 'file_id' in b
            assert 'size' in b


# ── Test 6: prompt files included in backup ──────────────────────

class TestPromptsIncluded:

    def test_prompts_included(self, mock_env):
        """All prompt .txt files (including client_overrides/) are backed up."""
        cb.backup_configs()
        backup = _parse_uploaded_backup(mock_env['mock'])

        prompts = backup['prompts']
        assert 'invoice-processor.txt' in prompts
        assert 'classifier.txt' in prompts
        assert 'client_overrides/custom-gilm-invoice.txt' in prompts

        # Content check
        assert prompts['invoice-processor.txt'] == 'You are an invoice processor.'
        assert prompts['client_overrides/custom-gilm-invoice.txt'] == \
            'Custom GILM invoice prompt.'


# ── Test 7: secrets never included ───────────────────────────────

class TestSecretsExcluded:

    def test_secrets_excluded(self, mock_env):
        """.env and service-account.json are never included in backups."""
        tmp = mock_env['tmp_path']

        # Create secret files in the project root
        (tmp / '.env').write_text('SECRET_KEY=abc123', encoding='utf-8')
        (tmp / 'service-account.json').write_text(
            '{"private_key": "REDACTED"}', encoding='utf-8')

        # Also put a secret in the config directory (should still be excluded
        # by the _template filter, but verify it's not backed up by name)
        cb.backup_configs()
        backup = _parse_uploaded_backup(mock_env['mock'])

        # Flatten every string value in the backup
        flat = json.dumps(backup)

        assert 'SECRET_KEY' not in flat
        assert 'abc123' not in flat
        assert 'private_key' not in flat
        assert 'REDACTED' not in flat
        assert '.env' not in backup.get('configs', {})
        assert 'service-account' not in backup.get('configs', {})
        assert '.env' not in backup.get('prompts', {})
        assert 'service-account.json' not in backup.get('prompts', {})
