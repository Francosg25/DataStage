# Proveedores acumulativos

Suppliers está centrado en dos archivos: Extranjeros y Nacionales. Cada publicación mensual actualiza las listas acumulativas y prepara los dos Excel. No se requiere revisar ni editar cientos de proveedores para descargarlos.

## Uso

1. En **Administración → Proveedores → Listas originales**, un administrador selecciona sus dos archivos `.xls` o `.xlsx` y pulsa **Usar estas listas**. Se conservan sus columnas, proveedores, orden, formato y hojas auxiliares. También funciona si ya había meses procesados. La lista nacional puede contener únicamente los encabezados si no hay proveedores de ese tipo.
2. Al publicar los meses siguientes, ambos Excel quedan disponibles automáticamente. Las altas nuevas llevan toda la fila amarilla. En el siguiente reporte pasan a **Sin modificación** y dejan de resaltarse.
3. Se puede descargar cada lista o ambas juntas. El selector permite volver a un reporte anterior. Las descargas utilizan el mismo reporte y no generan otra versión ni consumen las altas.
4. **Actualizar listas** aplica el reconocimiento al historial incluido. Después de establecer el corte descrito abajo, solo usa septiembre de 2026 y meses posteriores. Si nada cambió, conserva el mismo reporte. Al abrir la pantalla solo se leen las listas; no se recorre todo el historial en cada visita.

La pantalla **Proveedores** muestra el selector de reporte y las dos listas descargables. La carga inicial, el corte de operaciones y las herramientas de reinicio y respaldo están en **Administración → Proveedores**. El icono de configuración de la pantalla principal abre directamente esa pestaña para usuarios autorizados.

No se necesita volver a cargar las listas originales cada mes. Pueden seleccionarse de nuevo si es necesario incorporar una base o un formato actualizado. Las filas iniciales se conservan incluso cuando comparten nombres similares; la normalización evita agregar otra vez las variantes detectadas en las facturas.

## Empezar desde septiembre de 2026 y retirar las incorporaciones anteriores

Si una importación agregó proveedores de enero a agosto que no debían entrar, un **Admin** puede abrir **Administración → Proveedores → Mantenimiento de listas → Recalcular desde septiembre de 2026** y después **Guardar respaldo y recalcular**. Primero deben estar guardadas las dos listas originales correctas.

La acción guarda un respaldo privado y reconstruye el catálogo desde esas mismas dos plantillas. Se conservan todas sus filas originales, aunque el proveedor no tenga facturas en septiembre. Las altas adicionales se detectan únicamente en cargas mensuales **publicadas** desde septiembre de 2026, incluido ese mes. Octubre y los meses siguientes se acumulan normalmente; no es necesario volver a cargar los Excel cada mes.

Se reemplazan únicamente el catálogo generado, evidencias, equivalencias y reportes de proveedores de ese ámbito. Se reponen las equivalencias explícitas cuyo proveedor principal sigue en las listas originales. Las demás decisiones quedan en el respaldo. Los pedimentos, documentos de entrada y salida, cargas mensuales, períodos, datos de gráficas y auditoría general permanecen intactos. Los Excel de proveedores anteriores al reinicio dejan de estar disponibles en el selector; su contenido está dentro del respaldo.

Después aparece **Operaciones incluidas desde: 9/2026** dentro de la configuración de proveedores. Actualizar las listas, reiniciar el backend o volver a importar las plantillas no elimina este corte. Reprocesar agosto tampoco incorpora sus proveedores a las listas. Un proveedor anterior que ya esté en la lista original sigue apareciendo, porque esa lista es la base autorizada.

En **Administración → Proveedores → Mantenimiento de listas**, **Descargar respaldo de proveedores** entrega un JSON administrativo con el catálogo, evidencias, equivalencias, reportes y plantillas anteriores. El enlace sigue disponible al volver a entrar. Solo un Admin del mismo ámbito puede descargarlo. Se guarda en el almacenamiento persistente de documentos; debe incluirse en los respaldos habituales. Su restauración requiere intervención administrativa sobre una copia de la base: no hay un botón de restauración automática. No borres tablas ni carpetas manualmente.

La limpieza se ejecuta al confirmar dentro de tu aplicación; actualizar el código no borra datos por sí solo. Si falla la creación del respaldo, no se limpia el catálogo. Las solicitudes con una versión desactualizada se rechazan para evitar eliminar cambios concurrentes.

No se necesita una nueva migración: el corte y la referencia al respaldo se guardan en la configuración existente de Suppliers. El respaldo se registra como un documento separado, sin asociarlo a una carga mensual.

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

Los reportes publicados permanecen inmutables durante el uso habitual. La acción administrativa de reinicio descrita arriba los retira después de respaldarlos. Una importación o corrección posterior produce listas actualizadas sin modificar descargas históricas. Los reintentos de publicación no duplican reportes. Las decisiones y registros históricos de la versión anterior se conservan; su administración avanzada deja de formar parte de la pantalla principal.

## Administración

Los ámbitos de acceso y roles existentes se conservan. Reader descarga los archivos de su ámbito. Operator o Admin actualiza listas. Admin incorpora las listas originales. Los Excel privados, sus datos y la base de datos no se incluyen en el código ni se importan automáticamente en otros ámbitos.

Se admiten hasta 5 MB y 5000 filas por lista. `xlrd` permite leer XLS y `openpyxl` permite conservar y generar XLSX; ambas dependencias están declaradas en el backend. No se necesita una migración adicional sobre las migraciones de Suppliers que ya existen.

La alternativa administrativa para importar una base histórica sigue disponible en `app.cli.suppliers` y se explica en [validación de fuentes](supplier-source-validation.md). Este flujo usa una extracción privada guardada bajo `.data`; no requiere publicar los archivos de proveedores en Git.

## Verificación de este cambio

Se añadieron pruebas de regresión para el corte inclusivo, reemplazos de meses anteriores, publicaciones posteriores, filas amarillas, conservación del formato original, respaldos, permisos, aislamiento de ámbitos, reintentos y fallo de almacenamiento. También se añadieron pruebas del flujo y contrato HTTP del frontend.

El corte y la reconstrucción ya se verificaron con **23 pruebas del backend en Windows/Python 3.13.5**. Para esta simplificación de la interfaz pasaron **115 pruebas del frontend** y la compilación de producción (`npm run build`). Se comprobaron la navegación directa, la carga diferida de la configuración, ambos idiomas y los controles de permisos, confirmación y versión del catálogo. La revisión visual en el equipo de destino queda pendiente; estas comprobaciones no validan SQL Server, Entra ni un servidor de producción real. Los comandos de comprobación, con las dependencias ya instaladas, son:

```text
cd backend
python -m pytest tests/test_supplier_start_period.py tests/test_supplier_api.py tests/test_supplier_baseline.py tests/test_supplier_monthly_automatic.py
cd ../frontend
npm test -- --watch=false
npm run build
```

En Windows se puede usar `..\.venv\Scripts\python.exe` dentro de backend y `npm.cmd` en lugar de npm. Hacer la primera comprobación con una copia de la base local y del directorio de documentos, no con la base de producción.
