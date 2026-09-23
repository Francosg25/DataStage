import hashlib
import os
from pathlib import Path
from uuid import uuid4

from app.core.errors import ApplicationError


class FileSystemStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ApplicationError(400, "INVALID_STORAGE_KEY", "Ubicación documental inválida")
        return path

    def put_bytes(self, content: bytes, suffix: str) -> dict:
        key = f"{uuid4().hex}{suffix}"
        path = self.resolve(key)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return {"storage_key": key, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}

    async def put_upload(self, upload, maximum: int) -> dict:
        key = f"{uuid4().hex}.upload"
        path = self.resolve(key)
        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("xb") as stream:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > maximum:
                        raise ApplicationError(413, "UPLOAD_TOO_LARGE", "El archivo supera el tamaño permitido")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if size == 0:
                raise ApplicationError(400, "EMPTY_UPLOAD", "El archivo adjunto está vacío")
            return {"storage_key": key, "sha256": digest.hexdigest(), "size_bytes": size}
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def read_bytes(self, key: str) -> bytes:
        return self.resolve(key).read_bytes()
