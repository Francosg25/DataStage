import { TestBed } from "@angular/core/testing";
import { FormBuilder } from "@angular/forms";
import { Router } from "@angular/router";
import { of, Subject, throwError } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Period, Run, runLabel } from "../core/models";
import { Consolidated } from "./consolidated";

const period = (
  month: number,
  year = 2026,
  activeRunId: string | null = `run-${month}`,
): Period => ({
  id: `${year}-${month}`,
  year,
  month,
  name: `${month}_${year}`,
  activeRunId,
  version: 1,
});

function setup(
  periods = of([period(1)]),
  annual = vi.fn<Api["annual"]>(() => throwError(() => ({ status: 0 }))),
) {
  const navigate = vi.fn();
  TestBed.configureTestingModule({
    providers: [
      FormBuilder,
      { provide: Api, useValue: { periods: () => periods, annual } },
      { provide: Router, useValue: { navigate } },
    ],
  });
  const component = TestBed.runInInjectionContext(() => new Consolidated());
  component.form.setValue({
    startYear: 2026,
    startMonth: 1,
    endYear: 2026,
    endMonth: 8,
  });
  return { component, annual, navigate };
}

describe("consolidated uploads", () => {
  it("includes only published months in the selected year and range, in order", () => {
    const { component } = setup(
      of([
        period(8),
        period(9),
        period(1),
        period(2, 2025),
        period(3, 2026, null),
      ]),
    );
    expect(component.sources().map((p) => p.month)).toEqual([1, 8]);
  });

  it("preserves idempotency on retry and renews it when the range changes", () => {
    const { component, annual } = setup();
    component.submit();
    expect(component.busy()).toBe(false);
    expect(component.form.enabled).toBe(true);
    expect(annual.mock.calls[0][0]).toEqual({
      startYear: 2026,
      startMonth: 1,
      endYear: 2026,
      endMonth: 8,
    });
    component.submit();
    expect(annual.mock.calls[0][1]).toBe(annual.mock.calls[1][1]);
    component.form.controls.endMonth.setValue(7);
    component.submit();
    expect(annual.mock.calls[2][1]).not.toBe(annual.mock.calls[1][1]);
  });

  it("does not submit without published sources or with an invalid year", () => {
    const { component, annual } = setup(of([]));
    component.submit();
    component.periods.set([period(1)]);
    component.form.controls.startYear.setValue(1800);
    component.submit();
    expect(annual).not.toHaveBeenCalled();
  });

  it("does not submit while sources are loading", () => {
    const response = new Subject<Period[]>();
    const { component, annual } = setup(response);
    expect(component.loading()).toBe(true);
    component.submit();
    expect(annual).not.toHaveBeenCalled();
    response.next([period(1)]);
    expect(component.loading()).toBe(false);
    component.submit();
    expect(annual).toHaveBeenCalledOnce();
  });

  it("shows a source loading failure and stops the progress indicator", () => {
    const { component, annual } = setup(throwError(() => ({ status: 0 })));
    expect(component.loading()).toBe(false);
    expect(component.error()).not.toBe("");
    component.submit();
    expect(annual).not.toHaveBeenCalled();
  });

  it("includes both bounds across years and counts gaps without inventing sources", () => {
    const { component } = setup(
      of([
        period(4, 2026),
        period(3, 2026),
        period(3, 2025),
        period(4, 2025),
        period(12, 2025),
        period(1, 2026, null),
      ]),
    );
    component.form.setValue({
      startYear: 2025,
      startMonth: 4,
      endYear: 2026,
      endMonth: 3,
    });
    expect(component.form.valid).toBe(true);
    expect(component.sources().map((p) => p.id)).toEqual([
      "2025-4",
      "2025-12",
      "2026-3",
    ]);
    expect(component.monthCount()).toBe(12);
  });

  it("supports a non-January start and a single month", () => {
    const { component } = setup(
      of([period(1), period(4), period(5), period(6)]),
    );
    component.form.patchValue({ startMonth: 4, endMonth: 5 });
    expect(component.sources().map((p) => p.month)).toEqual([4, 5]);
    component.form.patchValue({ endMonth: 4 });
    expect(component.sources().map((p) => p.month)).toEqual([4]);
    expect(component.monthCount()).toBe(1);
  });

  it("rejects reversed ranges and invalid month values without submitting", () => {
    const { component, annual } = setup();
    component.form.patchValue({ startYear: 2027 });
    expect(component.form.hasError("rangeOrder")).toBe(true);
    component.submit();
    component.form.patchValue({ startYear: 2026, startMonth: 8, endMonth: 7 });
    expect(component.form.hasError("rangeOrder")).toBe(true);
    component.submit();
    component.form.patchValue({ startMonth: 0 });
    expect(component.form.invalid).toBe(true);
    component.submit();
    expect(annual).not.toHaveBeenCalled();
  });

  it("labels explicit ranges without repeating the start year and preserves legacy labels", () => {
    const legacy = { period: null, year: 2026, rangeName: "Ene-Ago" } as Run;
    expect(runLabel(legacy)).toBe("2026 · Ene-Ago");
    expect(
      runLabel({
        ...legacy,
        rangeName: "2025-04 - 2026-03",
        periodRange: {
          startYear: 2025,
          startMonth: 4,
          endYear: 2026,
          endMonth: 3,
        },
      }),
    ).toBe("2025-04 - 2026-03");
  });
});
