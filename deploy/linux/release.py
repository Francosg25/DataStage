"""IT-only release staging/activation. No operating-system package installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request

BASE = Path('/opt/datastage')
CONFIG = Path('/etc/datastage')
REFERENCES = Path('/var/lib/datastage/reference')
UNITS = Path('/etc/systemd/system')
VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')


def verify_archive(archive):
    members = archive.getmembers()
    if len(members) > 10000 or sum(m.size for m in members) > 1024**3:
        raise ValueError('Package exceeds release limits')
    names = set()
    for member in members:
        name = member.name
        p = PurePosixPath(name)
        if (not member.isfile() or p.is_absolute() or '..' in p.parts or '\\' in name
                or ':' in name or p.as_posix() != name or name in names):
            raise ValueError('Unsafe package entry')
        names.add(name)
    manifest = json.load(archive.extractfile('manifest.json'))
    if not VERSION.fullmatch(manifest['version']):
        raise ValueError('Invalid version')
    if set(manifest['files']) != names - {'manifest.json'}:
        raise ValueError('Incomplete package manifest')
    for name, digest in manifest['files'].items():
        if hashlib.sha256(archive.extractfile(name).read()).hexdigest() != digest:
            raise ValueError('Package checksum mismatch')
    for needed in ('backend/app/main.py', 'backend/app/worker.py', 'backend/alembic.ini', 'frontend/index.html'):
        if needed not in names:
            raise ValueError('Incomplete release')
    return manifest


def run(*command):
    subprocess.run(command, check=True)


def stage(args):
    # Sidecar expected hash must come through the approved promotion channel.
    actual = hashlib.sha256(args.package.read_bytes()).hexdigest()
    if actual != args.sha256.lower():
        raise ValueError('Archive SHA-256 differs from approved hash')
    run(args.python, '-c', 'import sys; assert (3, 12) <= sys.version_info[:2] <= (3, 13), "Use Python 3.12/3.13"')
    with tarfile.open(args.package, 'r:gz') as archive:
        manifest = verify_archive(archive)
        dest = BASE / 'releases' / manifest['version']
        dest.mkdir(mode=0o755)  # Never overwrite/reuse a release, even after failure.
        try:
            for member in archive.getmembers():
                path = dest / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, path.open('xb') as out:
                    shutil.copyfileobj(src, out)
                path.chmod(0o644)
            run(args.python, '-m', 'venv', str(dest / '.venv'))
            command = [str(dest / '.venv/bin/python'), '-m', 'pip', 'install', '--only-binary=:all:', '--no-deps',
                       '-r', str(dest / 'backend/requirements.lock')]
            if args.wheelhouse:
                command += ['--no-index', '--find-links', str(args.wheelhouse.resolve())]
            elif args.pip_config:
                # Root-owned pip config can refer to an approved corporate repository/CA.
                os.environ['PIP_CONFIG_FILE'] = str(args.pip_config.resolve())
            else:
                raise ValueError('Supply --wheelhouse or --pip-config; no implicit public repository')
            run(*command)
            run(str(dest / '.venv/bin/python'), '-m', 'pip', 'check')
            # Service accounts can read code even when IT uses a restrictive umask.
            for path in dest.rglob('*'):
                if not path.is_symlink():
                    path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
            dest.chmod(0o755)
            (dest / '.staged').write_text(actual + '\n')
        except BaseException:
            # Preserve for diagnosis, never activate a partial install.
            print('Staging failed; inactive release retained for IT inspection:', dest)
            raise
    print('Staged without changing running services:', dest)


def private_environment(path, owner=0):
    if path.stat().st_uid != owner or path.stat().st_mode & 0o077:
        raise ValueError('Environment files must be root-owned, mode 0600')
    return path.read_text()


def activate(args):
    if not VERSION.fullmatch(args.version):
        raise ValueError('Invalid version')
    dest = BASE / 'releases' / args.version
    if not (dest / '.staged').is_file() or dest.is_symlink():
        raise ValueError('Release has not been staged successfully')
    # Avoid a template accidentally reaching any database.
    for file in ('runtime.env', 'migration.env'):
        path = CONFIG / file
        if 'REPLACE_' in private_environment(path):
            raise ValueError('Complete IT configuration before activation')
    if not (REFERENCES / 'part_numbers.json').is_file():
        raise ValueError('Provision the approved PN catalog separately first')
    if not args.backup_confirmed:
        raise ValueError('Confirm a coordinated backup using --backup-confirmed')
    run('nginx', '-t')
    # No live application writes during migrations. Worker receives SIGTERM first.
    run('systemctl', 'stop', 'datastage-api', 'datastage-worker')
    previous = (BASE / 'current').resolve() if (BASE / 'current').exists() else None
    try:
        # Promote reviewed service definitions together with this release, never env/TLS.
        for source in (dest / 'deploy/linux').glob('*.service'):
            target = UNITS / source.name
            shutil.copyfile(source, target)
            target.chmod(0o644)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', f'datastage-migrate@{args.version}.service')
        run('systemctl', 'start', f'datastage-check@{args.version}.service')
        link = BASE / 'current.next'
        link.unlink(missing_ok=True)
        link.symlink_to(dest, target_is_directory=True)
        link.replace(BASE / 'current')
        run('systemctl', 'start', 'datastage-api', 'datastage-worker')
        for _ in range(30):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2) as response:
                    ready = response.status == 200
                if ready:
                    for service in ('datastage-api', 'datastage-worker'):
                        run('systemctl', 'is-active', '--quiet', service)
                    print('Active release:', args.version, 'Previous:', previous)
                    print('Complete HTTPS, Entra roles and upload/export acceptance before opening access.')
                    return
            except (OSError, subprocess.CalledProcessError):
                pass
            time.sleep(1)
        raise RuntimeError('Readiness failed')
    except BaseException:
        run('systemctl', 'stop', 'datastage-api', 'datastage-worker')
        print('Activation failed; services stopped. Previous release:', previous)
        print('Do not downgrade automatically: review schema compatibility or restore the coordinated backup.')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    install = commands.add_parser('stage')
    install.add_argument('package', type=Path)
    install.add_argument('--sha256', required=True)
    install.add_argument('--python', required=True, help='Approved Python 3.12/3.13 executable')
    source = install.add_mutually_exclusive_group(required=True)
    source.add_argument('--wheelhouse', type=Path)
    source.add_argument('--pip-config', type=Path)
    activation = commands.add_parser('activate')
    activation.add_argument('version')
    activation.add_argument('--backup-confirmed', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix' or os.geteuid() != 0:
        parser.error('IT must run through the approved root administration process on Linux')
    # Serialize activation and staging; a second deployment must not race the first.
    import fcntl
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE / '.deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (stage if args.action == 'stage' else activate)(args)


if __name__ == '__main__':
    main()
