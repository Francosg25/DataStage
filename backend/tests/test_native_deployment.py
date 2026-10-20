"""Native deployment contracts and ingestion regression checks; no corporate services."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.cli.migrate import migration_url
from app.core.config import Settings, validate_sqlserver_url
from app.modules.storage.filesystem import FileSystemStorage
from app.persistence.models import StoredDocument
from test_api_worker import drain, get_run, system as system, upload

SQL = 'mssql+pyodbc://runtime:synthetic@sql.test:1433/test?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no'


def production_settings(tmp_path, **overrides):
    return Settings(_env_file=None, **dict(environment='production', auth_mode='entra',
        database_url=SQL, document_root=tmp_path / 'persistent',
        entra_tenant_id='synthetic-tenant', entra_client_id='synthetic-spa',
        entra_audience='synthetic-api', entra_api_scope='api://synthetic/access_as_user',
        cors_origins=['https://ui.test'], **overrides))


def test_production_does_not_require_scanner(tmp_path):
    settings = production_settings(tmp_path)
    assert not settings.foundry_enabled
    assert 'antivirus_command' not in Settings.model_fields
    assert 'antivirus_timeout_seconds' not in Settings.model_fields


@pytest.mark.parametrize('url', [
    SQL.replace('Encrypt=yes', 'Encrypt=no'), SQL.replace('TrustServerCertificate=no', 'TrustServerCertificate=yes'),
    SQL.replace('&Encrypt=yes', ''), SQL.replace('&TrustServerCertificate=no', ''),
    SQL + '&odbc_connect=anything', SQL.replace('ODBC+Driver+18', 'ODBC+Driver+17'),
    SQL + '&encrypt=no', 'sqlite:///local.db', 'mssql+pyodbc://runtime:password@dsn',
])
def test_sql_transport_requires_encryption_and_verified_certificate(url):
    with pytest.raises(ValueError):
        validate_sqlserver_url(url)


def test_production_rejects_release_relative_storage_and_http_origin():
    values = dict(_env_file=None, environment='production', auth_mode='entra', database_url=SQL,
                  entra_tenant_id='test', entra_client_id='test', entra_audience='test', entra_api_scope='test')
    with pytest.raises(ValidationError):
        Settings(**values, document_root=Path('documents'), cors_origins=['https://ui.test'])
    with pytest.raises(ValidationError):
        Settings(**values, document_root=Path('/var/lib/datastage/documents'), cors_origins=['http://ui.test'])


def test_migration_identity_must_be_separate_and_same_target():
    assert migration_url(SQL, SQL.replace('runtime:', 'migrator:')).username == 'migrator'
    for target in (SQL, SQL.replace('runtime:', 'migrator:').replace('sql.test', 'other.test'),
                   SQL.replace('runtime:', 'migrator:').replace('/test?', '/other?')):
        with pytest.raises(ValueError):
            migration_url(SQL, target)


def test_upload_processing_export_never_executes_external_content_or_scanner(system, monkeypatch):
    app, client, settings = system
    execute = Mock(side_effect=AssertionError('Ingestion must not invoke a process'))
    monkeypatch.setattr('subprocess.run', execute)
    response = upload(client)
    drain(app, settings)
    result = get_run(client, response)
    assert result['publicationStatus'] == 'published'
    assert result['exportStatus'] == 'ready'
    assert client.get(f"/api/v1/documents/{result['exportDocumentId']}/download").status_code == 200
    with app.state.session_factory() as session:
        docs = list(session.scalars(select(StoredDocument)))
        assert docs and all(d.status == 'available' for d in docs)
        before = {d.storage_key: app.state.storage.read_bytes(d.storage_key) for d in docs}
    # A worker restart with an empty queue neither deletes nor rewrites documents.
    drain(app, settings)
    assert before == {key: app.state.storage.read_bytes(key) for key in before}
    execute.assert_not_called()


def test_atomic_document_write_removes_its_temporary_on_failure(tmp_path, monkeypatch):
    store = FileSystemStorage(tmp_path / 'docs')
    monkeypatch.setattr('app.modules.storage.filesystem.os.replace', Mock(side_effect=OSError('disk failure')))
    with pytest.raises(OSError):
        store.put_bytes(b'data', '.asc')
    assert list(store.root.iterdir()) == []
