# Analytics de DataStage

## Fuentes y granularidad

El contrato de lectura es `GET /api/v1/reports/analytics/options` y `GET /api/v1/reports/analytics`. Ambos requieren acceso Reader y derivan el ámbito de la identidad autenticada. La API nunca acepta un ámbito del navegador.

`published` consulta las versiones mensuales activas mediante `Period.active_run_id`. No consulta anuales ni versiones reemplazadas. `reference` lee un snapshot privado, con `schemaVersion`, `scopeId`, nombres y SHA-256 de archivos. Las dos fuentes no se mezclan. El snapshot no está en los assets de Angular. Retiene campos comerciales y observaciones 558, que pueden contener información corporativa sensible; se protege con el mismo ámbito que el resto de los datos.

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

Los rankings comerciales muestran ocho categorías y agrupan el resto en `Otros`. El ranking de NP muestra diez combinaciones NP/fracción con IGI positivo e identificación inequívoca. Las etiquetas verificadas proceden del Anexo 22 suministrado, del 15 de enero de 2026. Claves desconocidas muestran que su descripción no está validada. Las traducciones inglesas son etiquetas de interfaz, no interpretaciones legales.

## IGI, IVA y números de parte

Los indicadores de pago usan 557: clave 6 para IGI y clave 3 para IVA, únicamente importaciones y FormaPago 0 (efectivo). La clave 1 es DTA, no IGI. No se suman 510 y 557. 702 y la gráfica genérica de contribuciones por partida dejan de aparecer en el dashboard; los datos originales se conservan.

La relación 551/557/558 utiliza año, mes, patente, pedimento, sección aduanera, fracción y secuencia. El extractor admite etiquetas explícitas NP, N/P, P/N, No.Parte, número de parte y Part Number. Admite una etiqueta sola seguida de un token en la siguiente secuencia de observación. No adivina NP a partir de series, lotes, números sueltos o descripciones. Varias observaciones con el mismo NP no multiplican los pagos. Conforme a la aclaración del usuario, `NP: 1200-1030847AN OTRO NP: 1200-1030847AND` representa un principal y un código alternativo del mismo artículo: el importe se asigna una sola vez al principal. Los alternativos se muestran, exportan y permiten buscar el principal. Varios NP principales distintos en la misma partida, o un alternativo sin principal, requieren revisión. No se infieren equivalencias entre artículos diferentes únicamente por similitud de códigos.

Las alertas permanecen en el análisis de la selección hasta corregir la fuente y publicar una nueva versión. No hay descarte local ni envío por correo. Se pueden revisar y exportar. Los pagos sin partida u operación verificable se cuentan; sus totales se marcan pendientes de conciliación, no como cero.

El parámetro `currency=USD|MXN` selecciona la moneda de presentación, con USD por defecto. Cada registro se convierte usando el TipoCambio único y positivo de su pedimento en 501. Un importe distinto de cero sin tipo válido hace que su agregado convertido sea `null`, evitando totales parciales. Los campos históricos con sufijo `Mxn` o `Usd` mantienen sus unidades; `igiPaid`, `ivaPaid`, `partTaxes` y rankings usan la moneda de la respuesta.

El Excel IGI abril 2025 a marzo 2026 es referencia de presentación. No se incorpora al snapshot enero-agosto 2026 ni se inventa su desglose mensual.

## Preparar referencias

Desde `backend`, con las dependencias del lock instaladas:

```powershell
..\.venv\Scripts\python.exe -m app.cli.analytics_reference ..\DOCUMENTOS\DataStage_2026_Ene-Ago.xlsx --compare ..\DOCUMENTOS\DataStage_Agosto_2026.xlsx --scope local --output ..\.data\analytics-reference.json
```

El comando utiliza `openpyxl`, incluido en las dependencias de pruebas del lock; la API de producción no necesita abrir Excel. `--compare` valida agosto contra el consolidado pero **no incorpora sus filas**. La salida se reemplaza atómicamente y es ignorada por Git. El lanzador de desarrollo detecta `.data/analytics-reference.json`. En otros entornos configura `DATASTAGE_ANALYTICS_REFERENCE_FILE` explícitamente y genera el snapshot con el ámbito autorizado.

La conciliación normaliza campos numéricos de la especificación y excluye las columnas de procedencia de la comparación. Preserva diferencias en identificadores y texto. En los archivos suministrados hay diferencias como `NumeroGuia` con ceros iniciales perdidos, `IdentificadorCaso` convertido en fecha y representaciones de hora. El consolidado se utiliza como base anual identificada, sin corregir ni sobrescribir los Excel.

## Interfaz

La ruta `/analytics` conserva sus cinco vistas existentes. El panorama integra cuatro gráficas: valor de mercancías, IGI/IVA mensual, IGI por NP y rectificaciones por mes/patente. Contribuciones incluye dos tablas comparativas separadas de IGI e IVA. Control y calidad contiene las alertas NP. Se mantienen filtros, CSV, PNG, ampliación e impresión. ES/EN actualiza etiquetas y formatos regionales. El comparador visual de `/annual` permite mes/año contra mes/año y solo contiene análisis. El apartado Cargas separa los flujos de mensuales (`/uploads/monthly`) y consolidados (`/uploads/consolidated`), ambos reservados a Operator/Admin. `/monthly` redirige al nuevo flujo mensual. Los Excel nuevos usan rangos normales con autofiltros y fila superior inmovilizada, sin tablas de Excel; sus encabezados tienen fondo verde oscuro y texto blanco en negrita.

`get_analytics` en Foundry usa el mismo servicio y agrega evidencia de fuentes/versiones. Envía un resumen acotado de NP (20 filas, conteos completos, sin texto de observaciones), no todas las alertas al modelo. El enlace al asistente sólo prepara una pregunta; no la envía automáticamente.

## Operación de meses

Los consolidados manuales tienen cuatro selectores: año inicial, mes inicial, año final y mes final. Ambos extremos se incluyen y el rango puede cruzar años. Solo se fijan las versiones mensuales publicadas dentro del intervalo; la interfaz muestra meses disponibles frente a meses solicitados, sin inventar datos para los faltantes. No se permite un fin anterior al inicio.

`POST /annual-runs` recibe `startYear`, `startMonth`, `endYear` y `endMonth` (meses 1-12, años 1900-2100). El rango queda guardado en las opciones inmutables de la ejecución y se devuelve como `periodRange`. Los reprocesos conservan ese rango y sus versiones fuente; las descargas se identifican como `DataStage_2025-04_2026-03.xlsx`. El contrato anterior `anio` + `rangoNombre` sigue disponible para clientes existentes y consolidados automáticos, pero no se puede mezclar con el contrato de cuatro campos.

Una carga nueva reemplaza la versión mensual activa al publicarse correctamente; el historial se conserva. Volver a cargar un ZIP histórico genera una nueva versión para ese mes. El lector admite ASC en subcarpetas ZIP sin extraer rutas al disco.

La eliminación múltiple requiere Admin y admite hasta 24 meses por operación. `POST /periods/bulk-deletion-preview` calcula la unión de ejecuciones afectadas sin duplicar consolidados compartidos. `POST /periods/bulk-delete` valida token de impacto, versiones, confirmación y motivo antes de eliminar en una transacción. Archivos físicos se limpian después del commit; los fallos se devuelven explícitamente. Las pruebas usan bases temporales, nunca los meses del usuario.

## Límites

La primera versión agrega en Python usando Decimal, con consultas de columnas específicas y filtro SQL de ámbito, versión y año. El snapshot de referencia se cachea por ruta y modificación. Para muchos millones de filas conviene materializar agregados versionados en SQL, conservando este contrato y verificando sus totales antes de sustituir el lector.

La prueba automatizada cubre precisión, cero/nulo, granularidad, filtros, autorización, meses ausentes y lectura de versiones publicadas. El modo SQLite no sustituye una validación de integración con SQL Server real. Los Excel no incluyen telemetría suficiente para derivar duración o tasa de éxito del worker; no se fabrican esos indicadores.
