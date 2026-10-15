"""Corrige los tipos del Excel y añade su regeneración, con respaldo local."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4


def git_read(target, *args):
    return subprocess.check_output(
        ["git", "-C", str(target), *args], text=True, encoding="utf-8", stderr=subprocess.STDOUT,
    ).strip()


def apply(target, check=False):
    target = Path(target).expanduser().resolve()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    if not (target / "backend/app/main.py").is_file() or not (target / "frontend/package.json").is_file():
        raise ValueError("La carpeta indicada no es la raíz de DataStage.")
    if Path(git_read(target, "rev-parse", "--show-toplevel")).resolve() != target:
        raise ValueError("La carpeta indicada debe ser la raíz del repositorio.")
    branch = git_read(target, "branch", "--show-current")
    if branch != "Mejoras_Graficas":
        raise ValueError(f"No se aplicó ningún cambio. Rama actual: {branch}. Se requiere Mejoras_Graficas.")
    planned = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        destination = (target / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not destination.is_relative_to(target):
            raise ValueError("El paquete contiene una ruta no válida.")
        original = destination.read_bytes()
        if "payload" in entry:
            source = package / entry["payload"]
            proposed = source.read_bytes()
            if hashlib.sha256(proposed).hexdigest() != entry["sha256"]:
                raise ValueError(f"El paquete está incompleto o alterado: {relative}")
            unchanged = original.replace(b"\r\n", b"\n").removeprefix(b"\xef\xbb\xbf") == proposed
        else:
            text = original.decode("utf-8-sig").replace("\r\n", "\n")
            proposed_text = text
            for patch in entry["patches"]:
                old, new = patch["before"], patch["after"]
                if new in proposed_text:
                    if proposed_text.count(new) != 1:
                        raise ValueError(f"Se encontró un bloque repetido en {relative}. No se modificó ningún archivo.")
                    continue
                if proposed_text.count(old) != 1:
                    raise ValueError(
                        f"{relative} tiene una versión diferente a la prevista. "
                        "No se modificó ningún archivo. Comparte ese archivo para adaptar la corrección."
                    )
                proposed_text = proposed_text.replace(old, new, 1)
            unchanged = proposed_text == text
            newline = "\r\n" if b"\r\n" in original else "\n"
            proposed = proposed_text.replace("\n", newline).encode("utf-8")
            if original.startswith(b"\xef\xbb\xbf"):
                proposed = b"\xef\xbb\xbf" + proposed
        if not unchanged:
            planned.append((relative, destination, original, proposed))

    print(f"Carpeta: {target}\nRama: {branch}\nArchivos por corregir: {len(planned)}")
    if check:
        print("Comprobación correcta. No se modificó ningún archivo.")
        return None
    if not planned:
        print("La corrección ya está aplicada. Reinicia backend y worker antes de regenerar los Excel.")
        return None
    backup = target.parent / ("Respaldo_Excel_Tipos_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    backup.mkdir()
    for relative, _, original, _ in planned:
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(original)
    (backup / "respaldo.json").write_text(json.dumps({
        "project": str(target), "branch": branch, "files": [str(item[0]) for item in planned],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    changed = []
    try:
        for relative, destination, _, proposed in planned:
            temporary = destination.with_name(destination.name + "." + uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(proposed)
                temporary.replace(destination)
                changed.append((relative, destination))
            finally:
                temporary.unlink(missing_ok=True)
    except OSError:
        failures = []
        for relative, destination in reversed(changed):
            try:
                shutil.copy2(backup / relative, destination)
            except OSError:
                failures.append(str(relative))
        print("La aplicación falló. Respaldo disponible en: " + str(backup))
        if failures:
            print("No se pudo restaurar automáticamente: " + ", ".join(failures))
        else:
            print("Se restauraron los archivos afectados.")
        raise
    print(f"\nCambios aplicados. Respaldo: {backup}")
    print("Reinicia backend, worker y frontend con los comandos habituales.")
    print("En el detalle del proceso usa Regenerar Excel y después Descargar Excel.")
    print("No se ejecutó git add, commit, pull, push ni cambio de rama. No se instalaron dependencias.")
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--check", action="store_true", help="Verificar sin copiar archivos")
    arguments = parser.parse_args()
    try:
        apply(arguments.project, arguments.check)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
