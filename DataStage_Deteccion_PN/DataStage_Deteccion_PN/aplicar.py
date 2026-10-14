"""Aplica exclusivamente las mejoras de gráficas, sin modificar el historial Git."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def git_read(target, *args):
    return subprocess.check_output(
        ['git', '-C', str(target), *args], text=True, encoding='utf-8', stderr=subprocess.STDOUT,
    ).strip()


def apply(target, check=False):
    target = target.expanduser().resolve()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    if not (target / 'backend/app/main.py').is_file() or not (target / 'frontend/package.json').is_file():
        raise ValueError('La carpeta indicada no es la raíz de DataStage.')
    if Path(git_read(target, 'rev-parse', '--show-toplevel')).resolve() != target:
        raise ValueError('La carpeta debe ser la raíz del repositorio DataStage.')
    branch = git_read(target, 'branch', '--show-current')
    if branch != 'Mejoras_Graficas':
        raise ValueError(f'No se aplicó ningún cambio. Rama actual: {branch}. Se requiere Mejoras_Graficas.')
    sources = []
    for entry in manifest['files']:
        relative = Path(entry['path'])
        destination = (target / relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not destination.is_relative_to(target):
            raise ValueError('Ruta de archivo no válida.')
        source = package / 'payload' / relative
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Paquete incompleto o alterado: {relative}')
        sources.append((relative, source, destination))
    print(f'Carpeta: {target}\nRama: {branch}\nArchivos de la mejora: {len(sources)}')
    if check:
        print('Comprobación correcta. No se modificó ningún archivo.')
        return None

    backup = target.parent / ('Respaldo_Mejoras_Graficas_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir()
    original = {}
    for relative, _, destination in sources:
        original[str(relative)] = destination.exists()
        if destination.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, saved)
    (backup / 'respaldo.json').write_text(json.dumps({
        'project': str(target), 'branch': branch, 'files': original,
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    modified = []
    try:
        for relative, source, destination in sources:
            destination.parent.mkdir(parents=True, exist_ok=True)
            modified.append((relative, destination))
            shutil.copy2(source, destination)
    except OSError:
        failures = []
        for relative, destination in reversed(modified):
            try:
                if original[str(relative)]:
                    shutil.copy2(backup / relative, destination)
                else:
                    destination.unlink(missing_ok=True)
            except OSError:
                failures.append(str(relative))
        if failures:
            print('No se pudo restaurar automáticamente: ' + ', '.join(failures))
        else:
            print('La aplicación falló y los archivos afectados se restauraron.')
        print(f'Respaldo disponible en: {backup}')
        raise
    print(f'\nCambios aplicados. Respaldo: {backup}')
    print('Los archivos quedan como cambios locales de Mejoras_Graficas, pendientes de revisar.')
    print('No se ejecutó git add, commit, pull, push ni cambio de rama. No se instalaron dependencias.')
    print('Inicia backend, worker y frontend con tus comandos habituales.')
    return backup


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--check', action='store_true', help='Solo comprobar; no aplicar cambios.')
    args = parser.parse_args()
    try:
        apply(args.project, args.check)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
