import { TestBed } from "@angular/core/testing";
import { of } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api, BulkPeriodPreview } from "../core/api";
import { MonthDeletion } from "./month-deletion";
import { Period } from "../core/models";

function history(): Period[] {
  return Array.from({ length: 13 * 12 }, (_, index) => ({
    id: String(index),
    year: 2026 - Math.floor(index / 12),
    month: (index % 12) + 1,
    version: 1,
    name: "month",
    activeRunId: "mock",
  }));
}

function setup(periods = history(), api = {}) {
  TestBed.configureTestingModule({
    providers: [
      { provide: Api, useValue: { periods: () => of(periods), ...api } },
    ],
  });
  return TestBed.runInInjectionContext(() => new MonthDeletion());
}

describe("month deletion selection and confirmation", () => {
  it("starts collapsed and shows only uploaded months in the active year", () => {
    const periods = history().filter((p) => p.year !== 2026 || p.month <= 8);
    const component = setup(periods);
    expect(component.pickerOpen()).toBe(false);
    expect(component.years()).toHaveLength(13);
    expect(component.activeYear()).toBe(2026);
    expect(component.months()).toHaveLength(8);
    component.togglePicker();
    component.toggle("0");
    component.showYear(2014);
    expect(component.months()).toHaveLength(12);
    component.toggle("144");
    expect(
      component.selectedByYear().map((g) => [g.year, g.periods.length]),
    ).toEqual([
      [2026, 1],
      [2014, 1],
    ]);
    component.togglePicker();
    expect(component.pickerOpen()).toBe(false);
    expect(component.selected()).toEqual(["0", "144"]);
    component.showYear(2026);
    expect(component.pickerOpen()).toBe(true);
    expect(component.selectedPeriods().map((p) => p.id)).toEqual(["0", "144"]);
  });

  it("enforces the limit and freezes all selection changes during a request", () => {
    const component = setup();
    component.toggle("unknown");
    expect(component.selected()).toEqual([]);
    for (let i = 0; i < 25; i++) component.toggle(String(i));
    expect(component.selected()).toHaveLength(24);
    component.busy.set(true);
    component.toggle("0");
    component.toggleYear();
    component.clearSelection();
    component.showYear(2014);
    component.togglePicker();
    expect(component.selected()).toHaveLength(24);
    expect(component.activeYear()).toBe(2026);
    expect(component.pickerOpen()).toBe(false);
    component.busy.set(false);
    component.toggle("0");
    component.toggle("24");
    expect(component.selected()).toContain("24");
    expect(component.selected()).not.toContain("0");
  });

  it("selects or clears a full year without losing other years or silently taking a partial year", () => {
    const component = setup();
    component.toggleYear();
    expect(component.selected()).toHaveLength(12);
    expect(component.allYearSelected()).toBe(true);
    component.activeYear.set(2025);
    component.toggle("12");
    component.activeYear.set(2024);
    expect(component.canSelectYear()).toBe(false);
    component.toggleYear();
    expect(component.selected()).toHaveLength(13);
    component.activeYear.set(2025);
    component.toggleYear();
    expect(component.selected()).toHaveLength(24);
    expect(new Set(component.selected()).size).toBe(24);
    component.impact.set({
      confirmation: "DELETE 24 MONTHS",
    } as BulkPeriodPreview);
    component.confirmation = "DELETE 24 MONTHS";
    component.activeYear.set(2026);
    expect(component.canSelectYear()).toBe(true);
    component.toggleYear();
    expect(component.selectedPeriods().every((p) => p.year === 2025)).toBe(
      true,
    );
    expect(component.impact()).toBeNull();
    expect(component.confirmation).toBe("");
  });

  it("cancels a review without deleting or clearing the selection", () => {
    const deletePeriods = vi.fn();
    const component = setup(history(), { deletePeriods });
    component.toggle("0");
    component.impact.set({
      confirmation: "DELETE 1 MONTHS",
    } as BulkPeriodPreview);
    component.confirmation = "DELETE 1 MONTHS";
    component.cancelPreview();
    expect(component.selected()).toEqual(["0"]);
    expect(component.impact()).toBeNull();
    expect(component.confirmation).toBe("");
    component.remove();
    expect(deletePeriods).not.toHaveBeenCalled();
    component.clearSelection();
    expect(component.selected()).toEqual([]);
  });

  it("invalidates confirmation on selection changes and rejects missing or incorrect confirmation", () => {
    const deletePeriods = vi.fn();
    const component = setup(history(), { deletePeriods });
    component.toggle("0");
    component.remove();
    component.impact.set({
      confirmation: "DELETE 1 MONTHS",
    } as BulkPeriodPreview);
    component.remove();
    component.confirmation = "wrong";
    component.remove();
    expect(deletePeriods).not.toHaveBeenCalled();
    component.confirmation = "DELETE 1 MONTHS";
    component.toggle("1");
    expect(component.impact()).toBeNull();
    expect(component.confirmation).toBe("");
    component.remove();
    expect(deletePeriods).not.toHaveBeenCalled();
  });

  it("reviews and deletes the exact selection after confirmation without asking for a reason", () => {
    const preview = {
      periods: [{ periodId: "0" }],
      confirmation: "DELETE 1 MONTHS",
      token: "a".repeat(64),
      impact: { monthlyRuns: 1, annualRuns: 0, businessRows: 2, documents: 1 },
    } as BulkPeriodPreview;
    const bulkPeriodPreview = vi.fn(() => of(preview));
    const deletePeriods = vi.fn(() => of({ storageCleanupFailures: 0 }));
    const component = setup(history(), { bulkPeriodPreview, deletePeriods });
    component.togglePicker();
    component.toggle("0");
    component.preview();
    expect(bulkPeriodPreview).toHaveBeenCalledWith(["0"]);
    expect(component.pickerOpen()).toBe(false);
    expect(component.impact()).toEqual(preview);
    component.confirmation = preview.confirmation;
    component.remove();
    expect(deletePeriods).toHaveBeenCalledExactlyOnceWith(
      preview,
      preview.confirmation,
    );
    expect(component.selected()).toEqual([]);
    expect(component.impact()).toBeNull();
    expect(component.confirmation).toBe("");
    expect(component.busy()).toBe(false);
  });
});
