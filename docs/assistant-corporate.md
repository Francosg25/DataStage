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

### Eliminar una conversación

Selecciona la conversación en la barra superior y pulsa el botón de la papelera. La confirmación identifica el chat y explica qué se eliminará. Cancelar conserva el historial. Al confirmar, se borran los mensajes, su evidencia y métricas guardadas y las descargas generadas de esa conversación en DataStage. Los meses publicados, documentos originales, proveedores, otras conversaciones y reglas de negocio no se modifican.

El borrado exige el autor y ámbito autenticados, incluso para administradores. Queda un evento `agent.conversation.delete` con identidad, fecha, ID y cantidades, sin copiar el texto de la conversación. Los datos se eliminan en una transacción; una respuesta que llega tarde desde otra pestaña no vuelve a crear el historial. No se cambian tablas ni se necesita una nueva migración para esta función.

Primero se revocan las descargas en la base. La API intenta eliminar los archivos físicos y el worker reintenta cada minuto, en lotes de 20, si Windows/OneDrive o el almacenamiento los mantienen bloqueados. Los registros `stored_documents.status = pending_delete` permiten reintentar sin perder la ubicación. Una base de datos no disponible pospone el reintento; no se borran archivos operativos ni archivos que compartan clave de almacenamiento con otro documento. API y worker deben seguir usando el mismo directorio persistente. Los bloqueos permanentes se diagnostican en los registros `datastage.agent`.

Este borrado es de DataStage: no purga copias de respaldo ni las respuestas que ya se hayan almacenado en Foundry (`store=True`). No se afirma un borrado integral en Azure; la retención y eliminación de esas copias debe gestionarse por separado con TI y las APIs de Azure. No se envía ninguna llamada de inferencia para borrar un chat.

### Contexto, memoria y aprendizaje

| Capacidad | Estado actual |
| --- | --- |
| Continuar la conversación abierta | Sí: la siguiente pregunta recibe los últimos 20 mensajes previos, hasta 8,000 caracteres por mensaje |
| Recuperar una conversación al volver a la página | Sí: se muestran hasta los últimos 100 mensajes guardados y sus archivos |
| Recordar automáticamente otros chats del usuario | No: los chats son independientes; abrir uno nuevo no carga los anteriores |
| Recordar preferencias personales entre conversaciones | No se ha implementado una memoria de preferencias |
| Consultar información de meses nuevos | Sí, cuando se publique: las herramientas consultan las fuentes actuales del ámbito autorizado |
| Entrenar o modificar el modelo con cada conversación | No: guardar contexto no es entrenar el modelo |

Por ejemplo, dentro del mismo chat puedes pedir «haz el mismo reporte para junio» después de uno de mayo. En una conversación nueva tendrás que indicar de nuevo el reporte y los filtros. Un proveedor corregido en el catálogo se encontrará al consultar ese catálogo actualizado; una corrección escrita sólo en un chat no modifica la regla de negocio ni el catálogo compartido.

Una futura memoria persistente debería guardar preferencias y definiciones confirmadas, aisladas por usuario/ámbito, con opciones para revisar, corregir y olvidar. Los conocimientos de negocio compartidos requieren validación y una fuente mantenida. No conviene convertir automáticamente cada respuesta o corrección del chat en una regla corporativa. Esta entrega no activa memoria entre chats ni entrenamiento continuo. [Microsoft distingue la persistencia de conversaciones del entrenamiento de modelos](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy).

La interfaz conserva español e inglés, agrupa fuentes y consumo como detalles desplegables, muestra las descargas como tarjetas y elimina de la lectura los enlaces técnicos duplicados de archivos verificados. Enter envía; Mayús + Enter inserta una línea. Un campo vacío no se presenta como un error de validación.

Para instalar únicamente esta mejora del chat en una instalación que ya tiene las once herramientas: actualiza `feature/foundry-agent-setup` con el procedimiento Git habitual y reinicia API, worker y frontend con los comandos de siempre. No requiere instalar dependencias, migrar tablas ni ejecutar otra vez `--upgrade-local`; conserva la versión y el modelo ya configurados. El reinicio del worker activa los reintentos de limpieza de archivos bloqueados.

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
