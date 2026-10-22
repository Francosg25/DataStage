"""Data charts from verified QueryResult values; no generated code or markup."""
from decimal import Decimal
from html import escape
from io import BytesIO
import json
import math
import textwrap

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from .data_queries import fail

COLORS = ["#147D84", "#2D72B8", "#71944B"]


def display(value):
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        raw = format(Decimal(str(value)), ",f")
        return raw.rstrip("0").rstrip(".") if "." in raw else raw
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def chart_display(value):
    if value and (abs(value) < .01 or abs(value) >= 1_000_000_000):
        return f"{value:.4g}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def chart_data(result):
    if not result.rows or len(result.rows) > 30 or not 2 <= len(result.headers) <= 4:
        fail("agent_chart_shape", "La gráfica requiere entre 1 y 30 filas, una categoría y de 1 a 3 métricas numéricas. Agrupa o filtra la consulta.")
    if any(kind != "number" for kind in result.types[1:]):
        fail("agent_chart_shape", "La primera columna es la categoría; las demás deben ser métricas numéricas.")
    if result.units and len(set(result.units[1:])) > 1:
        fail("agent_mixed_units", "Separa las series que tengan unidades distintas en gráficas diferentes.")
    values = []
    for row in result.rows:
        if any(value is None or not isinstance(value, (int, float, Decimal)) or not math.isfinite(float(value)) for value in row[1:]):
            fail("agent_chart_missing", "La gráfica tiene valores ausentes o no válidos. Revísalos antes de dibujar; no se convierten a cero.")
        label = display(row[0])
        if len(label) > 80:
            fail("agent_chart_label", "Una etiqueta es demasiado larga para una gráfica; selecciona un identificador o agrupa los datos.")
        values.append([label, *[float(value) for value in row[1:]]])
    return values


def font(size):
    for name in ("DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def draw_chart(result, title, kind, format, source_caption, manifest):
    values = chart_data(result)
    if kind not in {"bar", "line"}:
        fail("agent_chart_kind", "Selecciona bar o line para generar una imagen.")
    width, left, right, top = 1600, 480, 1450, 165
    row_height = max(62, 34 * (len(result.headers) - 1), 34 * max(len(textwrap.wrap(row[0], 22)) for row in values))
    height = max(680, top + len(values) * row_height + 300) if kind == "bar" else 1000
    bottom = height - 300
    pixels = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(pixels)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>', f'<metadata>{escape(json.dumps(manifest, ensure_ascii=False))}</metadata>']
    def text(x, y, value, size=22, color="#28414C"):
        value = str(value)
        draw.text((x, y), value, fill=color, font=font(size))
        svg.append(f'<text x="{x}" y="{y + size}" font-family="Arial,sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>')
    def line(x1, y1, x2, y2, color="#D9E4E8", stroke=2):
        draw.line((x1, y1, x2, y2), fill=color, width=stroke)
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{stroke}"/>')
    for n, title_line in enumerate(textwrap.wrap(title, 68)):
        text(60, 22 + n * 48, title_line, 42, "#143E44")
    unit = result.units[1] if result.units else ""
    if unit in {"USD", "MXN", "%", "MXN/USD"}:
        text(60, 126, unit, 24)
    minimum = min(0, min(value for row in values for value in row[1:]))
    maximum = max(0, max(value for row in values for value in row[1:]))
    span = maximum - minimum or 1
    if kind == "bar":
        if minimum < 0:
            left = 600
        def scale(value):
            return left + (value - minimum) / span * (right - left - 110)
        zero = scale(0)
        for tick in range(6):
            value = minimum + span * tick / 5
            x = scale(value)
            line(x, top, x, bottom)
            text(x - 12, bottom + 15, chart_display(value), 24)
        for index, row in enumerate(values):
            y = top + index * row_height
            for number, label in enumerate(textwrap.wrap(row[0], 22)):
                text(60, y + number * 34, label, 28)
            for series, value in enumerate(row[1:]):
                y1 = y + series * 34
                x = scale(value)
                color = COLORS[series]
                x1, x2 = sorted((zero, x))
                draw.rectangle((x1, y1 + 2, max(x1 + 1, x2), y1 + 27), fill=color)
                svg.append(f'<rect x="{x1}" y="{y1 + 2}" width="{max(1, x2 - x1)}" height="25" fill="{color}"/>')
                text(x + 8 if value >= 0 else x - 175, y1 - 2, chart_display(value), 26)
    else:
        left = 180
        def sx(index):
            return left + index / max(1, len(values) - 1) * (right - left)
        def sy(value):
            return bottom - (value - minimum) / span * (bottom - top)
        for tick in range(6):
            value = minimum + span * tick / 5
            y = sy(value)
            line(left, y, right, y)
            text(20, y - 12, chart_display(value), 24)
        step = max(1, math.ceil(len(values) / 8))
        for index, row in enumerate(values):
            if index % step == 0 or index == len(values) - 1:
                label = textwrap.wrap(row[0], 17)
                for n, piece in enumerate(label):
                    text(sx(index) - 40, bottom + 12 + n * 28, piece, 24)
        for series in range(len(result.headers) - 1):
            for index in range(len(values) - 1):
                line(sx(index), sy(values[index][series + 1]), sx(index + 1), sy(values[index + 1][series + 1]), COLORS[series], 4)
            for index, row in enumerate(values):
                x, y = sx(index), sy(row[series + 1])
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=COLORS[series])
                svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{COLORS[series]}"/>')
    for index, header in enumerate(result.headers[1:]):
        for line_index, label in enumerate(textwrap.wrap(header, 28)):
            text(60 + index * 470, height - 200 + line_index * 34, label, 26, COLORS[index])
    for index, caption in enumerate(textwrap.wrap(source_caption, 145)[:2]):
        text(60, height - 48 + index * 20, caption, 16)
    svg.append("</svg>")
    if format == "svg":
        return "".join(svg).encode("utf-8")
    stream = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("DataStage sources", json.dumps(manifest, ensure_ascii=False))
    pixels.save(stream, format="PNG", pnginfo=metadata)
    return stream.getvalue()
