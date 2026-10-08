import { Component, DestroyRef, computed, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { NgTemplateOutlet } from "@angular/common";
import { RouterLink } from "@angular/router";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Subject, switchMap, catchError, of, tap, finalize } from "rxjs";
import { Api } from "../core/api";
import {
  AnalyticsFilters,
  AnalyticsOptions,
  AnalyticsReport,
  Ranking,
  PartTaxRow,
} from "../core/analytics";
import { customsLabel } from "../core/customs-labels";
import { I18n } from "../core/i18n";
import { errorText } from "../core/models";
import { Icon } from "../shared/ui";
import { AnalyticsChart, ChartSeries } from "../shared/analytics-chart";

@Component({
  selector: "ds-analytics",
  imports: [FormsModule, NgTemplateOutlet, RouterLink, Icon, AnalyticsChart],
  templateUrl: "./analytics.html",
  styleUrl: "./analytics.scss",
})
export class Analytics {
  readonly i18n = inject(I18n);
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  private requests = new Subject<AnalyticsFilters>();
  options = signal<AnalyticsOptions | null>(null);
  report = signal<AnalyticsReport | null>(null);
  loading = signal(true);
  error = signal("");
  exportingPdf = signal(false);
  pdfError = signal("");
  tab = signal("overview");
  partSearch = signal("");
  partPage = signal(0);
  alertPage = signal(0);
  readonly pageSize = 25;
  readonly taxTypes = ["igi", "iva"] as const;
  taxRows = computed(() => {
    const search = this.partSearch().trim().toLowerCase();
    return (this.report()?.partTaxes?.rows || []).filter(
      (r) =>
        !search ||
        `${r.partNumber || ""} ${(r.alternatePartNumbers || []).join(" ")} ${r.tariff}`
          .toLowerCase()
          .includes(search),
    );
  });
  visibleTaxRows = computed(() =>
    this.taxRows().slice(
      this.partPage() * this.pageSize,
      (this.partPage() + 1) * this.pageSize,
    ),
  );
  visibleAlerts = computed(() =>
    (this.report()?.partTaxes?.alerts || []).slice(
      this.alertPage() * this.pageSize,
      (this.alertPage() + 1) * this.pageSize,
    ),
  );
  filters: AnalyticsFilters = {
    source: "published",
    year: new Date().getFullYear(),
    startMonth: 1,
    endMonth: 12,
    operation: "",
    customs: "",
    document: "",
    currency: "USD",
  };
  months = Array.from({ length: 12 }, (_, i) => i + 1);
  first = signal(7);
  second = signal(8);
  tableMetric = signal("tradeUsd");
  trendMetric = signal("tradeUsd");
  selectedMonths = computed(
    () =>
      this.report()?.monthly.filter(
        (m) =>
          m.month >= this.report()!.startMonth &&
          m.month <= this.report()!.endMonth,
      ) || [],
  );
  activeMonths = computed(() =>
    this.selectedMonths().filter((m) => m.available),
  );
  years = computed(
    () =>
      this.options()?.sources.find((s) => s.id === this.filters.source)
        ?.years || [],
  );
  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
  readonly tabs = [
    { id: "overview", es: "Panorama general", en: "Overview" },
    { id: "trade", es: "Comercio y mercancías", en: "Trade & goods" },
    { id: "taxes", es: "Contribuciones", en: "Contributions" },
    { id: "quality", es: "Control y calidad", en: "Control & quality" },
    { id: "definitions", es: "Fuentes y métricas", en: "Sources & metrics" },
  ];
  get metricDefinitions() {
    return [
      {
        key: "declarations",
        es: "Pedimentos",
        en: "Declarations",
        unit: "",
        source: "501",
        color: "#11998b",
      },
      {
        key: this.moneyKey("trade"),
        es: "Valor de mercancías",
        en: "Trade value",
        unit: this.currency(),
        source: "551",
        color: "#447ec0",
      },
      {
        key: "igiPaid",
        es: "IGI pagado",
        en: "Import duty paid (IGI)",
        unit: this.currency(),
        source: "557 · FP 0",
        color: "#2877b5",
      },
      {
        key: "ivaPaid",
        es: "IVA pagado",
        en: "VAT paid (IVA)",
        unit: this.currency(),
        source: "557 · FP 0",
        color: "#9b6520",
      },
      {
        key: "rectifications",
        es: "Rectificaciones",
        en: "Amendments",
        unit: "",
        source: "701",
        color: "#5a9cac",
      },
      {
        key: "redRate",
        es: "Selecciones en rojo",
        en: "Red selections",
        unit: "%",
        source: "SEL",
        color: "#cf7165",
      },
    ];
  }
  readonly tableCodes = [
    "501",
    "502",
    "503",
    "504",
    "505",
    "506",
    "507",
    "508",
    "509",
    "510",
    "511",
    "512",
    "520",
    "551",
    "552",
    "553",
    "554",
    "555",
    "556",
    "557",
    "558",
    "701",
    "702",
    "sel",
    "inci",
    "resumen",
  ];
  constructor() {
    this.requests
      .pipe(
        tap(() => {
          this.loading.set(true);
          this.error.set("");
        }),
        switchMap((f) =>
          this.api.analytics(f).pipe(
            catchError((e) => {
              this.error.set(errorText(e));
              return of(null);
            }),
          ),
        ),
        takeUntilDestroyed(this.destroy),
      )
      .subscribe((data) => {
        this.report.set(data);
        this.loading.set(false);
        this.partPage.set(0);
        this.alertPage.set(0);
        if (data?.latestMonth) {
          this.second.set(data.latestMonth);
          this.first.set(Math.max(data.startMonth || 1, data.latestMonth - 1));
        }
      });
    this.initialize();
  }
  initialize() {
    this.loading.set(true);
    this.error.set("");
    this.api
      .analyticsOptions()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (o) => {
          this.options.set(o);
          this.filters.source = o.defaultSource;
          this.filters.year =
            o.sources.find((s) => s.id === o.defaultSource)?.years[0] ||
            new Date().getFullYear();
          this.load();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
  load() {
    if (this.filters.startMonth > this.filters.endMonth)
      this.filters.endMonth = this.filters.startMonth;
    this.requests.next({ ...this.filters });
  }
  retry() {
    this.options() ? this.load() : this.initialize();
  }
  sourceChanged() {
    this.filters.year =
      this.options()?.sources.find((s) => s.id === this.filters.source)
        ?.years[0] || new Date().getFullYear();
    this.filters.operation = "";
    this.filters.customs = "";
    this.filters.document = "";
    this.load();
  }
  reset() {
    this.filters = {
      ...this.filters,
      startMonth: 1,
      endMonth: 12,
      operation: "",
      customs: "",
      document: "",
    };
    this.load();
  }
  dimensionFiltered() {
    return !!(
      this.filters.operation ||
      this.filters.customs ||
      this.filters.document
    );
  }
  labels() {
    return this.selectedMonths().map((m) => this.i18n.month(m.month, true));
  }
  series(key: string, label: string, color = "#11998b"): ChartSeries[] {
    return [
      {
        label,
        color,
        values: this.selectedMonths().map((m) => m.metrics[key]),
      },
    ];
  }
  pairSeries(
    first: string,
    second: string,
    labels: [string, string],
  ): ChartSeries[] {
    return [
      ...this.series(
        first,
        labels[0],
        first === "igiPaid" ? "#2877b5" : "#11998b",
      ),
      ...this.series(
        second,
        labels[1],
        second === "ivaPaid" ? "#9b6520" : "#447ec0",
      ),
    ];
  }
  ranking(key: string): Ranking[] {
    return this.report()?.breakdowns[key] || [];
  }
  rankLabels(key: string) {
    return this.ranking(key).map((r) => this.category(r.key, key));
  }
  rankSeries(key: string, label: string, color = "#447ec0"): ChartSeries[] {
    return [{ label, color, values: this.ranking(key).map((r) => r.value) }];
  }
  category(key: string, dimension: string): string {
    if (key === "other") return this.t("Otros", "Other");
    if (key === "unknown") return this.t("Sin especificar", "Unspecified");
    if (dimension === "operations")
      return key === "1"
        ? this.t("Importación", "Import")
        : key === "2"
          ? this.t("Exportación", "Export")
          : key;
    if (dimension === "inspection")
      return (
        {
          S: this.t("Simple", "Minor"),
          G: this.t("Grave", "Serious"),
          C: this.t("Correcto", "Correct"),
        }[key] || key
      );
    return customsLabel(key, dimension, this.i18n.language()) || key;
  }
  crossFilter(
    dimension: "customs" | "document" | "operation",
    ranking: string,
    index: number,
  ) {
    const key = this.ranking(ranking)[index]?.key;
    if (!key || ["other", "unknown"].includes(key)) return;
    this.filters[dimension] = this.filters[dimension] === key ? "" : key;
    this.load();
  }
  selectMonth(index: number) {
    const month = this.selectedMonths()[index]?.month;
    if (month) {
      this.second.set(month);
      this.first.set(Math.max(1, month - 1));
    }
  }
  format(value: number | null | undefined, unit = "", compact = false) {
    if (value != null && !compact && ["USD", "MXN"].includes(unit))
      return new Intl.NumberFormat(this.i18n.locale(), {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
    return (
      this.i18n.number(
        value,
        compact,
        unit === "%" ? 1 : compact ? 2 : unit ? 2 : 0,
      ) + (value != null && unit === "%" ? "%" : "")
    );
  }
  delta(value: number | null | undefined) {
    return value == null
      ? this.t("Sin base comparable", "No comparable baseline")
      : `${value > 0 ? "+" : ""}${this.i18n.number(value, false, 1)}%`;
  }
  spark(key: string) {
    const values = this.activeMonths().map((m) => m.metrics[key] || 0);
    const max = Math.max(...values, 1);
    return values.map((v) => Math.max(3, (v / max) * 30));
  }
  compareValue(month: number, key: string) {
    return this.report()?.monthly[month - 1]?.metrics[key] ?? null;
  }
  compareDelta(key: string) {
    const a = this.compareValue(this.first(), key),
      b = this.compareValue(this.second(), key);
    return a == null || b == null || a === 0
      ? null
      : ((b - a) / Math.abs(a)) * 100;
  }
  trendName() {
    return (
      this.metricDefinitions.find((m) => m.key === this.trendMetric()) ||
      this.metricDefinitions[1]
    );
  }
  currency() {
    return this.report()?.currency || this.filters.currency || "USD";
  }
  moneyKey(name: string) {
    return name + (this.currency() === "USD" ? "Usd" : "Mxn");
  }
  setCurrency(currency: "USD" | "MXN") {
    if (this.filters.currency === currency) return;
    this.filters.currency = currency;
    this.trendMetric.set("trade" + (currency === "USD" ? "Usd" : "Mxn"));
    this.load();
  }
  rectificationSeries(): ChartSeries[] {
    const colors = [
      "#2877b5",
      "#138679",
      "#a16b20",
      "#a65877",
      "#586bbb",
      "#78873c",
      "#ba6657",
      "#647a85",
    ];
    return (this.report()?.rectifications || []).map((r, i) => ({
      label: `${this.t("Patente", "Broker license")} ${r.patent}`,
      color: colors[i % colors.length],
      values: this.selectedMonths().map((m) => r.values[m.month - 1]),
    }));
  }
  topParts() {
    return (this.report()?.partTaxes?.rows || [])
      .filter((r) => r.partNumber && r.igi != null && r.igi > 0)
      .slice(0, 10);
  }
  partLabels() {
    return this.topParts().map((r) => `${r.partNumber} · ${r.tariff}`);
  }
  partSeries(): ChartSeries[] {
    return [
      {
        label: this.currency(),
        color: "#2877b5",
        values: this.topParts().map((r) => r.igi),
      },
    ];
  }
  taxValue(row: PartTaxRow, month: number, tax: "igi" | "iva") {
    if (
      month < (this.report()?.startMonth || 1) ||
      month > (this.report()?.endMonth || 12)
    )
      return null;
    const m = this.report()?.monthly[month - 1];
    if (
      !m?.available ||
      !Object.hasOwn(m.tables, "557") ||
      !Object.hasOwn(m.tables, "551")
    )
      return null;
    return (
      row.months[String(month)]?.[tax] ?? (row.months[String(month)] ? null : 0)
    );
  }
  taxDifference(row: PartTaxRow, tax: "igi" | "iva") {
    const a = this.taxValue(row, this.first(), tax),
      b = this.taxValue(row, this.second(), tax);
    return a == null || b == null ? null : b - a;
  }
  taxChange(row: PartTaxRow, tax: "igi" | "iva") {
    const a = this.taxValue(row, this.first(), tax),
      b = this.taxValue(row, this.second(), tax);
    return a == null || b == null || a === 0
      ? null
      : ((b - a) / Math.abs(a)) * 100;
  }
  searchParts(value: string) {
    this.partSearch.set(value);
    this.partPage.set(0);
  }
  exportParts() {
    this.exportRows(
      [
        "part_number",
        "alternate_part_numbers",
        "tariff",
        "year",
        "month",
        "currency",
        "igi_paid_fp0",
        "iva_paid_fp0",
      ],
      this.taxRows().flatMap((r) =>
        Object.entries(r.months).map(([month, v]) => [
          r.partNumber,
          (r.alternatePartNumbers || []).join(" | "),
          r.tariff,
          this.report()?.year,
          month,
          this.currency(),
          v.igi,
          v.iva,
        ]),
      ),
      "IGI-IVA",
    );
  }
  exportAlerts() {
    this.exportRows(
      [
        "year",
        "month",
        "broker_license",
        "declaration",
        "customs",
        "tariff",
        "item_sequence",
        "status",
        "candidates",
      ],
      (this.report()?.partTaxes?.alerts || []).map((r) => [
        r.year,
        r.month,
        r.patent,
        r.declaration,
        r.customs,
        r.tariff,
        r.sequence,
        r.status,
        r.candidates.join(" | "),
      ]),
      "NP-alerts",
    );
  }
  private exportRows(headers: string[], rows: unknown[][], name: string) {
    const csv = [headers, ...rows]
      .map((row) =>
        row
          .map(
            (v) =>
              '"' +
              String(v ?? "")
                .replace(/^[=+@\-\t\r]/, "'$&")
                .replace(/"/g, '""') +
              '"',
          )
          .join(","),
      )
      .join("\r\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `DataStage-${name}-${this.report()?.year}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  share() {
    const r = this.report();
    if (!r) return null;
    const a = r.totals["importUsd"],
      b = r.totals["tradeUsd"];
    return a == null || !b ? null : (a / b) * 100;
  }
  financialCosts(): ChartSeries[] {
    const totals = this.report()?.totals;
    return [
      {
        label: "MXN",
        color: "#d69d31",
        values: [
          "freightMxn",
          "insuranceMxn",
          "packingMxn",
          "incrementsMxn",
          "deductionsMxn",
        ].map((k) => totals?.[k] ?? null),
      },
    ];
  }
  qualitySeries(): ChartSeries[] {
    return [
      {
        label: this.t("Registros", "Records"),
        color: "#5a9cac",
        values: this.selectedMonths().map((m) => m.rows),
      },
    ];
  }
  downloadCsv() {
    const r = this.report();
    if (!r || this.loading()) return;
    const keys = Object.keys(r.totals);
    const rows: unknown[][] = [
      [
        this.t("Fuente", "Source"),
        r.source,
        this.t("Año", "Year"),
        r.year,
        this.t("Operación", "Operation"),
        this.filters.operation || "all",
        this.t("Aduana", "Customs"),
        this.filters.customs || "all",
        this.t("Documento", "Document"),
        this.filters.document || "all",
        this.t("Moneda", "Currency"),
        this.currency(),
      ],
      ["month", "available", ...keys],
      ...this.selectedMonths().map((m) => [
        m.month,
        m.available,
        ...keys.map((k) => m.metrics[k]),
      ]),
    ];
    const csv = rows
      .map((row) =>
        row
          .map(
            (v) =>
              '"' +
              String(v ?? "")
                .replace(/^[=+@\-\t\r]/, "'$&")
                .replace(/"/g, '""') +
              '"',
          )
          .join(","),
      )
      .join("\r\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `DataStage-${r.year}-${r.startMonth}-${r.endMonth}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  percentage(value: number | null) {
    return value === null
      ? this.t("Sin dato", "Unavailable")
      : new Intl.NumberFormat(this.i18n.locale(), {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(value) + "%";
  }
  downloadPdf() {
    const report = this.report();
    if (!report || this.loading() || this.exportingPdf()) return;
    const language = this.i18n.language();
    this.exportingPdf.set(true);
    this.pdfError.set("");
    this.api
      .analyticsPdf(report.appliedFilters, language, report.snapshotId)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.exportingPdf.set(false)),
      )
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement("a");
          anchor.href = url;
          anchor.download = `DataStage-${report.year}-${String(report.startMonth).padStart(2, "0")}-${String(report.endMonth).padStart(2, "0")}-${report.currency}-${language}.pdf`;
          anchor.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        },
        error: (error) =>
          this.pdfError.set(
            error.status === 409
              ? this.t(
                  "Los datos cambiaron. Actualiza el análisis y vuelve a descargar el PDF.",
                  "Data changed. Refresh analytics and download the PDF again.",
                )
              : this.t(
                  "No se pudo generar el PDF. Revisa la conexión y vuelve a intentarlo.",
                  "The PDF could not be generated. Check the connection and try again.",
                ),
          ),
      });
  }
  aiPrompt() {
    const context = `source=${this.filters.source}, operation=${this.filters.operation || '""'}, customs=${this.filters.customs || '""'}, document=${this.filters.document || '""'}`;
    return this.t(
      `Analiza ${this.i18n.month(this.second())} de ${this.filters.year} frente a ${this.i18n.month(this.first())}. Filtros: ${context}. Explica los cambios y cita los indicadores.`,
      `Compare ${this.i18n.month(this.second())} ${this.filters.year} with ${this.i18n.month(this.first())}. Filters: ${context}. Explain changes and cite the metrics.`,
    );
  }
}
