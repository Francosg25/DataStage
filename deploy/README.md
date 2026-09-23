# Despliegue DataStage

Los archivos de esta carpeta no han sido desplegados en infraestructura corporativa. Docker y Kubernetes deben ejecutarse con los servicios homologados por IT; Azure no se presupone habilitado.

## Imágenes

Desde la raíz del repositorio:

```bash
docker build -f deploy/Dockerfile.backend -t datastage-backend:local .
docker build -f deploy/Dockerfile.frontend -t datastage-frontend:local .
```

El backend usa Python 3.13/Debian 12, ODBC Driver 18 y `clamscan`. La instalación del driver sigue la [documentación Microsoft para Debian](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server). API: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers`. Worker: `python -m app.worker`. Ambos trabajan en `/app/backend`.

La imagen instala las versiones exactas de `backend/requirements.lock` y comprueba su coherencia con `pip check`. Este lock incluye dependencias de ejecución y prueba; no resuelve versiones nuevas durante el build. Los archivos `Dockerfile.*.dockerignore` limitan el contexto a las fuentes necesarias y evitan copiar `node_modules` del host sobre los módulos Linux instalados por `npm ci`. Los documentos de `.data`, entornos virtuales, secretos y caches no entran al contexto de estas imágenes.

Fija los digests de las imágenes aprobadas en CI antes de promover el mismo artefacto a TEST/PROD. Los tags de las imágenes base y `2022-latest` facilitan pruebas locales, pero no son una política de versiones para producción.

## Compose para integración con SQL Server

1. Copia `deploy/compose.env.example` a `deploy/compose.env` y completa contraseña SQL y los cuatro valores Entra.
2. Registra en Entra la redirección SPA `http://127.0.0.1:4200/login` y concede los roles DataStage necesarios. En cada ambiente registra igualmente su URL HTTPS terminada en `/login`.
3. Ejecuta desde la raíz:

```bash
docker compose --env-file deploy/compose.env -f deploy/compose.yaml up --build -d
docker compose --env-file deploy/compose.env -f deploy/compose.yaml logs -f api worker
```

La UI está en `http://127.0.0.1:4200`. Compose crea `DataStage`, aplica Alembic y comparte el volumen `documents` entre API y worker. El SQL Server 2022 Developer incluido es solo para desarrollo/integración; sus requisitos y licencia se describen en la [guía oficial de contenedores SQL Server](https://learn.microsoft.com/en-us/sql/linux/install-upgrade/quickstart-install-docker?view=sql-server-ver17). Requiere arquitectura y recursos compatibles con esa imagen.

El modo local sin Entra rechaza conexiones desde redes de contenedores; Compose utiliza Entra expresamente. La cuenta `sa` y `TrustServerCertificate=yes` del ejemplo sirven únicamente para este SQL aislado de integración. Producción usa cuentas limitadas, certificados verificados y una conexión corporativa externa.

```bash
# Detener conservando los volúmenes:
docker compose --env-file deploy/compose.env -f deploy/compose.yaml down
```

## Entra y configuración de producción

Define `DATASTAGE_AUTH_MODE=entra` y `DATASTAGE_ENVIRONMENT=production`. La API necesita tenant, client ID de la SPA, audiencia de API y scope delegado. Los tokens deben incluir los roles asignados: `Reader`, `Operator`, `Reprocessor`, `Auditor` o `Admin`. Cada despliegue fija su ámbito empresarial con `DATASTAGE_SCOPE_ID`; no se toma del cuerpo de las solicitudes.

El secreto `datastage-secrets` debe aportar `DATASTAGE_DATABASE_URL`, `DATASTAGE_ENTRA_TENANT_ID`, `DATASTAGE_ENTRA_CLIENT_ID`, `DATASTAGE_ENTRA_AUDIENCE` y `DATASTAGE_ENTRA_API_SCOPE`. Usa el gestor corporativo para poblarlo. La URL SQL lleva `Encrypt=yes&TrustServerCertificate=no` y el driver `ODBC Driver 18 for SQL Server`. Codifica caracteres especiales de usuario/contraseña en la URL. El secreto separado `datastage-migration-secrets` tiene las mismas claves y una cuenta SQL autorizada para DDL.

El comando antivirus recibe la ruta del archivo como argumento final sin shell. `clamscan` devuelve éxito únicamente con un análisis limpio; errores o ausencia de firmas bloquean la carga. IT debe mantener actualizado y legible el volumen `datastage-antivirus-signatures`, con `main.cvd`/`main.cld`, `daily.cvd`/`daily.cld` y demás firmas necesarias. La imagen no presume una base de firmas vigente.

## Kubernetes/AKS

Se suministran manifiestos editables, sin ejecutar su publicación. Requieren registro corporativo, SQL externo, almacenamiento RWX, secretos, firmas antivirus, clase Ingress, DNS y certificado `datastage-tls`. La cuenta de ejecución tiene permisos de lectura/escritura de negocio; la de migración añade DDL.

Configura en el entorno `NAMESPACE`, `SCOPE_ID`, `STORAGE_CLASS`, `BACKEND_IMAGE`, `FRONTEND_IMAGE`, `INGRESS_CLASS`, `PUBLIC_HOST` y `CORS_ORIGINS` (array JSON de URLs HTTPS permitidas). Los valores de imagen deben señalar los digests homologados. El renderizador rechaza variables ausentes y no incorpora secretos:

```bash
python deploy/render_manifests.py > deploy/rendered.yaml
python deploy/render_manifests.py --migration > deploy/migration-rendered.yaml
```

Orden de despliegue para IT: crear namespace, ConfigMap, PVC, secretos y certificado; ejecutar el Job de migración mediante `kubectl create`; esperar su terminación correcta; aplicar Deployments, Services e Ingress. El manifiesto de aplicación contiene todos los recursos salvo secretos, certificado y PVC de firmas. Las migraciones no se ejecutan al arrancar cada réplica. Un Job con `generateName` permite una ejecución nueva por release sin repetirla automáticamente.

Configura el controlador Ingress con límite de cuerpo que cubra el mayor de `DATASTAGE_MAX_UPLOAD_MB` y `DATASTAGE_MAX_FILE_MB`, más el contenido multipart, y timeout suficiente. Nginx usa 102 MB por defecto para admitir ASC de hasta 100 MB; la API mantiene los límites específicos de cada ruta. Ajusta ambos componentes si cambian esos valores. Las políticas de red deben permitir SQL Server, Entra/JWKS, DNS y los endpoints Foundry autorizados cuando se habilite. Ninguna salida libre es necesaria para consultas de negocio.

Las sondas `/health/live` y `/health/ready` corresponden a proceso y disponibilidad de API. Supervisa además retraso de la cola, reservas vencidas, duración de trabajos, fallos de exportación y espacio documental en Grafana o la plataforma corporativa. Define backup/restauración de SQL y documentos con retención, RPO/RTO y pruebas reales antes del corte.

Foundry está apagado inicialmente. Al habilitarlo, configura el proyecto y versión del agente; concede solo las herramientas necesarias y una identidad de carga aprobada. Su conectividad y permisos se verifican en TEST antes de activar comandos.

El registro de una nueva versión se hace explícitamente desde el backend con `python -m app.modules.foundry.setup --apply`, después de configurar `DATASTAGE_FOUNDRY_PROJECT_ENDPOINT`, `DATASTAGE_FOUNDRY_MODEL` y las credenciales Azure aprobadas. La aplicación no crea agentes automáticamente. Las llamadas usan Responses con `store=True` para continuar herramientas mediante `previous_response_id`; los mensajes enviados y resultados de herramientas quedan sujetos a la retención y residencia configuradas en Foundry. No se crean conversaciones remotas compartidas.

## Alcance de la validación

Se comprueban localmente el lock Python, las migraciones SQLite, la compilación del DDL SQL Server y el renderizado de manifiestos. `docker compose config` permite verificar Compose sin arrancar contenedores. La compilación efectiva de imágenes requiere un daemon Docker y acceso a los repositorios; SQL Server, Entra, Foundry, RWX, antivirus, Ingress y TLS se certifican en el entorno de integración. Ningún archivo de esta carpeta acredita por sí solo ese despliegue ni la paridad de negocio con los scripts anteriores.
