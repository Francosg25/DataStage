# DataStage: instalación directa en Linux

## Qué prepara cada persona

| Responsable | Una sola vez | Cada versión |
|---|---|---|
| Franco / equipo de aplicación | Probar en Windows y acordar con TI el dominio, alcance y roles | Probar, compilar Angular y generar un paquete con versión y SHA-256; entregar el mismo paquete a TEST y PROD |
| TI Linux / red | Servidor, Python, Nginx, systemd, cuentas de servicio, DNS, HTTPS, acceso de red y almacenamiento | Preparar la versión sin afectar la activa, coordinar respaldo, activar y revisar servicios |
| DBA | Base SQL Server vacía, certificados y dos identidades SQL separadas | Respaldo coordinado; revisar migraciones y recuperación |
| Administrador Entra | Aplicaciones SPA/API, scope delegado, roles y asignaciones | Validar acceso y permisos después de cada cambio de identidad |

No se requieren Docker, Docker Hub, WSL2 ni Kubernetes. El servidor no necesita Node ni npm: recibe HTML, CSS y JavaScript ya compilados. Nginx sirve estos archivos por HTTPS y pasa `/api/` a FastAPI, accesible únicamente en `127.0.0.1:8000`. API y worker usan la misma base y el mismo directorio documental. El worker consulta su cola SQL de forma independiente. Foundry está desactivado por defecto.

Si TI habilita Foundry, usar `DATASTAGE_FOUNDRY_AUTH_MODE=default` y una identidad de servicio autorizada. La sesión personal cifrada del piloto Windows solo funciona en desarrollo local y se rechaza en producción. Un Linux interno necesita la identidad que TI configure (por ejemplo, aplicación con certificado); no dispone de identidad administrada automáticamente. Ver [la guía Foundry](azure-foundry.md) y `deploy/linux/runtime.env.example`.

## 1. Requisitos que proporciona TI

- Linux con systemd y Nginx; Python **3.12 o 3.13**, con soporte `venv` y pip, aprobado para la distribución/arquitectura concretas. Python 3.13 es el objetivo local.
- `unixODBC` y **Microsoft ODBC Driver 18 for SQL Server** compatibles con ese Linux; CA corporativa y dependencias de OpenSSL, Kerberos (`libgssapi-krb5-2` en Debian o equivalente), libc y libstdc++ según la distribución. `pyodbc` instalado con pip **no incluye** este driver ni esas bibliotecas. No copiarlas desde Windows.
- TI instala paquetes desde sus repositorios aprobados y acepta las licencias del driver por su procedimiento. Referencia: https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
- SQL Server corporativo con base dedicada. DNS del servidor SQL debe coincidir con su certificado; la CA debe ser confiable. Conexión `Encrypt=yes&TrustServerCertificate=no`; no se usa `sa`. El validador de producción exige URL explícito con Driver 18, sin DSN ni `odbc_connect` que oculten opciones.
- Identidad SQL de ejecución: SELECT/INSERT/UPDATE/DELETE sobre tablas de negocio y SELECT sobre vistas/`alembic_version`, sin DDL ni administración del servidor. La identidad de migración es diferente, apunta a la misma base y dispone de CREATE/ALTER de tablas, índices, constraints y vistas. El DBA concede permisos mínimos según las migraciones; no se crean usuarios SQL automáticamente. La migración `20261022_0005` añade `agent_memory_profiles` y `agent_memories`; la identidad runtime necesita SELECT/INSERT/UPDATE/DELETE sobre esas dos tablas para las preferencias personales del asistente. No se conceden permisos DDL al runtime.
- Red: HTTPS desde usuarios hacia Nginx; desde servicios hacia SQL y los endpoints Entra de autenticación/JWKS. Foundry solo si se habilita. El puerto 8000 no se publica a la red.
- Certificado HTTPS y clave privada, DNS corporativo y renovación gestionados por TI. Ningún dominio o contraseña real está incluido.
- Espacio para documentos y temporales de cargas/exportación; dimensionar con volúmenes reales. La API mantiene el límite global de cuerpo y los límites específicos por ruta. Nginx permite 102 MiB con los límites predeterminados (ASC 100 MiB + multipart); ajustar ambos de forma coordinada si TI cambia los límites.
- Las políticas de SELinux/AppArmor, firewall, endpoint protection, proxy y certificados se conservan. TI habilita los permisos concretos que correspondan; no se desactivan protecciones.

## 2. Preparar y validar el paquete (equipo de aplicación)

En una máquina de build autorizada con Node **24.13.1** y Python 3.13, instalar dependencias **una vez** desde el repositorio corporativo configurado:

```cmd
REM Desde la raíz; usa tu Python autorizado o .venv\Scripts\python.exe
python -m pip install --no-deps -r backend\requirements.lock
python -m pip check
python scripts\check_dependency_lock.py
cd frontend
npm.cmd ci
npm.cmd test -- --watch=false
npm.cmd run build
cd ..
python -m pytest backend\tests scripts\tests
python scripts\build_release.py --version 2026.10.20.1
```

En Linux sustituir `npm.cmd` por `npm`. `scripts/ci.sh` automatiza las mismas verificaciones en un entorno aislado. Las pruebas completas de la rama base tenían fallos preexistentes; revisar [el informe](native-validation.md) antes de promover. La creación del paquete no equivale a aprobación de producción.

Resultado: `dist/datastage-2026.10.20.1.tar.gz` y `.sha256`. El nombre de versión es único: nunca sobreescribir uno ya instalado. El manifest enumera SHA-256 de cada archivo y el commit de origen; `workingTreeChanges=true` identifica builds con cambios locales. Para promover se debe construir desde un commit revisado y limpio. Entregar también el hash mediante un canal corporativo confiable: un checksum detecta cambios, no sustituye una firma o aprobación.

El paquete incluye backend, migraciones, lock Python, frontend compilado y scripts/guías Linux. **Excluye `.env`, `.data`, bases SQLite, ZIP/Excel/PDF empresariales, mapas de plantas, diccionario PN empresarial, `.venv`, node_modules y archivos históricos de parches.** No modificar el paquete entre TEST y PROD.

### Dependencias Python sin Internet en producción

Opción A: TI configura un archivo pip privado con el índice/CA corporativos; `release.py stage --pip-config /ruta/privada/pip.conf` utiliza ese archivo. No poner contraseñas en comandos ni en el paquete.

Opción B: en un Linux de preparación **del mismo sistema, arquitectura y versión Python que el destino**, descargar ruedas aprobadas (incluidas sus dependencias exactas):

```bash
python3.13 -m pip download --only-binary=:all: --no-deps -r backend/requirements.lock --dest wheelhouse
```

El índice/CA se configuran por TI. Validar `pip check` en un venv limpio instalado desde ese wheelhouse, guardar inventario/checksums y transferirlo por separado. El instalador usa `--no-index --only-binary=:all: --no-deps`: no compila extensiones ni busca paquetes fuera del wheelhouse. Si falta una rueda, TI la prepara en el entorno de build aprobado; no instalar compiladores ni resolver versiones nuevas silenciosamente en producción. El lock actual incluye herramientas de prueba y SDK opcional Foundry, pero no activa ese servicio.

## 3. Preparación inicial del servidor (TI)

Extraer los scripts del paquete aprobado en una carpeta de preparación y verificar su checksum **antes** de ejecutarlos. `prepare-host.sh` crea cuentas locales sin login, directorios y unidades; no instala paquetes del sistema, no inicia DataStage y no modifica protecciones corporativas:

```bash
sudo bash deploy/linux/prepare-host.sh
```

Estructura fija de esta entrega:

```text
/opt/datastage/releases/<version>/    código + frontend + venv exclusivo de esa versión
/opt/datastage/current               enlace a la versión activa
/etc/datastage/runtime.env           configuración compartida API/worker (root:root 0600)
/etc/datastage/migration.env         credencial SQL DDL (root:root 0600)
/var/lib/datastage/documents/        documentos persistentes (datastage:datastage 0750)
/var/lib/datastage/reference/        catálogos/mapas aprobados (root:datastage, solo lectura)
```

La cuenta Linux `datastage` ejecuta API y worker, sin privilegios de root. `datastage-migrate` ejecuta migraciones y no escribe documentos. El código pertenece a root y los servicios no pueden modificarlo. systemd lee los archivos secretos antes de cambiar de usuario: no ampliar el acceso de esas cuentas a `/etc/datastage`.

Completar los dos `.env` a partir de las plantillas, sin dejar `REPLACE_`. Las comillas y valores son compatibles con `EnvironmentFile` de systemd; no usar expansión `$VARIABLE`. Codificar usuario/contraseña para URL cuando contienen `@`, `:`, `%`, etc. Los secretos se gestionan por el proceso de TI, nunca mediante Git ni logs.

Provisionar **por separado y de manera privada** el catálogo `backend/app/modules/reporting/part_numbers.json` y los archivos `backend/app/resources/project-maps/` aprobados para la empresa, en `/var/lib/datastage/reference/`. No vienen en el paquete. Conservar exactamente su contenido y permisos de lectura para `datastage`. `DATASTAGE_PART_CATALOG_FILE` y `DATASTAGE_PROJECT_MAPS_ROOT` apuntan a estas ubicaciones. Esto conserva la detección de PN y los mapas sin distribuir datos empresariales con el código. No reemplazarlos durante actualizaciones. Las plantillas/listas de proveedores existentes permanecen en la base/documentos; no se reinicializan.

Entra mantiene los roles **Reader, Operator, Reprocessor, Auditor y Admin**, scope delegado y control por ámbito existentes. Registrar como redirect URI SPA `https://<dominio aprobado>/login`, configurar las cuatro variables Entra y asignar roles. La configuración pública se obtiene en `/api/v1/config`; no hay secretos Entra en el bundle ni que recompilarlo para cambiar el dominio. Ver `docs/entra-id.md` en el repositorio.

Completar `deploy/linux/nginx.conf.template`, instalarla según el empaquetado Nginx corporativo y ejecutar `sudo nginx -t`. Habilitar Nginx con systemd y cargar la configuración según el procedimiento TI. La raíz es `/opt/datastage/current/frontend`; nunca apuntarla al backend, documentos o archivos `.env`. Nginx necesita leer solo los archivos públicos del frontend. La API usa `--no-proxy-headers` deliberadamente; las cabeceras de un cliente no habilitan identidad local.

## 4. Instalar y activar una versión

El instalador se ejecuta bajo el procedimiento administrativo de TI. No se ha ejecutado sobre infraestructura productiva.

```bash
sudo python3 deploy/linux/release.py stage /ruta/datastage-2026.10.20.1.tar.gz \
  --sha256 <hash_aprobado> --python /ruta/python3.13 --wheelhouse /ruta/wheelhouse
# O --pip-config /ruta/privada/pip.conf en lugar de --wheelhouse.
```

`stage` verifica entradas y hashes, rechaza enlaces/rutas peligrosas, crea la versión y su venv, instala el lock y ejecuta `pip check`. No cambia `current` ni detiene la versión activa. En caso de fallo deja la carpeta inactiva para diagnóstico; usar una versión nueva o retirarla después de inspección, nunca reutilizar una instalación parcial automáticamente.

En ventana acordada: bloquear acceso de usuarios, detener API/worker y hacer respaldo SQL + documentos coherente (ver abajo). Después:

```bash
sudo python3 deploy/linux/release.py activate 2026.10.20.1 --backup-confirmed
```

La activación valida configuración, detiene los dos servicios, actualiza las unidades systemd desde el paquete revisado y ejecuta `datastage-migrate@<version>` con credencial separada, comprueba el esquema y almacenamiento con `datastage-check@<version>`, cambia `current` de forma atómica, arranca API/worker y comprueba readiness/estado. Si falla mantiene los servicios detenidos y muestra la versión anterior; **no ejecuta downgrade ni restaura datos automáticamente**. Nginx puede seguir mostrando la interfaz durante mantenimiento, pero las llamadas a la API no estarán disponibles; TI puede poner su página de mantenimiento.

Comprobar antes de abrir acceso: HTTPS, inicio de sesión Entra, todos los roles y restricciones por ámbito, carga ZIP sintética, procesamiento worker, Excel, auditoría, catálogo PN/mapas y permisos de archivos. Reiniciar el servidor de TEST y confirmar que API, worker y Nginx inician solos. La migración es un paso explícito; no se ejecuta en cada arranque del servidor.

## 5. Operación cotidiana

```bash
sudo systemctl status datastage-api datastage-worker nginx
sudo systemctl start datastage-api datastage-worker
sudo systemctl stop datastage-api datastage-worker
sudo journalctl -u datastage-api -u datastage-worker --since today
sudo journalctl -u datastage-worker -f
sudo journalctl -u datastage-migrate@2026.10.20.1.service
sudo journalctl -u datastage-check@2026.10.20.1.service
curl --fail http://127.0.0.1:8000/health/ready
```

systemd reinicia fallos con espera de cinco segundos y conserva logs en journald. TI configura retención/persistencia de journald y logs de Nginx. No registrar contenido de ASC, tokens o cadenas de conexión. Revisar cola y trabajos fallidos, espacio, leases vencidas y tiempos de exportación. Al reiniciar, el worker recupera trabajos con leases vencidas; no se borran documentos ni se repite un resultado ya confirmado.

## 6. Respaldo, actualización y recuperación

1. Restringir nuevas solicitudes y detener API/worker; no confiar solo en cerrar el navegador. Esperar cierre, comprobar estado y registrar versión/commit y revisión Alembic.
2. DBA respalda SQL Server con sus herramientas aprobadas; TI respalda **todos** los documentos, referencias y configuración cifrada con acceso restringido. Mantener correspondencia entre el punto SQL y los archivos. No incluir backups dentro de releases.
3. Instalar/activar la siguiente versión con el mismo proceso. No copiar `.data` de un desarrollador a producción ni reemplazar SQL con SQLite.
4. Si falla una actualización, consultar primero el log de migración. Alembic puede haber aplicado cambios: volver solo al código anterior requiere confirmar compatibilidad de esquema. Si no es compatible, restaurar **SQL y archivos del mismo respaldo**, restaurar configuración, unidades systemd y versión anterior; probar antes de abrir tráfico. No usar `alembic downgrade` como receta genérica.
5. Probar una restauración completa en TEST periódicamente. Los archivos huérfanos se inventarían con SQL disponible y sin trabajos activos; no borrar por extensión ni por antigüedad sin comprobar referencias.

Los UUID de almacenamiento son relativos a `DATASTAGE_DOCUMENT_ROOT`; mantener intactos nombres, tamaños y SHA-256. La actualización no mueve ni vacía esa raíz.

## 7. Retirada del antivirus integrado

La aplicación ya no ejecuta ClamAV/clamscan ni requiere firmas o variables `DATASTAGE_ANTIVIRUS_*`. Retirar esas variables antiguas de la configuración de DataStage; no desinstalar ni detener las protecciones del equipo/servidor.

El esquema revisado no tiene campos de escaneo ni estados de cuarentena: `StoredDocument.status=available` significa disponible, **no escaneado ni libre de virus**. Por eso no se necesita una migración de esquema ni se alteran documentos históricos. Ejecuciones que fallaron antes por `SCAN_UNAVAILABLE`/`SCAN_REJECTED` conservan su error/auditoría: un usuario autorizado puede reprocesarlas por el flujo existente después de actualizar; no se publican automáticamente ni se inventa una aprobación de seguridad.

Permanecen las validaciones de extensión y contenido, tamaños, entradas ZIP, métodos de compresión, rutas, enlaces, cifrado, ratio y volumen descomprimido, hashes y estructura ASC. Los archivos se interpretan como datos y nunca se ejecutan. Los temporales de escritura se eliminan ante fallos; los uploads incompletos se limpian. Esto no representa una certificación de ausencia de malware.

## 8. Diagnóstico rápido

- **502 / API no disponible:** `systemctl status`, `journalctl`, `/health/ready`; verificar `current`, `.venv`, ODBC y base migrada.
- **SQL TLS/login:** driver instalado y visible, CA, nombre certificado, red, URL codificado y permisos de runtime. No cambiar a `TrustServerCertificate=yes`.
- **403 Entra:** tenant/audience/scope/roles y asignaciones; no habilitar modo development en producción.
- **Worker sin progreso:** servicio activo, misma configuración/raíz, permisos, acceso SQL, cola y leases; revisar errores funcionales desde la UI.
- **Documentos/mapas ausentes:** verificar montaje persistente y referencias privadas, no regenerar una raíz vacía sobre los datos existentes.
- **Foundry 403 por red privada:** validar endpoint/VNet/DNS con TI; el resto de DataStage funciona con Foundry deshabilitado.
- **Dependencia Linux faltante:** usar wheelhouse correspondiente a ABI/arquitectura/distribución; completar ODBC y bibliotecas con TI.
