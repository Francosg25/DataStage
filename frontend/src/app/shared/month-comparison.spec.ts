import { TestBed } from "@angular/core/testing";
import { of, Subject } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { AnalyticsFilters, AnalyticsReport } from "../core/analytics";
import { MonthComparison } from "./month-comparison";

describe("month/year comparison", () => {
  it("requests each year independently and cancels obsolete results", () => {
    const streams = Array.from(
      { length: 4 },
      () => new Subject<AnalyticsReport>(),
    );
    let call = 0;
    const analytics = vi.fn((_filters: AnalyticsFilters) => streams[call++]);
    TestBed.configureTestingModule({
      providers: [
        {
          provide: Api,
          useValue: {
            analytics,
            analyticsOptions: () =>
              of({
                defaultSource: "reference",
                sources: [{ id: "reference", years: [2026] }],
              }),
          },
        },
      ],
    });
    const component = TestBed.runInInjectionContext(
      () => new MonthComparison(),
    );
    component.baseline = "2025-12";
    component.comparison = "2026-01";
    component.load();
    expect(analytics.mock.calls[2][0]).toMatchObject({
      year: 2025,
      startMonth: 12,
      endMonth: 12,
    });
    expect(analytics.mock.calls[3][0]).toMatchObject({
      year: 2026,
      startMonth: 1,
      endMonth: 1,
    });
    for (const index of [2, 3]) {
      streams[index].next({
        year: 2026,
        totals: { igiPaid: index },
      } as unknown as AnalyticsReport);
      streams[index].complete();
    }
    for (const index of [0, 1]) {
      streams[index].next({ year: 1900 } as AnalyticsReport);
      streams[index].complete();
    }
    expect(component.result()?.[0].year).toBe(2026);
    expect(component.difference("igiPaid")).toBe(1);
  });
});
