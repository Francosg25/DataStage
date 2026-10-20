import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { HttpHeaders, HttpResponse } from "@angular/common/http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { of, Subject, throwError } from "rxjs";
import { Auth } from "../core/auth";
import { I18n } from "../core/i18n";
import { SupplierReport, SuppliersApi } from "../core/suppliers";
import { Suppliers } from "./suppliers";

const report: SupplierReport = {
  id: "pair-1",
  label: "Septiembre_2026",
  createdAt: "2026-10-16T01:00:00Z",
  nationalCount: 46,
  foreignCount: 235,
  sourceFingerprint: "fixed",
};
const page = <T>(items: T[], total = items.length) => ({
  items,
  total,
  offset: 0,
  limit: 50,
});
const summary = {
  catalogVersion: 3,
  backupDocumentId: null as string | null,
  startPeriod: null as { year: number; month: number } | null,
  initialized: true,
  national: 46,
  foreign: 235,
  pending: 126,
  reports: 1,
  equivalences: 1,
};

function setup(operator = true) {
  const api = {
    summary: vi.fn<SuppliersApi["summary"]>(() => of(summary)),
    reports: vi.fn<SuppliersApi["reports"]>(() => of(page([report]))),
    sync: vi.fn<SuppliersApi["sync"]>(() => of(summary)),
    rebuildFromSeptember: vi.fn<SuppliersApi["rebuildFromSeptember"]>(() =>
      of({
        ...summary,
        backupDocumentId: "backup-1",
        startPeriod: { year: 2026, month: 9 },
      }),
    ),
    downloadBackup: vi.fn<SuppliersApi["downloadBackup"]>(() =>
      of(new HttpResponse<Blob>({ body: null, headers: new HttpHeaders() })),
    ),
    importLists: vi.fn<SuppliersApi["importLists"]>(() => of(summary)),
    download: vi.fn<SuppliersApi["download"]>(() =>
      of(new HttpResponse<Blob>({ body: null, headers: new HttpHeaders() })),
    ),
  };
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: SuppliersApi, useValue: api },
      { provide: Auth, useValue: { hasRole: () => operator } },
    ],
  });
  const fixture = TestBed.createComponent(Suppliers);
  fixture.detectChanges();
  return { fixture, component: fixture.componentInstance, api };
}

afterEach(() => {
  localStorage.removeItem("datastage.language");
  vi.restoreAllMocks();
  TestBed.resetTestingModule();
});

describe("supplier Excel lists", () => {
  it("shows two download cards with the counts of the selected immutable report", () => {
    const { fixture, component, api } = setup();
    expect(
      fixture.nativeElement.querySelectorAll(".supplier-file-card"),
    ).toHaveLength(2);
    expect(component.count("foreign")).toBe(235);
    expect(component.count("national")).toBe(46);
    expect(fixture.nativeElement.textContent).not.toContain("126");
    expect(fixture.nativeElement.textContent).not.toContain("Equivalencias");
    expect(fixture.nativeElement.querySelectorAll("table")).toHaveLength(0);
    expect(api.sync).not.toHaveBeenCalled();
  });
  it("downloads the two files from the same existing snapshot", () => {
    const { component, api } = setup();
    component.download("both");
    expect(api.download.mock.calls).toEqual([
      ["pair-1", "foreign"],
      ["pair-1", "national"],
    ]);
    expect(api.sync).not.toHaveBeenCalled();
    expect(component.downloading()).toBeNull();
  });
  it("updates lists on request and switches to the latest report", () => {
    const { component, api } = setup();
    api.reports.mockReturnValue(
      of(page([{ ...report, id: "pair-2", foreignCount: 236 }, report])),
    );
    component.refresh();
    expect(api.sync).toHaveBeenCalledOnce();
    expect(component.selectedId()).toBe("pair-2");
    expect(component.count("foreign")).toBe(236);
  });
  it("lets readers download without offering import or update mutations", () => {
    const { fixture, component, api } = setup(false);
    expect(
      fixture.nativeElement.querySelectorAll("input[type=file]"),
    ).toHaveLength(0);
    expect(fixture.nativeElement.textContent).not.toContain(
      "Actualizar listas",
    );
    component.refresh();
    component.download("national");
    expect(api.sync).not.toHaveBeenCalled();
    expect(api.download).toHaveBeenCalledExactlyOnceWith("pair-1", "national");
  });
  it("keeps the selected historical counts and file IDs together", () => {
    const { component, api } = setup();
    component.reports.set([
      report,
      { ...report, id: "january", nationalCount: 44 },
    ]);
    component.selectedId.set("january");
    expect(component.count("national")).toBe(44);
    component.download("national");
    expect(api.download).toHaveBeenCalledExactlyOnceWith("january", "national");
  });
  it("blocks duplicate downloads until the first pair finishes", () => {
    const { component, api } = setup();
    const pending = new Subject<HttpResponse<Blob>>();
    api.download.mockReturnValue(pending);
    component.download("foreign");
    component.download("both");
    expect(api.download).toHaveBeenCalledOnce();
    pending.error({ status: 500, error: { detail: "Download failed" } });
    expect(component.downloading()).toBeNull();
    expect(component.error()).toContain("Download failed");
  });
  it("translates the simple file flow and allows retrying a failed refresh", () => {
    const { fixture, component, api } = setup();
    TestBed.inject(I18n).set("en");
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Download Excel");
    expect(
      fixture.nativeElement
        .querySelector(".supplier-configuration-link")
        .getAttribute("aria-label"),
    ).toBe("Supplier list settings");
    api.sync.mockReturnValue(
      throwError(() => ({
        status: 500,
        error: { detail: "Temporary failure" },
      })),
    );
    component.refresh();
    expect(component.loading()).toBe(false);
    expect(component.error()).toContain("Temporary failure");
    api.sync.mockReturnValue(of(summary));
    component.refresh();
    expect(component.error()).toBe("");
  });
  it("keeps setup, cutoff and reset controls out of the normal page even for Admin", () => {
    const { fixture, component, api } = setup();
    component.summary.set({
      ...summary,
      startPeriod: { year: 2026, month: 9 },
      backupDocumentId: "backup-1",
    });
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelectorAll("input[type=file], details"),
    ).toHaveLength(0);
    expect(fixture.nativeElement.textContent).not.toContain(
      "Recalcular listas",
    );
    expect(fixture.nativeElement.textContent).not.toContain(
      "Operaciones incluidas desde:",
    );
    const link = fixture.nativeElement.querySelector(
      ".supplier-configuration-link",
    );
    expect(link.getAttribute("href")).toBe("/administration?section=suppliers");
    expect(api.importLists).not.toHaveBeenCalled();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
  });

  it("offers initial setup through Administration when no reports exist", () => {
    const { fixture, component } = setup();
    component.summary.set({ ...summary, initialized: false });
    component.reports.set([]);
    component.selectedId.set("");
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector(".supplier-empty a");
    expect(link.textContent).toContain("Configurar listas");
    expect(link.getAttribute("href")).toBe("/administration?section=suppliers");
    expect(
      fixture.nativeElement.querySelectorAll("input[type=file]"),
    ).toHaveLength(0);
  });
});
