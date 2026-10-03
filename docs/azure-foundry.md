# Configurar el asistente DataStage en Microsoft Foundry

Guía del proyecto, revisada el 3 de octubre de 2026. El dashboard funciona sin IA. El asistente necesita un proyecto Foundry, un modelo desplegado y una identidad autorizada. Esta guía no crea recursos ni activa consumo en Azure por sí misma.

## 1. Preparar el proyecto y el modelo

Abre [Microsoft Foundry](https://ai.azure.com/), selecciona tu directorio corporativo y entra al proyecto que utilizará DataStage. Si no existe, crea un recurso y proyecto con tu administrador. Selecciona una región y una implementación de modelo compatibles con agentes y llamadas a funciones. Guarda el **nombre exacto del despliegue**, que puede ser diferente del nombre comercial del modelo.

Copia el **endpoint del proyecto** desde su página principal. Su formato es `https://RECURSO.services.ai.azure.com/api/projects/PROYECTO`. No uses el endpoint de una implementación de modelo ni un identificador `asst_` de una API anterior. Este proyecto utiliza agentes versionados y Azure AI Projects 2.x. [Referencia de creación del agente](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/prompt-agent).

## 2. Asignar las identidades correctas

En el control de acceso del recurso/proyecto, asigna al desarrollador permisos para crear versiones del agente, por ejemplo **Foundry User** en el proyecto. Para una identidad que sólo invocará agentes, revisa **Foundry Agent Consumer**. La administración de recursos y asignación de roles requiere permisos adicionales. Los nombres anteriores `Azure AI User` y `Azure AI Project Manager` pueden aparecer en entornos todavía no actualizados. El administrador debe verificar el ámbito y las operaciones necesarias según [RBAC de Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry).

La identidad del backend ante Azure es distinta de la identidad del usuario de DataStage. DataStage conserva su propia autorización `Reader`, `Operator`, `Reprocessor`, `Auditor` y `Admin`, junto con `scopeId`. No se envían claves de Azure al navegador.

## 3. Autenticarse desde Windows

Abre PowerShell en la carpeta raíz `DataStage`. Las dependencias Python ya están fijadas en `backend/requirements.lock` y la aplicación utiliza `.venv`.

Si Azure CLI no está instalado:

```powershell
winget install --exact --id Microsoft.AzureCLI
```

Abre una nueva terminal después de la instalación. Autentícate con tu cuenta corporativa y selecciona la suscripción:

```powershell
az login --tenant '<TENANT_ID>'
az account set --subscription '<SUBSCRIPTION_ID>'
az account show --query '{subscription:name,tenant:tenantId}'
```

`DefaultAzureCredential` usa la sesión de Azure CLI en desarrollo. En Azure, configura una identidad administrada para el backend y asígnale los permisos del paso 2. No guardes secretos en Angular ni en Git.

## 4. Configurar una sesión local

Ejecuta estos comandos en la misma terminal y sustituye los valores entre `<...>`:

```powershell
$env:DATASTAGE_FOUNDRY_PROJECT_ENDPOINT = 'https://<RECURSO>.services.ai.azure.com/api/projects/<PROYECTO>'
$env:DATASTAGE_FOUNDRY_MODEL = '<NOMBRE_DEL_DESPLIEGUE>'
$env:DATASTAGE_FOUNDRY_AGENT_NAME = 'datastage-assistant'
$env:DATASTAGE_FOUNDRY_ENABLED = 'false'
$env:DATASTAGE_ALLOW_AGENT_COMMANDS = 'false'
```

Las variables de esta sesión serán heredadas por los procesos iniciados desde ella. Para configuración persistente usa las variables del servicio o su gestor de secretos. `Settings` también lee `.env` en el directorio de trabajo del proceso; el lanzador local ejecuta el backend desde `backend`, por lo que un `.env` únicamente en la raíz no basta para ese lanzador.

## 5. Registrar el agente con las herramientas del proyecto

Primero consulta la definición local. Este comando no se conecta a Azure:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m app.modules.foundry.setup
Pop-Location
```

Revisa el modelo, nombre y herramientas. Después registra una versión en el proyecto configurado:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m app.modules.foundry.setup --apply
Pop-Location
```

Este segundo comando sí escribe una nueva versión en Azure. Guarda el `name` y `version` devueltos. No ejecutes repetidamente `--apply` para comprobar conectividad porque cada ejecución crea una versión.

Las funciones se registran desde el SDK y se ejecutan dentro del backend DataStage. Configurar un agente sólo en el portal no conecta automáticamente las herramientas con tus datos. [Funcionamiento de las llamadas a funciones](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling).

## 6. Activar y probar la conexión

Usa la versión exacta devuelta, sin asumir que sea `1`:

```powershell
$env:DATASTAGE_FOUNDRY_AGENT_VERSION = '<VERSION_DEVUELTA>'
$env:DATASTAGE_FOUNDRY_ENABLED = 'true'
.\scripts\stop-dev.ps1
.\scripts\start-dev.ps1 -SkipInstall
```

Abre `http://127.0.0.1:4200/agent`. La pantalla debe mostrar el asistente habilitado. Prueba estas consultas:

1. `¿Qué periodos publicados están disponibles?`
2. `Usando la referencia Excel de 2026, compara julio y agosto: pedimentos, ValorDolares de 551 y contribuciones de 510. Cita los indicadores.`
3. `¿Qué meses faltan y qué diferencias de conciliación se detectaron?`
4. Cambia a English y pregunta: `Compare July and August 2026 using the reference workbook. Keep USD and MXN separate.`

Una referencia Excel disponible no implica que existan ejecuciones publicadas en SQL. El asistente distingue `source=reference` y `source=published`.

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

Después de validar consultas de lectura:

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
| `DefaultAzureCredential` no encuentra identidad | Ejecuta `az login` en la misma cuenta del sistema que inicia el backend. |
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
