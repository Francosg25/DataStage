"""Pure monthly/yearly transformations with immutable source traceability."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace

from .catalog import (
    ENGINE_VERSION, TRACE_HEADERS, detect_table_code, folio_from_name, make_sheet_names,
    normalize_header, normalize_text, parse_period, range_end_month, table_sort_key,
)
from .dates import is_date_header, parse_date
from .models import EngineOptions, InputFile

_PATENTE = {"patente", "patenteaduanal"}
_PEDIMENTO = {"pedimento", "numeropedimento", "numerodepedimento"}
_SECCION = {"seccionaduanera", "claveseccionaduanera", "clavedeseccionaduaneradedespacho", "claveaduanadespacho"}
_COMPLETE = {"pedimentocompleto", "pedimentounificado"}
_TRACE = {normalize_header(h) for h in TRACE_HEADERS}


def _issue(file: InputFile, code: str, message: str, *, row: int | None = None, column: str | None = None, original: str | None = None) -> dict:
    return {"fileId": file.file_id, "fileName": file.file_name, "rowNumber": row,
            "column": column, "code": code, "message": message, "original": original}


def _split_line(line: str) -> list[str]:
    if line.endswith("|"):
        line = line[:-1]
    return [normalize_text(item) for item in line.split("|")]


def _parse_asc(file: InputFile, options: EngineOptions) -> tuple[list[str], list[tuple[int, list[str]]], str]:
    if not isinstance(file.content, str):
        raise ValueError("El contenido ASC debe ser texto decodificado.")
    lines = [(number, normalize_text(line)) for number, line in enumerate(file.content.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1)]
    lines = [(number, line) for number, line in lines if line]
    if not lines:
        return [], [], "Archivo vacio."
    headers = _split_line(lines[0][1])
    while headers and not headers[-1]:
        headers.pop()
    if not headers:
        return [], [], "No se detectaron encabezados."
    if len(headers) + len(TRACE_HEADERS) > options.max_columns:
        raise ValueError(f"Se excedió el límite de {options.max_columns} columnas incluyendo trazabilidad.")
    keys = [normalize_header(header) for header in headers]
    if any(not key for key in keys):
        raise ValueError("Un encabezado intermedio está vacío o no contiene letras/números.")
    if len(keys) != len(set(keys)):
        raise ValueError("Encabezados equivalentes duplicados dentro del archivo; no es posible alinearlos sin perder valores.")
    if set(keys) & _TRACE:
        raise ValueError("El ASC contiene un encabezado reservado para trazabilidad: Periodo, ArchivoOrigen o FolioOrigen.")
    if len(lines) - 1 > options.max_rows:
        raise ValueError(f"Se excedió el límite de {options.max_rows} filas por tabla.")
    width = len(headers)
    rows = []
    for number, line in lines[1:]:
        row = _split_line(line)
        rows.append((number, (row + [""] * width)[:width]))
    return headers, rows, "Procesado correctamente." if rows else "Archivo solo con encabezado."


def _add_pedimento(headers: list[str], rows: list[tuple[int, list[str]]], year: int, options: EngineOptions) -> tuple[list[str], list[tuple[int, list[str]]]]:
    keys = [normalize_header(header) for header in headers]
    if set(keys) & _COMPLETE:
        return headers, rows
    def index(aliases: set[str]) -> int | None:
        return next((i for i, key in enumerate(keys) if key in aliases), None)
    patente, pedimento, seccion = index(_PATENTE), index(_PEDIMENTO), index(_SECCION)
    if patente is None or pedimento is None or seccion is None:
        return headers, rows
    preferred = [normalize_header(header) for header in options.preferred_date_headers]
    date_indices = [keys.index(key) for key in preferred if key in keys and is_date_header(key)]
    date_indices += [i for i, header in enumerate(headers) if is_date_header(header) and i not in date_indices]
    updated_rows = []
    for number, row in rows:
        selected_year = year
        for date_index in date_indices:
            parsed, _ = parse_date(row[date_index], options.ambiguous_date_order)
            if parsed:
                selected_year = parsed.year
                break
        digits = "".join(c for c in row[seccion] if c in "0123456789")[:2].zfill(2)
        complete = f"{selected_year % 100:02d} {digits} {row[patente]} {row[pedimento]}"
        updated_rows.append((number, [complete] + row))
    return ["PedimentoCompleto"] + headers, updated_rows


def _process(kind: str, year: int, period: str | None, range_name: str | None, selected: list[InputFile], received: int, excluded: list[dict], options: EngineOptions, initial_warnings: list[dict]) -> dict:
    groups: dict[str, dict] = {}
    file_results, errors, warnings = [], [], list(initial_warnings)
    controls: list[dict] = []
    for file in selected:
        code = detect_table_code(file.file_name, file.table_code)
        result = {"fileId": file.file_id, "fileName": file.file_name, "period": file.period,
                  "tableCode": code, "headers": [], "rowsCount": 0, "columnsCount": 0,
                  "dateColumnsCount": 0, "status": "OK", "message": ""}
        try:
            if not code:
                raise ValueError("No se pudo determinar el código de tabla.")
            headers, rows, message = _parse_asc(file, options)
            file_year, _, canonical_period = parse_period(file.period)
            headers, rows = _add_pedimento(headers, rows, file_year, options)
            result.update(headers=headers, rowsCount=len(rows), columnsCount=len(headers),
                          dateColumnsCount=sum(is_date_header(h) for h in headers), message=message)
            if headers:
                new_keys = {normalize_header(h) for h in headers}
                existing = groups.get(code)
                combined_columns = len((_TRACE | new_keys) if existing is None else set(existing["headers"]) | new_keys)
                combined_rows = len(rows) + (len(existing["rawRows"]) if existing else 0)
                if combined_columns > options.max_columns or combined_rows > options.max_rows:
                    raise ValueError("La tabla unificada excede los límites configurados de filas o columnas.")
                group = groups.setdefault(code, {"headers": OrderedDict((normalize_header(h), h) for h in TRACE_HEADERS),
                                                  "rawRows": [], "files": [], "periods": set()})
                for header in headers:
                    group["headers"].setdefault(normalize_header(header), header)
                keys = [normalize_header(header) for header in headers]
                folio = folio_from_name(file.file_name, code)
                for number, row in rows:
                    values = dict(zip(keys, row))
                    values.update(periodo=canonical_period, archivoorigen=file.file_name, folioorigen=folio)
                    source = {"fileId": file.file_id, "fileName": file.file_name, "period": canonical_period,
                              "folio": folio, "rowNumber": number, "originalDates": {}}
                    group["rawRows"].append((file, values, source))
                group["files"].append(file)
                group["periods"].add(canonical_period)
        except (ValueError, TypeError, OverflowError) as exc:
            result.update(status="ERROR", message=f"ERROR: {exc}")
            errors.append(_issue(file, "FILE_PROCESSING_ERROR", str(exc)))
        file_results.append(result)

    names = make_sheet_names(list(groups))
    tables = []
    for code in sorted(groups, key=table_sort_key):
        group = groups[code]
        columns = group["headers"]
        date_keys = [key for key, header in columns.items() if is_date_header(header)]
        aligned_rows, row_sources = [], []
        for file, values, source in group["rawRows"]:
            row = []
            for key, header in columns.items():
                value = values.get(key, "")
                if key in date_keys:
                    source["originalDates"][key] = value
                    if value:
                        parsed, ambiguous = parse_date(value, options.ambiguous_date_order)
                        if parsed is None:
                            warnings.append(_issue(file, "INVALID_DATE", "Fecha no interpretable; se conservó el valor original.", row=source["rowNumber"], column=header, original=value))
                        else:
                            value = parsed.isoformat(timespec="seconds")
                            if ambiguous:
                                warnings.append(_issue(file, "AMBIGUOUS_DATE", f"Fecha ambigua interpretada con la regla {options.ambiguous_date_order}.", row=source["rowNumber"], column=header, original=values[key]))
                row.append(value)
            aligned_rows.append(row)
            row_sources.append(source)
        tables.append({"tableCode": code, "sheetName": names[code], "headers": list(columns.values()),
                       "dateColumns": date_keys, "rows": aligned_rows, "rowSources": row_sources})

    for result in file_results:
        control = {"Archivo": result["fileName"], "Tabla": result["tableCode"], "Hoja": names.get(result["tableCode"], ""),
                   "Estatus": result["status"], "Filas": result["rowsCount"], "Columnas": result["columnsCount"],
                   "ColumnasFecha": result["dateColumnsCount"], "Mensaje": result["message"]}
        if kind == "annual":
            control = {"Periodo": result["period"], **control}
            if result["headers"]:
                control["Columnas"] += len(TRACE_HEADERS)
        controls.append(control)
    for table in tables:
        code = table["tableCode"]
        group = groups[code]
        message = f"{len(group['files'])} archivos unificados."
        if kind == "annual":
            message = f"{len(group['files'])} archivos; {len(group['periods'])} periodos unificados."
        control = {"Archivo": "CONSOLIDADO", "Tabla": code, "Hoja": table["sheetName"], "Estatus": "OK",
                   "Filas": len(table["rows"]), "Columnas": len(table["headers"]),
                   "ColumnasFecha": len(table["dateColumns"]), "Mensaje": message}
        if kind == "annual":
            control = {"Periodo": "CONSOLIDADO", **control}
        controls.append(control)
    processed = sum(bool(file["headers"]) and file["status"] == "OK" for file in file_results)
    failed = sum(file["status"] == "ERROR" for file in file_results)
    return {"engineVersion": ENGINE_VERSION, "kind": kind, "period": period, "year": year, "rangeName": range_name,
            "functionalResult": "WARNING" if errors else "OK", "receivedFiles": received,
            "processedFiles": processed, "skippedFiles": received - processed - failed, "failedFiles": failed,
            "processedTables": len(tables), "sheets": ["Control_Proceso"] + [t["sheetName"] for t in tables],
            "controlRows": controls, "files": file_results, "warnings": warnings, "errors": errors,
            "tables": tables, "excludedFiles": excluded,
            "datePolicy": {"ambiguousOrder": options.ambiguous_date_order, "preferredHeaders": list(options.preferred_date_headers)}}


def process_monthly(period: str, files: list[InputFile], options: EngineOptions | None = None) -> dict:
    year, _, canonical = parse_period(period)
    selected = [replace(file, period=canonical) for file in files]
    return _process("monthly", year, canonical, None, selected, len(files), [], options or EngineOptions(), [])


def process_annual(year: int, range_name: str, files: list[InputFile], options: EngineOptions | None = None) -> dict:
    if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
        raise ValueError("El año objetivo debe estar entre 1900 y 2100.")
    end_month = range_end_month(range_name)
    selected, excluded, warnings = [], [], []
    if end_month is None:
        warnings.append({"fileId": "", "fileName": "", "rowNumber": None, "column": None,
                         "code": "UNRECOGNIZED_RANGE", "message": "Rango no interpretable; se incluyen todos los meses válidos del año.", "original": range_name})
        end_month = 12
    for ordinal, file in enumerate(files):
        reason = ""
        try:
            source_year, month, canonical = parse_period(file.period)
            if source_year != year:
                reason = "Periodo fuera del año objetivo."
            elif month > end_month:
                reason = "Periodo fuera del rango solicitado."
            else:
                selected.append((source_year, month, file.file_name, ordinal, replace(file, period=canonical)))
        except ValueError:
            reason = "Periodo inválido."
        if reason:
            excluded.append({"fileId": file.file_id, "fileName": file.file_name, "period": file.period, "reason": reason})
    selected.sort(key=lambda item: item[:4])
    return _process("annual", year, None, normalize_text(range_name), [item[4] for item in selected],
                    len(files), excluded, options or EngineOptions(), warnings)
