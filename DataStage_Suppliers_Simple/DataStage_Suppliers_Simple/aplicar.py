"""Apply the supplier update using only Python's standard library."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
PACKAGE=Path(__file__).resolve().parent

def git(repo,*args):
    return subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True,encoding="utf-8",errors="replace")

def sha(content):
    return hashlib.sha256(content.replace(b"\r\n",b"\n")).hexdigest()

def repository(explicit):
    if explicit:return Path(explicit).resolve()
    for candidate in [Path.cwd(),PACKAGE,*PACKAGE.parents]:
        found=git(candidate,"rev-parse","--show-toplevel")
        if found.returncode==0:return Path(found.stdout.strip())
    try:
        from tkinter import Tk,filedialog
        window=Tk();window.withdraw()
        selected=filedialog.askdirectory(title="Selecciona la carpeta DataStage (PostSCSTH)")
        window.destroy()
    except ImportError:
        selected=input("Ruta completa de la carpeta DataStage: ").strip().strip('"')
    if not selected:raise RuntimeError("No se selecciono la carpeta del proyecto")
    return Path(selected).resolve()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--repo");args=parser.parse_args()
    repo=repository(args.repo)
    manifest=json.loads((PACKAGE/"manifest.json").read_text(encoding="utf-8"))
    branch=git(repo,"symbolic-ref","--short","HEAD")
    if branch.returncode or branch.stdout.strip()!=manifest["branch"]:
        raise RuntimeError("La carpeta seleccionada debe tener activa la rama "+manifest["branch"])
    entries=[];conflicts=[]
    for item in manifest["files"]:
        path=Path(item["path"])
        if path.is_absolute() or ".." in path.parts or path.parts[0] in {".git",".data",".venv","node_modules"}:
            raise RuntimeError("Ruta no valida en el paquete")
        target=repo/path;payload=PACKAGE/"archivos"/path
        if not payload.is_file() or sha(payload.read_bytes())!=item["sha256"]:
            raise RuntimeError("Paquete incompleto o alterado: "+str(path))
        if target.exists() and not target.is_file():raise RuntimeError("La ruta no es un archivo: "+str(path))
        current=sha(target.read_bytes()) if target.exists() else None
        if current!=item["sha256"] and current not in item["accepted"]:conflicts.append(str(path))
        entries.append((item,target,payload,current))
    if conflicts:raise RuntimeError("Hay cambios locales o una version diferente en estos archivos. No se modifico el proyecto:\n"+"\n".join(conflicts))
    changed=[entry for entry in entries if entry[3]!=entry[0]["sha256"]]
    if not changed:
        print("La actualizacion ya esta aplicada.");return
    backup=repo.parent/("Respaldo_Suppliers_"+datetime.now().strftime("%Y%m%d_%H%M%S_")+uuid4().hex[:6]);backup.mkdir()
    previous=[]
    for item,target,_,_ in changed:
        previous.append({"path":item["path"],"existed":target.exists()})
        if target.exists():
            dest=backup/item["path"];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,dest)
    (backup/"archivos.json").write_text(json.dumps(previous,indent=2),encoding="utf-8")
    try:
        for item,target,payload,_ in changed:
            crlf=target.exists() and b"\r\n" in target.read_bytes()
            content=payload.read_bytes().replace(b"\r\n",b"\n")
            if crlf:content=content.replace(b"\n",b"\r\n")
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        for item,target,_,_ in entries:
            if sha(target.read_bytes())!=item["sha256"]:raise RuntimeError("No se pudo verificar "+item["path"])
    except Exception:
        for entry in previous:
            target=repo/entry["path"]
            if entry["existed"]:shutil.copy2(backup/entry["path"],target)
            elif target.exists():target.unlink()
        raise
    print("Suppliers actualizado en: "+str(repo))
    print("Respaldo: "+str(backup))
    print("Reinicia backend, worker y frontend con tus comandos habituales.")
    print("En Suppliers, incorpora tus dos listas originales una sola vez.")
    print("Si ya estaban incorporadas, pulsa Actualizar listas.")

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("ERROR: "+str(error),file=sys.stderr);sys.exit(1)
