# Validación histórica

Para el despliegue, consultar [validación Linux directo](native-validation.md). Para las nuevas capacidades del asistente, consultar el registro del 22 de octubre de 2026 al final de esta página. Los registros anteriores no acreditan por sí solos la instalación actual.

# Validación de la implementación

Ejecutada el 22 de septiembre de 2026 (hora de México). Estado: aplicación funcional local; sustitución operativa de Office Scripts pendiente de certificar.

| Comprobación | Resultado |
|---|---|
| Backend completo: motor, exportación, API, worker, persistencia, autorización y Foundry | 198 pruebas aprobadas |
| Integración SQL Server real | 1 prueba omitida: falta conexión a una base de pruebas corporativa |
| Angular | 11 pruebas aprobadas y compilación de producción correcta |
| Calidad Python | Ruff aprobado; 57 versiones verificadas; pip check correcto |
| Migraciones | Upgrade/downgrade SQLite, comparación con metadata y DDL SQL Server offline aprobados |
| Contratos | OpenAPI generado con 21 rutas y 17 esquemas |
| Contenedores e infraestructura | Configuración Compose y manifiestos revisados; imágenes y despliegue no ejecutados |

La prueba con API y worker como procesos separados recibió dos ASC sintéticos y completó el mensual y el anual automático. Ambos produjeron dos tablas, tres filas, una advertencia de calidad y cero errores. Se descargaron los dos Excel. La evidencia local se conserva en `.data/qa-ui`, fuera del control de versiones. La aplicación de uso comienza vacía.

En navegador se verificaron dashboard conectado, navegación, formulario mensual, diseño de escritorio y consola sin errores. La automatización del selector de archivos quedó bloqueada; el envío se verificó por API y por pruebas de Angular, sin afirmar una prueba completa de carga mediante navegador.

Las pruebas cubren reintentos, conflicto entre publicaciones, aislamiento por ámbito, roles, validación JWT, cargas multipart sin Content-Length, ZIP malicioso, fechas, texto con ceros iniciales, deduplicación, limpieza de documentos sin referencia y consultas anuales contra resultados inmutables. El adaptador Foundry utiliza el SDK real con transporte simulado en las pruebas; no se llamó al servicio corporativo.

La salida JUnit del backend está en `.data/test-results/backend.xml`. Los tests usan carpetas temporales y datos sintéticos; no modifican los Excel entregados.

Antes del cambio operativo quedan cuatro comprobaciones externas: paridad con los ASC/ZIP y scripts originales; SQL Server real y volumen de producción; Entra ID/roles; Foundry y la infraestructura aprobada por IT. Las diferencias provisionales están en [compatibility.md](compatibility.md), y el despliegue en [deploy/README.md](../deploy/README.md).

## Proveedores acumulativos — 15 de octubre de 2026

Implementación operativa local en `/suppliers`, integrada en la publicación mensual y en su resultado. Cada mes solicita automáticamente las listas nacional y extranjera. Si falta una decisión, conserva un borrador con los proveedores y registros de esa publicación; al resolverla finaliza automáticamente las dos descargas. Un mes posterior no altera el borrador previo. Las solicitudes y los reportes son idempotentes y los reportes listos permanecen inmutables.

| Comprobación | Resultado |
|---|---|
| Regresión de backend afectado: proveedores, API, worker, publicación, reproceso, eliminación, seguridad, persistencia y rangos | 136 aprobadas; 1 omitida por no disponer de conexión SQL Server de pruebas |
| API y flujo mensual después del ajuste de concurrencia inicial | 7 aprobadas |
| API después de optimizar los contadores acumulativos | 3 aprobadas |
| Angular completo, incluido el reporte mensual automático | 108 pruebas aprobadas en 15 suites |
| Producción frontend, Ruff y contrato de dependencias Python | Correctos; 59 versiones exactas verificadas |
| Migraciones locales | `20261015_0002` y `20261015_0003` aplicadas; 71 tablas verificadas |
| Contrato HTTP | OpenAPI regenerado con las rutas de catálogo, revisiones, evidencia, equivalencias, solicitudes y reportes |
| Listas iniciales exportadas | 44 nacionales y 206 extranjeros; todas las columnas, filas, valores, orden y estatus conciliados con las fuentes |
| Validación visual | Ambas hojas renderizadas y revisadas; pantalla real ES/EN, contadores, cuatro pestañas y descargas verificadas |

El caso de tres meses **Johnson Electric → Johnson Eletric → Johnson Eletric** valida la coincidencia probable, la decisión explícita de mismo proveedor, la equivalencia reutilizada en el tercer mes y las dos listas automáticas. Otras pruebas comprueban la rama de proveedor nuevo, toda la fila amarilla, la transición a Sin modificación, la conservación de proveedores sin movimientos, la inmutabilidad de descargas antiguas y la exclusión de altas posteriores en un reporte anterior pendiente.

La evidencia virtual verifica cruces de 505/507/501, RFC del contribuyente, autorizaciones IMMEX, fuentes de otro periodo o pedimento, confirmaciones manuales, evidencia de un mes anterior, retiro al sustituir/eliminar fuentes y ausencia de resurrección de evidencia inicial sustituida. Las consultas y descargas se probaron con Reader y con otro ámbito; los cambios requieren permisos de operación y registran auditoría.

La inicialización privada conserva los 250 proveedores originales y su primer reporte. La evidencia del anual se incorporó una sola vez: el catálogo actual contiene 259 proveedores (9 altas extranjeras claras) y 122 identidades agrupadas pendientes por contradicciones o datos incompletos. Sus decisiones de negocio no fueron inventadas. La carga anual no crea publicaciones mensuales ficticias. Los [hallazgos de las fuentes](supplier-source-validation.md) y el [flujo de uso](suppliers.md) detallan la procedencia y las reglas.

La ejecución de la suite general detectó además **seis fallos preexistentes ajenos a proveedores** en exportación numérica/identificadores y detección del catálogo de números de parte. Se reprodujeron los mismos seis en una copia aislada de `HEAD c7dc8fb15acae1718d2bd1dec9320040f5861a16` preparada con `git archive`, sin modificar el árbol de trabajo. La copia obtuvo 30 pruebas y 15,043 subpruebas aprobadas; el JUnit privado se conserva en `.data/supplier-before/baseline-supplier-regression.xml`. No se alteró esa lógica como parte de proveedores.

## Asistente: consultas, archivos y cambio de modelo — 22 de octubre de 2026

Ampliación en `feature/foundry-agent-setup`, sobre `2f99ed96d013963fb1f696fa2b3de1d6a05b493e`. Los datos de prueba son sintéticos y Azure está simulado; no se usó la clave de la captura ni se hizo inferencia contra el proyecto corporativo.

| Comprobación | Resultado |
| --- | --- |
| Foundry, autenticación/configuración, consultas, reportes, seguridad, persistencia y PDF del dashboard | 165 aprobadas; 1 omitida por falta de SQL Server de pruebas |
| Backend completo | 480 aprobadas, 15,043 subpruebas aprobadas, 1 omitida; persisten los seis fallos preexistentes detallados abajo |
| Frontend completo | 122 pruebas aprobadas en 18 suites |
| Compilación Angular de producción | Correcta, 1.02 MB inicial; no se añadieron dependencias |
| Ruff en Python modificado, Prettier en componentes y modelos del chat, `git diff --check` | Correctos |
| Migración aditiva | SQLite `0003 → 0004` conserva mensajes y documentos; paridad con metadata y ciclo completo de migraciones aprobados |
| Contrato HTTP | OpenAPI regenerado, 49 rutas; respuestas de mensajes, historial, adjuntos y uso tipadas |
| Seguridad de archivos | XLSX conserva tipos, identificadores y ceros; fórmulas/enlaces de datos se escriben como texto; descargas privadas y limpieza ante fallo verificadas |
| Nuevo deployment | `gpt-6-luna` identificado en la captura y contrastado con documentación de Microsoft; llamada real, calidad de respuestas y cuota pendientes en la red corporativa |

Las pruebas específicas incluyen: sumas de 125 filas frente a una vista previa de dos; libro con 120 filas completas y hoja agregada; pagos `21` y `21.0` como misma categoría; cobertura de tablas y meses; rechazo de periodos ajenos o sin publicar, SQL no permitido, columnas desconocidas, mezcla de monedas, valores inválidos y exceso de tamaño; fechas numéricas de Excel; PDF ES/EN; recuperación de historial y adjuntos; aislamiento entre autores incluso dentro del mismo ámbito; uso de tokens acumulado por ronda; actualización de modelo/versión con respaldo y sin cambiar `.env` cuando falla la verificación. El renderer del chat presenta tablas sin ejecutar HTML o enlaces del modelo.

Los seis fallos de la suite general se reprodujeron sin esta mejora, en un checkout aislado de `2f99ed9`: dos aserciones de exportación (`test_export_native_measures_dates_and_counts_preserves_identifiers_monthly_and_annual`, `test_numeric_export_keeps_invalid_and_overprecision_values_without_coercing_to_zero`), el conteo antiguo del catálogo de PN, dos subcasos de alias (`1616-5YY3237(ALT)` y `MATERIAL OVERHEAD`) y el reconocimiento de tokens del catálogo. La suite general no está totalmente aprobada. El exportador de ejecuciones y el diccionario privado no se modificaron en esta entrega.

La [guía del asistente](assistant-corporate.md) define los pasos de actualización y aceptación contra datos conocidos. Quedan pendientes el nuevo modelo real, SQL Server y Entra/servidor de producción; la prueba SQLite no los sustituye.

## Chat: eliminación de conversaciones y lectura — 22 de octubre de 2026

- Backend afectado: 177 pruebas aprobadas y una omitida por no disponer de SQL Server de pruebas. Incluye informes reales XLSX/PDF con Foundry simulado, permisos, historial, API/worker, autenticación local, persistencia y cobertura mensual.
- Las pruebas de borrado verifican autor y ámbito (también para administradores), aislamiento de otras conversaciones, conservación de datos fuente, auditoría sin contenido del chat, rollback de la transacción, descarga revocada, archivo bloqueado y reintento idempotente. Una conversación eliminada durante inferencia no se puede recrear por una respuesta o herramienta tardía.
- Frontend completo: 127 pruebas aprobadas en 18 suites. Revisión final: 23 aprobadas en las tres suites de chat, formato y API, incluidas dos pruebas adicionales del DELETE autenticado y de los controles/confirmación en inglés.
- Compilación de producción: correcta; bundle inicial de 1.03 MB. No se añadieron dependencias ni se cambiaron el modelo, sus instrucciones o los contratos de herramientas de Foundry.
- OpenAPI: 50 rutas; comparación estructural que acredita que el único cambio de contrato es el nuevo DELETE de conversación. No se requiere una migración de esquema.
- Ruff y `git diff --check`: aprobados.

La comprobación del frontend cubre el DOM, cancelación/confirmación, errores, bloqueo de envíos duplicados, teclado, tablas y enlaces de archivos verificados. Queda pendiente revisar visualmente escritorio y móvil en el navegador corporativo: no había navegador instalado y la descarga del navegador de pruebas no pudo completarse. No se afirma una revisión visual real ni se modificaron políticas del equipo del usuario. SQL Server, Entra, concurrencia real de varias instancias y retención/borrado en Azure quedan pendientes del entorno corporativo. Estas pruebas no hacen inferencia real en Foundry ni modifican datos corporativos.

## Memoria personal persistente — 22 de octubre de 2026

La memoria se implementa en la base de DataStage, con edición explícita por autor/ámbito. No usa el Memory Store de Foundry, extracción automática de conversaciones ni entrenamiento continuo. La versión registrada del agente y sus herramientas permanecen iguales; el adaptador añade orientación de uso y, cuando hay notas activas, un bloque acotado de datos de usuario.

| Comprobación | Resultado |
| --- | --- |
| Backend afectado: memoria, Foundry, informes, API/worker, seguridad, autenticación local, cobertura y persistencia | 201 aprobadas; una integración SQL Server omitida |
| Revisión final del contexto enviado a Foundry y memoria después de ajustar la orientación de uso | 63 aprobadas |
| Frontend completo: chat, panel Memoria, Recordar, permisos, descargas y secciones existentes | 137 aprobadas en 19 suites |
| Migración `20261022_0004` → `20261022_0005`, downgrade de prueba y paridad con metadata | Aprobadas en SQLite; 75 tablas; conversaciones previas conservadas |
| DDL SQL Server | Compila todas las tablas/índices; los textos Unicode contemplan pares UTF-16 |
| Frontend de producción | Compilación correcta; bundle inicial de 1.03 MB; sin dependencias nuevas |
| Contrato HTTP | 51 rutas; sólo API de memoria y contador de notas incluidas añadidos |
| Calidad | Ruff, Prettier y `git diff --check` aprobados |

Se verificaron persistencia tras reiniciar y en otro chat, aislamiento por usuario y ámbito también para administradores, edición, desactivación sin borrado, eliminación con control de versión, rechazo de sobrescrituras desde pestañas antiguas, rollback, límites y Unicode. Las notas no se aceptan desde el cuerpo de mensajes ni habilitan herramientas prohibidas. Se auditan cantidades y versiones sin copiar el contenido; el historial conserva el número de notas incluidas, no una copia automática del bloque de memoria.

En el DOM se verificaron la revisión de una nota propuesta, cancelación sin escrituras, guardado explícito, rechazo de mensajes largos sin truncarlos, confirmación de borrado, desactivación, conflictos y controles ES/EN. La confirmación de cómo el modelo real aplica preferencias, la revisión visual en el navegador corporativo y SQL Server/Entra reales quedan pendientes. No se hicieron llamadas de inferencia al proyecto corporativo ni cambios en infraestructura de producción. La función no certifica que el modelo siga siempre cada preferencia: requiere las pruebas de aceptación de la guía del asistente.

## Descripciones de KPI y referencias de hojas — 22 de octubre de 2026

- Frontend completo: **143 pruebas aprobadas en 20 suites**. Las nueve pruebas
  focalizadas de presentación/procedencia también pasan.
- Compilación Angular de producción correcta: bundle inicial de **1.03 MB**.
- Prettier en TypeScript/SCSS modificados y `git diff --check`: correctos.
- DOM ES/EN: ocho KPI con descripciones; fuente visible con «Detalles» cerrado y
  al ver tablas; referencias por indicador/moneda en la comparativa mensual;
  cruce 558 al buscar PN; referencias 701/501 en rectificaciones; actividad
  general atribuida a todas las hojas procesadas.
- Exportación PNG: se comprueba que dibuja la referencia de hojas en la imagen.
  Los códigos y cruces se contrastaron con el agregador y `part_taxes.py`.

La revisión visual en el navegador corporativo queda pendiente: este entorno no
tiene un navegador instalado. No se cambiaron cálculos, API, base, dependencias
ni configuración Foundry; estas pruebas no hacen inferencia real ni certifican
SQL Server/Entra o un despliegue productivo. La correspondencia de hojas y las
reglas de conversión se documentan en `docs/analytics.md`.

## Asistente: cruces de tablas y cálculos personalizados — 22 de octubre de 2026

Implementado sobre `0c293c9` en `feature/foundry-agent-setup`. Se amplían las
especificaciones de `query_data` y `create_excel` y las instrucciones registradas;
se conservan once herramientas, el modelo configurado y las fuentes de negocio.

| Comprobación | Resultado |
| --- | --- |
| Backend afectado: cruces, reportes, Foundry, autenticación/configuración local, cobertura, memoria, seguridad, API/worker y persistencia | **233 aprobadas; 1 omitida** por falta de SQL Server de pruebas |
| Ruff en todos los Python modificados y `git diff --check` | Correctos |
| Excel combinado real con datos sintéticos | 125 filas completas, resumen calculado, números y fechas nativos, texto literal, fuentes y diagnóstico verificados con openpyxl |
| Esquema y dependencias | Sin migraciones ni dependencias nuevas; contrato HTTP conservado |
| Configuración Foundry | Registro/validación de la definición actual probados con Azure simulado; es necesario registrar una nueva versión con `--upgrade-local` |

Se comprueban relaciones de 551 con 501 y de 557 con 551/501, aislamiento por
ámbito, mes y ejecución activa frente a versiones retiradas, claves compuestas,
filas sin coincidencia, rechazo de claves incompletas o duplicadas y ausencia de
totales inflados al repetir importes de una tabla de menor detalle. El control
de repeticiones se aplica al conjunto filtrado completo, también entre grupos
distintos y en columnas calculadas. Se permite reutilizar el tipo de cambio por
importe base, pero se rechazan tipos de cambio iguales a cero o negativos.

Las pruebas cubren seis operadores numéricos, cálculos encadenados, filtros,
agrupación y orden, precisión calculada de 15 dígitos, división por cero y datos
ausentes sin inventar ceros ni totales parciales, monedas incompatibles, límite
combinado de filas, columnas/alias desconocidos y rechazo de SQL, fórmulas o
código como expresiones. La evidencia del chat y el manifiesto del Excel
conservan las tablas y diagnósticos; el manifiesto une las fuentes de todas las
hojas del libro. Los esquemas de herramientas siguen cerrados y estrictos.

No se ejecutó inferencia ni se modificó el proyecto corporativo. Quedan pendientes
el registro de la nueva versión y una pregunta de aceptación con las fuentes
reales en la red corporativa, además de SQL Server/Entra y el servidor reales.
No se modificó el frontend ni se repitió su suite por este cambio de backend.
Los seis fallos generales preexistentes registrados anteriormente no quedan
resueltos ni se declara una aprobación de toda la suite del repositorio.
