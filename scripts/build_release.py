"""Build a code-only Linux release. Run after npm ci + npm run build in frontend."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def allowed_source(name):
    p = Path(name)
    if p.is_absolute() or any(x.startswith('.') or x == '__pycache__' for x in p.parts):
        return False
    if name.startswith('backend/app/'):
        return p.suffix == '.py'
    if name.startswith('backend/migrations/'):
        return p.suffix in {'.py', '.mako'}
    return (name in {'backend/alembic.ini', 'backend/requirements.lock', 'backend/pyproject.toml'}
            or name.startswith('deploy/linux/') and p.suffix in {'.py', '.sh', '.service', '.example', '.template'}
            or name in {'docs/linux-direct.md', 'docs/windows-local.md', 'docs/native-validation.md', 'docs/azure-foundry.md', 'docs/entra-id.md', 'docs/entra-id-primeros-pasos.txt'})


def payload(root):
    tracked = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root)
    files = {}
    for name in tracked.decode().split('\0'):
        if name and allowed_source(name) and (root / name).is_file():
            if (root / name).is_symlink():
                raise ValueError('Symlink in source: ' + name)
            files[name] = (root / name).read_bytes()
    front = root / 'frontend/dist/datastage-web/browser'
    if not (front / 'index.html').is_file():
        raise ValueError('Compile frontend first: cd frontend && npm run build')
    # Build output contains only application assets; never copy arbitrary public files.
    for p in front.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(front)
        if p.is_symlink() or p.suffix not in {'.html', '.js', '.css', '.woff', '.woff2', '.ico', '.svg', '.md', '.txt'}:
            raise ValueError('Unexpected frontend asset; review before release: ' + str(rel))
        files['frontend/' + rel.as_posix()] = p.read_bytes()
    licenses = front.parent / '3rdpartylicenses.txt'
    if licenses.is_file():
        files['frontend/3rdpartylicenses.txt'] = licenses.read_bytes()
    # Catalogs/plant maps are separately provisioned company data, never embedded.
    # A missing catalog is intentionally fatal rather than silently changing PN rules.
    return files


def build(root, version, output):
    if not VERSION.fullmatch(version):
        raise ValueError('Invalid release version')
    files = payload(root)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip())
    manifest = {'version': version, 'commit': commit, 'workingTreeChanges': dirty,
                'files': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}}
    files['manifest.json'] = json.dumps(manifest, indent=2).encode()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'datastage-{version}.tar.gz'
    with target.open('xb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(target.suffix + '.sha256').write_text(f'{digest}  {target.name}\n')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(build(ROOT, args.version, args.output))
