import { TestBed } from "@angular/core/testing";
import { of } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api, BulkPeriodPreview } from "../core/api";
import { MonthDeletion } from "./month-deletion";
import { Period } from "../core/models";

describe("month deletion confirmation", () => {
  it("keeps selections visible across years and clears approval on cancellation", () => {
    const periods = [
      { id: "jan", year: 2026, month: 1, version: 1 },
      { id: "may", year: 2025, month: 5, version: 1 },
    ] as Period[];
    TestBed.configureTestingModule({
      providers: [{ provide: Api, useValue: { periods: () => of(periods) } }],
    });
    const component = TestBed.runInInjectionContext(() => new MonthDeletion());
    expect(component.activeYear()).toBe(2026);
    expect(component.months()).toHaveLength(12);
    expect(component.months()[1].period).toBeUndefined();
    component.toggle("jan");
    component.activeYear.set(2025);
    component.toggle("may");
    expect(component.selectedPeriods().map((p) => p.id)).toEqual([
      "jan",
      "may",
    ]);
    component.impact.set({
      confirmation: "DELETE 2 MONTHS",
    } as BulkPeriodPreview);
    component.confirmation = "DELETE 2 MONTHS";
    component.reason = "Incorrect imports";
    component.clearSelection();
    expect(component.selected()).toEqual([]);
    expect(component.impact()).toBeNull();
    expect(component.confirmation).toBe("");
    expect(component.reason).toBe("");
  });

  it("enforces the selection limit and freezes changes during a request", () => {
    TestBed.configureTestingModule({
      providers: [{ provide: Api, useValue: { periods: () => of([]) } }],
    });
    const component = TestBed.runInInjectionContext(() => new MonthDeletion());
    for (let i = 0; i < 25; i++) component.toggle(String(i));
    expect(component.selected()).toHaveLength(24);
    component.busy.set(true);
    component.toggle("0");
    component.clearSelection();
    expect(component.selected()).toHaveLength(24);
    component.busy.set(false);
    component.toggle("0");
    component.toggle("24");
    expect(component.selected()).toContain("24");
    expect(component.selected()).not.toContain("0");
  });

  it("clears approval when selection changes and cannot submit without confirmation", () => {
    const deletePeriods = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        { provide: Api, useValue: { periods: () => of([]), deletePeriods } },
      ],
    });
    const component = TestBed.runInInjectionContext(() => new MonthDeletion());
    component.remove();
    component.impact.set({
      confirmation: "DELETE 2 MONTHS",
    } as BulkPeriodPreview);
    component.reason = "User approved test";
    component.remove();
    expect(deletePeriods).not.toHaveBeenCalled();
    component.confirmation = "DELETE 2 MONTHS";
    component.toggle("second-month");
    expect(component.impact()).toBeNull();
    expect(component.confirmation).toBe("");
    component.remove();
    expect(deletePeriods).not.toHaveBeenCalled();
  });
});
