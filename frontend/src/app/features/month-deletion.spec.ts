import { TestBed } from "@angular/core/testing";
import { of } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api, BulkPeriodPreview } from "../core/api";
import { MonthDeletion } from "./month-deletion";

describe("month deletion confirmation", () => {
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
