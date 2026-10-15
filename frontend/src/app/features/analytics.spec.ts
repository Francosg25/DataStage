import { TestBed } from "@angular/core/testing";
import { of, Subject, throwError } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Analytics } from "./analytics";
import {
  AnalyticsOptions,
  AnalyticsReport,
  PartAlert,
  PartTaxRow,
} from "../core/analytics";

describe("analytics filters and comparisons", () => {
  function pendingReport(alerts: PartAlert[]) {
    return { partTaxes: { alerts } } as unknown as AnalyticsReport;
  }
  function pendingAlert(index: number, candidates: string[] = []): PartAlert {
    return {
      year: 2026,
      month: 6,
      patent: "3658",
      declaration: String(index),
      customs: "730",
      tariff: "85045091",
      sequence: "1",
      status: candidates.length > 1 ? "ambiguous" : "missing",
      candidates,
      observations: [],
    };
  }
  it("searches candidates across every pending page before pagination and preserves independent PN filters", () => {
    const { component, analytics } = setup();
    const alerts = Array.from({ length: 76 }, (_, index) =>
      pendingAlert(index),
    );
    alerts[55] = pendingAlert(55, ["1606-5YY3019", "1606-5YY3020"]);
    component.report.set(pendingReport(alerts));
    component.partSearch.set("OTHER-PN");
    component.partTariff.set("84733004");
    component.alertPage.set(2);
    component.searchAlerts("  5yy3020  ");
    expect(component.filteredAlerts()).toEqual([alerts[55]]);
    expect(component.visibleAlerts()).toEqual([alerts[55]]);
    expect(component.alertPage()).toBe(0);
    expect(component.alertPages()).toBe(1);
    expect(component.partSearch()).toBe("OTHER-PN");
    expect(component.partTariff()).toBe("84733004");
    expect(component.report()?.partTaxes.alerts).toHaveLength(76);
    expect(analytics).toHaveBeenCalledTimes(1);
  });
  it("finds PN mentioned only in 558 observations and distinguishes no matches from an empty search", () => {
    const { component } = setup();
    const missing = {
      ...pendingAlert(1),
      observations: ["No.Parte 1651-EQM0165EN | P.O 123"],
    };
    component.report.set(pendingReport([missing, pendingAlert(2)]));
    component.searchAlerts("eqm0165");
    expect(component.visibleAlerts()).toEqual([missing]);
    component.searchAlerts("NOT-PRESENT");
    expect(component.filteredAlerts()).toEqual([]);
    expect(component.alertPages()).toBe(1);
    component.searchAlerts("  ");
    expect(component.filteredAlerts()).toHaveLength(2);
    component.searchAlerts("");
    expect(component.filteredAlerts()).toHaveLength(2);
    expect(component.alertPage()).toBe(0);
  });
  it("paginates matching results and exports all of them with their candidate and observation evidence", () => {
    const { component } = setup();
    const matches = Array.from({ length: 26 }, (_, index) => ({
      ...pendingAlert(index, ["1616-5TP1037", "OTHER-PN"]),
      observations: ["NP 1616-5TP1037N", "P.O 789"],
    }));
    component.report.set(pendingReport([pendingAlert(99), ...matches]));
    component.searchAlerts("1616-5TP1037");
    expect(component.alertPages()).toBe(2);
    expect(component.visibleAlerts()).toHaveLength(25);
    component.alertPage.set(1);
    expect(component.visibleAlerts()).toEqual([matches[25]]);
    const exportRows = vi
      .spyOn(
        component as unknown as {
          exportRows(headers: string[], rows: unknown[][], name: string): void;
        },
        "exportRows",
      )
      .mockImplementation(() => {});
    component.exportAlerts();
    const [headers, rows] = exportRows.mock.calls[0];
    expect(headers.slice(-2)).toEqual(["candidates", "observations_558"]);
    expect(rows).toHaveLength(26);
    expect(rows[0].slice(-2)).toEqual([
      "1616-5TP1037 | OTHER-PN",
      "NP 1616-5TP1037N | P.O 789",
    ]);
    component.searchAlerts("");
    expect(component.filteredAlerts()).toHaveLength(27);
    expect(component.alertPage()).toBe(0);
  });
  it("clears pending PN search on Reset and when switching the source", () => {
    const { component } = setup();
    component.searchAlerts("1606");
    component.reset();
    expect(component.alertSearch()).toBe("");
    component.searchAlerts("1606");
    component.filters.source = "published";
    component.sourceChanged();
    expect(component.alertSearch()).toBe("");
  });
  it("opens with the annual range and selects the latest loaded period independently of the visible report", () => {
    const { component, analytics } = setup();
    expect(analytics.mock.calls[0][0]).toMatchObject({
      year: 2026,
      startMonth: 1,
      endMonth: 12,
    });
    component.filters = {
      source: "reference",
      year: 2025,
      startMonth: 4,
      endMonth: 4,
      operation: "1",
      customs: "240",
      document: "A1",
      currency: "MXN",
    };
    component.report.set({ year: 2025, latestMonth: 4 } as AnalyticsReport);
    component.loading.set(false);
    component.selectLatestMonth();
    expect(analytics).toHaveBeenCalledTimes(2);
    expect(analytics.mock.calls.at(-1)?.[0]).toEqual({
      source: "reference",
      year: 2026,
      startMonth: 9,
      endMonth: 9,
      operation: "1",
      customs: "240",
      document: "A1",
      currency: "MXN",
    });
    expect(component.isLatestPeriod()).toBe(true);
    component.reset();
    expect(analytics.mock.calls.at(-1)?.[0]).toMatchObject({
      year: 2026,
      startMonth: 1,
      endMonth: 12,
    });
    expect(component.isLatestPeriod()).toBe(false);
  });
  it("uses the selected source's latest year and month across a year boundary", () => {
    const { component, analytics } = setup({
      defaultSource: "reference",
      sources: [
        {
          id: "reference",
          years: [2026],
          latestPeriod: { year: 2026, month: 9 },
        },
        {
          id: "published",
          years: [2027, 2026],
          latestPeriod: { year: 2027, month: 1 },
        },
      ],
    });
    component.filters.source = "published";
    component.filters.year = 2026;
    component.filters.startMonth = 12;
    component.filters.endMonth = 12;
    component.loading.set(false);
    component.selectLatestMonth();
    expect(analytics.mock.calls.at(-1)?.[0]).toMatchObject({
      source: "published",
      year: 2027,
      startMonth: 1,
      endMonth: 1,
    });
    expect(component.latestPeriod()).toEqual({ year: 2027, month: 1 });
  });
  it("does not invent a month for empty sources or request data while already loading", () => {
    const { component, analytics } = setup();
    component.selectLatestMonth();
    expect(analytics).toHaveBeenCalledTimes(1);
    component.loading.set(false);
    component.filters.source = "published";
    const original = { ...component.filters };
    expect(component.latestPeriod()).toBeNull();
    component.selectLatestMonth();
    expect(component.filters).toEqual(original);
    expect(component.isLatestPeriod()).toBe(false);
    expect(analytics).toHaveBeenCalledTimes(1);
  });
  it("keeps import/export values and colors aligned with their KPI cards in both currencies and languages", () => {
    const { component } = setup();
    for (const currency of ["USD", "MXN"] as const) {
      component.report.set({
        currency,
        startMonth: 1,
        endMonth: 1,
        monthly: [
          {
            month: 1,
            metrics: {
              importUsd: 100,
              exportUsd: 200,
              importMxn: 1700,
              exportMxn: 3400,
            },
          },
        ],
      } as unknown as AnalyticsReport);
      for (const language of ["es", "en"] as const) {
        component.i18n.set(language);
        const series = component.tradeSeries();
        const definitions = component.metricDefinitions;
        expect(series[0].color).toBe("#447ec0");
        expect(series[1].color).toBe("#22978a");
        expect(series[0].color).toBe(
          definitions.find((m) => m.key === component.moneyKey("import"))
            ?.color,
        );
        expect(series[1].color).toBe(
          definitions.find((m) => m.key === component.moneyKey("export"))
            ?.color,
        );
        expect(series.map((s) => s.label)).toEqual(
          language === "es"
            ? ["Importaciones", "Exportaciones"]
            : ["Imports", "Exports"],
        );
        expect(series.map((s) => s.values)).toEqual(
          currency === "USD" ? [[100], [200]] : [[1700], [3400]],
        );
      }
    }
  });
  it("shows eight indicators with cash IGI and VAT plus FP 21 VAT in both languages", () => {
    const { component } = setup();
    expect(component.metricDefinitions).toHaveLength(8);
    expect(component.metricDefinitions.map((metric) => metric.key)).toEqual([
      "declarations",
      "importUsd",
      "exportUsd",
      "igiPaid",
      "ivaPaid",
      "ivaFp21",
      "rectifications",
      "redRate",
    ]);
    expect(
      component.metricDefinitions.find((metric) => metric.key === "ivaFp21")
        ?.es,
    ).toBe("IVA · FP 21");
    component.i18n.set("en");
    expect(
      component.metricDefinitions.some((metric) => metric.key === "igiFp21"),
    ).toBe(false);
    expect(
      component.metricDefinitions.find((metric) => metric.key === "ivaFp21")
        ?.source,
    ).toContain("VAT/excise credit");
  });
  it("uses each payment method's own monthly changes and preserves the selected metric across currencies", () => {
    const { component } = setup();
    component.report.set({
      currency: "USD",
      startMonth: 1,
      endMonth: 2,
      latest: { ivaPaid: 6, ivaFp21: 24 },
      previous: { ivaPaid: 8, ivaFp21: 32 },
      deltas: { ivaPaid: -25, ivaFp21: -25 },
      monthly: [
        {
          month: 1,
          available: true,
          metrics: { ivaPaid: 8, ivaFp21: 32, exportUsd: 200 },
        },
        {
          month: 2,
          available: true,
          metrics: { ivaPaid: 6, ivaFp21: 24, exportUsd: 500 },
        },
      ],
    } as unknown as AnalyticsReport);
    expect(component.series("ivaFp21", "IVA FP 21")[0].values).toEqual([
      32, 24,
    ]);
    expect(component.metricDeltaLabel("ivaFp21")).toBe("-25%");
    expect(component.compareDelta("exportUsd")).toBeNull();
    component.first.set(1);
    component.second.set(2);
    expect(component.compareDelta("exportUsd")).toBe(150);
    component.trendMetric.set("exportUsd");
    component.setCurrency("MXN");
    expect(component.trendMetric()).toBe("exportMxn");
    component.report.set({ ...component.report()!, currency: "MXN" });
    expect(
      component.metricDefinitions.find((metric) => metric.key === "exportMxn")
        ?.unit,
    ).toBe("MXN");
    component.trendMetric.set("ivaFp21");
    component.setCurrency("USD");
    expect(component.trendMetric()).toBe("ivaFp21");
  });
  it("finds the principal part using its alternate code without duplicating tax rows", () => {
    const { component } = setup();
    const row = {
      partNumber: "1200-1030847AN",
      alternatePartNumbers: ["1200-1030847AND"],
      tariff: "123",
      items: 1,
      igi: 100,
      iva: 0,
      months: { "1": { igi: 100, iva: 0 } },
    };
    component.report.set({
      partTaxes: { rows: [row] },
    } as unknown as AnalyticsReport);
    component.searchParts("1200-1030847AND");
    expect(component.taxRows()).toEqual([row]);
  });
  function partReport(rows: PartTaxRow[], startMonth = 1, endMonth = 3) {
    return {
      year: 2026,
      currency: "MXN",
      startMonth,
      endMonth,
      partTaxes: { rows, available: true, unmatchedTaxRows: 0 },
      monthly: Array.from({ length: 12 }, (_, i) => ({
        month: i + 1,
        available: true,
        tables: { "551": 1, "557": 1, "558": 1 },
      })),
    } as unknown as AnalyticsReport;
  }
  function partRow(
    partNumber: string | null,
    tariff = "84733004",
    igi = 100,
  ): PartTaxRow {
    return {
      partNumber,
      tariff,
      alternatePartNumbers: [],
      items: 1,
      igi,
      iva: 20,
      months: { "1": { igi, iva: 20 } },
    };
  }
  it("ranks tariffs by all cash duty amounts, including unassigned PN and net adjustments", () => {
    const { component } = setup();
    component.report.set(
      partReport([
        partRow("PN-A", "85044099", 100),
        partRow("PN-B", "85044099", 300),
        partRow(null, "84733004", 1000),
        partRow("PN-C", "84733004", -100),
        partRow("PN-ZERO", "00000000", 0),
      ]),
    );
    expect(component.topTariffTaxes()).toEqual([
      { tariff: "84733004", igi: 900 },
      { tariff: "85044099", igi: 400 },
    ]);
    expect(component.tariffTaxLabels()).toEqual(["84733004", "85044099"]);
    expect(component.tariffTaxSeries()[0].values).toEqual([900, 400]);
    component.selectPartTariff("85044099");
    expect(component.topTariffTaxes()).toEqual([
      { tariff: "85044099", igi: 400 },
    ]);
    component.searchParts("PN-A");
    expect(component.tariffTaxSeries()[0].values).toEqual([100]);
  });
  it("filters before taking the top ten tariffs and handles unknown amounts and missing coverage", () => {
    const { component } = setup();
    const rows = Array.from({ length: 12 }, (_, i) =>
      partRow(`PN-${i}`, String(i).padStart(8, "0"), i + 1),
    );
    const report = partReport(rows);
    report.partTaxes.observationSourceAvailable = false;
    component.report.set(report);
    expect(component.topTariffTaxes()).toHaveLength(10);
    expect(component.topTariffTaxes()[0]).toEqual({
      tariff: "00000011",
      igi: 12,
    });
    component.selectPartTariff("00000000");
    expect(component.tariffTaxSeries()[0].values).toEqual([1]);
    component.clearPartFilters();
    component.report.set(
      partReport([...rows, { ...partRow(null), igi: null }]),
    );
    expect(component.topTariffTaxes()).toEqual([]);
    component.report.set({
      ...report,
      partTaxes: { ...report.partTaxes, available: false },
    });
    expect(component.topTariffTaxes()).toEqual([]);
    component.report.set({
      ...report,
      partTaxes: { ...report.partTaxes, unmatchedTaxRows: 1 },
    });
    expect(component.topTariffTaxes()).toEqual([]);
  });
  it("combines independent PN and tariff filters, including aliases, and resets pagination", () => {
    const { component } = setup();
    const primary = {
      ...partRow("1200-1030847AN"),
      alternatePartNumbers: ["1200-1030847AND"],
    };
    const otherTariff = { ...primary, tariff: "85044099" };
    const otherPart = partRow("2200-001");
    component.report.set(partReport([primary, otherTariff, otherPart]));
    component.partPage.set(2);
    component.selectPartTariff("84733004");
    expect(component.partPage()).toBe(0);
    expect(component.taxRows()).toEqual([primary, otherPart]);
    expect(component.partNumberOptions()).toEqual([
      "1200-1030847AN",
      "1200-1030847AND",
      "2200-001",
    ]);
    component.partPage.set(1);
    component.searchParts("  1200-1030847and  ");
    expect(component.partPage()).toBe(0);
    expect(component.taxRows()).toEqual([primary]);
    expect(component.topParts()).toEqual([primary]);
    expect(component.partTrendSeries().map((series) => series.values)).toEqual([
      [100, 0, 0],
      [20, 0, 0],
    ]);
    component.searchParts("84733004");
    expect(component.taxRows()).toEqual([]);
    component.clearPartFilters();
    expect(component.partTariff()).toBe("");
    expect(component.partSearch()).toBe("");
    expect(component.taxRows()).toHaveLength(3);
  });
  it("filters before choosing the ten highest-duty parts and excludes unassigned amounts", () => {
    const { component } = setup();
    const rows = Array.from({ length: 12 }, (_, i) =>
      partRow(`PN-${i}`, "84733004", i + 1),
    );
    const selected = partRow("PN-SELECTED", "85044099", 0.5);
    component.report.set(
      partReport([selected, partRow(null, "85044099", 9999), ...rows]),
    );
    expect(component.topParts().map((row) => row.igi)).toEqual([
      12, 11, 10, 9, 8, 7, 6, 5, 4, 3,
    ]);
    component.selectPartTariff("85044099");
    expect(component.topParts()).toEqual([selected]);
    expect(component.partLabels()).toEqual(["PN-SELECTED · 85044099"]);
    expect(component.partSeries()[0].values).toEqual([0.5]);
    expect(component.taxRows()).toHaveLength(2);
    expect(component.partMonthlyTotals()[0]).toEqual({ igi: 0.5, iva: 20 });
    expect(component.report()?.partTaxes.rows[0]).toBe(selected);
  });
  it("sums all matching parts for the trend, including VAT-only rows beyond the top ten", () => {
    const { component } = setup();
    const rows = Array.from({ length: 12 }, (_, i) =>
      partRow(`PN-${i}`, "84733004", 10),
    );
    const vatOnly = {
      ...partRow("PN-VAT", "84733004", 0),
      iva: 50,
      months: { "1": { igi: 0, iva: 50 } },
    };
    const unassigned = partRow(null, "84733004", 9999);
    component.report.set(partReport([...rows, vatOnly, unassigned]));
    expect(component.topParts()).toHaveLength(10);
    expect(component.partMonthlyTotals()).toEqual([
      { igi: 120, iva: 290 },
      { igi: 0, iva: 0 },
      { igi: 0, iva: 0 },
    ]);
    component.i18n.set("en");
    expect(component.partTrendSeries().map((series) => series.label)).toEqual([
      "IMPORT DUTY",
      "VAT",
    ]);
    expect(component.currency()).toBe("MXN");
    component.i18n.set("es");
    expect(component.partTrendSeries().map((series) => series.label)).toEqual([
      "IGI",
      "IVA",
    ]);
  });
  it("preserves unknown amounts and distinguishes missing coverage from zero payments within the range", () => {
    const { component } = setup();
    const row = {
      ...partRow("PN-1"),
      months: { "2": { igi: null, iva: 15 }, "3": { igi: 25, iva: null } },
    };
    const report = partReport([row, partRow("PN-2")], 2, 7);
    report.monthly[3].available = false;
    delete report.monthly[4].tables["557"];
    delete report.monthly[5].tables["558"];
    component.report.set(report);
    expect(component.partMonthlyTotals()).toEqual([
      { igi: null, iva: 15 },
      { igi: 25, iva: null },
      { igi: null, iva: null },
      { igi: null, iva: null },
      { igi: null, iva: null },
      { igi: 0, iva: 0 },
    ]);
    component.searchParts("no-match");
    expect(
      component
        .partMonthlyTotals()
        .every((month) => month.igi === null && month.iva === null),
    ).toBe(true);
    expect(component.topParts()).toEqual([]);
  });
  it("shows April cash VAT without assigning payments to unidentified parts", () => {
    const { component } = setup();
    const identified = {
      ...partRow("PN-APRIL", "84807103"),
      months: { "4": { igi: 64582.56, iva: 0 } },
    };
    const unassigned = {
      ...partRow(null, "84807103"),
      months: { "4": { igi: 2788.43, iva: 296.99 } },
    };
    const otherTariff = {
      ...partRow(null, "OTHER"),
      months: { "4": { igi: 100, iva: 200 } },
    };
    component.report.set(
      partReport([identified, unassigned, otherTariff], 4, 4),
    );
    component.selectPartTariff("84807103");
    expect(component.partMonthlyTotals()).toEqual([{ igi: 64582.56, iva: 0 }]);
    expect(component.partUnassignedTotals()).toEqual({
      igi: 2788.43,
      iva: 296.99,
    });
    component.searchParts("PN-APRIL");
    expect(component.partUnassignedTotals()).toEqual({ igi: 0, iva: 0 });
  });
  it("keeps unavailable unassigned payments distinct from real zero", () => {
    const { component } = setup();
    const row = { ...partRow(null), months: { "4": { igi: null, iva: 0 } } };
    const report = partReport([row], 4, 4);
    component.report.set(report);
    expect(component.partUnassignedTotals()).toEqual({ igi: null, iva: 0 });
    report.monthly[3].available = false;
    component.report.set({ ...report });
    expect(component.partUnassignedTotals()).toEqual({ igi: null, iva: null });
  });
  it("does not label partial unassigned amounts or an incomplete top ten as complete", () => {
    const { component } = setup();
    const report = partReport([partRow(null), partRow("KNOWN")], 1, 2);
    delete report.monthly[1].tables["557"];
    report.partTaxes.available = false;
    component.report.set(report);
    expect(component.partUnassignedTotals()).toEqual({ igi: null, iva: null });
    expect(component.topParts()).toEqual([]);
    component.report.set(
      partReport(
        [{ ...partRow("UNKNOWN"), igi: null }, partRow("KNOWN")],
        1,
        2,
      ),
    );
    expect(component.topParts()).toEqual([]);
  });
  it("shows each tax on its own scale without changing its monthly values", () => {
    const { component } = setup();
    component.report.set(partReport([partRow("PN", "123", 100000)], 1, 1));
    expect(component.partTrendSeries("igi")[0].values).toEqual([100000]);
    expect(component.partTrendSeries("iva")[0].values).toEqual([20]);
    expect(component.partTrendSeries("igi")).toHaveLength(1);
  });
  it("keeps missing spark values empty and comparisons within the selected range", () => {
    const { component } = setup();
    component.report.set({
      startMonth: 1,
      endMonth: 3,
      monthly: [
        { month: 1, available: true, metrics: { declarations: 10 } },
        { month: 2, available: true, metrics: { declarations: 0 } },
        { month: 3, available: false, metrics: { declarations: null } },
        { month: 4, available: true, metrics: { declarations: 30 } },
      ],
    } as unknown as AnalyticsReport);
    expect(component.spark("declarations")).toEqual([30, 0, null]);
    expect(component.compareValue(4, "declarations")).toBeNull();
  });
  it("keeps unknown trade operations visible rather than dropping their value", () => {
    const { component } = setup();
    component.report.set({
      startMonth: 1,
      endMonth: 1,
      currency: "USD",
      monthly: [
        {
          month: 1,
          metrics: { importUsd: 100, exportUsd: 20, unclassifiedTradeUsd: 3 },
        },
      ],
    } as unknown as AnalyticsReport);
    expect(component.tradeSeries().map((s) => s.values)).toEqual([
      [100],
      [20],
      [3],
    ]);
  });
  function setup(
    options: AnalyticsOptions = {
      defaultSource: "reference",
      sources: [
        {
          id: "reference",
          years: [2026],
          latestPeriod: { year: 2026, month: 9 },
        },
        { id: "published", years: [], latestPeriod: null },
      ],
    },
  ) {
    const first = new Subject<AnalyticsReport>();
    const second = new Subject<AnalyticsReport>();
    const analytics = vi
      .fn()
      .mockReturnValueOnce(first)
      .mockReturnValue(second);
    const analyticsPdf = vi
      .fn()
      .mockReturnValue(throwError(() => ({ status: 409 })));
    TestBed.configureTestingModule({
      providers: [
        {
          provide: Api,
          useValue: {
            analyticsOptions: () => of(options),
            analytics,
            analyticsPdf,
          },
        },
      ],
    });
    return {
      component: TestBed.runInInjectionContext(() => new Analytics()),
      first,
      second,
      analytics,
      analyticsPdf,
    };
  }
  it("exports the displayed filters and snapshot and allows retry after a conflict", () => {
    const { component, analyticsPdf } = setup();
    const appliedFilters = {
      source: "reference",
      year: 2026,
      startMonth: 1,
      endMonth: 6,
      operation: "1",
      customs: "240",
      document: "",
      currency: "MXN" as const,
    };
    component.report.set({
      appliedFilters,
      snapshotId: "snapshot",
    } as AnalyticsReport);
    component.loading.set(false);
    component.filters.startMonth = 9;
    component.i18n.set("en");
    component.downloadPdf();
    expect(analyticsPdf).toHaveBeenCalledWith(appliedFilters, "en", "snapshot");
    expect(component.pdfError()).toContain("Data changed");
    expect(component.exportingPdf()).toBe(false);
    component.downloadPdf();
    expect(analyticsPdf).toHaveBeenCalledTimes(2);
  });
  it("guards PDF downloads while loading or exporting", () => {
    const { component, analyticsPdf } = setup();
    component.downloadPdf();
    component.report.set({ snapshotId: "s" } as AnalyticsReport);
    component.downloadPdf();
    component.loading.set(false);
    component.exportingPdf.set(true);
    component.downloadPdf();
    expect(analyticsPdf).not.toHaveBeenCalled();
  });
  it("shows small amendment rates to two decimals without inventing missing rates", () => {
    const { component } = setup();
    component.i18n.set("en");
    expect(component.percentage(0.46)).toBe("0.46%");
    expect(component.percentage(0)).toBe("0.00%");
    expect(component.percentage(null)).toBe("Unavailable");
  });
  it("cancels obsolete requests when a filter changes", () => {
    const { component, first, second, analytics } = setup();
    component.filters.operation = "1";
    component.load();
    const current = { source: "reference", latestMonth: 2 } as AnalyticsReport;
    second.next(current);
    first.next({ source: "outdated" } as AnalyticsReport);
    expect(component.report()).toBe(current);
    expect(analytics.mock.calls[0][0].operation).toBe("");
    expect(analytics.mock.calls[1][0].operation).toBe("1");
  });
  it("does not present missing or zero baselines as a percentage increase", () => {
    const { component } = setup();
    component.report.set({
      monthly: [{ metrics: { tradeUsd: 0 } }, { metrics: { tradeUsd: 100 } }],
    } as unknown as AnalyticsReport);
    component.first.set(1);
    component.second.set(2);
    expect(component.compareDelta("tradeUsd")).toBeNull();
    component.first.set(2);
    component.second.set(1);
    expect(component.compareDelta("tradeUsd")).toBe(-100);
    component.second.set(3);
    expect(component.compareDelta("tradeUsd")).toBeNull();
  });
  it("expresses rate changes as percentage points, including a zero baseline", () => {
    const { component } = setup();
    component.i18n.set("es");
    expect(component.rateDifference(30, 20)).toBe("+10 p.p.");
    expect(component.rateDifference(5, 0)).toBe("+5 p.p.");
    expect(component.rateDifference(5, null)).toBe("Sin base comparable");
  });
  it("uses the selected currency and describes codes without changing identifiers", () => {
    const { component, analytics } = setup();
    component.setCurrency("MXN");
    expect(analytics.mock.calls.at(-1)?.[0].currency).toBe("MXN");
    component.i18n.set("en");
    expect(component.category("1", "headerTaxes")).toContain(
      "Customs processing fee",
    );
    expect(component.category("ZYA", "countries")).toContain("Netherlands");
    expect(component.category("521", "customs")).toContain("Mariano Escobedo");
    expect(component.category("DAT", "incoterms")).toContain(
      "Description not verified",
    );
  });
  it("does not show zero for part payments outside the report range", () => {
    const { component } = setup();
    component.report.set({
      startMonth: 2,
      endMonth: 2,
      monthly: [
        { available: true, tables: { 551: 1, 557: 1 } },
        { available: true, tables: { 551: 1, 557: 1 } },
      ],
    } as unknown as AnalyticsReport);
    const row = {
      partNumber: "NP-1",
      tariff: "123",
      items: 1,
      igi: 10,
      iva: 0,
      months: { "2": { igi: 10, iva: 0 } },
    };
    expect(component.taxValue(row, 1, "igi")).toBeNull();
    expect(component.taxValue(row, 2, "igi")).toBe(10);
  });
});
