import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('build_release', 'scripts/build_release.py')
release = module('release', 'deploy/linux/release.py')
dev = module('dev', 'scripts/dev.py')


@pytest.mark.parametrize('path', ['.env', 'backend/.env', 'backend/.data/local.db', 'backend/app/local.db',
    'backend/app/modules/reporting/part_numbers.json', 'backend/app/resources/project-maps/plant-1.png',
    'DOCUMENTOS/report.xlsx', 'frontend/node_modules/package.json', '.venv/bin/python',
    'DataStage_Suppliers_Simple/archivos/backend/app/main.py', 'backend/app/__pycache__/main.pyc'])
def test_package_excludes_data_secrets_and_development_files(path):
    assert not builder.allowed_source(path)


def test_package_includes_only_the_approved_presentation_template_and_knowledge():
    assert builder.allowed_source('backend/app/resources/reports/blank.pptx')
    assert not builder.allowed_source('backend/app/resources/reports/customer.pptx')
    assert not builder.allowed_source('backend/app/resources/reports/customer.xlsx')
    for name in ('analytics', 'suppliers', 'compatibility', 'operations', 'data-model',
                 'assistant-corporate', 'azure-foundry'):
        assert builder.allowed_source('docs/' + name + '.md')
    assert not builder.allowed_source('docs/private-customer.md')


def package(extra=None, bad_hash=False):
    files = {'backend/app/main.py': b'# main', 'backend/app/worker.py': b'# worker',
             'backend/alembic.ini': b'[alembic]', 'frontend/index.html': b'<html/>'}
    manifest = {'version': 'test-1', 'files': {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}}
    if bad_hash:
        manifest['files']['frontend/index.html'] = 'bad'
    files['manifest.json'] = json.dumps(manifest).encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name, data in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        if extra:
            archive.addfile(extra)
    stream.seek(0)
    return tarfile.open(fileobj=stream, mode='r:gz')


def test_package_integrity_checks():
    with package() as archive:
        assert release.verify_archive(archive)['version'] == 'test-1'
    with package(bad_hash=True) as archive, pytest.raises(ValueError):
        release.verify_archive(archive)


@pytest.mark.parametrize('name', ['../evil', '/etc/evil', 'C:/evil', 'a\\b', 'frontend/index.html', 'a/./b'])
def test_installer_rejects_paths_and_duplicates(name):
    with package(tarfile.TarInfo(name)) as archive, pytest.raises(ValueError):
        release.verify_archive(archive)


def test_installer_rejects_symlinks():
    entry = tarfile.TarInfo('link')
    entry.type, entry.linkname = tarfile.SYMTYPE, '/etc/passwd'
    with package(entry) as archive, pytest.raises(ValueError):
        release.verify_archive(archive)


def test_local_env_overrides_production_without_changing_parent(monkeypatch):
    monkeypatch.setenv('DATASTAGE_DATABASE_URL', 'production-db')
    monkeypatch.setenv('DATASTAGE_AUTH_MODE', 'entra')
    env = dev.local_environment()
    assert env['DATASTAGE_AUTH_MODE'] == 'development'
    assert env['DATASTAGE_DATABASE_URL'].startswith('sqlite:///')
    assert env['DATASTAGE_DOCUMENT_ROOT'].endswith('.data/documents')
    import os
    assert os.environ['DATASTAGE_DATABASE_URL'] == 'production-db'


def test_linux_environment_templates_are_assignments_and_separate_migration_identity():
    from dotenv import dotenv_values
    runtime_path = ROOT / 'deploy/linux/runtime.env.example'
    migration_path = ROOT / 'deploy/linux/migration.env.example'
    for path in (runtime_path, migration_path):
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                assert re.fullmatch(r'[A-Z][A-Z0-9_]*=.*', line), (path.name, line)
    runtime = dotenv_values(runtime_path)
    migration = dotenv_values(migration_path)
    assert runtime['DATASTAGE_ENVIRONMENT'] == 'production'
    assert runtime['DATASTAGE_FOUNDRY_AUTH_MODE'] == 'default'
    assert runtime['DATASTAGE_FOUNDRY_ENABLED'] == 'false'
    assert 'DATASTAGE_MIGRATION_DATABASE_URL' not in runtime
    assert 'DATASTAGE_MIGRATION_DATABASE_URL' in migration
    assert 'DATASTAGE_DATABASE_URL' not in migration


def test_stop_never_uses_recorded_pid_from_another_workspace():
    with pytest.raises(RuntimeError):
        dev.request('stop', {'root': '/another/workspace', 'pid': 1, 'token': 'irrelevant', 'port': 1})


def test_staging_failure_does_not_activate_or_leave_success_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'BASE', tmp_path)
    (tmp_path / 'releases').mkdir()
    archive = tmp_path / 'test.tar.gz'
    with package() as source:
        source.fileobj.seek(0)
        # Rebuild compressed file from the verified synthetic members.
        with tarfile.open(archive, 'w:gz') as dest:
            for member in source.getmembers():
                dest.addfile(member, source.extractfile(member))
    calls = []
    def fail(*command):
        calls.append(command)
        if 'venv' in command:
            raise OSError('test install failure')
    monkeypatch.setattr(release, 'run', fail)
    args = SimpleNamespace(package=archive, sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                           python='approved-python', wheelhouse=tmp_path, pip_config=None)
    with pytest.raises(OSError):
        release.stage(args)
    assert not (tmp_path / 'current').exists()
    assert not (tmp_path / 'releases/test-1/.staged').exists()
    assert not any('systemctl' in call for call in calls)


def activation_fixture(tmp_path, monkeypatch):
    base, config, references, units = [tmp_path / name for name in ('app', 'etc', 'reference', 'units')]
    for folder in (base, config, references, units):
        folder.mkdir()
    old, new = base / 'releases/old', base / 'releases/new'
    for folder in (old, new):
        folder.mkdir(parents=True)
        (folder / '.staged').write_text('hash')
    (new / 'deploy/linux').mkdir(parents=True)
    (new / 'deploy/linux/datastage-api.service').write_text('[Service]\nType=simple\n')
    (base / 'current').symlink_to(old)
    for name in ('runtime.env', 'migration.env'):
        (config / name).write_text('synthetic=values')
        (config / name).chmod(0o600)
    (references / 'part_numbers.json').write_text('["synthetic"]')
    for name, value in [('BASE', base), ('CONFIG', config), ('REFERENCES', references), ('UNITS', units)]:
        monkeypatch.setattr(release, name, value)
    import os
    original = release.private_environment
    monkeypatch.setattr(release, 'private_environment', lambda p: original(p, owner=os.getuid()))
    return base, old, new


def test_migration_failure_keeps_previous_version_and_stops_services(tmp_path, monkeypatch):
    base, old, new = activation_fixture(tmp_path, monkeypatch)
    calls = []
    def fail(*command):
        calls.append(command)
        if command == ('systemctl', 'start', 'datastage-migrate@new.service'):
            raise RuntimeError('synthetic migration failure')
    monkeypatch.setattr(release, 'run', fail)
    with pytest.raises(RuntimeError):
        release.activate(SimpleNamespace(version='new', backup_confirmed=True))
    assert (base / 'current').resolve() == old
    assert calls[-1] == ('systemctl', 'stop', 'datastage-api', 'datastage-worker')
    assert not any('datastage-check@new.service' in command for command in calls)


def test_activation_checks_both_services_individually_and_preserves_releases(tmp_path, monkeypatch):
    base, old, new = activation_fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(release, 'run', lambda *command: calls.append(command))
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(release.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    release.activate(SimpleNamespace(version='new', backup_confirmed=True))
    assert (base / 'current').resolve() == new
    assert old.is_dir()
    assert ('systemctl', 'is-active', '--quiet', 'datastage-api') in calls
    assert ('systemctl', 'is-active', '--quiet', 'datastage-worker') in calls
    assert calls.index(('systemctl', 'start', 'datastage-migrate@new.service')) < calls.index(('systemctl', 'start', 'datastage-check@new.service'))


def test_release_has_every_service_and_environment_template():
    files = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in (ROOT / 'deploy/linux').iterdir() if p.is_file() and builder.allowed_source(p.relative_to(ROOT).as_posix())}
    for name in ('runtime.env.example', 'migration.env.example', 'prepare-host.sh', 'release.py',
                 'nginx.conf.template', 'datastage-api.service', 'datastage-worker.service',
                 'datastage-migrate@.service', 'datastage-check@.service'):
        assert 'deploy/linux/' + name in files
    assert b'REPLACE_MIGRATION_LOGIN' in files['deploy/linux/migration.env.example']
