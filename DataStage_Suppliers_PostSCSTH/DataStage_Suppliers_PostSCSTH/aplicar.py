"""Apply the reviewed supplier patch with backups; no database is opened."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

PACKAGE = Path(__file__).resolve().parent

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")

def repository(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    for candidate in [Path.cwd(), PACKAGE, *PACKAGE.parents]:
        result = git(candidate, "rev-parse", "--show-toplevel")
        if result.returncode == 0:
            return Path(result.stdout.strip())
    from tkinter import Tk, filedialog
    window = Tk()
    window.withdraw()
    selected = filedialog.askdirectory(title="Selecciona la carpeta DataStage de tu rama PostSCSTH")
    window.destroy()
    if not selected:
        raise RuntimeError("No se selecciono la carpeta del proyecto")
    return Path(selected).resolve()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args()
    repo = repository(args.repo)
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    branch = git(repo, "symbolic-ref", "--short", "HEAD")
    if branch.returncode != 0 or branch.stdout.strip() != manifest["branch"]:
        raise RuntimeError("Selecciona el proyecto que tiene activa la rama " + manifest["branch"])
    patch = str(PACKAGE / "CAMBIOS.patch")
    if git(repo, "apply", "--reverse", "--check", patch).returncode == 0:
        print("Los cambios de este paquete ya estan aplicados.")
        return
    check = git(repo, "apply", "--check", patch)
    if check.returncode:
        raise RuntimeError("Los archivos no coinciden con la version revisada. No se modifico ningun archivo.\n" + check.stderr)
    for entry in manifest["files"]:
        path = Path(entry["path"])
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Ruta no valida en el paquete")
    backup = repo.parent / ("Respaldo_Suppliers_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6])
    backup.mkdir()
    previous = []
    for entry in manifest["files"]:
        source = repo / entry["path"]
        previous.append({"path": entry["path"], "existed": source.exists()})
        if source.exists():
            target = backup / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (backup / "archivos.json").write_text(json.dumps(previous, indent=2), encoding="utf-8")
    try:
        applied = git(repo, "apply", patch)
        if applied.returncode:
            raise RuntimeError(applied.stderr)
        for entry in manifest["files"]:
            digest = hashlib.sha256((repo / entry["path"]).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            if digest != entry["sha256"]:
                raise RuntimeError("No se pudo verificar " + entry["path"])
    except Exception:
        for entry in previous:
            target = repo / entry["path"]
            if entry["existed"]:
                shutil.copy2(backup / entry["path"], target)
            elif target.exists():
                target.unlink()
        raise
    print("Cambios aplicados en: " + str(repo))
    print("Respaldo: " + str(backup))
    print("Reinicia backend, worker y frontend con tus comandos habituales.")
    print("Abre Suppliers e importa las dos listas iniciales, si aun no estaban incorporadas.")
    print("Revisa LEEME.txt para las dependencias de lectura de Excel.")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
