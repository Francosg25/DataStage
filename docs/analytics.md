# Analytics de DataStage

## Fuentes y granularidad

El contrato de lectura es `GET /api/v1/reports/analytics/options` y `GET /api/v1/reports/analytics`. Ambos requieren acceso Reader y derivan el ámbito de la identidad autenticada. La API nunca acepta un ámbito del navegador.

`published` consulta las versiones mensuales activas mediante `Period.active_run_id`. No consulta anuales ni versiones reemplazadas. `reference` lee un snapshot privado, con `schemaVersion`, `scopeId`, nombres y SHA-256 de archivos. Las dos fuentes no se mezclan. El snapshot no está en los assets de Angular y no contiene RFC, CURP ni domicilios; retiene los campos comerciales necesarios, incluidos nombres de proveedores.

El servicio agrega cada tabla independientemente. Los filtros por operación, aduana y documento se relacionan mediante pertenencia a las llaves de 501, sin multiplicar filas por facturas o contribuciones. Las métricas por tabla conservan sus propias unidades y granularidad.

El Manual de Consulta Data Stage, julio 2021, aporta las definiciones de 501, 551, contribuciones, selección e incidencias. El documento es una referencia de estructura de datos, no una certificación de normativa actual ni un catálogo actualizado de claves aduaneras.

## Definiciones

| Indicador | Base |
| --- | --- |
| Pedimentos | Llaves distintas de año, mes, patente, pedimento y sección aduanera en 501. |
| Partidas | Filas de 551, sin eliminación silenciosa de registros. |
| Valor de mercancías USD | Suma decimal de `ValorDolares` en 551. |
| Valor en aduana / comercial MXN | `ValorAduana` / `ValorComercial` en 551. |
| Facturación USD | `ValorDolares` en 505, separado de 551. |
| Contribuciones del pedimento | `ImportePago` en 510, todas las formas de pago. |
| Contribuciones de partidas | `ImportePago` en 557, separado de 510. |
| Diferencias de contribuciones | `ImportePago` en 702, separado de 510 y 557. |
| Peso bruto | `PesoBrutoMercancia` de 501 en kg. |
| Semáforo rojo | Eventos SEL con código 0 / eventos con código 0 o 1. |
| Reconocimientos | INCI S = simple, G = grave, C = correcto. C no es una incidencia. |
| Rectificaciones | Filas de 701. No se interpreta automáticamente como sustitución de otras operaciones. |
| Variación | `(actual - base) / abs(base) * 100`; sin porcentaje con base cero o ausente. |

El mes procede de `Periodo`, no de la fecha de pago. Un mes sin fuente muestra `null`, no cero. Los totales suman datos disponibles del rango; la cobertura se muestra junto al informe. Los nulos numéricos no se convierten en cero y se cuentan en calidad. La variación de las tarjetas corresponde al último mes disponible frente al mes calendario anterior, incluso si ese mes queda fuera del rango seleccionado.

Los rankings muestran ocho categorías y agrupan el resto en `Otros`. Las claves se conservan sin inventar nombres de aduanas o significados fiscales no incluidos en los archivos. Los gráficos de volumen y la matriz de cobertura técnica no se filtran por dimensiones comerciales, y así se rotulan.

## Preparar referencias

Desde `backend`, con las dependencias del lock instaladas:

```powershell
..\.venv\Scripts\python.exe -m app.cli.analytics_reference ..\DataStage_2026_Ene-Ago.xlsx --compare ..\DataStage_Agosto_2026.xlsx --scope local --output ..\.data\analytics-reference.json
```

El comando utiliza `openpyxl`, incluido en las dependencias de pruebas del lock; la API de producción no necesita abrir Excel. `--compare` valida agosto contra el consolidado pero **no incorpora sus filas**. La salida se reemplaza atómicamente y es ignorada por Git. El lanzador de desarrollo detecta `.data/analytics-reference.json`. En otros entornos configura `DATASTAGE_ANALYTICS_REFERENCE_FILE` explícitamente y genera el snapshot con el ámbito autorizado.

La conciliación normaliza campos numéricos de la especificación y excluye las columnas de procedencia de la comparación. Preserva diferencias en identificadores y texto. En los archivos suministrados hay diferencias como `NumeroGuia` con ceros iniciales perdidos, `IdentificadorCaso` convertido en fecha y representaciones de hora. El consolidado se utiliza como base anual identificada, sin corregir ni sobrescribir los Excel.

## Interfaz

La ruta `/analytics` incluye cinco vistas, filtros por fuente/año/rango/operación/aduana/documento, métricas, tendencias, rankings, comparador de meses, detalle tabular, matriz de cobertura, descarga CSV y PNG, ampliación de gráficas e impresión. Los gráficos usan Chart.js y tienen vista tabular accesible. El selector ES/EN es persistente y actualiza los formatos regionales de cifras y fechas.

`get_analytics` en Foundry usa el mismo servicio y agrega evidencia de fuentes/versiones a la respuesta. El enlace al asistente sólo prepara una pregunta; no la envía automáticamente.

## Límites

La primera versión agrega en Python usando Decimal, con consultas de columnas específicas y filtro SQL de ámbito, versión y año. El snapshot de referencia se cachea por ruta y modificación. Para muchos millones de filas conviene materializar agregados versionados en SQL, conservando este contrato y verificando sus totales antes de sustituir el lector.

La prueba automatizada cubre precisión, cero/nulo, granularidad, filtros, autorización, meses ausentes y lectura de versiones publicadas. El modo SQLite no sustituye una validación de integración con SQL Server real. Los Excel no incluyen telemetría suficiente para derivar duración o tasa de éxito del worker; no se fabrican esos indicadores.
