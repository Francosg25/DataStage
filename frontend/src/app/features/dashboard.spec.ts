import { TestBed } from "@angular/core/testing";
import { of } from "rxjs";
import { describe, expect, it } from "vitest";
import { Api } from "../core/api";
import { Dashboard } from "./dashboard";

describe("dashboard activity window", () => {
  it("defaults to six chronological published months without changing all-time totals", () => {
    const monthly = Array.from({ length: 18 }, (_, i) => ({
      period: `period-${i}`,
      rows: i + 1,
    }));
    TestBed.configureTestingModule({
      providers: [
        {
          provide: Api,
          useValue: {
            overview: () => of({ monthly, rowsCount: 171, recentRuns: [] }),
          },
        },
      ],
    });
    const component = TestBed.runInInjectionContext(() => new Dashboard());
    expect(component.visibleMonths()).toEqual(monthly.slice(-6));
    component.monthLimit.set(12);
    expect(component.visibleMonths()).toEqual(monthly.slice(-12));
    component.monthLimit.set(3);
    expect(component.visibleMonths()).toEqual(monthly.slice(-3));
    expect(component.overview()?.rowsCount).toBe(171);
    expect(component.overview()?.monthly).toHaveLength(18);
    component.overview.set(null);
    expect(component.visibleMonths()).toEqual([]);
  });
});
