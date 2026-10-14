import { TestBed } from "@angular/core/testing";
import { of, Observable, Subject, throwError } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { AnalyticsMonthlyReport } from "../core/analytics";
import { MonthComparison } from "./month-comparison";

const options = () =>
  of({
    defaultSource: "reference",
    sources: [{ id: "reference", years: [2026, 2025] }],
  });
function report(year = 2026): AnalyticsMonthlyReport {
  return {
    source: "reference",
    year,
    currency: "USD",
    generatedAt: "2026-10-13",
    monthly: Array.from({ length: 12 }, (_, index) => ({
      month: index + 1,
      available: index < 8,
      metrics: {
        igiPaid: index < 8 ? index * 10 : null,
        declarations: index < 8 ? index + 1 : null,
      },
    })),
  };
}
function create(analyticsMonths: ReturnType<typeof vi.fn>) {
  TestBed.configureTestingModule({
    providers: [
      {
        provide: Api,
        useValue: { analyticsMonths, analyticsOptions: options },
      },
    ],
  });
  return TestBed.runInInjectionContext(() => new MonthComparison());
}

describe("month/year comparison", () => {
  it("compares FP 21 independently and keeps import/export values separate", () => {
    const data = report();
    data.monthly[0].metrics = {
      igiPaid: 10,
      ivaFp21: 320,
      importUsd: 100,
      exportUsd: 200,
    };
    data.monthly[1].metrics = {
      igiPaid: 15,
      ivaFp21: 640,
      importUsd: 150,
      exportUsd: 500,
    };
    const component = create(vi.fn(() => of(data)));
    expect(component.metrics()).toHaveLength(9);
    expect(
      component.metrics().some((metric) => metric.key.startsWith("trade")),
    ).toBe(false);
    component.metric = "ivaFp21";
    expect(component.series()[0].values).toEqual([320, 640]);
    expect(component.difference("ivaFp21")).toBe(320);
    expect(component.difference("igiPaid")).toBe(5);
    expect(component.metricNote()).toContain("CERTIVA");
    component.metric = "exportUsd";
    expect(component.series()[0].values).toEqual([200, 500]);
    expect(component.difference("importUsd")).toBe(50);
    expect(component.difference("exportUsd")).toBe(300);
    component.currency = "MXN";
    component.load();
    expect(component.metric).toBe("exportMxn");
  });
  it("uses one lightweight yearly request for two months in the same year", () => {
    const analyticsMonths = vi.fn(() => of(report()));
    const component = create(analyticsMonths);
    expect(analyticsMonths).toHaveBeenCalledTimes(1);
    expect(analyticsMonths).toHaveBeenCalledWith({
      source: "reference",
      year: 2026,
      currency: "USD",
    });
    expect(component.result()?.map((month) => month.month)).toEqual([1, 2]);
    expect(component.difference("igiPaid")).toBe(10);
    component.baseline = "2026-03";
    component.comparison = "2026-04";
    component.load();
    expect(analyticsMonths).toHaveBeenCalledTimes(2);
    expect(
      component.result()?.map((month) => month.totals["declarations"]),
    ).toEqual([3, 4]);
  });

  it("requests each year independently and cancels obsolete results", () => {
    const streams = Array.from(
      { length: 3 },
      () => new Subject<AnalyticsMonthlyReport>(),
    );
    let call = 0;
    const analyticsMonths = vi.fn(() => streams[call++]);
    const component = create(analyticsMonths);
    component.baseline = "2025-12";
    component.comparison = "2026-01";
    component.load();
    expect(analyticsMonths.mock.calls).toHaveLength(3);
    expect(analyticsMonths).toHaveBeenNthCalledWith(2, {
      source: "reference",
      year: 2025,
      currency: "USD",
    });
    expect(analyticsMonths).toHaveBeenNthCalledWith(3, {
      source: "reference",
      year: 2026,
      currency: "USD",
    });
    for (const index of [1, 2]) {
      const current = report(index === 1 ? 2025 : 2026);
      current.monthly = [
        {
          month: index === 1 ? 12 : 1,
          available: true,
          metrics: { igiPaid: index },
        },
      ];
      streams[index].next(current);
      streams[index].complete();
    }
    streams[0].next(report(1900));
    streams[0].complete();
    expect(component.result()?.map((month) => month.year)).toEqual([
      2025, 2026,
    ]);
    expect(component.difference("igiPaid")).toBe(1);
  });

  it("preserves true zero and unavailable months when comparing", () => {
    const component = create(vi.fn(() => of(report())));
    component.comparison = "2026-12";
    component.load();
    expect(component.result()?.[0].totals["igiPaid"]).toBe(0);
    expect(component.result()?.[1].available).toBe(false);
    expect(component.result()?.[1].totals["igiPaid"]).toBeNull();
    expect(component.difference("igiPaid")).toBeNull();
  });

  it("does not request invalid dates and supports retry after a failed summary", () => {
    const analyticsMonths = vi.fn<() => Observable<AnalyticsMonthlyReport>>(
      () => throwError(() => ({ status: 500 })),
    );
    const component = create(analyticsMonths);
    expect(component.loading()).toBe(false);
    expect(component.error()).not.toBe("");
    component.baseline = "2026-00";
    component.load();
    expect(analyticsMonths).toHaveBeenCalledTimes(1);
    component.baseline = "2026-01";
    analyticsMonths.mockImplementation(() => of(report()));
    component.load();
    expect(component.error()).toBe("");
    expect(component.result()?.[0].year).toBe(2026);
  });
});
