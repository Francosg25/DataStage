import { Component, DestroyRef, computed, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Subject, switchMap, catchError, of, tap } from "rxjs";
import { Api } from "../core/api";
import {
  AnalyticsFilters,
  AnalyticsOptions,
  AnalyticsReport,
  Ranking,
} from "../core/analytics";
import { I18n } from "../core/i18n";
import { errorText } from "../core/models";
import { Icon } from "../shared/ui";
import { AnalyticsChart, ChartSeries } from "../shared/analytics-chart";

@Component({
  selector: "ds-analytics",
  imports: [FormsModule, RouterLink, Icon, AnalyticsChart],
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
  tab = signal("overview");
  filters: AnalyticsFilters = {
    source: "published",
    year: new Date().getFullYear(),
    startMonth: 1,
    endMonth: 12,
    operation: "",
    customs: "",
    document: "",
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
  readonly metricDefinitions = [
    {
      key: "declarations",
      es: "Pedimentos",
      en: "Declarations",
      unit: "",
      source: "501",
      color: "#11998b",
    },
    {
      key: "tradeUsd",
      es: "Valor de mercancías",
      en: "Trade value",
      unit: "USD",
      source: "551",
      color: "#447ec0",
    },
    {
      key: "customsMxn",
      es: "Valor en aduana",
      en: "Customs value",
      unit: "MXN",
      source: "551",
      color: "#8b70ae",
    },
    {
      key: "headerPaymentsMxn",
      es: "Contribuciones de pedimento",
      en: "Declaration contributions",
      unit: "MXN",
      source: "510",
      color: "#d69d31",
    },
    {
      key: "items",
      es: "Partidas",
      en: "Line items",
      unit: "",
      source: "551",
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
        if (data?.latestMonth) {
          this.second.set(data.latestMonth);
          this.first.set(Math.max(1, data.latestMonth - 1));
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
      ...this.series(first, labels[0], "#11998b"),
      ...this.series(second, labels[1], "#447ec0"),
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
    return key;
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
    return this.metricDefinitions.find((m) => m.key === this.trendMetric());
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
  print() {
    window.print();
  }
  aiPrompt() {
    const context = `source=${this.filters.source}, operation=${this.filters.operation || '""'}, customs=${this.filters.customs || '""'}, document=${this.filters.document || '""'}`;
    return this.t(
      `Analiza ${this.i18n.month(this.second())} de ${this.filters.year} frente a ${this.i18n.month(this.first())}. Filtros: ${context}. Explica los cambios y cita los indicadores.`,
      `Compare ${this.i18n.month(this.second())} ${this.filters.year} with ${this.i18n.month(this.first())}. Filters: ${context}. Explain changes and cite the metrics.`,
    );
  }
}
