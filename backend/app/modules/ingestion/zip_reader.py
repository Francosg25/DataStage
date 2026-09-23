import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from app.core.errors import ApplicationError


def scan_document(path: Path, settings):
    if not settings.antivirus_command:
        return
    try:
        completed = subprocess.run([*settings.antivirus_command, str(path)], shell=False,
                                   capture_output=True, timeout=settings.antivirus_timeout_seconds)
    except (OSError, subprocess.TimeoutExpired):
        raise ApplicationError(503, "SCAN_UNAVAILABLE", "No fue posible completar el análisis de seguridad") from None
    if completed.returncode != 0:
        raise ApplicationError(422, "SCAN_REJECTED", "El análisis de seguridad no aprobó el archivo")


def read_zip(path: Path, settings):
    """Yield (relative entry name, original bytes); never extract arbitrary paths."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_zip_entries:
                raise ApplicationError(422, "ZIP_ENTRY_LIMIT", "El ZIP contiene demasiadas entradas")
            total_declared = sum(entry.file_size for entry in entries)
            if total_declared > settings.max_extracted_mb * 1024 * 1024:
                raise ApplicationError(422, "ZIP_SIZE_LIMIT", "El ZIP descomprimido supera el límite")
            names, actual_total, files = set(), 0, 0
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                parts = PurePosixPath(name).parts
                if not parts or name.startswith("/") or any(p in ("..", ".") for p in parts) or ":" in name or "\x00" in name:
                    raise ApplicationError(422, "UNSAFE_ZIP_PATH", "El ZIP contiene una ruta no permitida")
                unix_type = stat.S_IFMT(entry.external_attr >> 16)
                if unix_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ApplicationError(422, "ZIP_LINK_REJECTED", "El ZIP contiene enlaces o entradas especiales")
                if entry.flag_bits & 1:
                    raise ApplicationError(422, "ENCRYPTED_ZIP", "No se aceptan ZIP cifrados")
                if entry.is_dir():
                    continue
                if name.casefold() in names:
                    raise ApplicationError(422, "DUPLICATE_ZIP_PATH", "El ZIP contiene nombres de archivo repetidos")
                names.add(name.casefold())
                if not name.lower().endswith(".asc"):
                    raise ApplicationError(422, "UNSUPPORTED_ZIP_ENTRY", "El ZIP debe contener únicamente archivos ASC")
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ApplicationError(422, "ZIP_COMPRESSION", "Método de compresión no admitido")
                if entry.file_size > settings.max_file_mb * 1024 * 1024:
                    raise ApplicationError(422, "ASC_SIZE_LIMIT", "Un archivo ASC supera el límite")
                if entry.file_size / max(1, entry.compress_size) > settings.max_compression_ratio:
                    raise ApplicationError(422, "ZIP_RATIO_LIMIT", "La relación de compresión supera el límite")
                data = bytearray()
                with archive.open(entry) as stream:
                    while chunk := stream.read(1024 * 1024):
                        data.extend(chunk)
                        actual_total += len(chunk)
                        if len(data) > settings.max_file_mb * 1024 * 1024 or actual_total > settings.max_extracted_mb * 1024 * 1024:
                            raise ApplicationError(422, "ZIP_SIZE_LIMIT", "Se superó el límite durante la descompresión")
                files += 1
                yield name, bytes(data)
            if not files:
                raise ApplicationError(422, "ZIP_NO_ASC", "El ZIP no contiene archivos ASC")
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, RuntimeError):
        raise ApplicationError(422, "INVALID_ZIP", "El archivo ZIP está dañado o no es compatible") from None
