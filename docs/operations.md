# Operación y promoción

## Dependencias y CI

El lock Python se obtuvo de la `.venv` validada en Python 3.13 sobre Windows. Contiene ejecución y pruebas, con versiones exactas, sin rutas personales, paquetes editables ni credenciales. No incluye las herramientas de instalación (`pip`, `setuptools`, `wheel`). El mismo archivo alimenta desarrollo, CI e imagen Linux; las ruedas y bibliotecas nativas Linux deben verificarse durante el build corporativo. `pip check` impide continuar con dependencias incompletas.

Desde la raíz, con un entorno Python activado:

```bash
python -m pip install --no-deps -r backend/requirements.lock
python -m pip check
python scripts/check_dependency_lock.py
```

Las actualizaciones se realizan en un entorno de prueba aislado: cambiar el rango del proyecto cuando corresponda, resolver las versiones deseadas, ejecutar las pruebas y guardar nuevamente el conjunto congelado. Revisar el diff del lock antes de promoverlo; no regenerarlo automáticamente al iniciar la aplicación. El frontend utiliza `npm ci` y su `package-lock.json`.

`bash scripts/ci.sh` requiere Python 3.12/3.13, Node compatible con `frontend/package.json`, npm y acceso a los registros de paquetes. Ejecuta validación de dependencias, Ruff, pytest, pruebas Angular y compilación de producción. `DATASTAGE_BUILD_IMAGES=true` añade únicamente builds Docker locales. No hace `push`, `kubectl apply` ni publicación externa. JE Git debe configurar el disparador del pipeline en su plataforma corporativa.

## Migración y verificación del release

1. Respaldar SQL y el almacén documental según la política aprobada.
2. Promover las mismas imágenes verificadas mediante sus digests, sin reconstruir entre TEST y PROD.
3. Ejecutar `python -m alembic upgrade head` con la identidad de migración; comprobar `python -m alembic current`.
4. Arrancar API y worker con identidades de ejecución, configuración y volumen documental compartido.
5. Comprobar `/health/ready`, SSO, roles, carga de una fuente sintética y descarga del Excel. Verificar la auditoría y la actualización anual.

Un rollback de imagen no implica hacer automáticamente `alembic downgrade` ni borrar documentos. Revisar primero la compatibilidad de esquema y preservar las versiones ya publicadas. La migración inicial tiene downgrade para bases de pruebas; no es una estrategia de restauración de producción.

Alembic utiliza la misma configuración de base que API y worker: `DATASTAGE_DATABASE_URL`, después `backend/.env` y por último `.data/datastage.db` en la raíz. Un URL o conexión pasados explícitamente mediante la API de Alembic tienen precedencia, para pruebas y generación SQL offline. Ejecutar desde la raíz con `python -m alembic -c backend/alembic.ini ...` también carga el `.env` junto al archivo INI.

## SQL Server y archivos

`DATASTAGE_TEST_SQLSERVER_URL` debe apuntar a una base exclusiva para integración. La prueba de persistencia crea el esquema cuando está vacía y revierte sus inserciones; no usa una base operativa. El DDL revisable está en `backend/migrations/initial_sqlserver.sql`. Compilar ese SQL no sustituye ejecutarlo en la versión corporativa de SQL Server.

SQL y documentos deben respaldarse de forma coordinada. Los documentos tienen nombres internos opacos, tamaño y SHA-256 registrados. No borrar ZIP/ASC que aún sean fuentes de versiones mensuales o anuales. Para revisar archivos sin referencia, inventariar primero las claves del almacenamiento y compararlas con `StoredDocument`; considerar trabajos activos antes de aplicar cualquier política de retención.

Después de un fallo, el worker elimina únicamente los documentos creados por su propio intento cuya ausencia de referencias SQL puede confirmar. Si SQL no responde o la consulta no es concluyente, conserva los archivos. Una caída abrupta puede dejar archivos pendientes de reconciliación: revisar ese inventario fuera del procesamiento, con SQL disponible y respetando trabajos activos, antes de autorizar una eliminación.

Las consultas por identificador de consolidado anual leen el resultado JSON inmutable de esa ejecución, conservando sus encabezados y su política de fechas. Un anual basado en meses fija sus fuentes mediante `AnnualSource` y no inserta otra copia de esas filas mensuales en las tablas de negocio. El contrato API generado está en `contracts/openapi/datastage.v1.json`.

Supervisar cola pendiente, trabajos fallidos, reservas vencidas, espacio disponible, tiempos de procesamiento y exportación. Los errores API devuelven un identificador de correlación; los logs estructurados evitan incluir datos ASC y cuerpos de excepciones. La conectividad real, permisos de almacenamiento, actualización de firmas antivirus, recuperación de backups y pruebas de carga son requisitos del ambiente corporativo.

## Foundry

Configurar proyecto, despliegue de modelo, identidad y política de tratamiento de datos. `python -m app.modules.foundry.setup` muestra el contrato local; añadir `--apply` registra una nueva versión. Actualizar `DATASTAGE_FOUNDRY_AGENT_VERSION` con el valor devuelto y habilitar el módulo sólo después de validarlo en TEST. No se necesita habilitar comandos para consultar ejecuciones, datos, documentación o reportes existentes.

La API conserva el dueño y ámbito de cada conversación. `start_annual` y `reprocess_run` requieren autorización explícita de acciones y los roles correspondientes. La integración usa respuestas persistidas para continuar llamadas de herramienta: validar residencia y retención de esos datos en Foundry. Las pruebas locales usan transporte simulado y no acreditan acceso a Azure.
