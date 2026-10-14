# Guía de gráficas y cálculos de DataStage

Documento funcional y técnico. Revisión del 13 de octubre de 2026. Contrastada con el Manual de Consulta (julio 2021, páginas 12–23) y el Anexo 22 suministrado (15 de enero de 2026, apéndices 12 y 13, páginas 119–120). Esta fuente incorpora las tablas FP 0/21 y rectificaciones por aduana. El PDF anterior del 6 de octubre conserva la versión previa; el reporte PDF descargable de la aplicación incluye los criterios actuales junto a cada corte.

Esta guía explica de dónde obtiene DataStage cada visualización, qué calcula y qué debe comprobarse al interpretar sus resultados. Cubre Resumen operativo, las cinco vistas de Análisis de operaciones y Comparativa mensual. Está dirigida al equipo que consulta los datos y a quienes deben conciliarlos con los archivos de origen.

Las cifras se calculan con código determinista, no con inteligencia artificial. Azure Foundry puede consultar resultados y explicarlos, pero no determina las fórmulas de estas gráficas. El criterio documentado es el de la implementación revisada, no una certificación fiscal. Los ejemplos numéricos de esta guía son didácticos y no representan operaciones reales.

## 1 Fuentes y alcance

### Cargas publicadas

La fuente `published` toma únicamente la versión mensual activa de cada mes del año solicitado. Relaciona `periods.active_run_id` con `processing_runs.id`, exige una ejecución mensual publicada y limita la consulta al ámbito corporativo de la identidad autenticada. Los datos comerciales están en tablas SQL `ds_501`, `ds_551`, etc. La cobertura y el número de registros proceden de `processing_tables` y de los conteos de la ejecución.

Una carga nueva sustituye a la versión activa cuando se publica correctamente. Las versiones anteriores permanecen en el historial, pero no se vuelven a sumar en el dashboard. Los consolidados anuales tampoco se agregan encima de los mensuales. Así se evita contar dos veces los mismos datos por conservar varias versiones o un archivo acumulado.

### Excel de referencia

La fuente `reference` lee una instantánea privada preparada desde el Excel, separada de las cargas publicadas. Conserva ámbito, versión de esquema, nombres de archivos y sus huellas SHA-256. Las hojas aportan el código de tabla y la columna `Periodo` determina el año y mes de cada fila.

El consolidado DataStage de enero a agosto de 2026 sirve como base de referencia. El archivo mensual de agosto puede compararse con esa base, pero sus filas no se anexan otra vez. La comparación normaliza campos numéricos y cuenta las ocurrencias de cada registro; excluye `ArchivoOrigen` y `FolioOrigen`. Una coincidencia en esa revisión no constituye por sí sola una auditoría fiscal.

El archivo «05. IGI PAGADO ABRIL 25 - MARZO 26 vAO.xlsx» es referencia para la presentación por número de parte. No se mezcla con enero a agosto de 2026, ni se distribuyen sus importes por meses que no estén sustentados en datos. El Manual de Consulta orienta la estructura de tablas y el Anexo 22 suministrado orienta las etiquetas de catálogo. Las fórmulas efectivamente ejecutadas son las que se describen aquí.

### Tiempo y cobertura

El mes analizado es el de la carga o `Periodo`, no un mes recalculado con `FechaPagoReal`. Un registro con fecha de pago distinta sigue perteneciendo al mes de su fuente. La interfaz muestra meses disponibles frente a meses solicitados. Un mes sin fuente es «sin dato», no un mes con actividad cero.

Una tabla registrada con cero filas puede producir cero; una tabla ausente produce un indicador no disponible. En la referencia, la existencia de una hoja registrada se utiliza para completar cobertura con cero filas en meses identificados. Esa regla de importación no prueba por sí sola que la extracción externa esté completa.

Los totales generales se calculan con los meses disponibles del rango. Cada indicador exige sus tablas de origen en todos los meses disponibles seleccionados. Por ejemplo, 551 para valor declarado y 551/557 para impuestos. Un mes totalmente ausente se evidencia en cobertura, pero no se inventa ni convierte automáticamente todo el rango en no disponible. Por ello siempre se debe revisar la cobertura junto al total.

## 2 Tablas y campos de origen

En los Excel se usan encabezados como `ValorDolares`; en el servicio y SQL aparecen normalizados como `valor_dolares`. Es el mismo campo. «Tabla 551» significa el conjunto de datos de partidas; no significa que el Excel descargado tenga un objeto de tabla de Excel.

| Fuente | Nivel de detalle | Campos relevantes | Uso actual |
| --- | --- | --- | --- |
| 501 o ds_501 | Registro de datos generales | Patente, Pedimento, SeccionAduanera, TipoOperacion, ClaveDocumento, TipoCambio | Pedimentos, aduanas, documentos, filtros y conversión |
| 551 o ds_551 | Registro de partida | Fraccion, SecuenciaFraccion, TipoOperacion, ValorDolares, PaisOrigenDestino | Valor comercial analizado, países, fracciones y relación de pagos |
| 557 o ds_557 | Registro de contribución por partida | ClaveContribucion, FormaPago, ImportePago y llave de partida | IGI e IVA pagados |
| 558 o ds_558 | Observación de partida | SecuenciaObservacion, Observaciones y llave de partida | Número de parte principal y alternativos |
| 701 o ds_701 | Registro de rectificación | Patente y llave de pedimento | Rectificaciones por aduana y patente |
| SEL o ds_sel | Evento de selección | SemaforoFiscal y llave de pedimento | Selecciones rojas y verdes |
| 505 o ds_505 | Registro de factura | ValorDolares, ProveedorMercancia, TerminoFacturacion | Métricas adicionales de API y exportación |
| 510 o ds_510 | Pago a nivel de pedimento | ClaveContribucion, FormaPago, ImportePago | Métricas generales separadas de pagos |
| 702 o ds_702 | Diferencia de contribución | ClaveContribucion, FormaPago, ImportePago | Métrica adicional separada |
| INCI o ds_inci | Registro de reconocimiento | GradoIncidencia | Métricas adicionales de calidad |
| Control de cargas | Mes y ejecución | active_run_id, counts_json | Resumen operativo y selección de versión |

Las tablas 505, 510, 702 e INCI no tienen gráficas propias visibles en las vistas actuales. El servicio todavía calcula indicadores de ellas. No deben confundirse los campos disponibles en la API o CSV con visualizaciones efectivamente mostradas.

## 3 Llaves filtros y prevención de duplicaciones

### Identidad del pedimento

La llave de análisis es la combinación de año, mes, patente, pedimento y sección aduanera. Si falta cualquiera de los tres identificadores aduaneros, la llave no es válida. Los identificadores que representan enteros se normalizan para comparar, por ejemplo `001` y `1`; esto no modifica los identificadores del Excel exportado.

El conteo de pedimentos únicos utiliza llaves distintas. La misma identificación aduanera en meses diferentes cuenta una vez en cada mes: no existe una deduplicación fiscal entre meses. Las filas repetidas pueden afectar los importes y rankings basados en registros aunque no aumenten el conteo de llaves distintas.

### Identidad de la partida

La llave anterior se amplía con fracción arancelaria y secuencia de fracción. Esta llave de siete componentes vincula 551, 557 y 558. No se relacionan registros solo porque su descripción o número de parte sean parecidos. Una llave incompleta se registra como problema de calidad.

### Aplicación de filtros

El análisis permite fuente, año, mes inicial, mes final, operación, aduana, documento y moneda. Los filtros dimensionales se aplican primero a 501. Las demás tablas se restringen por pertenencia a las llaves de pedimento admitidas, sin expandir cada fila por el número de facturas o contribuciones relacionadas. En 551, SEL e INCI también se comprueban sus propios campos de operación y documento.

Sin filtros dimensionales, cada tabla conserva sus filas aunque alguna carezca de correspondencia con 501; por eso existen controles de partidas huérfanas. Con filtros, las filas sin cabecera elegible dejan de entrar en los agregados filtrados. Un filtro de exportaciones produce cero IGI/IVA de importación cuando hay cobertura y no hay pagos de importación elegibles.

Las estadísticas técnicas de procesamiento no se redistribuyen por aduana, documento u operación. Además, el contador de partidas huérfanas revisa 551 del rango antes de esos filtros. No debe compararse directamente con un subtotal comercial filtrado como si ambos representaran la misma población.

## 4 Moneda y tratamiento de importes

### Tipo de cambio histórico

USD es la moneda de presentación inicial. La conversión utiliza `TipoCambio` de 501 para la llave exacta del pedimento. No consulta una cotización de hoy, un promedio mensual ni un tipo de cambio generado por IA. Así, cambiar la fecha en que se abre el dashboard no revaloriza las operaciones históricas.

Para cada llave, todas las filas 501 deben coincidir en un tipo de cambio positivo y válido. Tipos distintos, cero, negativos, ausentes o inválidos impiden utilizar esa llave para conversiones. Repetir el mismo tipo válido no lo vuelve ambiguo; mezclarlo con una fila sin tipo válido sí.

- De MXN a USD: dividir el importe individual entre su tipo de cambio.
- De USD a MXN: multiplicar el importe individual por su tipo de cambio.
- Si la moneda de origen ya es la solicitada, no se convierte.
- Un importe cero permanece cero aunque no haya un tipo válido. Un importe inválido permanece no disponible.

Cada registro se convierte antes de sumar. Por ejemplo, 1,700 MXN con tipo 17 equivalen a 100 USD; 1,800 MXN con tipo 18 equivalen a otros 100 USD. El total es 200 USD. No se debe dividir 3,500 MXN entre el tipo de cambio del último pedimento.

### Precisión y valores faltantes

El servicio interpreta los valores numéricos con `Decimal`. Los vacíos, textos no numéricos y valores no finitos se consideran inválidos. Las sumas monetarias de las visualizaciones activas utilizan suma estricta: si un registro que participa no puede convertirse o contiene un importe inválido, el agregado afectado queda sin dato. La lista vacía suma cero cuando su tabla tiene cobertura.

La respuesta JSON usa números y la interfaz redondea para mostrar, normalmente a dos decimales en importes. Los formatos compactos de tarjetas y ejes pueden abreviar miles o millones. Debe conciliarse con el valor detallado, no con la etiqueta abreviada de una tarjeta.

Todas las sumas numéricas, incluidos los indicadores auxiliares y el grupo «Otros», conservan los valores inválidos como no disponibles; no publican una suma parcial como total.

## 5 Gráficas del panorama general

### Valor de mercancías por mes

**Origen:** tabla 551, campos `ValorDolares` y `TipoOperacion`; 501 aporta el tipo de cambio cuando se solicita MXN. El eje horizontal contiene los meses del rango y el vertical el importe en la moneda elegida. Hay una serie de importaciones, código 1, y otra de exportaciones, código 2.

**Cálculo:** para cada mes y tipo de operación, sumar `ValorDolares` convertido individualmente cuando corresponda. La gráfica dibuja líneas; un valor no disponible interrumpe la línea. Se usan segmentos rectos sin relleno. Los puntos representan meses observados; no hay suavizado ni pronósticos entre meses.

**Lectura:** permite comparar valor declarado y su evolución. No mide utilidades, unidades físicas ni facturación de 505. Las tarjetas de importación y exportación separan los tipos de operación 1 y 2. El agregado histórico de todas las operaciones se conserva en la API, sin mostrarse como una tarjeta combinada. Las filas 551 no se deduplican silenciosamente.

### IGI e IVA por mes y forma de pago

**Origen:** 557 aporta contribución, forma de pago e importe; 551 identifica si la partida corresponde a importación; 501 aporta el tipo de cambio para USD. Se toma clave 6 para IGI y clave 3 para IVA, separando `FormaPago = 0` (efectivo) y `FormaPago = 21` (crédito en IVA e IEPS, identificado en la aplicación como CERTIVA). La clave 1 corresponde a DTA y no entra como IGI.

**Cálculo:** seleccionar por separado los registros de cada forma de pago, relacionarlos con su llave completa de partida y comprobar que 551 tiene una única operación identificable igual a 1. Sumar `ImportePago` por mes, contribución y forma. El importe original es MXN; para USD se divide cada registro entre su tipo de cambio.

No se calculan los impuestos multiplicando una tasa estimada por un valor de mercancía. Se suman los pagos registrados. No se añade 510 a 557 y tampoco se añade 702. Las exportaciones quedan fuera; las otras formas de pago de importación aparecen en un desglose independiente y no se añaden a FP 0/21. Varios registros de pago de una partida se suman como registros distintos; no hay una deduplicación automática de pagos repetidos en origen.

**Calidad:** si un pago candidato no tiene partida u operación verificable, se incrementa `unmatchedTaxRows`. Los totales de ambos impuestos para ese conjunto quedan sin dato, aunque el fallo se haya detectado en uno de ellos. Un tipo de cambio inválido afecta al agregado que necesita esa conversión. Sin NP verificable, el pago puede seguir entrando al total del impuesto si la partida y operación sí están verificadas.

La tabla aparece únicamente en Contribuciones y presenta IGI FP 0, IVA FP 0 e IVA FP 21. Se retiró IGI FP 21 de esta tabla y de su equivalente en el PDF; su tarjeta también se retiró del análisis y de la comparativa, conservando los datos originales de API/CSV. Cada forma tiene su propio conteo de pagos sin cruce verificable; una forma incompleta no invalida la otra. No se añade CERTIVA al efectivo. Las tres tarjetas muestran IGI FP 0, IVA FP 0 e IVA FP 21; el análisis por NP sigue limitado a FP 0. No es una conciliación bancaria.

### Números de parte con mayor IGI

**Origen:** pagos de IGI elegibles de 557, partida de 551 y observaciones de 558. Agrupa por número de parte principal y fracción arancelaria, acumulando los meses seleccionados.

**Cálculo:** resolver el NP, sumar IGI por combinación NP/fracción, ordenar por IGI descendente y conservar las primeras diez combinaciones con NP inequívoco e IGI positivo. Los empates se ordenan por NP y fracción. El eje de categorías muestra ambos identificadores.

Una misma parte en dos fracciones aparece como dos combinaciones. Las combinaciones fuera del Top 10 no se agrupan en «Otros» en esta gráfica. Los pagos sin NP, con NP ambiguo, IGI cero o negativo no forman parte del ranking. Si hay importes IGI desconocidos entre PN identificados, el ranking completo queda sin dato porque no puede ordenarse con certeza. Por ello la suma de sus barras no debe equipararse al IGI total del rango. El ranking aparece únicamente en Contribuciones.

### Fracciones con mayor IGI pagado - Forma de pago 0

**Origen:** los pagos de contribución 6 de 557 con FormaPago 0, relacionados por llave completa con partidas de importación de 551. La moneda USD utiliza el tipo de cambio del pedimento en 501. No exige observaciones 558 ni un PN identificado.

**Cálculo:** agrupar los importes IGI de `partTaxes.rows` por fracción, sumar cada grupo antes de ordenar y mostrar las diez fracciones con mayor suma positiva. Se conservan ajustes negativos dentro de la suma; no se cuenta el número de pagos ni se utiliza ValorDolares. Los empates se ordenan por código de fracción.

**Filtros:** respeta el rango, moneda, aduana, operación y documento del reporte, además del filtro local por fracción y la búsqueda PN/alternativos. Sin búsqueda PN incluye los pagos sin PN que tengan una fracción verificable. Con cobertura 551/557 incompleta, pagos sin cruce verificable o importes IGI desconocidos, el ranking queda sin dato. El Top 10 puede ser menor que el IGI total y no añade Otros.

### Rectificaciones por aduana y patente

**Origen:** pedimentos de 501 y rectificaciones de 701. La primera tabla agrupa por aduana y patente, mostrando ambas columnas, conteos, porcentaje de la combinación y porcentaje global. La segunda agrupa solo por patente. Se cuentan registros distintos de 701 sin exigir que ClaveDocumento diga R1: el archivo conserva claves AF, IN, RT y otras.

Se cuentan llaves distintas (año, mes de carga, patente, pedimento y aduana). Repeticiones de la misma llave se cuentan una vez; apariciones en meses diferentes se conservan por separado. `% aduana / patente = rectificados de la combinación / pedimentos 501 de esa combinación * 100`. `% patente = rectificados de la patente / pedimentos 501 de esa patente * 100`. `% global = rectificados del grupo / total 501 de la selección * 100`. El total global respeta también el filtro de aduana y se muestra explícitamente. Los totales recalculan tasas, no promedian porcentajes. Base cero, llaves inválidas, 701 sin 501 o falta de cobertura producen tasas sin dato, no cero.

La tabla se reutiliza en Control y calidad. Más rectificaciones no demuestra por sí solo un error operativo. No se infieren responsables logísticos, costos ni sustituciones fiscales, ni se netean importes de 702. La imagen muestra 1,105 pedimentos, pero los datos de referencia enero-junio con todas las operaciones arrojan 1,527 y 31 rectificados; 7/1,527 = 0.46%, consistente con su porcentaje global de Manzanillo. Se muestran todas las aduanas, incluidas las que no tienen rectificaciones. Los conteos por aduana proceden de 501, no se fuerzan a coincidir con la imagen.

## 6 Gráficas de comercio y mercancías

### Pedimentos por aduana y por clave de documento

**Origen y fórmula:** llaves distintas por mes de 501, agrupadas por `SeccionAduanera` o `ClaveDocumento`. Comparten la población de la tarjeta Pedimentos; las filas repetidas no inflan las barras. Si una misma llave tiene categorías contradictorias, se cuenta una sola vez en Sin especificar. Las llaves incompletas dejan el conteo y ambos rankings sin dato.

Se muestran ocho categorías y el resto en Otros. Seleccionar una barra identificable aplica o retira el filtro correspondiente. Otros y Sin especificar no activan filtros. El título «clave de documento» describe las claves A1, AF, IN, RT, etc.; no las confunde con TipoOperacion 1/2. Las descripciones usan el apéndice 2 del Anexo 22 aportado.

### Importaciones por país de origen y exportaciones por país de destino

Son dos gráficas separadas. Agrupan 551 por `PaisOrigenDestino` y suman `ValorDolares`, convertido individualmente si se solicita MXN. La primera incluye solo TipoOperacion 1; la segunda, solo 2. Un mismo país puede aparecer en ambas con importes distintos. El campo no representa necesariamente el país del proveedor de 505.

Cada ranking muestra ocho países y Otros. Campos vacíos van a Sin especificar. Ambas gráficas conservan todos los filtros generales: si se filtra solo importación, la gráfica de exportaciones queda sin registros elegibles.

### Fracciones arancelarias

**Origen y fórmula:** agrupar 551 por `Fraccion` y sumar el valor de mercancías convertido a la moneda elegida. Las ocho fracciones con mayor agregado se presentan individualmente y las restantes en «Otros».

Esta gráfica agrupa por Fraccion; no desglosa NICO. Compara valor declarado, no IGI pagado ni tasas. Una fracción con mucho valor puede no ser la de mayor IGI. Los grupos monetarios utilizan suma estricta: un valor inválido o no convertible vuelve no disponible ese grupo. «Otros» también queda sin dato si alguno de sus grupos no tiene agregado válido. Los empates se resuelven por clave y los valores no disponibles usan cero únicamente para ordenar, no para presentarse como importes cero.

## 7 Selección aduanera y alertas de calidad

### Selección aduanera

**Origen:** SEL, campo `SemaforoFiscal`. Por cada mes se cuentan los registros con código 0 como rojo y con código 1 como verde. Estos conteos permanecen como datos; la gráfica de eventos de selección se retiró. Son eventos, no pedimentos únicos.

Un pedimento puede tener más de un evento. Valores diferentes de 0 o 1 se contabilizan como sin clasificar y dejan la tasa de rojo sin dato. Sin SEL disponible no se sustituye por cero. El indicador no mide resultados de inspección ni multas.

La tarjeta «Selecciones en rojo» se obtiene como 100 multiplicado por eventos rojos dividido entre eventos rojos más verdes. El total del rango se calcula sobre todos sus eventos; no es el promedio simple de los porcentajes mensuales. Con 2 rojos y 8 verdes resulta 20 %. Si no hay eventos rojos o verdes, o existe algún evento sin clasificar, el porcentaje no está disponible.

### Resolución del número de parte

El extractor lee 558 en orden de `SecuenciaObservacion`. Reconoce etiquetas explícitas NP, N/P, P/N, Part Number, No. Parte y Número de parte, seguidas de los separadores admitidos por el patrón. También admite una etiqueta sola y un token en la secuencia inmediatamente siguiente. Los códigos se normalizan a mayúsculas. Textos como NA, N/A, NULL o SIN no se aceptan como parte verificable.

`NP: 1200-1030847AN OTRO NP: 1200-1030847AND` representa un principal y un alternativo del mismo artículo. El importe se asigna una sola vez al principal; el alternativo se muestra y permite localizarlo. Repetir el mismo NP en varias observaciones no multiplica el pago. No se deduce que partes de artículos distintos sean equivalentes solo porque sus códigos se parezcan.

Una única parte principal distinta permite asignación. Más de una principal distinta genera estado ambiguo. Ninguna principal genera estado faltante, incluso si solo se encontró un alternativo. No se adivinan NP a partir de números de serie, lotes o números sueltos.

Las alertas se calculan sobre las llaves identificables de 551 de la selección, no solo sobre las que pagaron IGI. Una partida sin impuestos puede tener alerta y una sin llave completa se cuenta aparte. Permanecen mientras la fuente vigente siga incorrecta; cambiar un filtro puede ocultarlas porque cambia la población. La corrección requiere actualizar la fuente y publicar una nueva versión, o regenerar la referencia si se utiliza esa fuente.

### Contadores de calidad

- `invalidNumericValues`: cuenta celdas ausentes o inválidas, no filas. Revisa seis campos de 501: peso, fletes, seguros, embalajes, incrementables y deducibles; tres de 551: valores en dólares, aduana y comercial; ValorDolares de 505; e ImportePago de 510, 557 y 702. Una fila puede aportar varias incidencias.
- `orphanItems`: cuenta filas 551 del rango sin llave de pedimento presente en 501, antes de los filtros dimensionales. No es un importe.
- `duplicateDeclarationRows`: filas 501 con llave válida menos llaves válidas distintas. Las filas con llave incompleta se cuentan por separado en `invalidDeclarationKeys`.
- `missingExchangeRates`: filas 501 seleccionadas cuya llave no tiene tipo único y válido. Cuenta filas, no necesariamente pedimentos únicos. No incluye por sí solo todas las filas de otras tablas huérfanas de 501.
- `invalidItemKeys`: filas 551 con llave de partida incompleta. Las alertas detalladas de NP solo pueden construirse para llaves completas.
- `unmatchedTaxRows`: registros candidatos de IGI/IVA con forma 0 sin una operación verificable mediante 551. Las exportaciones verificadas se excluyen de los pagos de importación, pero no se marcan como relaciones fallidas.

## 8 Tarjetas y comparaciones

### Indicadores del análisis

Las ocho tarjetas del análisis muestran: pedimentos únicos de 501; valor de importaciones de 551 (TipoOperacion 1); valor de exportaciones de 551 (TipoOperacion 2); IGI FP 0; IVA FP 0; IVA FP 21; llaves distintas de 701; y porcentaje rojo de SEL. El número principal corresponde al rango seleccionado. Para rojo es una proporción del conjunto, no una suma de porcentajes. Los impuestos usan pagos de importación de 557, verificados con 551: contribución 6 para IGI y 3 para IVA. FormaPago 0 es efectivo y 21 es crédito IVA/IEPS (CERTIVA); sus importes nunca se combinan en una tarjeta. Las gráficas por PN conservan únicamente FP 0.

La variación pequeña de cada tarjeta compara el último mes disponible del rango contra el mes calendario inmediatamente anterior. No compara el total del rango contra otro total. El mes anterior puede quedar fuera del rango seleccionado; si falta o su valor base es cero, no hay porcentaje comparable. En enero esta tarjeta no busca automáticamente diciembre del año anterior.

Las minibarras conservan los meses del rango: un valor ausente deja un espacio, cero se representa con una marca neutral en la base y los valores positivos se escalan proporcionalmente. Son auxiliares; los datos exactos están en las tablas.

### Distribución de vistas y comparación

Panorama general contiene las ocho tarjetas y la tendencia comercial. Comercio y mercancías contiene los cinco rankings por aduana, documento, países y fracción. Contribuciones contiene la tabla mensual de pagos, los dos rankings de IGI en efectivo por PN y fracción, y las comparativas por PN. Control y calidad contiene rectificaciones y alertas. Fuentes y métricas documenta los cálculos. Cada bloque detallado se muestra en una única pestaña y las tarjetas se concentran en Panorama general.

La comparación general entre meses se consulta en Comparativa mensual. Las comparativas por PN permanecen en Contribuciones y sus meses respetan el rango del análisis. Un mes sin cobertura conserva sin dato. Las variaciones de las tarjetas siguen comparando el último mes disponible contra el anterior; la tasa de rojo se expresa en puntos porcentuales.

### Comparativa mensual entre años

La página Comparativa mensual consulta un resumen anual ligero: una petición si los dos meses pertenecen al mismo año y una por año si son diferentes. Permite comparar años diferentes y usa la misma fuente y moneda en ambos lados. Sus controles no heredan los filtros de aduana, operación o documento de Análisis de operaciones; las consultas se realizan sin esos filtros. No se calcula identificación de PN ni rankings en este resumen.

La gráfica de dos barras admite ocho indicadores: pedimentos, valor de importaciones, valor de exportaciones, IGI FP 0, IVA FP 0, IVA FP 21, partidas y rectificaciones. Partidas significa cantidad de filas 551. Las ocho fichas muestran ambos valores, diferencia absoluta `B - A` y variación relativa con la misma fórmula anterior. No incluye la tasa roja en esta página.

Ejemplo: A = 100 y B = 120 producen diferencia de 20 y variación de 20 %. A = 0 y B = 120 producen diferencia de 120, pero no un crecimiento porcentual definido. Si A falta, tanto la diferencia como el porcentaje quedan sin dato. La página solo analiza información; crear Excel consolidados pertenece a Cargas.

### Comparativa de IGI e IVA por NP

Las dos tablas de Contribuciones muestran los impuestos por combinación NP principal/fracción. Acumulan los pagos elegibles por mes y presentan mes base, mes comparado, diferencia y variación. Son tablas de la aplicación web, independientes del formato de los archivos XLSX.

Cuando el mes está dentro del rango y tiene 551 y 557, la ausencia de pagos para una combinación significa cero. Un agregado de esa combinación que no pudo convertirse permanece sin dato. Sin cobertura o fuera del rango se muestra sin dato. El cálculo de diferencia requiere ambos importes y el porcentaje requiere además base no cero.

Los pagos de partidas sin NP verificable se agrupan como «Sin asignar» por fracción; no se reparten arbitrariamente entre candidatos. Pueden contribuir a los totales de IGI/IVA, aunque se excluyan del Top 10. Los filtros independientes revisan PN principal/alternativos y fracción y afecta las filas y su exportación CSV, no las gráficas generales. La paginación de 25 filas no limita los totales ni la descarga completa de resultados filtrados por esa búsqueda.

## 9 Gráfica de Resumen operativo

«Actividad por mes», traducida desde el rótulo técnico «Actividad por periodo», se obtiene de `overview()` y no del reporte comercial. Para cada mes con versión activa toma `counts_json.rows` de la ejecución y dibuja una barra. El eje vertical mide registros procesados; no dólares, pedimentos únicos ni exclusivamente partidas 551. Abarca todas las filas de datos contadas por el motor para esa carga.

Incluye meses de diferentes años en orden cronológico. No mezcla la referencia Excel ni añade filas de consolidados anuales. No aplica los filtros de Análisis de operaciones. Un reproceso publicado cambia la barra de su mes porque cambia la versión activa.

Las tarjetas del resumen usan la misma población para meses publicados y registros procesados. «Ejecuciones» cuenta el historial mensual y anual completo del ámbito, no solo versiones activas. «Observaciones» suma advertencias y errores de las versiones mensuales activas; no es el número de alertas NP del análisis comercial. Ninguno de estos indicadores mide duración del worker o su tasa de éxito.

## 10 Métricas auxiliares de la API y el CSV

La exportación general CSV contiene metadatos de filtros y las métricas mensuales de la respuesta. Puede incluir campos que no tienen una gráfica visible. Los sufijos `Usd` y `Mxn` identifican la unidad del campo, aunque la moneda de presentación actual sea otra.

| Campo o grupo | Fuente y cálculo | Precaución |
| --- | --- | --- |
| imports y exports | Llaves distintas 501 con operación 1 o 2 | No son las series monetarias |
| customsMxn y commercialMxn | ValorAduana y ValorComercial de 551 | No son ValorDolares ni necesariamente coinciden entre sí |
| invoiceUsd e invoices | Suma ValorDolares y conteo de filas 505 | Facturación separada de mercancías 551 |
| headerPaymentsMxn | Suma ImportePago de 510 | Todas las formas de pago |
| itemPaymentsMxn | Suma ImportePago de 557 | Todas las contribuciones y formas; no equivale a IGI pagado |
| paymentDifferencesMxn | Suma ImportePago de 702 | Diferencias separadas, no sumar como nuevo IGI |
| weightKg | Suma PesoBrutoMercancia de 501 | Kilogramos, no moneda |
| freightMxn e insuranceMxn | TotalFletes y TotalSeguros de 501 | Importes por registro de cabecera |
| packingMxn e incrementsMxn | TotalEmbalajes y TotalIncrementables de 501 | No sumar automáticamente a ValorDolares |
| deductionsMxn | TotalDeducibles de 501 | El servicio lo reporta, no lo resta de la gráfica comercial |
| simpleIncidents y seriousIncidents | Filas INCI con grado S o G | Conteo de registros |
| correctInspections | Filas INCI con grado C | C es correcto, no una incidencia |

Todos estos totales utilizan suma estricta: un valor vacío, inválido o no finito vuelve no disponible su agregado. Una tabla presente y vacía suma cero. Los campos con sufijo Mxn o Usd conservan la moneda indicada; los rankings y los campos sin sufijo de impuestos usan la moneda de la respuesta.

IGI e IVA utilizan siempre el procedimiento específico de partidas y forma 0 descrito antes. Los rankings monetarios de países, fracciones, proveedores, Incoterms, contribuciones de cabecera y formas de pago también usan conversión individual y suma estricta. Solo países y fracciones se dibujan hoy entre esos rankings monetarios.

## 11 Ejemplo de conciliación por partida

Supóngase una partida de importación con una llave completa y un tipo de cambio histórico de 17. En 558 aparece el NP principal 1200-1030847AN y su alternativo 1200-1030847AND. En 557 hay IGI clave 6 por 1,700 MXN y IVA clave 3 por 2,720 MXN, ambos con forma 0.

El total de esa partida es IGI de 100 USD e IVA de 160 USD. En las tablas por NP ambos se asignan una sola vez a 1200-1030847AN y su fracción. Buscar el alternativo encuentra esa misma combinación, no otra asignación de impuestos. El ranking Top 10 puede mostrar los 100 USD de IGI si la combinación queda entre las diez mayores del rango.

Si se añade otro registro IGI de 340 MXN para la misma partida y forma 0, se suman 20 USD adicionales: IGI total 120 USD. No se distribuye una sola fila de pago entre las dos etiquetas NP. Si en lugar de un alternativo se encuentra otro principal diferente, ambos pagos permanecen sin asignar a un NP concreto hasta corregirlo.

Si falta el tipo de cambio, los 2,040 MXN de IGI siguen siendo consultables en MXN, pero su agregado convertido a USD queda sin dato. Si falta una operación verificable de 551, el pago no se considera importación confirmada y los totales se señalan pendientes de conciliación. Son problemas distintos y requieren correcciones distintas.

## 12 Cómo revisar un resultado

1. Anotar fuente, año, rango, moneda y filtros visibles. No comparar una referencia Excel con una carga publicada sin comprobar sus versiones.
2. Revisar meses y tablas disponibles. Identificar si el número visible es cero, no disponible o abreviado.
3. Consultar el conjunto de origen con la misma versión y mes. Reconstruir la llave de pedimento o partida según la métrica.
4. Aplicar los filtros y comprobar si se cuentan filas, llaves únicas o eventos. Revisar duplicados antes de sumar importes.
5. Para moneda, convertir registro a registro con el TipoCambio de su 501. Para IGI/IVA, verificar contribución, forma 0 y operación de importación.
6. Para NP, revisar todas las observaciones 558 de la partida, distinguiendo principal y alternativos. No eliminar pagos solo porque falta el NP.
7. Sumar primero con precisión completa y redondear al presentar. En rankings revisar la agrupación «Otros» o la exclusión del Top 10, según corresponda.
8. Comparar el resultado detallado o CSV y conservar evidencia de fuente y versión. Si se corrige una carga, publicar una nueva versión y volver a consultar.

Las herramientas de una gráfica permiten ver su tabla de datos, descargar PNG y ampliar la vista. Las descargas CSV se ofrecen a nivel de reporte y de números de parte. El PNG incluye título, periodo, filtros, moneda y notas de la gráfica. Presentan el mismo conjunto calculado; cambiar entre gráfica y tabla no recalcula otra población. La descarga CSV general incluye meses del rango; el CSV por NP incluye las combinaciones buscadas y los meses que tienen datos en esas combinaciones. Una celda vacía exportada no debe reemplazarse masivamente por cero.

## 13 Referencias de implementación

Esta revisión se apoya en los siguientes módulos del proyecto. Las referencias son rutas relativas a DataStage y nombres de funciones para facilitar su localización aunque cambien los números de línea.

- `backend/app/modules/reporting/analytics.py`: `published_dataset`, `summarize`, `metrics`, `ranking`, `change`. Fuentes, filtros, cobertura, tarjetas, series mensuales y rankings.
- `backend/app/modules/reporting/trade_values.py`: `identity`, `item_identity`, `normalized`, `number`, `strict_sum`. Identificadores y aritmética.
- `backend/app/modules/reporting/part_taxes.py`: `part_numbers`, `exchange_rates`, `convert`, `import_payments`, `paid_totals`, `paid_taxes`. Moneda, impuestos y NP.
- `backend/app/modules/reporting/queries.py`: `overview`. Resumen operativo y conteos de versiones activas.
- `backend/app/cli/analytics_reference.py`: `read_workbook`, `canonical_value`, `main`. Importación y conciliación de referencias.
- `backend/app/persistence/business.py` y `catalog.py`: nombres de tablas, columnas y correspondencia con encabezados originales.
- `frontend/src/app/features/analytics.html` y `analytics.ts`: gráficas visibles, indicadores, filtros, Top 10, comparativas y CSV.
- `frontend/src/app/shared/month-comparison.ts`: consultas de ambos meses, indicador seleccionado, diferencias y porcentajes entre años.
- `frontend/src/app/shared/analytics-chart.ts`: presentación, nulos, líneas, ejes, tabla de datos y exportaciones de la gráfica.
- `frontend/src/app/features/dashboard.ts`: gráfica y tarjetas del resumen operativo.
- `frontend/src/app/core/customs-labels.ts`: descripciones de catálogos en español e inglés.

Las pruebas relevantes están en `backend/tests/test_analytics.py`, `backend/tests/test_part_taxes.py`, `frontend/src/app/features/analytics.spec.ts` y `frontend/src/app/shared/month-comparison.spec.ts`. La publicación mensual y sus versiones se revisan también en `backend/tests/test_month_workflows.py`. Estas pruebas automatizadas no sustituyen la conciliación de la fuente de la empresa ni validan por sí solas una conexión de producción con SQL Server.

Los cambios de esta entrega separan Cargas en Mensuales y Consolidados y dejan Comparativa mensual solo para análisis. El exportador común `backend/app/modules/engine/exporter.py` produce los nuevos XLSX como rangos normales con filtros y encabezados oscuros legibles, sin tablas nativas de Excel. No escribe celdas vacías con formato ni filas totalmente vacías. El motor omite líneas ASC compuestas solo por separadores antes de añadir Periodo, ArchivoOrigen y FolioOrigen. Cada campo conserva su posición y los ceros se mantienen como datos; no se combinan celdas. Los archivos ya generados requieren una nueva exportación. Este formato de salida no modifica las fórmulas del dashboard.



## 14 Criterios de claridad de esta revisión

- **IGI e IVA por PN:** se conservan en las tablas comparativas. Se retiraron sus dos gráficas mensuales y se conserva el Top 10 de IGI por PN, junto al nuevo ranking por fracción. Se mantienen los filtros PN/fracción. Los importes de PN sin identificar se presentan explícitamente debajo y siguen formando parte del total general de efectivo. El Top 10 queda sin dato si falta cobertura 551/557/558 o hay un importe IGI desconocido entre los PN identificados.
- **Formas de pago:** la tabla principal separa FP 0 y FP 21. Una tabla adicional desglosa todas las otras formas presentes en las importaciones, con IGI, IVA y número de registros. FP 13 significa pago ya efectuado; FP 22 es garantía en IVA e IEPS. No se suman al efectivo. Los pagos sin cruce verificable invalidan únicamente la forma de pago afectada.
- **Selección:** se dibujan también eventos con código distinto de 0/1 como Sin clasificar. La tasa de rojo queda no disponible si existe alguno; no se ocultan para publicar una tasa aparentemente completa.
- **Rectificaciones e importes:** el valor declarado suma las filas 551 de la fuente activa. No reconstruye una operación fiscal final ni netea rectificaciones contra sus originales. La interfaz y el PDF explican este alcance; 702 permanece separado.
- **Cargas:** marcadores de posición con brillo muestran el estado real de las consultas. Desaparecen al resolver o fallar; no generan porcentajes ficticios. Se respeta la preferencia de movimiento reducido.
- **Unidades y precisión:** los ejes, tablas y tooltips distinguen importes monetarios, conteos enteros y porcentajes. Los tooltips monetarios muestran dos decimales; cero y Sin dato tienen estados distintos. Las etiquetas extensas se dividen en líneas y se pueden consultar completas en la tabla.

### Conciliación del Excel de abril de 2026

La lectura independiente y el servicio arrojan: 250 pedimentos, 3 pedimentos rectificados; IGI en efectivo 1,195,277 MXN; IVA en efectivo 5,421 MXN; IVA FP 21 de 31,167,147 MXN; e IGI FP 13 de 2,180,339 MXN en tres registros. Estos últimos importes permanecen separados de FP 0.

Con el catálogo del repositorio, el IVA en efectivo de abril queda sin PN identificado (296.99328052510873 USD). Por eso la gráfica de IVA por PN identificado es cero aunque el total general de IVA en efectivo sea positivo. La nota de atribución muestra la diferencia. Un catálogo local distinto puede modificar la atribución, sin alterar el total de impuestos.

### Tipos de celda de los Excel nuevos

Los importes, valores, cantidades, pesos, tasas y conteos reconocidos por su encabezado se exportan como números nativos, aptos para SUMA y SUMAR.SI.CONJUNTO. Las fechas válidas se exportan como fechas nativas; los valores con hora conservan fecha y hora. Las columnas de identificación conservan texto y ceros iniciales. Se mantiene la precisión del dato en la celda, aunque el formato monetario muestre dos decimales. Valores inválidos o que exceden 15 cifras significativas permanecen en texto para preservar el original. Los archivos existentes requieren una nueva generación para adoptar los tipos nuevos.

### Desglose de rectificaciones por patente

La tabla principal añade Patente y separa filas por aduana/patente. Su porcentaje de grupo divide pedimentos rectificados de esa combinación entre pedimentos 501 de la misma combinación. La segunda tabla agrupa todas las aduanas seleccionadas por patente: porcentaje de patente = rectificados de esa patente / pedimentos de esa patente × 100. El porcentaje global usa en ambos casos la base 501 filtrada completa. Ambas tablas comparten el total global y no deben sumarse entre sí. Se usan llaves distintas de año, mes, patente, pedimento y aduana, por lo que registros repetidos no multiplican los conteos. Se mantienen las reglas de cobertura, llaves inválidas y rectificaciones sin 501. El PDF contiene ambos desgloses.
