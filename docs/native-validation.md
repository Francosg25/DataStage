# Validación de instalación nativa — 20 de octubre de 2026

Base conservada: `PostSCSTH`, commit `3933379f742a4d7ecc039c8d4c957acc8d7d68c6`.
Rama de trabajo: `feature/linux-direct-no-antivirus`.

## Verificado en el entorno de desarrollo Linux

- Python **3.13.16**, 60 versiones exactas del lock, `pip check` y `check_dependency_lock.py`: correctos. No se cambiaron locks ni dependencias de negocio.
- Node **24.13.1** real, Angular Core **21.2.25**, CLI/build **21.2.24**, Rollup **4.63.4**, esbuild **0.28.2**: comprobación de engines y carga/ejecución de binarios correctas.
- Compilación Angular producción con Node 24.13.1: correcta. **101/101 pruebas frontend** correctas.
- **39/39 verificaciones nuevas**: producción sin scanner, cifrado SQL, identidad de migración separada, upload/worker/exportación sin comandos externos, documentos conservados, limpieza de temporales, rechazo de paquetes alterados/rutas/enlaces y aislamiento de configuración local.
- Suite completa Python antes de añadir las tres últimas pruebas de herramientas: **419 passed, 6 failed, 1 skipped**, 15043 subtests passed. Los **mismos seis fallos** ya estaban presentes antes de editar el repositorio (baseline: 384 passed, 6 failed, 1 skipped). Se retiró una prueba específica de antivirus y se añadieron 39 comprobaciones; las tres últimas cubren activación/fallo de migración con systemd simulado y presencia de todas las plantillas.
- Suite focalizada final (despliegue, seguridad, API/worker y herramientas): **101/101 passed** con Python 3.13.16.
- Ruff backend y scripts/deploy (E4/E7/E9/F), `git diff --check`, sintaxis Bash: correctos.
- `systemd-analyze verify`: sintaxis/dependencias de las cuatro unidades correctas al sustituir únicamente el ejecutable por uno disponible en el host de pruebas. Las rutas productivas no existen en este entorno y el gestor systemd no se ejecutó como sistema de producción.

- Arranque real del supervisor con Python 3.13/Node 24.13.1: API, worker y frontend listos. Carga ZIP sintética, publicación, exportación Excel, stop/start, recuperación de la misma ejecución y descarga idéntica: correctos. Diez documentos preservados por SHA-256; un proceso independiente sobrevivió a stop. Durante esta prueba se corrigió una falsa detección de puerto ocupado por TIME_WAIT al reiniciar en Linux.
- Paquete `2026.10.20-rc1`: 124 archivos de código/assets; inspección de manifest y exclusión de mapas/diccionario/datos empresariales. Instalación real en directorio temporal desde wheelhouse Linux, `--no-index --only-binary=:all:`, venv nuevo, `pip check` e importación API/worker correctos. No se activaron servicios corporativos.

## Fallos preexistentes, no ocultados ni corregidos en este cambio de despliegue

1. `test_export_native_measures_dates_and_counts_preserves_identifiers_monthly_and_annual`.
2. `test_numeric_export_keeps_invalid_and_overprecision_values_without_coercing_to_zero`.
3. `test_catalog_covers_complete_codes_in_supported_contexts`.
4. Subtest catálogo: `1616-5YY3237(ALT)`.
5. Subtest catálogo: `MATERIAL OVERHEAD`.
6. `test_all_catalog_codes_are_found_as_whole_tokens_inside_descriptions`.

Afectan expectativas de celdas numéricas y reconocimiento de algunos valores del catálogo, no la eliminación del scanner. No se modifican las reglas de exportación ni se limpia el diccionario del usuario para hacer pasar pruebas. La suite completa/CI sigue señalando esos fallos y debe revisarse antes de promover a producción. La prueba de integración SQL Server se omite porque no se proporcionó `DATASTAGE_TEST_SQLSERVER_URL`.

## Pendiente con TI y el equipo corporativo real

- Ejecutar `datastage.cmd doctor/start/status/logs/stop` en Windows 10/11 con Python autorizado, OneDrive y sus políticas. La implementación Windows usa Job Objects, pero no se ha ejecutado Windows aquí.
- Instalar con la distribución/arquitectura Linux destino y su wheelhouse real. Validar Nginx con `nginx -t` y el certificado/CA aprobados; el binario Nginx no está disponible aquí.
- SQL Server/ODBC18 reales: TLS, migraciones iniciales/incrementales, grants separados, inserciones, concurrencia, leases y restauración. El DDL y pruebas SQLite no certifican SQL Server.
- Entra real: tenant, redirect URI, audiencia, scope, roles y usuarios por región.
- Arranque al reiniciar el servidor, reinicio ante fallos de servicios, límites/espacio, journald y monitoreo.
- Restauración coherente de SQL, documentos y catálogos; pruebas de carga y aceptación con datos aprobados.
- Foundry solo si se habilita: red privada, identidad y endpoint. Permanece opcional/desactivado por defecto.

No se ejecutaron cambios de infraestructura productiva ni se modificaron protecciones corporativas.
