# DataStage

## Análisis de operaciones

El dashboard está en `/analytics`: evolución mensual, comercio, contribuciones, selección aduanera, cobertura y comparación de meses. Incluye filtros, datos detrás de las gráficas, descarga CSV/PNG y cambio español/inglés. Consulta [definiciones y fuentes](docs/analytics.md).

El asistente comparte las métricas del dashboard mediante `get_analytics`. La [guía de Azure Foundry](docs/azure-foundry.md) también está disponible en `/foundry-guide`, desde la sección Asistente.

Aplicación Angular + FastAPI para cargar ZIP/ASC, procesar periodos mensuales, consolidar el año, consultar resultados y descargar Excel. La API y el worker comparten el motor Python y una base de datos. Los documentos se conservan fuera de la base, con hash y trazabilidad.

La ejecución local usa **SQLite únicamente para desarrollo**. El despliegue corporativo usa **SQL Server, Entra ID y antivirus obligatorio**. La equivalencia con Office Scripts aún requiere los ASC/ZIP y scripts originales; consulta [las decisiones de compatibilidad](docs/compatibility.md).

## Iniciar en Windows

Requisitos: Python 3.12 o 3.13, Node.js compatible con Angular 22 (22.22.3+, 24.15+ o 26+) y npm. Desde la raíz:

```powershell
.\scripts\start-dev.ps1
```

El script crea `.venv`, instala dependencias, aplica migraciones e inicia API, worker y frontend en ventanas ocultas. La identidad local solo admite conexiones desde la propia computadora. Abre [DataStage local](http://127.0.0.1:4200) o [contratos de la API](http://127.0.0.1:8000/docs).

```powershell
# Inicio posterior, con dependencias ya instaladas:
.\scripts\start-dev.ps1 -SkipInstall
# Node instalado fuera de PATH:
.\scripts\start-dev.ps1 -NodeExe 'C:\ruta\node.exe'
# Detener únicamente los procesos registrados por el lanzador:
.\scripts\stop-dev.ps1
```

Los logs quedan en `.data/logs`, la base en `.data/datastage.db` y los documentos en `.data/documents`. El script no borra resultados al detenerse. La interfaz inicia vacía y muestra información de las cargas reales.

## Inicio manual

Instala el backend y aplica migraciones una vez desde la raíz:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --no-deps -r backend/requirements.lock
python -m pip check
python scripts/check_dependency_lock.py
cd backend
python -m alembic upgrade head
```

En dos terminales con el entorno activado y directorio `backend`, ejecuta:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

```bash
python -m app.worker
```

En otra terminal, desde `frontend`:

```bash
npm ci
npm start
```

La configuración manual puede cargarse desde `backend/.env`, copiando [.env.example](.env.example). Los valores del entorno tienen precedencia. El lanzador Windows fija expresamente desarrollo local, SQLite y loopback.

[backend/requirements.lock](backend/requirements.lock) fija las 57 versiones Python verificadas, incluyendo herramientas de prueba; [frontend/package-lock.json](frontend/package-lock.json) fija el árbol npm. Desarrollo, CI e imagen backend utilizan el mismo lock. La aplicación se ejecuta desde el código fuente con `backend` como directorio de trabajo; no requiere instalación editable. El lock congela versiones, pero los hashes de paquetes y los digests de las imágenes base deben formar parte del proceso corporativo de promoción.

## Uso y verificación

Selecciona periodo, adjunta un ZIP con archivos `.asc` y consulta el avance. La publicación mensual solicita automáticamente el consolidado anual cuando `DATASTAGE_AUTO_ANNUAL=true`. Los resultados muestran archivos, tablas, incidencias y versiones; el Excel se descarga desde el resultado de la ejecución. Los identificadores conservan ceros iniciales y las fechas válidas se exportan como celdas de fecha.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
.\.venv\Scripts\python.exe -m ruff check backend
Set-Location frontend
npm test -- --watch=false
npm run build
```

Las pruebas SQL Server se habilitan con `DATASTAGE_TEST_SQLSERVER_URL` sobre una **base de pruebas exclusiva**; la prueba de persistencia crea el esquema si está vacía, revierte sus datos y no elimina la base. SQLite no certifica el comportamiento SQL Server. El pipeline genérico de [scripts/ci.sh](scripts/ci.sh) comprueba el lock, ejecuta Ruff y pytest, usa `npm ci`, ejecuta pruebas Angular y compila producción. Puede integrarse con JE Git sin asumir un proveedor de CI/CD; no publica imágenes ni despliega recursos. Los pasos de operación y actualización están en [docs/operations.md](docs/operations.md).

Para comparar un Excel generado con una referencia, desde `backend`: `python -m app.cli.compare_workbooks "generado.xlsx" "referencia.xlsx" --report "../.data/comparacion.json"`. Lee los archivos sin modificarlos y omite valores sensibles del reporte por defecto. Devuelve 0 si coincide, 1 si hay diferencias y 2 ante errores; [compatibilidad](docs/compatibility.md) detalla sus opciones y alcance.

## Despliegue corporativo

Los archivos ejecutables de despliegue y sus requisitos están en [deploy/README.md](deploy/README.md). API y worker usan la misma imagen y volumen documental compartido. Las migraciones se ejecutan como paso separado, con una identidad distinta de la identidad de ejecución. La publicación corporativa aún necesita endpoints, credenciales, DNS, TLS, almacenamiento, límites y aprobación de infraestructura reales.

Foundry permanece deshabilitado hasta configurar el proyecto, agente y credenciales. Desde `backend`, `python -m app.modules.foundry.setup` muestra la definición sin contactar Azure; `python -m app.modules.foundry.setup --apply` registra una versión en el proyecto configurado. Conserva la versión devuelta en `DATASTAGE_FOUNDRY_AGENT_VERSION`. Sus herramientas consultan las APIs autorizadas; los comandos requieren `DATASTAGE_ALLOW_AGENT_COMMANDS=true`, permiso del usuario y autorización de acciones en la petición. No se incluyen secretos ni datos empresariales en el repositorio.

## Código y evidencia

El motor y los módulos están en `backend/app/modules`, la persistencia en `backend/app/persistence` y las pantallas en `frontend/src/app/features`. El [contrato OpenAPI](contracts/openapi/datastage.v1.json) documenta solicitudes y respuestas. El [registro de validación](docs/validation.md) resume las pruebas ejecutadas y los controles corporativos pendientes.
