"""Closed tool contracts. Identity and authorization are never model arguments."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import ApplicationError


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


RunId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]
PeriodName = Annotated[str, Field(min_length=5, max_length=40, pattern=r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+_[0-9]{4}$")]
Limit = Annotated[int, Field(ge=1, le=100)]


class GetRun(ToolArguments):
    runId: RunId


class ListRuns(ToolArguments):
    limit: Limit


class GetData(ToolArguments):
    tableCode: Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[a-z0-9_]+$")]
    period: PeriodName
    limit: Limit


class ComparePeriods(ToolArguments):
    firstPeriod: PeriodName
    secondPeriod: PeriodName


class SearchDocumentation(ToolArguments):
    query: Annotated[str, Field(min_length=1, max_length=500)]


class GetAnalytics(ToolArguments):
    source: Literal['published', 'reference']
    year: Annotated[int, Field(ge=1900, le=2100)]
    startMonth: Annotated[int, Field(ge=1, le=12)]
    endMonth: Annotated[int, Field(ge=1, le=12)]
    operation: Annotated[str, Field(max_length=10)]
    customs: Annotated[str, Field(max_length=10)]
    document: Annotated[str, Field(max_length=10)]


class StartAnnual(ToolArguments):
    anio: Annotated[int, Field(ge=1900, le=2100)]
    rangoNombre: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ -]+$")]


class ReprocessRun(GetRun):
    reason: Annotated[str, Field(min_length=5, max_length=500)]
    expectedVersion: Annotated[int, Field(ge=0, le=2147483647)]


TOOL_MODELS = {
    "get_run": GetRun,
    "list_runs": ListRuns,
    "get_data": GetData,
    "get_analytics": GetAnalytics,
    "compare_periods": ComparePeriods,
    "search_documentation": SearchDocumentation,
    "request_report": GetRun,
    "start_annual": StartAnnual,
    "reprocess_run": ReprocessRun,
}
COMMAND_TOOLS = frozenset({"start_annual", "reprocess_run"})
DESCRIPTIONS = {
    "get_run": "Consulta estado, resultado e incidencias de una ejecución autorizada.",
    "list_runs": "Lista ejecuciones recientes dentro del ámbito autorizado del usuario.",
    "get_data": "Consulta una muestra limitada de una tabla y periodo publicados; no permite SQL.",
    "get_analytics": "Obtiene los mismos indicadores, series mensuales, USD/MXN, cobertura y fuentes del dashboard. source separa published de reference. Filtros vacíos incluyen todo. No suma 510/557/702 ni facturas con partidas.",
    "compare_periods": "Compara conteos y cobertura de dos periodos autorizados.",
    "search_documentation": "Busca documentación local aprobada y devuelve extractos con sus fuentes.",
    "request_report": "Obtiene el reporte existente de una ejecución autorizada, sin modificar datos.",
    "start_annual": "Solicita consolidación anual sólo si el usuario autorizó acciones y tiene permiso.",
    "reprocess_run": "Solicita reproceso con motivo y versión esperada, sujeto a autorización del backend.",
}


def tool_definitions(allow_commands: bool = False) -> list[dict]:
    result = []
    for name, model in TOOL_MODELS.items():
        if name in COMMAND_TOOLS and not allow_commands:
            continue
        schema = model.model_json_schema()
        schema.pop("title", None)
        result.append({
            "type": "function", "name": name, "description": DESCRIPTIONS[name],
            "parameters": schema, "strict": True,
        })
    return result


def validate_tool_arguments(name: str, arguments: dict, *, allow_commands: bool = False) -> dict:
    model = TOOL_MODELS.get(name)
    if model is None:
        raise ApplicationError(403, "agent_tool_forbidden", "La herramienta solicitada no está permitida.")
    if name in COMMAND_TOOLS and not allow_commands:
        raise ApplicationError(403, "agent_commands_disabled", "Las acciones del agente están deshabilitadas.")
    if not isinstance(arguments, dict):
        raise ApplicationError(400, "agent_tool_arguments", "Los argumentos deben ser un objeto JSON.")
    try:
        return model.model_validate(arguments).model_dump()
    except ValidationError as error:
        # Avoid returning untrusted argument contents or sensitive identifiers.
        raise ApplicationError(400, "agent_tool_arguments", "Los argumentos no cumplen el contrato de la herramienta.") from error
