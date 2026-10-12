import { TestBed } from "@angular/core/testing";
import { of, Subject, throwError } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Analytics } from "./analytics";
import { AnalyticsReport, PartTaxRow } from "../core/analytics";

describe("analytics filters and comparisons", () => {
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
      partTaxes: { rows },
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
  function setup() {
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
            analyticsOptions: () =>
              of({
                defaultSource: "reference",
                sources: [{ id: "reference", years: [2026] }],
              }),
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
