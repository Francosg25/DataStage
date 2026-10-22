# DataStage

## Proveedores

El catálogo acumulativo de proveedores nacionales y extranjeros está en `/suppliers`. Incluye revisión de identidades, equivalencias corregibles, evidencia y reportes Excel por instantánea. Consulta el [flujo de proveedores](docs/suppliers.md).

## Análisis de operaciones

El dashboard está en `/analytics`: evolución mensual, comercio, contribuciones, selección aduanera, cobertura y comparación de meses. Incluye filtros, datos detrás de las gráficas, descarga CSV/PNG y cambio español/inglés. Consulta [definiciones y fuentes](docs/analytics.md).

El asistente comparte las métricas del dashboard mediante `get_analytics`. La [guía de Azure Foundry](docs/azure-foundry.md) también está disponible en `/foundry-guide`, desde la sección Asistente.

El chat también consulta tablas publicadas, combina columnas mediante relaciones verificadas por pedimento o partida y realiza cálculos, filtros y agrupaciones. Genera Excel personalizados y PDF de KPI, conserva conversaciones y muestra descargas y uso del modelo. Consulta la [guía del asistente corporativo](docs/assistant-corporate.md) para activar las nuevas capacidades conservando el modelo y la autenticación configurados.

Aplicación Angular + FastAPI para cargar ZIP/ASC, procesar periodos mensuales, consolidar el año, consultar resultados y descargar Excel. La API y el worker comparten el motor Python y una base de datos. Los documentos se conservan fuera de la base, con hash y trazabilidad.

## Instalación principal: servidor Linux corporativo

**Nginx con HTTPS, API FastAPI y worker como servicios systemd, SQL Server corporativo y Microsoft Entra.** Foundry sigue siendo opcional. No se requieren Docker, Docker Hub, WSL2, Kubernetes ni antivirus integrado. Las protecciones corporativas del servidor no se modifican.

Consulta la [guía de instalación, actualizaciones y recuperación](docs/linux-direct.md): indica qué prepara TI una sola vez, cómo generamos un paquete versionado con Angular compilado y cómo activamos versiones sin reemplazar documentos ni configuración. El servidor no necesita Node.

## Iniciar en Windows

Node **24.13.1**, Python **3.13** y las dependencias previamente instaladas. Desde la raíz, en CMD:

```cmd
datastage.cmd doctor
datastage.cmd start
datastage.cmd status
datastage.cmd logs worker
datastage.cmd stop
```

Abre http://127.0.0.1:4200. El lanzador reutiliza dependencias, fuerza SQLite y acceso local, inicia API/worker/frontend y detiene exclusivamente su instancia. No depende de PowerShell ni cambia políticas. Permite seleccionar un Python corporativo autorizado mediante `DATASTAGE_PYTHON`; consulta [los pasos locales y el inicio manual](docs/windows-local.md).

Los locks `backend/requirements.lock` y `frontend/package-lock.json` conservan las versiones existentes. Verifica [lo probado y lo pendiente](docs/native-validation.md), incluyendo los fallos preexistentes de la rama base.

## Uso y verificación

Selecciona periodo, adjunta un ZIP con archivos `.asc` y consulta el avance. La publicación mensual solicita automáticamente el consolidado anual cuando `DATASTAGE_AUTO_ANNUAL=true`. Los resultados muestran archivos, tablas, incidencias y versiones; el Excel se descarga desde el resultado de la ejecución. Los identificadores conservan ceros iniciales y las fechas válidas se exportan como celdas de fecha.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
.\.venv\Scripts\python.exe -m ruff check backend
Set-Location frontend
npm.cmd test -- --watch=false
npm.cmd run build
```

Las pruebas SQL Server se habilitan con `DATASTAGE_TEST_SQLSERVER_URL` sobre una **base de pruebas exclusiva**; la prueba de persistencia crea el esquema si está vacía, revierte sus datos y no elimina la base. SQLite no certifica el comportamiento SQL Server. El pipeline genérico de [scripts/ci.sh](scripts/ci.sh) comprueba el lock, ejecuta Ruff y pytest, usa `npm ci`, ejecuta pruebas Angular y compila producción. Puede integrarse con JE Git sin asumir un proveedor de CI/CD; no publica ni despliega recursos. Los pasos de operación y actualización están en [docs/operations.md](docs/operations.md).

Para comparar un Excel generado con una referencia, desde `backend`: `python -m app.cli.compare_workbooks "generado.xlsx" "referencia.xlsx" --report "../.data/comparacion.json"`. Lee los archivos sin modificarlos y omite valores sensibles del reporte por defecto. Devuelve 0 si coincide, 1 si hay diferencias y 2 ante errores; [compatibilidad](docs/compatibility.md) detalla sus opciones y alcance.

## Despliegue corporativo

Los archivos ejecutables de despliegue y sus requisitos están en [deploy/README.md](deploy/README.md). API y worker usan la misma versión y directorio documental persistente compartido. Las migraciones se ejecutan como paso separado, con una identidad distinta de la identidad de ejecución. La publicación corporativa aún necesita endpoints, credenciales, DNS, TLS, almacenamiento, límites y aprobación de infraestructura reales.

Foundry permanece deshabilitado hasta configurar el proyecto, agente y credenciales. Desde `backend`, `python -m app.modules.foundry.setup` muestra la definición sin contactar Azure; `python -m app.modules.foundry.setup --apply` registra una versión en el proyecto configurado. Conserva la versión devuelta en `DATASTAGE_FOUNDRY_AGENT_VERSION`. Sus herramientas consultan las APIs autorizadas; los comandos requieren `DATASTAGE_ALLOW_AGENT_COMMANDS=true`, permiso del usuario y autorización de acciones en la petición. La entrega instalable excluye credenciales y archivos empresariales; las referencias privadas se provisionan aparte.

## Código y evidencia

El motor y los módulos están en `backend/app/modules`, la persistencia en `backend/app/persistence` y las pantallas en `frontend/src/app/features`. El [contrato OpenAPI](contracts/openapi/datastage.v1.json) documenta solicitudes y respuestas. El [registro de validación](docs/validation.md) resume las pruebas ejecutadas y los controles corporativos pendientes.
