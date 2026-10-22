// Worksheet identifiers follow the exported DataStage tables, not Excel tab positions.
// Sources describe the metric itself; the general 501 filters still apply.
type Currency = "USD" | "MXN";
interface MetricHelp {
  descriptionEs: string;
  descriptionEn: string;
  sourceSheets: readonly string[];
  nativeCurrency?: Currency;
}

const METRICS: Record<string, MetricHelp> = {
  declarations: {
    descriptionEs:
      "Pedimentos distintos registrados en los meses seleccionados.",
    descriptionEn:
      "Distinct customs declarations recorded in the selected months.",
    sourceSheets: ["501"],
  },
  import: {
    descriptionEs: "Valor declarado de las mercancías de importación.",
    descriptionEn: "Declared value of imported goods.",
    sourceSheets: ["551"],
    nativeCurrency: "USD",
  },
  export: {
    descriptionEs: "Valor declarado de las mercancías de exportación.",
    descriptionEn: "Declared value of exported goods.",
    sourceSheets: ["551"],
    nativeCurrency: "USD",
  },
  igiPaid: {
    descriptionEs: "IGI: impuesto de importación pagado en efectivo (FP 0).",
    descriptionEn: "Import duty paid in cash (payment method 0).",
    sourceSheets: ["557", "551"],
    nativeCurrency: "MXN",
  },
  ivaPaid: {
    descriptionEs: "IVA de importación pagado en efectivo (FP 0).",
    descriptionEn: "Import VAT paid in cash (payment method 0).",
    sourceSheets: ["557", "551"],
    nativeCurrency: "MXN",
  },
  ivaFp21: {
    descriptionEs:
      "IVA de importación registrado como crédito IVA/IEPS (FP 21).",
    descriptionEn:
      "Import VAT recorded as VAT/excise tax credit (payment method 21).",
    sourceSheets: ["557", "551"],
    nativeCurrency: "MXN",
  },
  rectifications: {
    descriptionEs:
      "Pedimentos distintos con una modificación o corrección registrada.",
    descriptionEn:
      "Distinct declarations with a recorded change or correction.",
    sourceSheets: ["701"],
  },
  redRate: {
    descriptionEs:
      "Porcentaje de eventos de selección aduanera marcados en rojo.",
    descriptionEn: "Percentage of customs selection events marked red.",
    sourceSheets: ["SEL"],
  },
  items: {
    descriptionEs: "Cantidad de registros de partidas de mercancías.",
    descriptionEn: "Number of goods line-item records.",
    sourceSheets: ["551"],
  },
};

export function monetarySources(
  sheets: readonly string[],
  nativeCurrency: Currency,
  displayCurrency: Currency,
): readonly string[] {
  return nativeCurrency === displayCurrency ? sheets : [...sheets, "501"];
}

export function metricHelp(key: string, currency: Currency): MetricHelp {
  const help = METRICS[key.replace(/(Usd|Mxn)$/, "")];
  if (!help) return { descriptionEs: "", descriptionEn: "", sourceSheets: [] };
  return {
    ...help,
    sourceSheets: help.nativeCurrency
      ? monetarySources(help.sourceSheets, help.nativeCurrency, currency)
      : help.sourceSheets,
  };
}

export function sheetSource(sheets: readonly string[], language: "es" | "en") {
  const codes = [...new Set(sheets.map((code) => code.toUpperCase()))];
  if (!codes.length) return "";
  const prefix =
    language === "en"
      ? codes.length === 1
        ? "Source: sheet"
        : "Source: sheets"
      : codes.length === 1
        ? "Fuente: hoja"
        : "Fuente: hojas";
  return `${prefix} ${codes.join(" · ")}`;
}
