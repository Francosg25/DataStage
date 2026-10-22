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


class DataJoin(ToolArguments):
    tableCode: Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[a-z0-9_]+$")]
    kind: Literal["left", "inner"]


class DataCalculation(ToolArguments):
    left: ColumnName
    operator: Literal["add", "subtract", "multiply", "divide", "percent_of", "percent_change"]
    right: Annotated[str, Field(min_length=1, max_length=100, description="Columna o constante decimal sin separadores.")]
    rightIsColumn: bool
    alias: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[\w ÁÉÍÓÚÜÑáéíóúüñ-]+$")]


class DataQuery(ToolArguments):
    tableCode: Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[a-z0-9_]+$")]
    periods: Annotated[list[PeriodName], Field(min_length=1, max_length=24)]
    columns: Annotated[list[ColumnName], Field(max_length=40, description="Columnas del detalle; vacío para una agregación.")]
    filters: Annotated[list[DataFilter], Field(max_length=10)]
    groupBy: Annotated[list[ColumnName], Field(max_length=4)]
    metrics: Annotated[list[DataMetric], Field(max_length=6)]
    orderBy: Annotated[list[DataOrder], Field(max_length=3)]
    joins: Annotated[list[DataJoin], Field(max_length=2, description="Cruces many-to-one del catálogo; [] sin cruces. Usa prefijos 501.Campo en columnas relacionadas.")] = Field(default_factory=list)
    calculations: Annotated[list[DataCalculation], Field(max_length=8, description="Cálculos numéricos por fila, en orden; después se filtran/agrupan. [] sin cálculos. Sin código ni SQL.")] = Field(default_factory=list)


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


class ListAttachments(ToolArguments):
    pass


class DescribeAttachment(ToolArguments):
    fileId: RunId


class AttachmentQuery(ToolArguments):
    fileId: RunId
    sheet: Annotated[str, Field(min_length=1, max_length=100)]
    columns: Annotated[list[ColumnName], Field(max_length=40)]
    filters: Annotated[list[DataFilter], Field(max_length=10)]
    groupBy: Annotated[list[ColumnName], Field(max_length=4)]
    metrics: Annotated[list[DataMetric], Field(max_length=6)]
    orderBy: Annotated[list[DataOrder], Field(max_length=3)]


class QueryAttachment(ToolArguments):
    query: AttachmentQuery
    limit: Limit
    offset: Annotated[int, Field(ge=0, le=50000)]
    textOffset: Annotated[int, Field(ge=0, le=50000, description="0 normalmente; para continuar una celda larga usa su nextTextOffset y selecciona esa fila/columna.")] = 0
    textLimit: Annotated[int, Field(ge=100, le=6000, description="Máximo de caracteres por celda en la vista previa; 1000 normalmente. Los datos originales permanecen completos.")] = 1000


class FileSection(ToolArguments):
    title: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[^\r\n\t]+$")]
    query: DataQuery | AttachmentQuery
    commentary: Annotated[str, Field(max_length=800, description="Comentario del asistente basado en resultados verificados; vacío si no hace falta.")]
    chart: Literal["none", "bar", "line"]


class CreateFile(ToolArguments):
    title: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[^\r\n\t]+$")]
    format: Literal["docx", "pptx", "csv", "json", "png", "svg", "html", "pdf", "xlsx"]
    sections: Annotated[list[FileSection], Field(min_length=1, max_length=5)]


class CreatePackage(ToolArguments):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    documentIds: Annotated[list[RunId], Field(min_length=1, max_length=10)]


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
    "list_attachments": ListAttachments,
    "describe_attachment": DescribeAttachment,
    "query_attachment": QueryAttachment,
    "create_file": CreateFile,
    "create_package": CreatePackage,
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
    "describe_data": "Descubre tablas, columnas, tipos, unidades y relaciones many-to-one autorizadas. Úsala antes de consultar o crear Excel; tableCode vacío lista tablas. Elige como base la tabla de mayor detalle.",
    "query_data": "Consulta datos mensuales publicados: columnas de una o varias tablas mediante joins del catálogo, cálculos por fila, filtros, agrupaciones y orden. Usa 501.Campo para campos relacionados; joins/calculations vacíos si no se usan. Resultados completos con vista previa limitada. Rechaza cruces ambiguos e importes duplicados. Sin SQL ni código.",
    "create_excel": "Genera Excel real de hasta cinco hojas con consultas completas: cruces autorizados, columnas calculadas, filtros y agrupaciones. Números y fechas nativos, fuentes y diagnóstico de relaciones. Exporta todas las filas autorizadas, no muestras; no modifica las fuentes.",
    "create_analysis_report": "Genera un informe PDF descargable con los KPI, gráficos y fuentes del análisis del periodo y filtros solicitados. La moneda es explícita y el idioma lo determina la aplicación.",
    "list_attachments": "Enumera los archivos privados adjuntos a ESTA conversación, sus hojas/páginas, filas y advertencias. No son meses publicados ni documentos operativos.",
    "describe_attachment": "Consulta cabeceras, tipos, hojas y advertencias de un adjunto de esta conversación antes de analizarlo. No ejecuta macros, fórmulas ni enlaces.",
    "query_attachment": "Lee, filtra, ordena o agrega TODAS las filas de una hoja adjunta. columns vacío con métricas. Vista previa paginada: offset para filas, textOffset/textLimit para celdas largas. textContinuations indica resultado/fila/columna y nextTextOffset; para continuar selecciona esa fila y columna. No infieras todo un documento desde una muestra.",
    "create_file": "Genera un archivo real DOCX/PPTX/CSV/JSON/PNG/SVG/HTML/PDF/XLSX a partir de consultas completas publicadas o de adjuntos. Cada sección tiene título, query, commentary y chart (none/bar/line). CSV/PNG/SVG usan una sección. Documentos visuales: máximo 8 columnas, 200 filas por sección y 2000 celdas totales. Gráficas: categoría y métricas numéricas compatibles, máximo 30 filas; no se truncan. Para tablas grandes usa CSV/JSON/XLSX. Las fuentes quedan incluidas.",
    "create_package": "Empaqueta hasta 10 archivos YA generados en esta conversación en un ZIP con manifiesto de fuentes y hashes. Usa sólo documentIds de descargas reales; no admite rutas ni archivos de otros usuarios.",
    "start_annual": "Solicita consolidación anual sólo si el usuario autorizó acciones y tiene permiso.",
    "reprocess_run": "Solicita reproceso con motivo y versión esperada, sujeto a autorización del backend.",
}


def tool_definitions(allow_commands: bool = False) -> list[dict]:
    def close_schema(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object":
                value["additionalProperties"] = False
                value["required"] = list(value.get("properties", {}))
            for child in value.values():
                close_schema(child)
        elif isinstance(value, list):
            for child in value:
                close_schema(child)

    result = []
    for name, model in TOOL_MODELS.items():
        if name in COMMAND_TOOLS and not allow_commands:
            continue
        schema = model.model_json_schema()
        schema.pop("title", None)
        close_schema(schema)
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
