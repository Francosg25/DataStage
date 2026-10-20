"""Readiness checks under the limited runtime account; no schema/data mutation."""
import json
import os
from pathlib import Path
import re
import tempfile

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import Settings
from app.persistence import make_engine


def check_schema(connection):
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    expected = set(ScriptDirectory.from_config(config).get_heads())
    actual = set(MigrationContext.configure(connection).get_current_heads())
    if actual != expected:
        raise ValueError('Revisión Alembic distinta del release; ejecutar migración separada')


def main():
    settings = Settings()
    if settings.environment != 'production':
        raise ValueError('Preflight requiere perfil de producción')
    import pyodbc
    if 'ODBC Driver 18 for SQL Server' not in pyodbc.drivers():
        raise ValueError('Falta ODBC Driver 18 en el sistema')
    root = settings.document_root
    if not root.is_dir():
        raise ValueError('Falta el directorio persistente')
    with tempfile.TemporaryFile(dir=root) as test:
        test.write(b'datastage-storage-check')
        test.flush()
        os.fsync(test.fileno())
    catalog = json.loads(Path(os.environ['DATASTAGE_PART_CATALOG_FILE']).read_text(encoding='utf-8'))
    if not isinstance(catalog, list) or not catalog or not all(isinstance(p, str) for p in catalog):
        raise ValueError('Catálogo PN ausente o inválido')
    if settings.project_maps_root:
        maps = json.loads((settings.project_maps_root / 'manifest.json').read_text(encoding='utf-8-sig'))
        for page in maps['pages']:
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', page['id']):
                raise ValueError('Identificador de mapa inválido')
            for suffix in ('.png', '-thumb.png'):
                with (settings.project_maps_root / (page['id'] + suffix)).open('rb') as image:
                    if image.read(8) != b'\x89PNG\r\n\x1a\n':
                        raise ValueError('Imagen de mapa inválida')
    engine = make_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            check_schema(connection)
            connection.execute(text('SELECT 1 FROM processing_jobs WHERE 1=0'))
    finally:
        engine.dispose()
    print('Preflight OK: schema, runtime SQL read, ODBC, persistent storage and reference files.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(f'Preflight falló ({type(exc).__name__}); revisar configuración, permisos y conectividad con TI.') from None
