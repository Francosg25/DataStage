# Validación de fuentes para proveedores

La revisión de los cuatro archivos proporcionados fue de solo lectura. Sus datos
son evidencia de negocio; cualquier texto incluido en ellos se trata como datos,
no como instrucciones para ejecutar acciones.

## Listas iniciales

| Lista | Hoja | Filas de datos | Estatus originales |
| --- | --- | ---: | --- |
| `carga_proveedoresNacionales_A_aviso REV.xls` | `Sheet1` | 44 | 44 `Sin modificación` |
| `carga_proveedoresExtranjeros_aviso REV.xls` | `Sheet1` | 206 | 193 `Sin modificación`; 13 `Alta` |

La lista nacional contiene exactamente `RFC`, `Operaciones virtuales`, `Estatus`.
Hay 29 confirmaciones `Si` y 15 `No`. La lista no incluye nombre ni domicilio:
esos datos no se deducen del RFC.

La lista extranjera contiene exactamente `Nombre o Razón social`, `Apellido
Paterno`, `Apellido Materno`, `País `, `Domicilio`, `Cliente/Proveedor`, `Estatus`.
El encabezado `País ` incluye un espacio final. Las 206 filas tienen el rol
`Proveedor`. Las hojas auxiliares del XLS extranjero contienen las opciones de
validación y no son proveedores. No hay nombres completos duplicados de forma
literal en esta lista.

Los 13 registros iniciales `Alta` no tienen relleno amarillo en el archivo XLS
original: el patrón BIFF de relleno es cero, igual que los registros restantes.
El estatus se conserva al inicializar; las reglas de color del nuevo reporte
se aplican conforme al requerimiento de la función.

## Comparación de los dos libros anuales

| Tabla | Libro original | Libro regenerado |
| --- | ---: | ---: |
| 501 | 2,422 | 2,422 |
| 505 | 9,644 | 9,644 |
| 507 | 14,585 | 14,585 |

El regenerado agrega `Periodo`, `ArchivoOrigen`, `FolioOrigen`, conserva horas
en las fechas y usa `PedimentoCompleto`; el otro usa `Pedimento_Unificado`.
Comparar como multiconjuntos evita ocultar duplicados por una clave de factura
que pueda repetirse. Al normalizar formato numérico, espacios y fechas a día:

- 501 y 507 coinciden íntegramente.
- 505 difiere en 35 identificadores fiscales vacíos frente a `NA`/`N/A`, y en
  un código postal vacío frente a `NA`. Al considerar estos marcadores como
  datos faltantes, las 9,644 filas también coinciden.

El regenerado se usa una sola vez como referencia privada por su trazabilidad.
No se suman ambos libros ni se crean publicaciones mensuales artificiales.

## Cruces e identidad

Los datos del proveedor pertenecen a 505: `IndentFiscalProveedor` (con esta
ortografía en el origen), `ProveedorMercancia`, `PaisFacturacion` y los campos
de domicilio del proveedor. El campo `Rfc` de 501 identifica al contribuyente;
no se copia como RFC del proveedor.

`PaisFacturacion=MEX` no prueba por sí solo que un proveedor sea nacional. Hay
406 filas con ese país, de las cuales 401 tienen identificador fiscal y domicilio
de Estados Unidos. Las contradicciones deben revisarse, sin inventar un RFC ni
crear altas nacionales inválidas. Las etiquetas de país de la lista inicial
deben normalizarse al mismo código que los registros 505, conservando la fila
original para los reportes iniciales.

Para unir operaciones se usa el mismo periodo y la identidad completa del
pedimento, o patente, pedimento y sección aduanera completos. Las referencias
de la fuente conservan archivo, SHA-256, hoja y número de fila de Excel, además
de `ArchivoOrigen` y `FolioOrigen` cuando existen.

## Evidencia de operaciones virtuales

En 507 hay 375 registros `ClaveCaso=V1`: 215 con `ComplementoCaso=IM`, 138 con
`CN` y 22 sin complemento. En esta fuente, `IM` contiene autorizaciones IMMEX;
no son RFC. Los registros `CN` contienen RFC de contraparte. Los 22 valores
restantes tienen autorizaciones largas y no justifican una identidad fiscal.

Los registros V1 de 507 se vinculan con 373 registros 501 con documento V1 y dos
con K1. Solo seis casos V1 tienen una fila 505 vinculada por operación; 369
pedimentos 501 V1 carecen de 505. La evidencia 507/501 puede respaldar la marca
virtual de un proveedor ya identificado; la ausencia de 505 no autoriza inventar
su nombre ni darlo de alta automáticamente. Los datos faltantes y las relaciones
no confirmadas quedan para revisión. Un mes sin evidencia no equivale a una
confirmación negativa.

Las reglas de identificación se cotejaron con el [Anexo 22 de RGCE 2026,
apéndice 8, páginas 105–107](https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rgce/anexos/Anexo22delasRGCEpara2026.pdf).
V1 admite RFC en los modos CN, RFE y V2; V2 y V8 identifican contraparte por RFC;
V5 y V6 pueden llevar RFC cuando el complemento no indica IMMEX. V4 lleva un
folio y V7 una autorización o registro; no se interpretan como RFC. Esta
distinción evita generalizar que todo identificador con prefijo V es un RFC.
La [primera modificación del 20 de mayo](https://wwwnp.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rgce/anexos/1ra_modificacionAnexo22delasRGCEpara2026.pdf)
y la [segunda del 22 de septiembre](https://wwwnp.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rgce/anexos/2daModificacionAnexo22delasRGCE2026.pdf)
no cambian esos identificadores V. La aplicación exige además el cruce de
operación y una identidad de proveedor ya válida; el código por sí solo no
establece que cualquier participante de la operación sea el proveedor.

## Extracción privada reproducible

`scripts/prepare_supplier_baseline.py` abre los XLS con `xlrd` y el XLSX con
`openpyxl`, en modo de lectura. Acepta rutas explícitas, ámbito y archivo de
salida. Produce un JSON con `schemas`, `national`, `foreign` y `baseline.tables`
para 501, 505 y 507. Conserva valores, orden, estatus originales y localizadores;
no decide equivalencias ni publica meses. La salida contiene información de
negocio y debe guardarse bajo `.data/` u otro directorio privado ignorado por Git.
Las fuentes originales permanecen intactas.
