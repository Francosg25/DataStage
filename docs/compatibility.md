# Contrato de compatibilidad DataStage

Estado: **implementación ejecutable y pruebas sintéticas; migración no certificada**. Los Excel de abril y enero–agosto 2026 son referencias de salida. Faltan los ZIP/ASC exactos y los Office Scripts que los generaron para comparar cada fila y regla sin inferencias.

## Reglas implementadas

El motor procesa texto por pipes, conserva identificadores como texto, añade trazabilidad, construye `PedimentoCompleto`, unifica esquemas por encabezado normalizado y exporta las 26 tablas oficiales en el orden solicitado. El anual filtra periodos, ordena por año/mes/nombre y vuelve a alinear filas contra el esquema final. Las fechas originales se conservan junto con la interpretación válida; las inválidas generan advertencias.

Fechas compactas `yyyyMMdd` y `yyyyMMddHHmmss`, año bisiesto, límites 1900–2100, exclusiones `TipoFecha`, horas y AM/PM tienen pruebas explícitas. Las fechas se guardan sin conversión de huso horario. La salida Excel se verifica por valores, tipos de celda, estilo, tablas, filtros, nombres y paneles congelados; no por igualdad de bytes ZIP.

## Decisiones provisionales que necesitan el script original

| Tema | Comportamiento actual | Cierre necesario |
|---|---|---|
| Fecha ambigua `04/05/2026` | DMY por defecto; MDY configurable; advertencia `AMBIGUOUS_DATE`. | Confirmar orden legado. |
| Año de pedimento | Primera fecha válida de la lista configurada, después otras fechas y por último el periodo. | Confirmar prioridad exacta de fechas. |
| Encoding ASC | UTF-8 con BOM opcional por defecto; Windows-1252 configurable, sin fallback silencioso. | Confirmar encoding de las fuentes. |
| Encabezados equivalentes dentro de un archivo | Archivo `ERROR`, para evitar descartar valores ambiguos. Entre archivos se unifican. | Aceptar esta validación o aportar regla de conflicto. |
| Encabezados vacíos intermedios o reservados de trazabilidad | Archivo `ERROR`. Los vacíos finales se eliminan. | Confirmar que las fuentes no dependen de otra regla. |
| Duplicado exacto de archivo | Ingesta omite contenido repetido con mismo hash, periodo y código, y registra advertencia. | Confirmar tratamiento de archivos renombrados. |
| Duplicación por llave de negocio | No se aplica sin llave certificada por tabla. `PedimentoCompleto` no es llave universal. | Entregar reglas específicas por tabla. |
| Control anual | Nueve columnas y detalle por archivo/consolidado según la solicitud. El Excel anual entregado tiene cinco columnas y ocho filas de resumen mensual. | Diferencia pendiente de aceptación funcional. |
| Mensajes de control | Se usan los mensajes del requerimiento y mensajes explícitos de consolidación. | Comparar puntuación, conteos y estados exactos con scripts. |
| Tablas desconocidas | Se incluyen después de las oficiales; persistencia específica pendiente de catálogo. | Aprobar alta y columnas del nuevo tipo. |

Lista preferente de fechas configurada para la API: `FechaPagoReal`, `FechaValidacionPagoR`, `FechaPago`, `FechaOperacion`, `FechaRecepcionPedimento`. Cada ejecución conserva su configuración; un cambio posterior requiere reprocesar en una nueva versión.

## Contadores y controles

`receivedFiles` cuenta todas las entradas recibidas, incluidos los duplicados omitidos por ingesta. `processedFiles` cuenta archivos aceptados con encabezados, incluso si no tienen filas. `skippedFiles` cuenta archivos vacíos, sin encabezados, excluidos por periodo y duplicados omitidos. `failedFiles` cuenta archivos con `ERROR`; la suma de los tres coincide con `receivedFiles`. `processedTables` cuenta tablas aceptadas. `sheets` incluye `Control_Proceso`.

En el control mensual, las columnas por archivo son las de negocio, incluido `PedimentoCompleto` cuando procede. El consolidado incluye las tres columnas de trazabilidad. El control anual incluye trazabilidad en ambos conteos. Las advertencias de calidad por sí solas no cambian `OK` a `WARNING`; la presencia de errores de archivo sí lo hace.

La publicación es versionada. Una falla técnica no sustituye una versión vigente. Los resultados Excel y el consolidado anual se generan desde fuentes registradas; los Excel de salida nunca se usan como motor de cálculo.

Cada consulta por ejecución anual lee su resultado JSON inmutable para respetar los encabezados, valores y opciones de fecha de esa versión. El consolidado basado en meses referencia sus fuentes exactas y no duplica las filas mensuales en SQL. Los archivos creados por un intento fallido sólo se eliminan cuando puede confirmarse que SQL no los referencia; ante una caída de SQL se conservan y se revisan mediante reconciliación fuera del procesamiento.

## Comparación de salidas

Desde `backend`, con las dependencias del lock instaladas:

```bash
python -m app.cli.compare_workbooks generado.xlsx referencia.xlsx --report ../.data/comparacion.json
```

El comando compara hojas y su orden, encabezados, valores y tipos de celdas, fechas nativas, ceros iniciales y el contenido de `Control_Proceso`. Devuelve código 0 si coincide, 1 si encuentra diferencias y 2 ante un error. El reporte muestra ubicaciones y tipos sin valores sensibles por defecto; `--include-values` añade vistas previas al archivo local, `--max-differences 100` limita el detalle conservando el conteo total y `--max-value-characters 120` limita las vistas previas. Trata `None` y texto vacío como equivalentes, ignora estilos y compara las fórmulas como texto, sin recalcularlas. Las pruebas del exportador validan estilos por separado. El comparador ayuda a revisar diferencias; no certifica la migración sin las fuentes y scripts originales.

## Evidencia necesaria para autorizar el cambio operativo

1. Emparejar cada ZIP/ASC de referencia con su script, periodo y Excel esperado.
2. Ejecutar ambos motores con la misma entrada y comparar código/orden de tablas, encabezados, filas, valores, fechas, pedimentos, trazabilidad, controles y contadores.
3. Registrar cada diferencia con archivo, fila, columna, valor esperado, valor obtenido y decisión del dueño funcional.
4. Validar SQL Server real, reintentos, concurrencia, recuperación, volumen, Entra y antivirus en TEST.
5. Autorizar el corte únicamente tras coincidencia o aprobación explícita de cada diferencia.
