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


class DescribeData(ToolArguments):
    tableCode: Annotated[str, Field(max_length=30, description="Vacío lista las tablas; un código devuelve sus columnas y tipos.")]


ColumnName = Annotated[str, Field(min_length=1, max_length=100)]


class DataFilter(ToolArguments):
    column: ColumnName
    operator: Literal["eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_empty", "not_empty"]
    value: Annotated[str, Field(max_length=500, description="Número sin separadores o fecha ISO para rangos. Vacío con is_empty/not_empty.")]


class DataMetric(ToolArguments):
    function: Literal["count_rows", "count_distinct", "sum", "mean", "min", "max"]
    column: Annotated[str, Field(max_length=100, description="Vacío sólo para count_rows.")]
    alias: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[\w ÁÉÍÓÚÜÑáéíóúüñ.-]+$")]


class DataOrder(ToolArguments):
    column: ColumnName
    direction: Literal["asc", "desc"]


class DataQuery(ToolArguments):
    tableCode: Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[a-z0-9_]+$")]
    periods: Annotated[list[PeriodName], Field(min_length=1, max_length=24)]
    columns: Annotated[list[ColumnName], Field(max_length=40, description="Columnas del detalle; vacío para una agregación.")]
    filters: Annotated[list[DataFilter], Field(max_length=10)]
    groupBy: Annotated[list[ColumnName], Field(max_length=4)]
    metrics: Annotated[list[DataMetric], Field(max_length=6)]
    orderBy: Annotated[list[DataOrder], Field(max_length=3)]


class QueryData(ToolArguments):
    query: DataQuery
    limit: Limit


class ExcelSheet(ToolArguments):
    name: Annotated[str, Field(min_length=1, max_length=31)]
    query: DataQuery


class CreateExcel(ToolArguments):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    sheets: Annotated[list[ExcelSheet], Field(min_length=1, max_length=5)]


class CreateAnalysisReport(GetAnalytics):
    currency: Literal["USD", "MXN"]


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
    "describe_data": DescribeData,
    "query_data": QueryData,
    "create_excel": CreateExcel,
    "create_analysis_report": CreateAnalysisReport,
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
    "describe_data": "Descubre tablas aprobadas y sus columnas, tipos, unidades y límites. Úsala antes de preparar consultas o Excel; tableCode vacío lista tablas.",
    "query_data": "Consulta una tabla mensual publicada con filtros, orden, conteos distintos, sumas y agrupaciones calculadas por Python sobre TODAS las filas del rango autorizado. Sólo la vista previa se limita; complete y totals describen cobertura. Sin SQL ni cruces que dupliquen importes.",
    "create_excel": "Genera un Excel descargable real de hasta cinco hojas con columnas, filtros y/o agrupaciones elegidos. Exporta el resultado completo de cada consulta, con números y fechas reales y trazabilidad. No depende de muestras ni modifica los datos fuente.",
    "create_analysis_report": "Genera un informe PDF descargable con los KPI, gráficos y fuentes del análisis del periodo y filtros solicitados. La moneda es explícita y el idioma lo determina la aplicación.",
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
