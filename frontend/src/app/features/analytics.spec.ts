import { TestBed } from "@angular/core/testing";
import { of, Subject, throwError } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Analytics } from "./analytics";
import { AnalyticsReport } from "../core/analytics";

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
