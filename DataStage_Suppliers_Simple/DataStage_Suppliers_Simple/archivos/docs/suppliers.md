# Proveedores acumulativos

Suppliers está centrado en dos archivos: Extranjeros y Nacionales. Cada publicación mensual actualiza las listas acumulativas y prepara los dos Excel. No se requiere revisar ni editar cientos de proveedores para descargarlos.

## Uso

1. En **Listas originales**, un administrador selecciona sus dos archivos `.xls` o `.xlsx` y pulsa **Usar estas listas**. Se conservan sus columnas, proveedores, orden, formato y hojas auxiliares. También funciona si ya había meses procesados. La lista nacional puede contener únicamente los encabezados si no hay proveedores de ese tipo.
2. Al publicar los meses siguientes, ambos Excel quedan disponibles automáticamente. Las altas nuevas llevan toda la fila amarilla. En el siguiente reporte pasan a **Sin modificación** y dejan de resaltarse.
3. Se puede descargar cada lista o ambas juntas. El selector permite volver a un reporte anterior. Las descargas utilizan el mismo reporte y no generan otra versión ni consumen las altas.
4. **Actualizar listas** aplica el reconocimiento al historial que ya existía antes de esta actualización. Si nada cambió, conserva el mismo reporte. Al abrir la pantalla solo se leen las listas; no se recorre todo el historial en cada visita.

No se necesita volver a cargar las listas originales cada mes. Pueden seleccionarse de nuevo si es necesario incorporar una base o un formato actualizado. Las filas iniciales se conservan incluso cuando comparten nombres similares; la normalización evita agregar otra vez las variantes detectadas en las facturas.

## Fuentes y reconocimiento

- **505 Facturas** aporta los nuevos proveedores y sus datos. Los nacionales se identifican por un RFC válido en **IndentFiscalProveedor**, que corresponde a la columna **P** del archivo con columnas de trazabilidad. Se usa el nombre del campo; su posición puede cambiar en otros formatos.
- El cruce con **501** distingue las importaciones de las exportaciones. Las facturas de exportación corresponden a clientes y no crean proveedores. El RFC del contribuyente no sustituye al RFC del proveedor.
- **507 no genera altas nacionales**. Solo respalda el indicador de operaciones virtuales de proveedores identificados en 505 o presentes en las listas originales. Una autorización IMMEX no se interpreta como RFC. El indicador conserva **Si** cuando hay evidencia en el historial vigente o en la lista inicial; un mes sin virtuales no lo reinicia.
- Los espacios, puntuación, acentos, mayúsculas, sufijos y abreviaciones societarias se normalizan para comparar nombres. Las variantes suficientemente próximas se reconocen automáticamente. Las filiales con nombres distintos permanecen separadas. La equivalencia confirmada **PTM-AEC → PTM CORPORATION** reutiliza la fila original.
- La falta de identificador extranjero, país, calle u otros datos opcionales no bloquea los archivos. Los datos ausentes quedan vacíos. Un país vacío no se sustituye por un país adivinado. La separación operativa nacional se basa en el RFC de 505; la ausencia de país en una fila extranjera sigue significando país desconocido.
- Un proveedor ya incorporado permanece en la lista acumulativa aunque no tenga facturas en otro mes.

## Archivos y consistencia

Nacionales conserva **RFC**, **Operaciones virtuales** y **Estatus**. Extranjeros conserva **Nombre o Razón social**, **Apellido Paterno**, **Apellido Materno**, **País **, **Domicilio**, **Cliente/Proveedor** y **Estatus**, incluido el espacio original del encabezado País.

Los XLS se convierten a XLSX conservando el formato de celdas, fuentes, bordes, alineaciones, anchos, alturas y hojas auxiliares. Los XLSX seleccionados se utilizan como plantilla, conservando sus hojas y validaciones. Los dos archivos se generan desde una instantánea común. Los nombres y RFC se exportan como texto literal, sin ejecutarlos como fórmulas. Las filas nuevas heredan el formato del cuerpo y añaden únicamente el relleno amarillo.

Los reportes publicados permanecen inmutables. Una importación o corrección posterior produce listas actualizadas sin modificar descargas históricas. Los reintentos de publicación no duplican reportes. Las decisiones y registros históricos de la versión anterior se conservan; su administración avanzada deja de formar parte de la pantalla principal.

## Administración

Los ámbitos de acceso y roles existentes se conservan. Reader descarga los archivos de su ámbito. Operator o Admin actualiza listas. Admin incorpora las listas originales. Los Excel privados, sus datos y la base de datos no se incluyen en el código ni se importan automáticamente en otros ámbitos.

Se admiten hasta 5 MB y 5000 filas por lista. `xlrd` permite leer XLS y `openpyxl` permite conservar y generar XLSX; ambas dependencias están declaradas en el backend. No se necesita una migración adicional sobre las migraciones de Suppliers que ya existen.

La alternativa administrativa para importar una base histórica sigue disponible en `app.cli.suppliers` y se explica en [validación de fuentes](supplier-source-validation.md). Este flujo usa una extracción privada guardada bajo `.data`; no requiere publicar los archivos de proveedores en Git.
