# DataStage local en Windows: comandos sencillos

Desde la carpeta del proyecto, en CMD (también funciona llamando `.cmd` desde PowerShell):

```cmd
datastage.cmd doctor
datastage.cmd start
datastage.cmd status
datastage.cmd logs api
datastage.cmd logs worker
datastage.cmd logs frontend
datastage.cmd stop
```

Abre http://127.0.0.1:4200. `start` inicia API, worker y Angular, reutiliza dependencias y aplica las migraciones locales pendientes. No instala paquetes. La base permanece en `.data/datastage.db`, los documentos en `.data/documents` y los registros en `.data/logs`. No cambiar los nombres de estos archivos al actualizar.

Si TI autorizó un Python concreto (incluso si no está en `.venv`), indica su ruta **sin comillas dentro del valor**:

```cmd
set "DATASTAGE_PYTHON=C:\ruta autorizada\python.exe"
set "DATASTAGE_NODE=C:\ruta autorizada\node.exe"
datastage.cmd start
```

Si no indicas Python, usa `.venv\Scripts\python.exe` si existe; en otro caso `python` de PATH. No copia ni instala otro intérprete. El lanzador admite espacios en la ruta del proyecto/OneDrive. `doctor` comprueba versiones, importaciones Python, `pip check` y carga real de los binarios de Rollup/esbuild; no modifica políticas ni intenta saltarse un bloqueo.

Node **24.13.1** satisface el árbol bloqueado Angular 21.2, TypeScript 5.9, Vite y Rollup. Referencia: https://angular.dev/reference/versions. La compilación en Linux con ese Node no demuestra que Device Guard autorice los binarios en Windows: `doctor` lo verifica en el equipo real. Si una dependencia ya instalada es bloqueada, conservar el mensaje y pedir a TI el paquete aprobado; no desactivar protecciones.

## Preparar dependencias una sola vez

Con el intérprete/índice aprobados por TI, instalar el lock y ejecutar `pip check`. No hace falta activar un venv con PowerShell:

```cmd
"%DATASTAGE_PYTHON%" -m pip install --no-deps -r backend\requirements.lock
"%DATASTAGE_PYTHON%" -m pip check
cd frontend
npm.cmd ci
cd ..
```

Si usas `.venv`, sustituye `"%DATASTAGE_PYTHON%"` por `.venv\Scripts\python.exe`. Repetir instalación solo cuando cambien los locks y siguiendo las políticas TI. `npm.cmd` evita ejecutar `npm.ps1`. Los wrappers `scripts/start-dev.ps1` y `stop-dev.ps1` se conservan por compatibilidad, pero no son necesarios y ya no instalan paquetes.

## Cómo se detiene de manera segura

Un supervisor conserva los procesos que creó y recibe las órdenes por un socket de loopback con token por instancia. En Windows crea un Job Object **antes** de iniciar los hijos; cerrarlo detiene exclusivamente ese grupo, incluidos hijos de Angular. No ejecuta `taskkill /IM`, no termina procesos por nombre y no confía en un PID guardado que podría haber sido reutilizado. Si Windows impide el Job Object, falla sin cambiar la política: usa las tres terminales manuales.

No iniciar a la vez los scripts anteriores y el nuevo lanzador. Si los puertos 8000/4200 ya están ocupados, se informa sin matar el proceso existente. Un registro sin supervisor verificable no autoriza detener nada. Revisar `supervisor.log` y procesos propios; retirar **solo** `.data/local-supervisor.json` tras confirmar que aquella instancia ya terminó. Nunca borrar `.data` completa. Los inicios concurrentes se serializan por un archivo exclusivo.

Se fuerza SQLite, autenticación development y escucha 127.0.0.1 para esta instancia, aunque exista una configuración productiva en `.env`. El control de autenticación también rechaza clientes remotos. No compartir esta modalidad por IP/red. Foundry conserva su configuración opcional; no hace falta habilitarlo para procesar.

## Inicio manual de respaldo

Desde la raíz, en tres terminales distintas, usando el mismo Python autorizado y la configuración local de `.env.example`:

```cmd
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

```cmd
cd backend
..\.venv\Scripts\python.exe -m app.worker
```

```cmd
cd frontend
npm.cmd start
```

Ctrl+C en cada terminal para detenerlos. El supervisor no administra procesos iniciados manualmente.

## OneDrive y datos existentes

Mantén el proyecto dentro de OneDrive si así lo requiere la empresa. Marca documentos necesarios como disponibles localmente según la política corporativa, y no ejecutes dos copias de la misma base SQLite desde computadoras diferentes. No mover/copiar una base mientras API/worker escriben. Los bloqueos de sincronización se reportan: no se desactiva OneDrive ni el antivirus del equipo.

Antes de la primera actualización, detener los procesos y respaldar `.data`. Si una base antigua tiene tablas pero no historial `alembic_version`, el lanzador no la borra ni aplica `stamp head` a ciegas: la migración se detiene para revisar su esquema contra las revisiones existentes. No crear una base vacía para ocultar el error.
