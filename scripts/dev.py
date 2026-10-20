"""Local supervisor: no installs, no PowerShell, no killing processes by name/PID files.

A loopback control socket authenticates stop/status with an instance token.
The supervisor owns child handles. Windows Job Objects contain all descendants.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.data'
STATE = DATA / 'local-supervisor.json'
LOGS = DATA / 'logs'
ROLES = ('api', 'worker', 'frontend')


def local_environment():
    env = os.environ.copy()
    env.update(DATASTAGE_ENVIRONMENT='development', DATASTAGE_AUTH_MODE='development',
               DATASTAGE_DATABASE_URL='sqlite:///' + (DATA / 'datastage.db').as_posix(),
               DATASTAGE_DOCUMENT_ROOT=str(DATA / 'documents'),
               DATASTAGE_CORS_ORIGINS='["http://127.0.0.1:4200","http://localhost:4200"]',
               PYTHONUNBUFFERED='1')
    if (DATA / 'analytics-reference.json').is_file():
        env['DATASTAGE_ANALYTICS_REFERENCE_FILE'] = str(DATA / 'analytics-reference.json')
    return env


def node_exe():
    candidate = os.environ.get('DATASTAGE_NODE') or shutil.which('node')
    if not candidate or not Path(candidate).is_file():
        raise RuntimeError('Node no encontrado; define DATASTAGE_NODE con el ejecutable autorizado.')
    return str(Path(candidate).resolve())


def request(action, state=None):
    state = state or json.loads(STATE.read_text())
    if state.get('root') != str(ROOT):
        raise RuntimeError('El registro pertenece a otra carpeta; no se detuvo ningún proceso.')
    with socket.create_connection(('127.0.0.1', state['port']), timeout=3) as client:
        client.sendall(json.dumps({'token': state['token'], 'action': action}).encode() + b'\n')
        reply = json.loads(client.makefile('rb').readline(65536))
    if reply.get('token') != state['token']:
        raise RuntimeError('Identidad del supervisor no coincide; no se detuvo ningún proceso.')
    return reply


def save_state(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state))
    temp.chmod(0o600)
    temp.replace(STATE)


def windows_job():
    """Assign supervisor BEFORE spawning anything; all children inherit this job.

    Closing the only handle kills only this job, including spawned descendants.
    Corporate job restrictions are reported; no policy is changed or bypassed.
    """
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [('ProcessTime', ctypes.c_int64), ('JobTime', ctypes.c_int64),
                    ('Flags', w.DWORD), ('MinWorking', ctypes.c_size_t), ('MaxWorking', ctypes.c_size_t),
                    ('ActiveLimit', w.DWORD), ('Affinity', ctypes.c_size_t),
                    ('Priority', w.DWORD), ('Scheduling', w.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
    class Extended(ctypes.Structure):
        _fields_ = [('Basic', Basic), ('IO', IO), ('ProcessMemory', ctypes.c_size_t),
                    ('JobMemory', ctypes.c_size_t), ('PeakProcess', ctypes.c_size_t), ('PeakJob', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = Extended()
    limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel.CloseHandle(handle)
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle)
        raise RuntimeError('Windows impidió crear el grupo de procesos. Usa el inicio manual autorizado.')
    return kernel, handle


def stop_children(children):
    if os.name == 'nt':
        # The job handle is closed at the very end; no taskkill /IM or PID reuse risk.
        return
    for p in children.values():
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
    for p in children.values():
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()


def healthy(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def serve():
    state = json.loads(STATE.read_text())
    children, logs, job = {}, [], None
    try:
        if os.name == 'nt':
            job = windows_job()
        env = local_environment()
        node = node_exe()
        commands = {
            'api': ([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-proxy-headers'], ROOT / 'backend'),
            'worker': ([sys.executable, '-m', 'app.worker'], ROOT / 'backend'),
            'frontend': ([node, str(ROOT / 'frontend/node_modules/@angular/cli/bin/ng.js'), 'serve', '--host', '127.0.0.1', '--port', '4200', '--proxy-config', 'proxy.conf.json'], ROOT / 'frontend'),
        }
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen(4)
            server.settimeout(0.5)
            state.update(port=server.getsockname()[1], pid=os.getpid())
            save_state(state)
            for role, (command, cwd) in commands.items():
                stream = (LOGS / f'{role}.log').open('ab', buffering=0)
                logs.append(stream)
                children[role] = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                    stdout=stream, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt')
            stopping = False
            deadline = time.monotonic() + 120
            ready = False
            while not stopping:
                if any(p.poll() is not None for p in children.values()):
                    raise RuntimeError('Un proceso terminó; revisa api.log, worker.log y frontend.log.')
                if not ready:
                    ready = healthy('http://127.0.0.1:8000/health/ready') and healthy('http://127.0.0.1:4200/')
                    if time.monotonic() > deadline:
                        raise RuntimeError('Tiempo de arranque agotado. Revisa los logs.')
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue
                with client:
                    client.settimeout(2)
                    try:
                        message = json.loads(client.makefile('rb').readline(4096))
                        if not secrets.compare_digest(str(message.get('token', '')), state['token']):
                            continue
                        if message.get('action') not in ('status', 'stop'):
                            continue
                        stopping = message['action'] == 'stop'
                        current_ready = ready
                        if message['action'] == 'status' and ready:
                            current_ready = healthy('http://127.0.0.1:8000/health/ready') and healthy('http://127.0.0.1:4200/')
                        response = {'token': state['token'], 'ready': current_ready,
                                    'processes': {r: {'pid': p.pid, 'running': p.poll() is None} for r, p in children.items()}}
                        client.sendall(json.dumps(response).encode() + b'\n')
                    except (OSError, ValueError):
                        continue
    finally:
        stop_children(children)
        if STATE.exists() and json.loads(STATE.read_text()).get('token') == state['token']:
            STATE.unlink()
        for stream in logs:
            stream.close()
        if job:
            # This terminates our supervisor too; keep it after cleanup and response.
            job[0].CloseHandle(job[1])


def check_dependencies():
    if not (3, 12) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError('Usa un Python corporativo autorizado 3.12 o 3.13.')
    node = node_exe()
    env = local_environment()
    subprocess.run([node, str(ROOT / 'scripts/check_node.cjs')], check=True, env=env)
    subprocess.run([sys.executable, '-c', 'import fastapi,uvicorn,sqlalchemy,alembic,xlsxwriter,openpyxl,xlrd,azure.ai.projects'], check=True, env=env)
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True, env=env)
    print('Python:', sys.executable)
    print('Node:', node)
    return env, node


def start():
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        try:
            reply = request('status')
            print('Ya está iniciado:', {k: v for k, v in reply.items() if k != 'token'})
            return
        except (OSError, ValueError, KeyError):
            raise RuntimeError('Registro sin respuesta. Consulta logs y verifica procesos; no se matará ni reemplazará ningún proceso.') from None
    # Exclusive file also serializes concurrent starts. A stale file is never used to kill a PID.
    state = {'root': str(ROOT), 'token': secrets.token_hex(32), 'port': 0}
    with STATE.open('x') as stream:
        json.dump(state, stream)
    STATE.chmod(0o600)
    launched = False
    try:
        for port in (8000, 4200):
            with socket.socket() as probe:
                # TIME_WAIT from our prior instance is not an active listener.
                option = socket.SO_EXCLUSIVEADDRUSE if os.name == 'nt' else socket.SO_REUSEADDR
                probe.setsockopt(socket.SOL_SOCKET, option, 1)
                probe.bind(('127.0.0.1', port))
        env, node = check_dependencies()
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'backend', env=env, check=True)
        subprocess.run([node, str(ROOT / 'frontend/scripts/sync-guides.mjs')], check=True)
        with (LOGS / 'supervisor.log').open('ab', buffering=0) as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_serve'], cwd=ROOT,
                env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=os.name != 'nt',
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS) if os.name == 'nt' else 0)
        launched = True
        for _ in range(150):
            time.sleep(1)
            if not STATE.exists():
                raise RuntimeError('El arranque falló; revisa .data/logs/supervisor.log y los logs de cada servicio.')
            try:
                if request('status').get('ready'):
                    print('DataStage: http://127.0.0.1:4200  |  Detener: datastage.cmd stop')
                    return
            except (OSError, ValueError, KeyError):
                pass
        try:
            request('stop')
        except (OSError, ValueError, KeyError):
            pass
        raise RuntimeError('No quedó listo; revisa los logs. Se solicitó detener solo esta instancia.')
    finally:
        if not launched:
            STATE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'logs', 'doctor', '_serve'])
    parser.add_argument('role', nargs='?', choices=[*ROLES, 'supervisor'], default='api')
    args = parser.parse_args()
    if args.action == '_serve':
        serve()
    elif args.action == 'start':
        start()
    elif args.action == 'doctor':
        check_dependencies()
    elif args.action == 'logs':
        path = LOGS / (args.role + '.log')
        print('\n'.join(path.read_text(errors='replace').splitlines()[-100:]) if path.exists() else 'Sin registros.')
    elif not STATE.exists():
        print('No hay una instancia registrada por este lanzador.')
    else:
        result = request(args.action)
        print(json.dumps({k: v for k, v in result.items() if k != 'token'}, indent=2))
        if args.action == 'stop':
            for _ in range(40):
                if not STATE.exists():
                    print('Instancia detenida; documentos conservados.')
                    return
                time.sleep(0.5)
            raise RuntimeError('Cierre en curso; conserva el registro y revisa los logs.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
