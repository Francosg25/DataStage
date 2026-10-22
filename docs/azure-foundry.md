# Configurar el asistente DataStage en Microsoft Foundry

Guía del proyecto, revisada el 21 de octubre de 2026. El dashboard funciona sin IA. El asistente necesita un proyecto Foundry, un modelo desplegado y una identidad autorizada. Esta guía no crea recursos ni activa consumo en Azure por sí misma.

**Para una cuenta y laptop corporativas:** no necesitas instalar Azure CLI en tu equipo para avanzar. Puedes revisar el proyecto, el modelo y sus datos de conexión desde [Microsoft Foundry](https://ai.azure.com/) en el navegador. Registrar las funciones de DataStage requiere ejecutar el script Python del repositorio en un entorno autorizado por TI; una máquina o proceso de Azure con identidad administrada es la ruta recomendada. Si tu organización permite Azure CLI en la laptop, se ofrece como alternativa al final de la guía. No sabemos qué herramientas, permisos o redes habilita la política de tu empresa.

| Paso | Dónde se hace | Qué se necesita |
| --- | --- | --- |
| Ver proyecto y modelo | Navegador corporativo | Acceso al proyecto Foundry |
| Revisar la definición de DataStage | Laptop o entorno de desarrollo autorizado | Repositorio y Python del proyecto; sin conexión a Azure |
| Registrar las funciones | Ejecutor corporativo autorizado | Repositorio, Python, acceso de red a Foundry e identidad con permiso para crear versiones |
| Responder desde DataStage | Backend donde esté desplegada la API | Identidad para invocar el agente, configuración de la versión y acceso a las fuentes de datos |

## Inicio local en Windows con una versión de agente ya registrada

Esta ruta reutiliza Python y las dependencias instaladas. Usa CMD y el mismo intérprete autorizado que inicia el backend. La sesión personal es exclusiva de `DATASTAGE_ENVIRONMENT=development` y `DATASTAGE_AUTH_MODE=development`, cuyo acceso está limitado a loopback. No se usa en un servidor compartido ni en producción.

Desde `backend`, configura los identificadores reales sin cambiar las opciones de base de datos, documentos, ámbito u otros módulos:

```bat
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --configure-local --project-endpoint "https://<RECURSO>.services.ai.azure.com/api/projects/<PROYECTO>" --tenant-id "<TENANT_ID_GUID>" --model "<NOMBRE_DEL_DESPLIEGUE>" --agent-name "<NOMBRE_DEL_AGENTE>" --agent-version "<VERSION_EXISTENTE>"
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --login
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --check
```

`--configure-local` actualiza únicamente las claves de Foundry en `backend/.env`, mantiene los demás valores y comentarios y guarda el contenido anterior en `.data/config-backups/` si ya existía el archivo. Las opciones de invocación y acciones quedan desactivadas. Los respaldos son privados: pueden contener otros valores sensibles del `.env` y no se incluyen en Git ni en las entregas.

La configuración valida los valores nuevos antes de guardar; puede sustituir un modo de autenticación anterior inválido por `interactive`. Las validaciones de desarrollo local y del resto de la aplicación siguen vigentes. Las variables heredadas por la terminal tienen prioridad sobre `.env`: si una sesión CMD conserva un modo inválido, ejecuta `set "DATASTAGE_FOUNDRY_AUTH_MODE="` antes de configurar y utiliza esa misma terminal para los pasos siguientes. Esto elimina únicamente esa variable de la sesión actual, sin cambiar las variables permanentes de Windows. Los únicos modos válidos son `default` e `interactive`.

`--login` es el único comando que abre el navegador. Inicia sesión corporativa y completa la MFA que corresponda. Azure Identity guarda los tokens en su caché cifrada del usuario del sistema operativo, con un nombre exclusivo para el tenant, proyecto y aplicación cliente. DataStage guarda solamente el registro no secreto de la cuenta en `%LOCALAPPDATA%/DataStage/Foundry/` en Windows. Estos datos quedan fuera del repositorio, OneDrive y los paquetes de instalación. Se rechaza almacenamiento de tokens sin cifrar. Referencias: [caché cifrada](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.tokencachepersistenceoptions), [registro de cuenta](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.authenticationrecord).

El cliente de desarrollo del SDK sirve para el piloto local si está permitido por la empresa. Si TI proporciona una aplicación pública de escritorio propia, añade `--client-id "<CLIENT_ID>" --redirect-uri "http://localhost:<PUERTO_APROBADO>"` a `--configure-local`. Ambos valores deben corresponder al registro aprobado por TI; este cliente es distinto de las identidades del servicio y de los registros SPA/API utilizados para entrar a DataStage.

`--check` consulta la versión exacta mediante GET y compara el modelo, las instrucciones y los contratos de las herramientas con el backend. No crea versiones, no llama al modelo y no modifica datos. Cuando indique `status: verified`, puedes activar la configuración local:

```bat
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --enable-local
```

Este comando vuelve a comprobar la versión y habilita Foundry en el `.env`. Reinicia únicamente la API con tus comandos habituales. El worker y el frontend siguen funcionando como antes. Abre `/agent` para hacer la primera consulta: las respuestas del modelo sí consumen tokens. Contrasta sus cifras con las gráficas usando los mismos filtros.

La API reutiliza la sesión cifrada y nunca abre un navegador al atender preguntas. Si la política corporativa requiere renovar la sesión o completar MFA, mostrará `foundry_login_required`; vuelve a ejecutar `--login` desde CMD. No es necesario registrar otra versión. La sesión depende de la cuenta de Windows y del equipo; no se copia al servidor Linux.

No uses `--apply` para comprobar la conexión: ese comando crea una nueva versión. Los comandos locales anteriores reutilizan la que ya existe y mantienen las acciones de consolidación/reproceso deshabilitadas.

## 1. Preparar el proyecto y el modelo

Abre [Microsoft Foundry](https://ai.azure.com/), selecciona tu directorio corporativo y entra al proyecto que utilizará DataStage. Si no existe, crea un recurso y proyecto con tu administrador. Selecciona una región y una implementación de modelo compatibles con agentes y llamadas a funciones. Guarda el **nombre exacto del despliegue**, que puede ser diferente del nombre comercial del modelo.

Copia el **endpoint del proyecto** desde su página principal. Su formato es `https://RECURSO.services.ai.azure.com/api/projects/PROYECTO`. No uses el endpoint de una implementación de modelo ni un identificador `asst_` de una API anterior. Este proyecto utiliza agentes versionados y Azure AI Projects 2.x. [Referencia de creación del agente](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/prompt-agent).

## 2. Solicitar accesos a TI o al administrador de Azure

Pide a TI estos datos y permisos concretos:

1. El directorio corporativo, suscripción, proyecto Foundry, **endpoint del proyecto** y nombre del despliegue del modelo. Confirma región, cuota y acceso de red desde el entorno donde se ejecutará DataStage.
2. Un entorno aprobado para ejecutar el backend y el comando de registro: por ejemplo, una VM Windows de desarrollo o un proceso de integración corporativo con acceso al repositorio y a Python. Si ese entorno está en Azure, solicita una **identidad administrada** para el proceso. Un ejecutor con identidad federada también puede funcionar si TI configura la identidad y las variables que espera Azure Identity.
3. Permiso de creación de versiones para la identidad que ejecutará `setup --apply`, por ejemplo **Foundry User** en el ámbito que TI determine. Para la identidad del backend que sólo invoca el agente, revisa **Foundry Agent Consumer**. La identidad administrada del proyecto Foundry puede requerir roles propios; no es automáticamente la identidad del backend.

La asignación de roles corresponde al administrador. Los nombres anteriores `Azure AI User` y `Azure AI Project Manager` pueden aparecer en entornos todavía no actualizados. Consulta [RBAC de Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry) para confirmar roles y ámbitos.

La identidad del backend ante Azure es distinta de la identidad del usuario de DataStage. DataStage conserva su propia autorización `Reader`, `Operator`, `Reprocessor`, `Auditor` y `Admin`, junto con `scopeId`. No se envían claves de Azure al navegador. No compartas contraseñas, tokens ni claves personales para resolver permisos.

## 3. Elegir la ruta de autenticación

**Ruta recomendada sin Azure CLI en la laptop:** entra al portal con tu cuenta corporativa para identificar el proyecto y el modelo. TI prepara un entorno aprobado con identidad administrada o federada y acceso de red. `DefaultAzureCredential`, usado tanto por el registro como por el backend, obtiene la identidad de ese entorno. El script no exige Azure CLI si ya encuentra una identidad válida. [Credenciales admitidas por Azure Identity](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python).

**Si sólo tienes acceso al portal:** puedes verificar el despliegue y probar un agente básico allí. El portal no permite agregar o actualizar las definiciones de las funciones personalizadas de DataStage. Para conectar `get_analytics` y las demás herramientas se requiere ejecutar el script con el SDK, o una integración equivalente por REST, desde un entorno autorizado. El navegador por sí solo no puede ejecutar estas funciones contra la API de DataStage. [Limitación del portal y llamadas a funciones](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling).

Si TI permite una herramienta de desarrollo ya instalada que Azure Identity reconozca, puede usarse en un entorno de desarrollo, con los permisos anteriores. El acceso al portal con el navegador no autentica automáticamente al proceso Python. El modo `default` excluye el navegador; el modo `interactive` local utiliza la sesión cifrada creada explícitamente mediante `--login`, como se explica arriba. En Azure, prefiere identidad administrada para el backend. No guardes secretos en Angular ni en Git.

En Linux de producción configura `DATASTAGE_FOUNDRY_AUTH_MODE=default`, junto con endpoint, modelo, nombre y versión. En producción se excluyen las sesiones de CLI, PowerShell, VS Code, broker y caché personal del usuario. Una VM de Azure o un entorno federado puede proporcionar la identidad administrada o de carga de trabajo configurada por TI. Un servidor Linux interno no obtiene una identidad administrada por el simple hecho de ejecutar Linux: TI debe proporcionar una identidad de servicio admitida, por ejemplo una aplicación con certificado y `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_CERTIFICATE_PATH`. El certificado privado se entrega por separado y debe ser legible por la cuenta que ejecuta la API; se excluye del paquete y de Git. `AZURE_CLIENT_ID` identifica al servicio que invoca Foundry, no al frontend de DataStage. La plantilla es `deploy/linux/runtime.env.example`.

## 4. Preparar la configuración del entorno aprobado

En el entorno donde se registrará el agente, configura estos valores y sustituye los marcadores. En Windows PowerShell puedes usar la forma siguiente; en un pipeline, define las mismas variables en la configuración segura del trabajo:

```powershell
$env:DATASTAGE_FOUNDRY_PROJECT_ENDPOINT = 'https://<RECURSO>.services.ai.azure.com/api/projects/<PROYECTO>'
$env:DATASTAGE_FOUNDRY_MODEL = '<NOMBRE_DEL_DESPLIEGUE>'
$env:DATASTAGE_FOUNDRY_AGENT_NAME = 'datastage-assistant'
$env:DATASTAGE_FOUNDRY_ENABLED = 'false'
$env:DATASTAGE_ALLOW_AGENT_COMMANDS = 'false'
```

Las variables de esta sesión serán heredadas por los procesos iniciados desde ella. Para el backend desplegado, configura los mismos valores como variables del servicio; `DATASTAGE_FOUNDRY_ENABLED` debe seguir en `false` hasta registrar y probar una versión. `Settings` también lee `.env` en el directorio de trabajo del proceso; el lanzador local ejecuta el backend desde `backend`, por lo que un `.env` únicamente en la raíz no basta para ese lanzador. La identidad administrada se configura en el servicio Azure, no mediante una clave en este bloque.

## 5. Registrar el agente con las herramientas de DataStage

Primero consulta la definición en tu laptop o en el entorno de desarrollo autorizado. Este comando no se conecta a Azure y no necesita Azure CLI:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m app.modules.foundry.setup
Pop-Location
```

Revisa el modelo, nombre y herramientas. Cuando TI haya preparado el entorno autorizado, ejecuta allí el mismo repositorio con las dependencias Python de `backend/requirements.lock` instaladas. En una VM Windows con `.venv` en la raíz, el comando es:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --apply
Pop-Location
```

En otro sistema operativo, ajusta únicamente la ruta al Python del entorno virtual. Este segundo comando sí escribe una nueva versión en Azure. Guarda el `name` y `version` devueltos. No ejecutes repetidamente `--apply` para comprobar conectividad porque cada ejecución crea una versión. La identidad del ejecutor debe poder obtener un token y crear versiones en el proyecto; iniciar sesión en la web desde la laptop no aporta ese token al proceso remoto.

Las funciones se registran desde el SDK y se ejecutan dentro del backend DataStage. Configurar un agente sólo en el portal no conecta automáticamente las herramientas con tus datos. [Funcionamiento de las llamadas a funciones](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling).

Cada consulta utiliza `agent_reference` con nombre y versión exactos. Las instrucciones y las definiciones de herramientas se obtienen de esa versión: no se vuelven a enviar como parámetros `instructions` ni `tools` de `responses.create`, porque Foundry rechaza esa combinación con `invalid_payload`. El idioma seleccionado en la interfaz se transmite mediante un mensaje de contexto `developer` generado por el backend; el historial recibido sólo admite mensajes de usuario y asistente. La continuación con resultados de herramientas mantiene la misma referencia y `previous_response_id`. El backend sigue validando los argumentos, permisos y ámbito antes de ejecutar cada función. Si se cambian las instrucciones o los contratos registrados, prepara y comprueba una nueva versión antes de habilitarla.

Todos los mensajes enviados en `input` incluyen explícitamente `type: "message"`, tanto el contexto de idioma como los mensajes de usuario y asistente del historial. Aunque el SDK permite omitir ese discriminador, el endpoint del proyecto puede rechazarlo como `invalid_value` en `input[n]`. Los resultados de funciones conservan su tipo distinto `function_call_output` y su `call_id`.

## 6. Activar y probar la conexión

Usa la versión exacta devuelta, sin asumir que sea `1`. Configura estas variables **en el entorno que ejecuta la API** y reinicia ese proceso:

```powershell
$env:DATASTAGE_FOUNDRY_AGENT_VERSION = '<VERSION_DEVUELTA>'
$env:DATASTAGE_FOUNDRY_ENABLED = 'true'
```

Si estás probando en la misma máquina con el lanzador local, reinicia con `scripts/stop-dev.ps1` y `scripts/start-dev.ps1 -SkipInstall` desde la terminal que contiene esas variables. Si la API está hospedada por TI, reinicia el servicio desde su plataforma. La identidad del backend necesita permiso de invocación y salida de red al endpoint del proyecto.

Abre la pantalla `/agent` de la aplicación en ese entorno. Debe mostrar el asistente habilitado. Prueba estas consultas:

1. `¿Qué periodos publicados están disponibles?`
2. `Usando la referencia Excel de 2026, compara julio y agosto: pedimentos, ValorDolares de 551 y contribuciones de 510. Cita los indicadores.`
3. `¿Qué meses faltan y qué diferencias de conciliación se detectaron?`
4. Cambia a English y pregunta: `Compare July and August 2026 using the reference workbook. Keep USD and MXN separate.`

Las preguntas 2 y 3 requieren que la referencia privada esté preparada también en el backend conectado: genera el snapshot con `app.cli.analytics_reference` para el `scopeId` autorizado, coloca el archivo en almacenamiento aprobado y configura `DATASTAGE_ANALYTICS_REFERENCE_FILE` según `docs/analytics.md` del repositorio. No basta con que el Excel esté en la laptop. Si TI aún no autoriza esa transferencia, prueba `source=published` con los periodos cargados en SQL. Una referencia Excel disponible no implica que existan ejecuciones publicadas en SQL; el asistente distingue ambas fuentes.

Revisa que cada respuesta incluya evidencia y que sus cifras coincidan con el dashboard con los mismos filtros. La llamada `get_analytics` utiliza exactamente el mismo servicio que las gráficas.

## 7. Herramientas disponibles

| Herramienta | Función | Modifica datos |
| --- | --- | --- |
| `get_analytics` | Totales, evolución mensual, comparaciones, desglose y cobertura del dashboard | No |
| `get_run` | Estado e incidencias de una ejecución | No |
| `list_runs` | Ejecuciones recientes del ámbito autorizado | No |
| `get_data` | Muestra limitada de una tabla publicada | No |
| `compare_periods` | Comparación de conteos y cobertura operativa | No |
| `search_documentation` | Extractos de la documentación local aprobada incluida en el backend | No |
| `request_report` | Información del reporte Excel existente | No |
| `describe_data` | Catálogo autorizado de tablas, columnas, tipos, unidades y relaciones | No |
| `query_data` | Cruces muchos a uno verificados, cálculos por fila, filtros y agregaciones completas | No |
| `create_excel` | Excel de hasta cinco hojas con cruces, cálculos, tipos reales y fuentes | Crea una descarga privada; no cambia datos operativos |
| `create_analysis_report` | PDF de KPI y gráficas del dashboard con moneda y filtros explícitos | Crea una descarga privada; no cambia datos operativos |
| `list_attachments` | Inventario de adjuntos de esta conversación | No |
| `describe_attachment` | Hojas, columnas, tipos y advertencias de un adjunto privado | No |
| `query_attachment` | Consultas completas de adjuntos con vista previa paginada de filas y texto | No |
| `create_file` | Word, PowerPoint, CSV/JSON, PNG/SVG, HTML, PDF o XLSX desde consultas verificadas | Crea una descarga privada |
| `create_package` | ZIP de hasta diez descargas de esta conversación con manifiesto | Crea una descarga privada |
| `start_annual` | Crea una consolidación anual | Sí, requiere `Operator` o `Admin` |
| `reprocess_run` | Crea una nueva versión con motivo y versión esperada | Sí, requiere `Reprocessor` o `Admin` |

`search_documentation` no indexa automáticamente archivos del equipo ni el PDF completo. Los archivos que el usuario adjunta mediante el clip se consultan por separado con las herramientas de adjuntos: XLSX, CSV, PDF de texto, DOCX y PPTX. Se guardan por autor/conversación, sin importarlos como meses ni proveedores. Cargar archivos no ejecuta inferencia: los fragmentos consultados al enviar preguntas sí forman parte del contexto del modelo. Los PDF sin texto requieren OCR; las imágenes no se interpretan. La semántica del dashboard está implementada en código y en `docs/analytics.md`. Incorporar una base documental compartida ampliada sería una integración adicional.

`list_runs` devuelve dos conceptos separados: `items` contiene las ejecuciones recientes y `publishedPeriodCoverage` enumera todos los meses con una ejecución mensual activa y publicada del ámbito autorizado. El límite de resultados sólo aplica a `items`. Los rangos de los consolidados anuales son intervalos seleccionados, no prueba de que cada mes esté cargado. Por ejemplo, un consolidado enero-julio con cargas mensuales de mayo y junio debe informar únicamente mayo y junio como meses publicados. La cobertura se añade también a la evidencia. La entrega actual registra dieciséis herramientas de consulta/generación; las versiones anteriores de siete u once herramientas deben actualizarse antes de utilizar adjuntos y los nuevos formatos.

Ejecutar DataStage en la laptop no convierte el modelo en local: las preguntas del chat y una llamada real a `FoundryAgent.respond` invocan Azure y pueden consumir tokens de entrada y salida, incluidas las llamadas sucesivas para resolver herramientas. `--configure-local`, `--login`, `--check` y las pruebas con proveedor simulado no ejecutan inferencia del modelo. Un código HTTP de error por sí solo no determina si hubo procesamiento facturable. El consumo y el importe se verifican con las métricas y Cost Management de Azure. Referencia: [costos de Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs).

`create_excel` genera archivos personalizados reales: el modelo propone una especificación de columnas, relaciones autorizadas, cálculos numéricos, filtros y agrupaciones; Python consulta las versiones mensuales autorizadas y construye el XLSX completo. El catálogo admite enriquecer el detalle con 501 por pedimento y con 551 por clave completa de partida, sin multiplicar filas ni sumar medidas repetidas de un nivel distinto. No admite relaciones arbitrarias entre facturas y partidas. El límite de 50,000 filas suma todas las tablas leídas. La hoja de fuentes incluye unidades, versiones y diagnóstico de coincidencias y valores ausentes. `request_report` sigue localizando el reporte original de una ejecución. Las nuevas descargas se muestran como botones del chat y sólo están disponibles para su autor.

Para activar los cruces en una instalación local ya configurada, actualiza el código, detén la API y ejecuta desde `backend` `..\.venv\Scripts\python.exe -m app.modules.foundry.setup --upgrade-local`, después `..\.venv\Scripts\python.exe -m app.modules.foundry.setup --check` y reinicia la API. Se conserva el modelo configurado y se registra una nueva versión de las dieciséis herramientas con las instrucciones actualizadas. No repitas una actualización correcta: cada ejecución crea otra versión. Consulta [relaciones, cálculos, límites y prueba de aceptación](assistant-corporate.md#cruces-y-columnas-calculadas). Los cruces por sí solos no añadieron una migración. La ampliación de adjuntos sí requiere la migración aditiva `20261022_0006` y las dependencias de lectura/generación. Sigue [la instalación de adjuntos y formatos](assistant-corporate.md#instalar-esta-ampliación-en-windows) antes de reiniciar. No se necesita Code Interpreter ni un recurso Azure adicional.

El modelo se basa en redes neuronales profundas (deep learning) ya entrenadas. La integración añade recuperación de datos y herramientas; no entrena un modelo propio ni aprende automáticamente de las conversaciones. La calidad depende también de la cobertura real, las reglas de negocio y la validación contra datos conocidos.

## 8. Habilitar tareas del asistente

Después de validar consultas de lectura, habilita las acciones en la configuración **del backend**. Registra una nueva versión desde el mismo entorno autorizado:

```powershell
$env:DATASTAGE_ALLOW_AGENT_COMMANDS = 'true'
Push-Location backend
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --apply
Pop-Location
```

Actualiza `DATASTAGE_FOUNDRY_AGENT_VERSION` con la nueva versión y reinicia los servicios. Dentro del chat, marca **Permitir que esta consulta inicie un consolidado o reproceso autorizado** y formula una petición explícita. El permiso aplica sólo al siguiente mensaje y se reinicia al terminar.

Las acciones siguen requiriendo el rol del usuario. El agente no decide su identidad, ámbito, permisos ni versión esperada. Los comandos generan ejecuciones normales con idempotencia y auditoría. No se ofrecen borrado, SQL libre, carga arbitraria de archivos ni ejecución general de código.

## 9. Diagnóstico

| Síntoma | Comprobación |
| --- | --- |
| El chat sigue deshabilitado | Comprueba que el proceso API heredó `DATASTAGE_FOUNDRY_ENABLED=true` y reinícialo. |
| Al enviar una consulta se recarga la página y desaparece el mensaje | Actualiza `feature/foundry-agent-setup` y reinicia el frontend con `npm.cmd start`. La corrección del formulario evita el envío HTML que recargaba la página; conserva la consulta durante la espera y muestra los errores de la API para poder reintentar. |
| `DefaultAzureCredential` no encuentra identidad | Comprueba que el proceso corre en el entorno con identidad administrada o federada configurada. Si se usa una herramienta de desarrollo autorizada, confirma que su sesión pertenece a esa misma cuenta del sistema. |
| El portal funciona, pero el script no | El inicio de sesión web no autentica automáticamente al SDK. Confirma la identidad del ejecutor, sus roles y su acceso a red. |
| `foundry_auth_mode`: `Input should be 'default' or 'interactive'` | Actualiza esta rama y repite `--configure-local`. Si CMD hereda un valor anterior, ejecuta antes `set "DATASTAGE_FOUNDRY_AUTH_MODE="`. No modifica la configuración permanente de Windows. |
| `foundry_login_required` en desarrollo | Ejecuta `python -m app.modules.foundry.setup --login` con el intérprete y la cuenta que utilizan la API; la solicitud HTTP nunca abre el navegador. |
| El almacenamiento cifrado no está disponible | Revisar con TI la protección de datos del usuario y el soporte del SDK. No se permite guardar tokens sin cifrar. |
| La versión no coincide al ejecutar `--check` | Revisar el modelo, la versión exacta, las instrucciones y las herramientas. La comprobación no crea otra versión ni cambia el agente. |
| Foundry devuelve `invalid_payload`: `Not allowed when agent is specified`, con `instructions` o `tools` | Descarga la corrección de `feature/foundry-agent-setup`, ejecuta `--check` y reinicia la API. La invocación reutiliza la definición registrada mediante `agent_reference`. Esta corrección del cliente no requiere crear otra versión del agente. |
| Foundry devuelve `invalid_value` en `input[n]` con `Invalid value: ''` | Descarga la corrección de `feature/foundry-agent-setup` y reinicia la API. El cliente debe incluir `type: "message"` en todos los mensajes del contexto y del historial. |
| 401 o 403 desde Azure | Comprueba directorio, identidad, ámbito y roles de Foundry. |
| No encuentra modelo o agente | Comprueba el endpoint del proyecto, nombre de despliegue y versión registrada. |
| 429 | Revisa cuota y capacidad del despliegue. El adaptador ya usa reintentos limitados. |
| `foundry_circuit_open` | Hubo fallos consecutivos. Revisa conectividad; el circuito permite otra prueba después de su intervalo. |
| El agente no ejecuta acciones | Revisa las dos autorizaciones: variable del entorno y casilla del mensaje, además del rol DataStage. |
| No hay evidencia | Confirma fuente, año y cargas publicadas. Una muestra de `get_data` no representa el total. |

Logs locales: `.data/logs/api.error.log` y `.data/logs/api.log`. No publiques tokens ni contenido sensible de los registros en incidencias compartidas.

## 10. Antes de operar en Azure

Verifica la autenticación real Entra de la aplicación, el ámbito empresarial, la conectividad a SQL Server y la identidad administrada del backend. Prueba las respuestas contra un conjunto de preguntas con resultados conocidos y verifica que las acciones rechazadas tampoco modifiquen datos.

Este adaptador usa `store=True` y `previous_response_id` para continuar llamadas a funciones. Revisa la configuración de región y retención del proyecto. La prueba local automatizada utiliza respuestas simuladas del proveedor; no certifica conectividad con tu tenant. El panel y el tutorial quedaron preparados, pero el agente sólo estará conectado después de completar estos pasos con tus recursos Azure.

Un endpoint privado controla el acceso de red. La ubicación del procesamiento sigue dependiendo del tipo de despliegue del modelo, por ejemplo `GlobalStandard`; debe corresponder a la política corporativa antes de consultar información empresarial real.

Las pruebas de autenticación local verifican aislamiento de caché, cifrado obligatorio, sesión expirada, ausencia de ventanas de login desde la API, conservación del `.env`, respaldo, contratos de herramientas y rechazo del modo personal fuera del desarrollo local. La ejecución real del cifrado de Windows, el acceso privado desde cada equipo y la identidad Linux deben validarse en esos entornos.

Validación del 21 de octubre de 2026: **115 pruebas** de Foundry, autenticación local, cobertura de periodos y revisión de seguridad, correctas en Linux/Python 3.12.14 con las versiones del lock (`azure-identity 1.25.3`, `azure-ai-projects 2.7.0`). Incluyen la reconfiguración de modos anteriores inválidos, la reproducción de `invalid_payload` e `invalid_value` con el SDK real y transporte simulado, los tipos explícitos en mensajes de usuario, asistente e idioma, la continuación de herramientas en ambos idiomas y la comprobación de las instrucciones registradas. La cobertura se prueba con sólo mayo y junio de 2025 frente a un anual enero-julio, un listado reciente limitado a una ejecución, meses sin publicación vigente y datos ajenos al ámbito autorizado. En la entrega inicial también pasaron **26 pruebas** de herramientas nativas, `pip check` y la comprobación del lock; Ruff volvió a pasar en los archivos Python modificados. Las llamadas a Azure de estas pruebas están simuladas; no acreditan la sesión cifrada real en Windows/Python 3.13 ni la identidad de producción.

## Alternativa: Azure CLI aprobado por TI

Si TI permite instalar y usar Azure CLI en un entorno de desarrollo, autentícate allí con tu cuenta corporativa y registra el agente desde esa misma sesión. No necesitas hacerlo para la ruta con identidad administrada. Solicita la instalación por los canales de software corporativos; no omitas restricciones del equipo.

```powershell
az login --tenant '<TENANT_ID>'
az account set --subscription '<SUBSCRIPTION_ID>'
az account show --query '{subscription:name,tenant:tenantId}'
```

`DefaultAzureCredential` puede reutilizar esa sesión. Se requieren los mismos permisos de Foundry del paso 2. El backend desplegado debe usar su propia identidad; la sesión `az login` de un desarrollador no es una credencial de producción.

## Memoria personal entre conversaciones

DataStage permite guardar, editar, desactivar y borrar preferencias personales desde **Memoria** y preparar una nota desde **Recordar**. Son notas explícitas por identidad y ámbito, almacenadas en SQLite/SQL Server, incluidas como contexto acotado en las siguientes consultas. No hay extracción automática de conversaciones ni entrenamiento continuo. No se añade el Memory Store de Foundry ni se cambian modelo o herramientas; no hace falta registrar otra versión por esta función. La migración aditiva `20261022_0005` se aplica antes del arranque en las bases gestionadas por Alembic. Consulta [uso, límites, actualización y retención](assistant-corporate.md#guardar-y-gestionar-memoria-personal).
