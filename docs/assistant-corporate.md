# Asistente corporativo de DataStage

El chat consulta los datos publicados del usuario, calcula resultados verificables y genera archivos reales. El modelo interpreta la solicitud y explica los resultados; las consultas y los archivos se ejecutan en Python dentro de DataStage. Se conservan las métricas y reglas de negocio del dashboard.

## Qué puedes pedir

| Petición | Resultado |
| --- | --- |
| ¿Qué meses publicados tengo en 2025? | Inventario completo de meses, sin deducirlos del rango anual |
| ¿Qué proveedores facturaron más en mayo? | Consulta 505 con sumas USD por proveedor, calculadas sobre toda la selección |
| Crea un Excel de mayo y junio de 2025 con pedimento, patente, aduana y fecha de pago | Hoja de detalle 501 con las columnas solicitadas |
| Añade otra hoja con el total de facturas y valor en dólares por proveedor | Segunda hoja 505 agregada; 505 y 501 mantienen su propio nivel |
| Cruza las partidas 551 con el RFC y tipo de cambio del pedimento 501, calcula su valor en MXN y crea un Excel | Una hoja combinada por partida, con relación verificada, columna calculada y fuentes |
| Desglosa los pagos 557 por país de origen de la partida 551 y convierte los importes a USD con 501 | Consulta de tres tablas, conservando el nivel del pago y validando el tipo de cambio |
| Genera un PDF con los KPI de septiembre de 2026 en USD | Informe de análisis con las gráficas y fuentes del dashboard |
| Compara importaciones, exportaciones, IGI e IVA de dos meses | Cálculos de análisis existentes, con moneda, formas de pago y cobertura explícitas |
| ¿Qué significa FP21? | Explicación apoyada en extractos de las guías aprobadas disponibles |

Los ejemplos requieren los periodos y tablas indicados. Si faltan, el asistente debe informar la limitación y solicitar los datos necesarios. La pregunta siguiente puede referirse a la anterior; el backend conserva los mensajes y envía los últimos 20 como contexto. El historial recupera hasta los últimos 100 mensajes. No hay memoria ilimitada.

## Datos, cálculos y Excel

- `describe_data` enumera las 26 tablas registradas y, para una tabla, sus columnas, tipos, unidades y relaciones permitidas. Cada campo incluye su nombre calificado, por ejemplo `501.TipoCambio`. No revela tablas de identidad, configuración, conversaciones o credenciales.
- `query_data` recibe una especificación cerrada: tabla base, periodos, columnas, cruces, cálculos, filtros AND, agrupaciones, métricas y orden. Los identificadores de tabla y columna se resuelven contra el catálogo; no se acepta SQL, código, rutas o identidades del modelo.
- Las versiones se seleccionan una sola vez, con ámbito del usuario, estado publicado y pertenencia mensual. Se exige cobertura de la tabla en cada periodo solicitado. Una tabla ausente no se convierte en un cero.
- Los cálculos se realizan sobre todas las filas seleccionadas, hasta 50,000 filas de origen por consulta y 24 meses. En un cruce, el límite suma las filas leídas de todas sus tablas. Si se excede se rechaza la consulta; no se presentan totales parciales. Los filtros se aplican dentro de esa selección acotada: si un mes por sí solo supera el límite, reducir sólo el texto del filtro no elimina ese límite.
- La vista previa del chat contiene como máximo 100 resultados. Los campos `matchedSourceRows`, `totalResultRows`, `previewLimited` y `complete` distinguen filas de origen, resultados y muestra.
- Se admiten conteo de filas, conteo distinto, suma, promedio, mínimo y máximo. Una suma de dinero no omite valores numéricos inválidos. El total en moneda extranjera exige agrupar o filtrar la moneda. Para conversiones fiscales y métricas oficiales se utiliza `get_analytics`, que comparte la lógica del dashboard.
- Cada hoja puede combinar una tabla base y hasta dos relaciones verificadas. Se conserva como máximo una fila por fila base; no se realizan cruces arbitrarios entre 505/551 o entre 510/557/702 que multipliquen o sumen niveles distintos. Consulta las reglas siguientes.
- El Excel contiene hasta cinco hojas solicitadas y una hoja adicional de fuentes: consulta, tablas, periodos, ejecución, versión, filas, unidades y diagnóstico del cruce. Se exportan los resultados completos; no sólo la vista previa del modelo.
- El libro tiene un límite conjunto de 500,000 celdas y 20 MiB. No se truncan resultados para cumplirlo. Los valores que no caben en una celda se rechazan.
- Los importes y medidas válidos son celdas numéricas; las fechas válidas son fechas Excel. Los identificadores como pedimento, factura, patente y fracción conservan texto y ceros iniciales. Los códigos de catálogo numéricos se escriben como números con su formato de ceros. Los valores inválidos o con más precisión de la que Excel conserva se mantienen como texto y se contabilizan en la hoja de fuentes.
- El contenido proveniente de proveedores y documentos se escribe como texto literal: no se convierte en fórmula, enlace o programa ejecutable.

### Cruces y columnas calculadas

La tabla base determina qué representa una fila. Para analizar pagos por partida se parte de **557**, se añade la descripción de **551** y, si se necesita, información del pedimento **501**. Para analizar mercancías se parte de **551** y se añade **501**. Invertir ese orden para repartir un importe de pedimento entre partidas no es una asignación válida por sí sola.

| Relación disponible | Claves verificadas dentro de la misma ejecución mensual |
| --- | --- |
| Tabla con claves de pedimento → 501 | Patente + Pedimento + SeccionAduanera |
| Tabla con claves completas de partida → 551 | Patente + Pedimento + SeccionAduanera + Fraccion + SecuenciaFraccion |

`describe_data` devuelve las relaciones concretas de cada tabla base. No permite unirse consigo misma ni elegir llaves arbitrarias. Las fuentes se fijan a las versiones mensuales activas del ámbito autenticado: dos pedimentos iguales en meses, versiones o ámbitos distintos no se mezclan. No es un cruce entre periodos.

- **`left`** conserva las filas base sin coincidencia, con campos relacionados vacíos. **`inner`** las excluye; el diagnóstico indica cuántas no encontraron correspondencia. Una tabla ausente en un mes se informa como falta de cobertura, no como una tabla vacía.
- La tabla relacionada debe contener una sola fila por clave. Si tiene duplicados o si alguna clave del conjunto leído está incompleta, se rechaza la consulta con una explicación. No se elige una fila al azar ni se omite silenciosamente. Esta validación precede al filtrado del resultado.
- Los campos relacionados usan `tabla.Campo`. Los nombres sin prefijo se refieren sólo a la tabla base. Los alias de cálculo deben ser únicos y pueden utilizarse en cálculos posteriores, filtros, agrupaciones y métricas.
- `calculations` permite hasta ocho cálculos numéricos por fila: `add`, `subtract`, `multiply`, `divide`, `percent_of` (`izquierda / derecha × 100`) y `percent_change` (`(izquierda − derecha) / abs(derecha) × 100`). El operando derecho es una columna o una constante decimal explícita. Después se filtra y agrupa. No se admiten fórmulas Excel, SQL ni programas del modelo.
- Se comprueban las unidades monetarias conocidas. Ejemplos: `551.ValorDolares × 501.TipoCambio` produce MXN; `557.ImportePago / 501.TipoCambio` produce USD. El tipo de cambio debe ser positivo. No se suman USD y MXN. La moneda de facturación se separa mediante filtro o agrupación también en importes calculados.
- Los resultados calculados se redondean a **15 dígitos significativos**, compatibles con la precisión numérica de Excel. Los valores originales no se reescriben. Si falta un operando o el denominador es cero, el cálculo queda vacío (`null`) y se cuenta en el diagnóstico. Un total que depende de valores ausentes queda no disponible, en vez de sumar sólo la parte conocida.
- Si una medida de la tabla relacionada se repite en varias filas base, no se permite sumarla ni promediarla, tampoco ocultando la repetición en otra agrupación o cálculo. Por ejemplo, no se suman los fletes completos de un pedimento una vez por cada partida. El tipo de cambio sí puede aplicarse a cada importe base. Los porcentajes y tipos de cambio no se suman.

Los diagnósticos incluyen coincidencias, ausencias, claves relacionadas repetidas en el detalle y cálculos no disponibles o con denominador cero. Que una relación sea muchos a uno permite enriquecer el detalle, pero no convierte un importe de pedimento en un importe por partida. Facturas 505 y partidas 551 siguen requiriendo una relación de negocio adicional para combinarlas de forma fiable. Para KPI fiscales y comparaciones mensuales oficiales se conserva `get_analytics`.

### Activar los cruces en tu agente existente

Esta mejora no añade dependencias, tablas de base de datos ni endpoints. Sí cambia la definición de las herramientas y las instrucciones registradas en Foundry. Después de actualizar el código y detener la API, ejecuta **una vez** desde `backend`, en tu red corporativa:

```cmd
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --upgrade-local
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --check
```

Sin `--model`, se conserva el deployment configurado. El primer comando registra y comprueba una nueva versión del mismo agente, respalda `.env` y actualiza su versión local; conserva el estado de habilitación y el resto de la configuración. No lo repitas si ya terminó correctamente. Si la sesión ha expirado, usa `--login` con el mismo intérprete y reintenta el paso fallido. `--check` por sí solo no añade capacidades a una versión anterior.

Reinicia la API con tu comando habitual y abre una conversación nueva para que no arrastre una respuesta anterior que afirmara que no podía cruzar tablas. No hace falta cambiar el frontend ni el worker por esta mejora. La migración de memoria, si todavía está pendiente en tu instalación, se gestiona por separado con las instrucciones posteriores. En producción se registra y fija la versión con la identidad autorizada; no se usa un inicio de sesión personal interactivo.

Prueba con un mes publicado y sus tablas disponibles: «Genera un Excel de mayo de 2025 con las partidas 551, fracción y valor en dólares; añade RFC y tipo de cambio de 501, calcula valor en MXN y una segunda hoja con el total por fracción. Indica si alguna partida no pudo cruzarse». Contrasta los resultados con las fuentes y revisa la hoja **Fuentes**. La prueba automatizada es local y simulada; esta pregunta real sí invoca Foundry.

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
| Continuar la conversación abierta | Sí: la pregunta recibe los últimos 20 mensajes previos, hasta 8,000 caracteres por mensaje |
| Recuperar una conversación al volver a la página | Sí: se muestran hasta los últimos 100 mensajes guardados y sus archivos |
| Recordar preferencias entre conversaciones | Sí: las memorias personales que guardes y actives en el panel Memoria |
| Recuperar automáticamente todos tus chats anteriores | No: no se importan conversaciones antiguas ni se extraen notas automáticamente |
| Consultar información de meses nuevos | Sí, cuando se publique: las herramientas consultan las fuentes actuales del ámbito autorizado |
| Entrenar o modificar el modelo con cada conversación | No: guardar contexto o preferencias no entrena el modelo |

### Guardar y gestionar memoria personal

1. Pulsa **Memoria** en la cabecera del asistente y después **Añadir memoria**. También puedes pulsar **Recordar** debajo de uno de tus mensajes para prellenar una nota revisable.
2. Escribe un título y qué debe recordar. Ejemplo: **Mis reportes mensuales** / «Prefiero reportes en USD, con una hoja de detalle y otra de resumen por proveedor».
3. Comprueba **Usar mis memorias en los chats** y pulsa **Guardar**. Añadir una nota marca esa opción en el borrador; nada se guarda hasta confirmar. Cancelar no escribe cambios. Un mensaje demasiado largo se conserva íntegro en el borrador y debe resumirse: no se trunca para guardarlo.
4. Abre una conversación nueva. Las preferencias activas se incluyen como contexto en las siguientes preguntas, junto con las herramientas y las fuentes actuales. La pregunta explícita y el idioma elegido tienen prioridad. Si una preferencia entra en conflicto o resulta ambigua, el agente debe pedir aclaración.
5. En el mismo panel puedes editar, quitar una nota, desactivar su uso sin borrarla o elegir **Borrar toda la memoria**, con confirmación. Borrar un chat conserva estas notas; borrar las notas conserva los chats.

Se admiten hasta **12 notas por usuario y ámbito**, con títulos de 80 caracteres, contenido de 600 caracteres por nota y un límite conjunto de 6,000 caracteres. No se admiten títulos duplicados. Se incluye el conjunto activo completo y acotado; no se utiliza una base vectorial ni un buscador semántico. El indicador **Contexto personal** cuenta las notas incluidas en esa consulta; no garantiza que todas resultaran pertinentes ni que el modelo haya aplicado cada preferencia correctamente.

Esta implementación utiliza la base de DataStage: SQLite en desarrollo y SQL Server en producción. No crea un Memory Store de Foundry ni necesita otro deployment, embeddings, permisos Azure o una versión nueva del agente. El Memory Store administrado de Foundry es una alternativa en versión preliminar y su documentación indica que no admite integración VNet; por eso no se añade como requisito al entorno privado actual. Referencia: [memoria de Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory).

Las memorias se separan por la identidad y ámbito autenticados, incluso para administradores. La aplicación no acepta un usuario o ámbito enviado por el modelo o navegador para cambiar al propietario. Las escrituras y el borrado tienen control de versión: una pestaña antigua no puede sobrescribir una edición nueva o restaurar notas eliminadas silenciosamente. El evento `agent.memory.update` audita actor, cantidades y versión, sin copiar títulos ni contenido.

Sólo el usuario guarda las notas desde la interfaz. Decir «recuerda esto» en el chat no las persiste por sí solo: utiliza **Recordar**, revisa y guarda. El agente recibe instrucciones para no afirmar que realizó una escritura de memoria. Las notas se envían como datos de usuario de menor confianza, nunca como instrucciones del sistema ni evidencia de cifras. Las reglas del backend, los permisos, monedas, tablas y validaciones se conservan. Una nota que diga «estos dos proveedores son iguales» no cambia el catálogo compartido ni crea una equivalencia oficial. Ese cambio requiere el flujo de negocio correspondiente.

Guardar, editar o borrar notas no invoca el modelo. Incluir notas en una pregunta sí aumenta el contexto de entrada y puede aumentar tokens facturados. Las cifras reportadas siguen apareciendo en **Uso del modelo**. No se modifica el entrenamiento del modelo; [Microsoft distingue la persistencia del entrenamiento](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy).

El borrado o la desactivación se aplica al contexto personal de las siguientes consultas. No puede retirar información que una petición en curso ya envió a Foundry. Los mensajes anteriores pueden seguir conteniendo una preferencia que escribiste o una respuesta que la mencionó; para comprobar el efecto del borrado sin ese contexto, inicia un chat nuevo. No se copia automáticamente el bloque completo de notas al historial: sólo se registra cuántas se incluyeron y la versión del perfil en auditoría. Si el modelo cita una nota en su respuesta, ese texto sí forma parte del historial normal. La retención de Azure y los respaldos se gestiona por separado.

### Instalar la mejora de memoria

La migración aditiva **`20261022_0005`** crea `agent_memory_profiles` y `agent_memories`; no modifica columnas ni elimina conversaciones, archivos o datos de negocio. El esquema completo tiene 75 tablas. No se generan notas iniciales a partir de los chats existentes y la memoria empieza desactivada para cada usuario hasta que la active y guarde.

Actualiza el código con los servicios detenidos. Si tu SQLite local **ya está gestionado por Alembic**, aplica `..\.venv\Scripts\python.exe -m alembic upgrade head` desde `backend` **antes de reiniciar la API**. Si tu SQLite local fue creado con `create_all` y no está gestionado por Alembic, el arranque habitual crea las dos tablas nuevas; no uses `stamp` ni borres la base. No mezcles una creación automática de tablas con una revisión Alembic anterior pendiente de actualizar. En producción TI aplica la migración mediante la identidad separada y concede al runtime los permisos de las dos tablas, según [Linux directo](linux-direct.md). La API de producción no crea ni migra tablas al arrancar.

Reinicia API y frontend con los comandos habituales. El worker conserva su configuración. No se cambian dependencias, `.env`, autenticación, modelo, `INSTRUCTIONS` registrado ni las once herramientas. **No repitas `--upgrade-local` por esta función**: el contexto personal lo añade DataStage a cada petición, manteniendo la misma referencia del agente.

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
