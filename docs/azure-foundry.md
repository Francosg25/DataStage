# Configurar el asistente DataStage en Microsoft Foundry

Guía del proyecto, revisada el 3 de octubre de 2026. El dashboard funciona sin IA. El asistente necesita un proyecto Foundry, un modelo desplegado y una identidad autorizada. Esta guía no crea recursos ni activa consumo en Azure por sí misma.

**Para una cuenta y laptop corporativas:** no necesitas instalar Azure CLI en tu equipo para avanzar. Puedes revisar el proyecto, el modelo y sus datos de conexión desde [Microsoft Foundry](https://ai.azure.com/) en el navegador. Registrar las funciones de DataStage requiere ejecutar el script Python del repositorio en un entorno autorizado por TI; una máquina o proceso de Azure con identidad administrada es la ruta recomendada. Si tu organización permite Azure CLI en la laptop, se ofrece como alternativa al final de la guía. No sabemos qué herramientas, permisos o redes habilita la política de tu empresa.

| Paso | Dónde se hace | Qué se necesita |
| --- | --- | --- |
| Ver proyecto y modelo | Navegador corporativo | Acceso al proyecto Foundry |
| Revisar la definición de DataStage | Laptop o entorno de desarrollo autorizado | Repositorio y Python del proyecto; sin conexión a Azure |
| Registrar las funciones | Ejecutor corporativo autorizado | Repositorio, Python, acceso de red a Foundry e identidad con permiso para crear versiones |
| Responder desde DataStage | Backend donde esté desplegada la API | Identidad para invocar el agente, configuración de la versión y acceso a las fuentes de datos |

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

Si TI permite una herramienta de desarrollo ya instalada que Azure Identity reconozca, puede usarse en un entorno de desarrollo, con los permisos anteriores. El acceso al portal con el navegador no autentica automáticamente al proceso Python. El código actual excluye el inicio interactivo mediante navegador, así que no lo presentamos como un paso que vaya a funcionar sin preparación. En Azure, prefiere identidad administrada para el backend. No guardes secretos en Angular ni en Git.

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
| `start_annual` | Crea una consolidación anual | Sí, requiere `Operator` o `Admin` |
| `reprocess_run` | Crea una nueva versión con motivo y versión esperada | Sí, requiere `Reprocessor` o `Admin` |

`search_documentation` no indexa automáticamente archivos del equipo ni el PDF completo. La semántica del dashboard está implementada en código y en `docs/analytics.md`. Incorporar una base documental de búsqueda ampliada sería una integración adicional.

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
| `DefaultAzureCredential` no encuentra identidad | Comprueba que el proceso corre en el entorno con identidad administrada o federada configurada. Si se usa una herramienta de desarrollo autorizada, confirma que su sesión pertenece a esa misma cuenta del sistema. |
| El portal funciona, pero el script no | El inicio de sesión web no autentica automáticamente al SDK. Confirma la identidad del ejecutor, sus roles y su acceso a red. |
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

## Alternativa: Azure CLI aprobado por TI

Si TI permite instalar y usar Azure CLI en un entorno de desarrollo, autentícate allí con tu cuenta corporativa y registra el agente desde esa misma sesión. No necesitas hacerlo para la ruta con identidad administrada. Solicita la instalación por los canales de software corporativos; no omitas restricciones del equipo.

```powershell
az login --tenant '<TENANT_ID>'
az account set --subscription '<SUBSCRIPTION_ID>'
az account show --query '{subscription:name,tenant:tenantId}'
```

`DefaultAzureCredential` puede reutilizar esa sesión. Se requieren los mismos permisos de Foundry del paso 2. El backend desplegado debe usar su propia identidad; la sesión `az login` de un desarrollador no es una credencial de producción.
