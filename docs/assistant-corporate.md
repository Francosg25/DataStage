# Asistente corporativo de DataStage

El chat consulta los datos publicados del usuario, calcula resultados verificables y genera archivos reales. El modelo interpreta la solicitud y explica los resultados; las consultas y los archivos se ejecutan en Python dentro de DataStage. Se conservan las métricas y reglas de negocio del dashboard.

## Qué puedes pedir

| Petición | Resultado |
| --- | --- |
| ¿Qué meses publicados tengo en 2025? | Inventario completo de meses, sin deducirlos del rango anual |
| ¿Qué proveedores facturaron más en mayo? | Consulta 505 con sumas USD por proveedor, calculadas sobre toda la selección |
| Crea un Excel de mayo y junio de 2025 con pedimento, patente, aduana y fecha de pago | Hoja de detalle 501 con las columnas solicitadas |
| Añade otra hoja con el total de facturas y valor en dólares por proveedor | Segunda hoja 505 agregada; 505 y 501 mantienen su propio nivel |
| Genera un PDF con los KPI de septiembre de 2026 en USD | Informe de análisis con las gráficas y fuentes del dashboard |
| Compara importaciones, exportaciones, IGI e IVA de dos meses | Cálculos de análisis existentes, con moneda, formas de pago y cobertura explícitas |
| ¿Qué significa FP21? | Explicación apoyada en extractos de las guías aprobadas disponibles |

Los ejemplos requieren los periodos y tablas indicados. Si faltan, el asistente debe informar la limitación y solicitar los datos necesarios. La pregunta siguiente puede referirse a la anterior; el backend conserva los mensajes y envía los últimos 20 como contexto. El historial recupera hasta los últimos 100 mensajes. No hay memoria ilimitada.

## Datos, cálculos y Excel

- `describe_data` enumera las 26 tablas registradas y, para una tabla, sus columnas, tipos y unidades. No revela tablas de identidad, configuración, conversaciones o credenciales.
- `query_data` recibe una especificación cerrada: tabla, periodos, columnas, filtros AND, agrupaciones, métricas y orden. Los identificadores de tabla y columna se resuelven contra el catálogo; no se acepta SQL, código, rutas o identidades del modelo.
- Las versiones se seleccionan una sola vez, con ámbito del usuario, estado publicado y pertenencia mensual. Se exige cobertura de la tabla en cada periodo solicitado. Una tabla ausente no se convierte en un cero.
- Los cálculos se realizan sobre todas las filas seleccionadas, hasta 50,000 filas de origen por consulta y 24 meses. Si se excede el límite se rechaza la consulta; no se presentan totales parciales. Los filtros se aplican dentro de esa selección acotada: si un mes por sí solo supera el límite, reducir sólo el texto del filtro no elimina ese límite.
- La vista previa del chat contiene como máximo 100 resultados. Los campos `matchedSourceRows`, `totalResultRows`, `previewLimited` y `complete` distinguen filas de origen, resultados y muestra.
- Se admiten conteo de filas, conteo distinto, suma, promedio, mínimo y máximo. Una suma de dinero no omite valores numéricos inválidos. El total en moneda extranjera exige agrupar o filtrar la moneda. Para conversiones fiscales y métricas oficiales se utiliza `get_analytics`, que comparte la lógica del dashboard.
- Cada hoja utiliza una sola tabla de origen. No se realizan cruces arbitrarios entre 505/551 o entre 510/557/702 que multipliquen o sumen niveles distintos. Los cruces nuevos requieren una relación de negocio implementada y validada.
- El Excel contiene hasta cinco hojas solicitadas y una hoja adicional de fuentes: consulta, periodos, ejecución, versión y número de filas. Se exportan los resultados completos; no sólo la vista previa del modelo.
- El libro tiene un límite conjunto de 500,000 celdas y 20 MiB. No se truncan resultados para cumplirlo. Los valores que no caben en una celda se rechazan.
- Los importes y medidas válidos son celdas numéricas; las fechas válidas son fechas Excel. Los identificadores como pedimento, factura, patente y fracción conservan texto y ceros iniciales. Los códigos de catálogo numéricos se escriben como números con su formato de ceros. Los valores inválidos o con más precisión de la que Excel conserva se mantienen como texto y se contabilizan en la hoja de fuentes.
- El contenido proveniente de proveedores y documentos se escribe como texto literal: no se convierte en fórmula, enlace o programa ejecutable.

## Conversación, archivos y permisos

Las conversaciones, evidencias, archivos y el uso reportado se conservan en la base y el almacenamiento documental de DataStage. Sólo el mismo autor y ámbito pueden recuperar el historial o descargar sus archivos generados. Conocer un identificador de documento o compartir un ámbito no concede acceso a otra conversación. Las acciones y descargas quedan auditadas con la identidad actual.

Las dos tablas nuevas de la migración `20261022_0004` son aditivas: `agent_message_details` y `agent_artifacts`. Los mensajes, documentos y datos de negocio anteriores permanecen. Los reportes se guardan como instantáneas; su manifiesto conserva las versiones usadas. El respaldo de la aplicación debe incluir la base y el directorio documental compartido. La política corporativa de retención debe contemplar también estas copias generadas.

El chat presenta tablas y formato básico sin ejecutar HTML del modelo. Los botones de descarga utilizan identificadores devueltos por el backend, no enlaces inventados en la respuesta. Los archivos normales de una ejecución continúan en su descarga existente.

Generar un reporte no requiere habilitar las acciones de consolidación o reproceso. Esas acciones mantienen sus permisos y consentimiento por mensaje; permanecen deshabilitadas durante esta puesta en marcha.

## Actualizar la instalación local y cambiar el modelo

Conserva el proyecto, tenant, autenticación y configuración actuales. La captura del despliegue del 22 de octubre de 2026 muestra `gpt-6-luna` con estado `Succeeded`. El nombre de deployment se usa tal cual; no se utiliza la clave API de la captura. La clave expuesta debe rotarse en Foundry.

1. Detén la API con Ctrl+C y actualiza el código en `feature/foundry-agent-setup`, conservando los cambios de tu checkout mediante el procedimiento Git habitual.
2. En el perfil local SQLite de desarrollo, el arranque de la API crea las dos tablas nuevas automáticamente. No se modifican columnas de tablas existentes. Si tu base local ya está gestionada por Alembic, también puedes aplicar la migración desde `backend`, con el intérprete instalado:

```cmd
..\.venv\Scripts\python.exe -m alembic upgrade head
```

Si la base local fue creada inicialmente con `create_all` y todavía no está gestionada por Alembic, utiliza el arranque normal. No borres la base ni ejecutes un `stamp` sin comprobar previamente su esquema y seguir la guía de migración. En producción la migración es obligatoria y se ejecuta con una identidad distinta de los servicios, según `linux-direct.md`. La prueba de migraciones usa una base temporal, nunca la base corporativa del usuario.

3. Registra una versión nueva con las once herramientas, verifica su definición y actualiza sólo el modelo y la versión en `backend/.env`:

```cmd
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --upgrade-local --model "gpt-6-luna"
```

El comando guarda un respaldo de `.env`, conserva la habilitación actual, la autenticación, la base, el almacenamiento y las demás opciones. Primero crea y comprueba la nueva versión; sólo después cambia el archivo local. Si falla la comprobación, `.env` permanece intacto. Puede quedar una versión remota creada pero no seleccionada. No repitas el comando después de un resultado correcto: cada ejecución registra otra versión.

Este paso no hace inferencia del modelo; no confirma por sí solo la llamada real ni la cuota disponible. Si expira la sesión corporativa, ejecuta `python -m app.modules.foundry.setup --login` con el mismo intérprete y reintenta el paso que falló. No se requieren Azure CLI ni cambios de políticas.

4. Si el asistente estaba deshabilitado, usa `--enable-local`. Si ya estaba habilitado, conserva ese estado. Inicia la API con el comando habitual y reinicia/actualiza el frontend para cargar la nueva interfaz. El worker no cambia en esta entrega.

```cmd
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Desde `frontend`: `npm.cmd start`. No se añadieron dependencias. La configuración de producción debe registrar y fijar la misma versión con su identidad de servicio, sin autenticación interactiva.

## Tokens y verificación real

Una pregunta del chat puede ejecutar varias inferencias: planificación, consulta de herramientas y respuesta. El uso de entrada, salida y llamadas se suma para esa respuesta y se muestra bajo **Uso del modelo**. Los tokens de razonamiento y de entrada en caché son desgloses, no cantidades que deban sumarse otra vez al total. Si Azure no reporta métricas completas, el chat indica **No disponible**.

La cifra del chat no es una factura: no incluye solicitudes fallidas sin respuesta, reintentos de transporte no reportados ni otros servicios. El importe se verifica en Azure Cost Management. El máximo de salida se configura con `DATASTAGE_FOUNDRY_MAX_OUTPUT_TOKENS` (predeterminado 4000 por llamada); no es un presupuesto monetario ni el total máximo de tokens de una conversación. `--check`, `--upgrade-local` y las pruebas simuladas no hacen inferencia. Las preguntas de aceptación siguientes sí consumen modelo.

Después del cambio prueba una conversación nueva, paso a paso:

1. `¿Qué meses publicados tengo de 2025?` Debe conservar mayo y junio si son los únicos publicados.
2. `Genera un Excel de mayo y junio de 2025 con pedimento completo, patente, aduana y fecha de pago.` Abre la descarga y revisa las fechas y las fuentes.
3. `Crea un Excel de facturas de mayo de 2025: una hoja con proveedor, número de factura y valor en dólares; otra con el total en dólares por proveedor.` Compara el detalle completo y la suma con una consulta conocida.
4. `Genera un PDF de los KPI de mayo de 2025 en USD.` Contrasta las cifras con el dashboard con esos mismos filtros.
5. Recarga la página, recupera la conversación y descarga el mismo archivo. Comprueba que otra identidad no pueda abrirlo.

Los tests automatizados prueban las consultas, seguridad, tipos XLSX, PDF, persistencia, migración y contratos con Azure simulado. La exactitud lingüística, selección de herramientas, latencia, cuota, conectividad privada y comportamiento de `gpt-6-luna` deben validarse con el deployment real; SQLite no certifica SQL Server. No se afirma equivalencia total con ChatGPT ni aprendizaje automático continuo.

Referencias oficiales: [herramientas por function calling](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling), [capacidades GPT-6](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure#gpt-6), [costos de Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs).
