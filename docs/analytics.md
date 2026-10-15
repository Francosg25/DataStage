# Analytics de DataStage

## Fuentes y granularidad

El contrato de lectura es `GET /api/v1/reports/analytics/options` y `GET /api/v1/reports/analytics`. Ambos requieren acceso Reader y derivan el ámbito de la identidad autenticada. La API nunca acepta un ámbito del navegador.

`published` consulta las versiones mensuales activas mediante `Period.active_run_id`. No consulta anuales ni versiones reemplazadas. `reference` lee un snapshot privado, con `schemaVersion`, `scopeId`, nombres y SHA-256 de archivos. Las dos fuentes no se mezclan. El snapshot no está en los assets de Angular. Retiene campos comerciales y observaciones 558, que pueden contener información corporativa sensible; se protege con el mismo ámbito que el resto de los datos.

El servicio agrega cada tabla independientemente. Los filtros por operación, aduana y documento se relacionan mediante pertenencia a las llaves de 501, sin multiplicar filas por facturas o contribuciones. Las métricas por tabla conservan sus propias unidades y granularidad.

El análisis abre con el rango enero–diciembre. El botón «Último mes cargado» selecciona el año y el mes más recientes disponibles de la fuente elegida y fija Desde/Hasta en ese mismo mes. Conserva operación, aduana, documento y moneda. `/analytics/options` entrega `latestPeriod` por fuente, independiente del rango visible; para cargas publicadas solo considera ejecuciones mensuales activas y publicadas del ámbito autenticado. No usa el mes del reloj ni la fecha de una recarga de un período antiguo. Sin meses disponibles el botón queda deshabilitado. «Restablecer» recupera enero–diciembre del año seleccionado.

Se retiró la leyenda «Indicadores del rango…» encima de los KPI. Los colores de valor de importaciones y exportaciones se comparten entre tarjetas y evolución mensual: importaciones azul `#447ec0`, exportaciones verde `#22978a`, tanto en USD como en MXN.

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
| Rectificaciones | Llaves distintas de año, mes, patente, pedimento y aduana en 701. No implica error operativo ni sustitución fiscal. |
| Variación | `(actual - base) / abs(base) * 100`; sin porcentaje con base cero o ausente. |

El mes procede de `Periodo`, no de la fecha de pago. Un mes sin fuente muestra `null`, no cero. Los totales suman datos disponibles del rango; la cobertura se muestra junto al informe. Los nulos numéricos no se convierten en cero y se cuentan en calidad. La variación de las tarjetas corresponde al último mes disponible frente al mes calendario anterior, incluso si ese mes queda fuera del rango seleccionado.

Los rankings comerciales muestran ocho categorías y agrupan el resto en `Otros`. El ranking de NP muestra diez combinaciones NP/fracción con IGI positivo e identificación inequívoca. Las etiquetas verificadas proceden del Anexo 22 suministrado, del 15 de enero de 2026. Claves desconocidas muestran que su descripción no está validada. Las traducciones inglesas son etiquetas de interfaz, no interpretaciones legales.

## IGI, IVA y números de parte

Los indicadores de pago usan 557: clave 6 para IGI y clave 3 para IVA, únicamente importaciones verificadas en 551. Las tres tarjetas de contribuciones muestran IGI FP 0, IVA FP 0 e IVA FP 21. La tarjeta IGI FP 21 se retiró; el dato se conserva en API/CSV. `igiPaid` y `ivaPaid` conservan FP 0; `igiFp21` e `ivaFp21` conservan FP 21, en la moneda de la respuesta. Cada tarjeta usa su importe mensual para la tendencia y variación. La clave 1 es DTA, no IGI. No se suman 510 y 557. 702 y la gráfica genérica de contribuciones por partida dejan de aparecer en el dashboard; los datos originales se conservan.

El análisis muestra ocho tarjetas: pedimentos, valor de importaciones, valor de exportaciones, IGI FP 0, IVA FP 0, IVA FP 21, rectificaciones y tasa roja. Los valores comerciales proceden de 551 y se separan por TipoOperacion 1 y 2; cada importe se convierte por pedimento cuando se solicita MXN. El total histórico `tradeUsd`/`tradeMxn` se mantiene en la API para compatibilidad y puede incluir operaciones sin clasificar, pero no aparece como una tarjeta combinada. Las tres tarjetas de contribuciones conservan cero con cobertura e importes verificados; sin cobertura o con cruces o conversiones inválidos conservan `null`. Los filtros generales siguen aplicándose; elegir solo exportación deja los pagos de importación y el valor de importación en cero cuando hay cobertura.

La comparativa mensual utiliza el mismo desglose comercial y de pagos, con Partidas en lugar de tasa roja. El PDF muestra el mismo resumen de ocho indicadores y separa importación/exportación en su evolución mensual. El CSV incluye las nuevas métricas. Las gráficas de impuestos por PN siguen midiendo pagos en efectivo FP 0.

La relación 551/557/558 utiliza año, mes, patente, pedimento, sección aduanera, fracción y secuencia. El extractor admite etiquetas explícitas NP, NP INTERNO, N/P, P/N, No.Parte, N. DE PARTE, número de parte y Part Number, con o sin dos puntos. Admite una etiqueta sola seguida de un token en la siguiente secuencia de observación, o en el siguiente segmento separado por `|` o salto de línea. Conserva códigos completos, incluidos `/MX`, segundos guiones y `+`. Excluye el contador de `ORDEN DE NUMERO DE PARTE 1`.

El catálogo `backend/app/modules/reporting/part_numbers.json` contiene 381 NP únicos de `EXCEL NP.xlsx`, columna A de Sheet1 (17,595 registros, 17,214 repeticiones; archivo suministrado el 9 de octubre de 2026). Permite identificar un PN conocido como token completo dentro de una descripción u observación, aunque no tenga etiqueta, incluido el segmento posterior a `P.O ... |`. Respeta etiquetas de serie, modelo, factura, lote y orden de compra para evitar atribuciones falsas. Se normalizan mayúsculas y espacios del catálogo y se retiran puntos finales de oración conservando los puntos internos del PN. Para códigos nuevos conserva las etiquetas explícitas y la regla confirmada `P.O ... | 1905-...`. El catálogo se carga al iniciar el proceso: para actualizarlo, agregar los códigos completos y reiniciar el backend. La actualización de detección preserva el `part_numbers.json` local del usuario. No se requiere el Excel ni una librería de Excel en producción.

Una coincidencia exacta del catálogo tiene prioridad. Si un token termina en `EN` o `N` y no existe completo en el catálogo, se admite como variante de empaque únicamente si al retirar ese sufijo queda un PN exacto registrado. El PN registrado se utiliza como principal y el observado completo se conserva en `alternatePartNumbers`, por lo que también se puede buscar y exportar. No se comparan prefijos aproximados ni se retiran otras letras automáticamente.

No infiere NP de series, modelos, lotes o facturas etiquetados ni por coincidencias parciales. Las pruebas comprueban los 381 códigos en contextos controlados, no prometen precisión del 100% en todas las observaciones. Varias observaciones con el mismo NP no multiplican los pagos. `NP: 1200-1030847AN OTRO NP: 1200-1030847AND` representa un principal y un alternativo: el importe se asigna una sola vez al principal. Los alternativos se muestran, exportan y permiten buscar el principal. Varios NP principales distintos en la misma partida, o un alternativo sin principal, requieren revisión. No se infieren equivalencias por similitud de códigos.

Las alertas se recalculan al consultar el análisis: una mejora del detector puede resolverlas con las observaciones 558 ya guardadas, sin volver a cargar el ZIP. Si la fuente contiene datos incorrectos, se debe corregir y publicar una nueva versión. No hay descarte local ni envío por correo. Se pueden revisar y exportar. Los pagos sin partida u operación verificable se cuentan; sus totales se marcan pendientes de conciliación, no como cero.

El parámetro `currency=USD|MXN` selecciona la moneda de presentación, con USD por defecto. Cada registro se convierte usando el TipoCambio único y positivo de su pedimento en 501. Un importe distinto de cero sin tipo válido hace que su agregado convertido sea `null`, evitando totales parciales. Los campos históricos con sufijo `Mxn` o `Usd` mantienen sus unidades; `igiPaid`, `ivaPaid`, `partTaxes` y rankings usan la moneda de la respuesta.

El Excel IGI abril 2025 a marzo 2026 es referencia de presentación. No se incorpora al snapshot enero-agosto 2026 ni se inventa su desglose mensual.

## Contribuciones por forma de pago y rectificaciones

La tabla mensual usa `paymentMethods` en cada mes y en el total. Separa IGI/IVA
de importación por `FormaPago=0` (efectivo) y `FormaPago=21` (CERTIVA). No suma
crédito y efectivo. Las tarjetas y el análisis por NP siguen midiendo FP 0.
Otros medios se desglosan por código en `paymentMethods.other`, con IGI, IVA, registros de importación y cruces pendientes. `otherPaymentRows` cuenta importaciones verificadas; `otherUnmatchedRows` cuenta registros sin operación verificable. FP 13 es pago ya efectuado y FP 22 garantía en IVA e IEPS; no se añaden al efectivo.
El cruce con 551 no multiplica pagos cuando hay partidas repetidas. Un cruce
incompleto o ambiguo invalida el total de la forma afectada, no el de la otra.

`rectificationsByCustoms` agrupa llaves únicas de 701 y 501 por aduana. La etiqueta visible es Pedimentos rectificados; el campo `r1` se conserva como alias de compatibilidad del contrato: las claves de documento
del Excel de ejemplo son AF, IN, RT, etc., no la cadena R1. Los meses forman parte
de la llave, de modo que apariciones en meses distintos se mantienen separadas.
No se deduplican las filas de pago 557 por igualdad de monto.

- `% aduana = rectificados de la aduana / pedimentos 501 de esa aduana * 100`.
- `% global = rectificados de la aduana / pedimentos 501 de toda la selección * 100`.
- El filtro de aduana también restringe la base global. Su valor se muestra en pantalla.
- Los totales porcentuales se recalculan con los conteos, no con promedios de tasas.
- Base cero, llaves inválidas, 701 sin 501 o cobertura incompleta no generan tasas falsas.
- La imagen ilustrativa suma 1,105 pedimentos visibles. En el Excel de referencia,
  enero-junio de 2026 con todas las operaciones suma 1,527 pedimentos y 31 rectificados:
  7/1,527 = 0.46%, consistente con el porcentaje global de Manzanillo del ejemplo.
  Se muestran también aduanas sin rectificaciones. Los conteos 501 de Altamira y
  AIFA en esta selección difieren de la imagen; no se reemplazan por valores manuales.
- No se inventaron responsables logísticos ni costos aproximados.

## Reporte PDF

`GET /api/v1/reports/analytics/pdf` reutiliza exactamente la dependencia de
consulta y autorización del análisis. Acepta los mismos filtros, `language=es|en`
y opcionalmente `snapshot`, el SHA-256 de la respuesta sin `generatedAt`.
El cliente siempre manda los filtros y snapshot del reporte mostrado, no del
formulario mientras cambia. Un corte distinto devuelve 409 y exige actualizar.
El archivo se genera en memoria con ReportLab, sin mandar datos a terceros,
sin persistirlos públicamente y con respuesta `no-store`.

Incluye indicadores, evolución mensual, FP 0/21, principales NP, rectificaciones,
fórmulas, cobertura, alertas, fuentes SHA-256 y versiones publicadas. Las tablas
repiten encabezados al paginar. La descarga incorpora año, meses, moneda e idioma.
La carga histórica 2020-2026 queda expresamente pendiente.

## Preparar referencias

Desde `backend`, con las dependencias del lock instaladas:

```powershell
..\.venv\Scripts\python.exe -m app.cli.analytics_reference ..\DOCUMENTOS\DataStage_2026_Ene-Ago.xlsx --compare ..\DOCUMENTOS\DataStage_Agosto_2026.xlsx --scope local --output ..\.data\analytics-reference.json
```

El comando utiliza `openpyxl`, incluido en las dependencias de pruebas del lock; la API de producción no necesita abrir Excel. `--compare` valida agosto contra el consolidado pero **no incorpora sus filas**. La salida se reemplaza atómicamente y es ignorada por Git. El lanzador de desarrollo detecta `.data/analytics-reference.json`. En otros entornos configura `DATASTAGE_ANALYTICS_REFERENCE_FILE` explícitamente y genera el snapshot con el ámbito autorizado.

La conciliación normaliza campos numéricos de la especificación y excluye las columnas de procedencia de la comparación. Preserva diferencias en identificadores y texto. En los archivos suministrados hay diferencias como `NumeroGuia` con ceros iniciales perdidos, `IdentificadorCaso` convertido en fecha y representaciones de hora. El consolidado se utiliza como base anual identificada, sin corregir ni sobrescribir los Excel.

## Interfaz

«Números de parte pendientes de corrección» dispone de búsqueda parcial de PN, sin distinguir mayúsculas, en los candidatos detectados y en las observaciones 558. Filtra todos los pendientes del rango antes de paginar, vuelve a la primera página al cambiar la búsqueda y muestra resultados frente al total. Es un filtro local, independiente del buscador de Contribuciones, sin consultas adicionales ni cambios de clasificación. El CSV incluye todas las coincidencias, no solo la página visible, y conserva candidatos y observaciones. Limpiar búsqueda restaura todos los pendientes. Restablecer y cambiar de fuente limpian también esta búsqueda.

Las gráficas de operaciones y comparativa mensual muestran por defecto título, unidad, ejes y etiquetas de series. Los subtítulos explicativos, el contexto repetido y las notas largas están en «Detalles», cerrado por defecto y accesible con teclado. Las condiciones reales de valores ausentes o cero mantienen un estado breve visible. Ver datos, PNG y ampliación conservan su funcionamiento; el PNG sigue incluyendo alcance y notas para identificar el corte fuera de la aplicación.

La ruta `/analytics` conserva cinco vistas, con contenido propio en cada una. Panorama general muestra las ocho tarjetas y la tendencia del valor de mercancías; el enlace de comparación abre `/annual`. Comercio y mercancías contiene los cinco rankings comerciales. Contribuciones contiene la tabla de pagos, los rankings de IGI pagado por PN y por fracción, uno junto al otro, y las comparativas de IGI/IVA por PN. Control y calidad contiene rectificaciones y alertas NP; se retiró la gráfica de eventos de selección aduanera. Fuentes y métricas explica los cálculos. Las tarjetas aparecen únicamente en Panorama general. Las tablas de pagos y rectificaciones y las gráficas PN no se repiten en otras pestañas. La comparación general de meses se consulta en Comparativa mensual; los controles de meses por PN permanecen en Contribuciones.

La tabla mensual de pagos presenta IGI FP 0, IVA FP 0 e IVA FP 21. Se retiró la columna de IGI del bloque FP 21 de esa tabla y de su tabla equivalente en el PDF. La tarjeta IGI FP 21 también se retiró del análisis y de la comparativa; los datos originales de API/CSV conservan su cálculo. Se mantienen filtros, CSV, PNG y ampliación; el PDF corresponde al reporte completo, con independencia de la pestaña activa. ES/EN actualiza etiquetas y formatos regionales. Resumen muestra por defecto los últimos seis meses publicados, con selector de 3/6/12. Cargas separa mensuales y consolidados.

Los Excel nuevos son rangos normales con autofiltros, sin tablas nativas y con encabezados legibles. El motor omite líneas ASC formadas solo por separadores antes de añadir trazabilidad: esas líneas no generan registros ni inflan los conteos de Control_Proceso. Los ceros y las filas con algún dato se conservan. El exportador no escribe celdas vacías con formato ni filas totalmente vacías, y ajusta el filtro a las filas exportadas. Conserva todos los encabezados y posiciones de campos. ImportePago, valores monetarios, cantidades, pesos, tasas y conteos se escriben como números nativos; las fechas válidas se escriben como fechas de Excel, mostrando la hora cuando existe. PN, fracciones, pedimentos y otros códigos permanecen como texto. Valores numéricos no interpretables o con más de 15 cifras significativas y fechas inválidas conservan el original como texto. La clasificación se basa en encabezados de medidas explícitos; no convierte cualquier texto con dígitos. No combina ni mueve celdas para cerrar huecos. Los archivos ya generados requieren una nueva exportación para adoptar este ajuste.

Después de aplicar una actualización, se reinician backend, worker y frontend. El comando habitual de Uvicorn no usa recarga automática; un proceso anterior puede no ofrecer `/reports/analytics/months` o no incluir `ivaFp21` en los indicadores, aunque el frontend ya se haya actualizado. En ese caso aparece `Not Found` o un guion de dato no disponible. Esto no significa que el importe de crédito sea cero.

`get_analytics` en Foundry usa el mismo servicio y agrega evidencia de fuentes/versiones. Envía un resumen acotado de NP (20 filas, conteos completos, sin texto de observaciones), no todas las alertas al modelo. El enlace al asistente sólo prepara una pregunta; no la envía automáticamente.

## Operación de meses

Los consolidados manuales tienen cuatro selectores: año inicial, mes inicial, año final y mes final. Ambos extremos se incluyen y el rango puede cruzar años. Solo se fijan las versiones mensuales publicadas dentro del intervalo; la interfaz muestra meses disponibles frente a meses solicitados, sin inventar datos para los faltantes. No se permite un fin anterior al inicio.

`POST /annual-runs` recibe `startYear`, `startMonth`, `endYear` y `endMonth` (meses 1-12, años 1900-2100). El rango queda guardado en las opciones inmutables de la ejecución y se devuelve como `periodRange`. Los reprocesos conservan ese rango y sus versiones fuente; las descargas se identifican como `DataStage_2025-04_2026-03.xlsx`. El contrato anterior `anio` + `rangoNombre` sigue disponible para clientes existentes y consolidados automáticos, pero no se puede mezclar con el contrato de cuatro campos.

Una carga nueva reemplaza la versión mensual activa al publicarse correctamente; el historial se conserva. Volver a cargar un ZIP histórico genera una nueva versión para ese mes. El lector admite ASC en subcarpetas ZIP sin extraer rutas al disco.

La eliminación múltiple requiere Admin y admite hasta 24 meses por operación. `POST /periods/bulk-deletion-preview` calcula la unión de ejecuciones afectadas sin duplicar consolidados compartidos. `POST /periods/bulk-delete` valida token de impacto, versiones, confirmación y motivo antes de eliminar en una transacción. Archivos físicos se limpian después del commit; los fallos se devuelven explícitamente. Las pruebas usan bases temporales, nunca los meses del usuario.

## Límites

La primera versión agrega en Python usando Decimal, con consultas de columnas específicas y filtro SQL de ámbito, versión y año. El snapshot de referencia se cachea por ruta y modificación. Para muchos millones de filas conviene materializar agregados versionados en SQL, conservando este contrato y verificando sus totales antes de sustituir el lector.

La prueba automatizada cubre precisión, cero/nulo, granularidad, filtros, autorización, meses ausentes y lectura de versiones publicadas. El modo SQLite no sustituye una validación de integración con SQL Server real. Los Excel no incluyen telemetría suficiente para derivar duración o tasa de éxito del worker; no se fabrican esos indicadores.



## Revisión de claridad — 13 de octubre de 2026

- Rankings 501 por aduana/documento/operación usan llaves distintas, como el KPI. Una llave con categorías contradictorias se cuenta una vez en `unknown`; llaves incompletas dejan el conteo y los rankings sin dato.
- `originCountries` incluye solo importaciones y `destinationCountries` solo exportaciones. `countries` se conserva para compatibilidad; las gráficas usan los dos desgloses separados.
- La cobertura de agregados es la intersección de tablas en los meses disponibles. `coverage.incompleteTables` identifica ausencias parciales y `invalidDeclarationKeys` identifica llaves incompletas. Una tabla vacía registrada es cero; una ausente no lo es.
- Todas las sumas numéricas usan `strict_sum`, incluidos campos auxiliares y Otros. Las partidas monetarias no se deduplican silenciosamente.
- SEL añade `unclassifiedSelections`. Cualquier evento distinto de 0/1 invalida `redRate` y permanece visible. Los eventos no son pedimentos únicos.
- El Top 10 de IGI queda sin dato con cobertura de PN incompleta o importes desconocidos entre los PN identificados. Las tendencias conservan cada mes válido y usan escalas independientes para IGI e IVA.
- Las comparativas por PN respetan el rango seleccionado. Los tooltips y tablas muestran moneda y precisión; PNG conserva contexto y notas. Resumen operativo ofrece su propia tabla de datos y explica que cuenta filas de todas las tablas.
- El PDF usa las mismas definiciones de efectivo, crédito, otras formas y pedimentos rectificados. No se cambia el significado fiscal de las operaciones: el valor declarado no netea originales/rectificaciones y las diferencias 702 permanecen separadas.

Referencias aportadas: Manual de Consulta, julio 2021, páginas 12–23; Anexo 22 del 15 de enero de 2026, páginas 119–120 (apéndices 12 y 13). Pruebas adicionales en `backend/tests/test_chart_semantics.py` y `frontend/src/app/features/analytics.spec.ts`.

## Tiempo de carga

Los reportes se reutilizan en memoria cuando la fuente y los filtros siguen
iguales. Cada petición mantiene la comprobación de permisos y consulta la
versión de la fuente: ejecución activa y versión del mes en cargas publicadas;
ruta, tamaño y marcas del archivo en la referencia Excel. Publicar, reemplazar
o quitar un mes, o cambiar la referencia, provoca un cálculo nuevo. El botón
Actualizar y volver a entrar en la sección hacen esta comprobación.

La caché pertenece a cada proceso del backend, con un máximo de 12 resultados
y 32 MiB de contenido serializado. Solicitudes simultáneas del mismo reporte
comparten el cálculo. No se guardan resultados en disco ni en el navegador.
Al reiniciar el backend, la primera consulta vuelve a calcularse.

`GET /api/v1/reports/analytics/months` devuelve los indicadores
mensuales utilizados por la comparativa y el total comercial histórico de compatibilidad. No procesa observaciones 558 ni calcula
atribución a PN o rankings. Dos meses del mismo año requieren una petición;
años diferentes requieren una por año. Conserva el conteo por llave, la moneda,
la cobertura y los importes desconocidos del reporte completo.

En cargas publicadas consulta solo 501, 551, 557 y 701. La referencia JSON
completa se lee en su primer acceso y se reutiliza mientras el archivo conserve
la misma versión.

En la prueba con enero–agosto de 2026, el cálculo completo repetido pasó de
2.82 s a 0.035 s. La comparativa pasó de dos respuestas de unos 220 kB a una
respuesta de 2.3 kB; su primer cálculo tardó 0.20 s. Son medidas del entorno
de prueba, no tiempos garantizados de pantalla en otros equipos.


El ranking de fracciones agrupa `partTaxes.rows` por `tariff`, suma IGI FP 0 de la selección y ordena los diez importes positivos más altos. Incluye pagos sin PN cuando el filtro PN está vacío. Respeta el filtro por fracción y la búsqueda PN/alternativos. No usa el valor de mercancías, FP 21 ni conteos de pagos como sustitutos del IGI. Cobertura 551/557 incompleta, pagos sin cruce verificable o importes IGI desconocidos dejan el ranking sin dato.

### Desglose de rectificaciones por patente

La tabla principal añade Patente y separa filas por aduana/patente. Su porcentaje de grupo divide pedimentos rectificados de esa combinación entre pedimentos 501 de la misma combinación. La segunda tabla agrupa todas las aduanas seleccionadas por patente: porcentaje de patente = rectificados de esa patente / pedimentos de esa patente × 100. El porcentaje global usa en ambos casos la base 501 filtrada completa. Ambas tablas comparten el total global y no deben sumarse entre sí. Se usan llaves distintas de año, mes, patente, pedimento y aduana, por lo que registros repetidos no multiplican los conteos. Se mantienen las reglas de cobertura, llaves inválidas y rectificaciones sin 501. El PDF contiene ambos desgloses.
