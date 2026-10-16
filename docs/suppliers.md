# Proveedores acumulativos

La sección `/suppliers` reúne **Por revisar**, **Catálogo**, **Reportes** y **Equivalencias**. Los usuarios con acceso de lectura pueden consultar el catálogo, la evidencia y descargar reportes. Las altas, ediciones, decisiones, equivalencias y generación de reportes requieren Operator o Admin. Los datos y las decisiones se aíslan por el mismo ámbito que las cargas y se registran en la auditoría existente.

La publicación mensual incorpora automáticamente los registros 505 del historial vigente y solicita las dos listas Excel. El catálogo conserva proveedores aunque dejen de aparecer. La normalización de nombres ignora espacios, puntuación, acentos y mayúsculas. Las similitudes y las contradicciones se presentan para confirmar **Es el mismo proveedor** o **Es un proveedor nuevo**. Por ejemplo, `Johnson Eletric` y `Johnson Electric` se presentan como posible coincidencia; la decisión confirmada se reconoce automáticamente en meses posteriores. Las equivalencias pueden cambiarse o retirarse desde su pestaña. Las ediciones verifican la versión leída para evitar sobrescribir cambios concurrentes.

Los datos de identidad proceden de 505. Los cruces con 501 y 507 conservan las referencias a los registros de origen. El RFC del contribuyente en 501 no se asigna al proveedor. Los complementos de 507 que representan autorizaciones IMMEX no se interpretan como RFC. El país de facturación tampoco basta para resolver una identidad contradictoria. Los identificadores virtuales se interpretan de forma conservadora con base en el [Anexo 22 de las RGCE 2026, apéndice 8](https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rgce/compiladas/CompiladoAnexo22_2daRMRGCE2026.pdf).

**Operaciones virtuales** es Sí cuando existe evidencia confirmada en el historial vigente o una confirmación manual válida. Un mes sin evidencia no elimina el Sí de otro mes. El reproceso o la eliminación de un mes retira su evidencia del historial vigente. Las confirmaciones manuales pueden corregirse o retirarse. Cuando un alta nacional carece de evidencia suficiente, la revisión solicita confirmar Sí o No.

Cada reporte congela las dos listas en una sola transacción. Sus descargas se reconstruyen exclusivamente desde esa instantánea: editar el catálogo, retirar una equivalencia o publicar otro mes no cambia reportes anteriores. Las filas nuevas tienen estatus Alta y relleno amarillo en todas sus columnas. En el siguiente reporte pasan a Sin modificación. La inicialización conserva los estatus de las listas originales. Los reintentos deben reutilizar `Idempotency-Key`; una misma clave con otro contenido produce conflicto.

Si no hay dudas, el reporte mensual queda listo automáticamente al publicar. Si hay revisiones o confirmaciones nacionales faltantes, la solicitud conserva un borrador del catálogo y las fuentes de esa publicación. Al resolverlas se completan ambas listas automáticamente. Un mes cargado después no agrega datos al borrador anterior. El resultado mensual enlaza el reporte listo o las revisiones pendientes; también se consultan desde Reportes. Descargar un reporte existente no genera uno nuevo ni consume sus altas.

## Inicialización local y evidencia histórica

La extracción de los XLS originales y del anual se documenta en [validación de fuentes](supplier-source-validation.md). El archivo de extracción contiene información privada y permanece bajo `.data`, fuera de Git. Su ámbito debe coincidir con el ámbito configurado; las listas nunca se distribuyen automáticamente a otras empresas.

Con las migraciones aplicadas, desde `backend`:

```powershell
..\.venv\Scripts\python.exe -m app.cli.suppliers --seed ..\.data\supplier-seed.json --scope local --initial-report --output ..\.data\supplier-reports
..\.venv\Scripts\python.exe -m app.cli.suppliers --seed ..\.data\supplier-seed.json --scope local --baseline-only
```

El primer paso conserva las 250 filas iniciales y crea una instantánea repetible. Los 13 estatus Alta que ya estaban en la lista extranjera se conservan como datos históricos; las filas amarillas identifican altas nuevas detectadas por la aplicación. El segundo incorpora una sola vez la evidencia del anual regenerado, sin inventar ejecuciones mensuales. Ambos pasos admiten reintentos sin duplicar datos.

Una publicación mensual sustituye la evidencia inicial del mismo mes. La evidencia sustituida permanece histórica y no vuelve a estar vigente al eliminar la publicación posterior.

Las tablas de persistencia se incorporan mediante una migración aditiva de Alembic. En producción se aplica con la identidad de migración habitual antes de actualizar API y worker. El inicio local también aplica las migraciones.
