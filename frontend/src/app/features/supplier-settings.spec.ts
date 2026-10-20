import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { HttpHeaders, HttpResponse } from "@angular/common/http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { of, Subject, throwError } from "rxjs";
import { Auth } from "../core/auth";
import { I18n } from "../core/i18n";
import { SupplierSummary, SuppliersApi } from "../core/suppliers";
import { SupplierSettings } from "./supplier-settings";

const summary: SupplierSummary = {
  catalogVersion: 3,
  initialized: true,
  national: 46,
  foreign: 235,
  pending: 0,
  reports: 1,
  equivalences: 1,
  startPeriod: null,
  backupDocumentId: null,
};
const rebuilt = {
  ...summary,
  catalogVersion: 9,
  backupDocumentId: "backup-1",
  startPeriod: { year: 2026, month: 9 },
};
function setup(admin = true) {
  const api = {
    summary: vi.fn<SuppliersApi["summary"]>(() => of(summary)),
    importLists: vi.fn<SuppliersApi["importLists"]>(() => of(summary)),
    rebuildFromSeptember: vi.fn<SuppliersApi["rebuildFromSeptember"]>(() =>
      of(rebuilt),
    ),
    downloadBackup: vi.fn<SuppliersApi["downloadBackup"]>(() =>
      of(new HttpResponse<Blob>({ body: null, headers: new HttpHeaders() })),
    ),
  };
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: SuppliersApi, useValue: api },
      { provide: Auth, useValue: { hasRole: () => admin } },
    ],
  });
  const fixture = TestBed.createComponent(SupplierSettings);
  fixture.detectChanges();
  return { fixture, component: fixture.componentInstance, api };
}
afterEach(() => {
  localStorage.removeItem("datastage.language");
  vi.restoreAllMocks();
  TestBed.resetTestingModule();
});

describe("supplier settings", () => {
  it("reads saved settings without changing the catalog and collapses one-time controls", () => {
    const { fixture, api } = setup();
    expect(api.summary).toHaveBeenCalledOnce();
    expect(api.importLists).not.toHaveBeenCalled();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
    expect(
      fixture.nativeElement.querySelector(".supplier-originals").open,
    ).toBe(false);
    expect(
      fixture.nativeElement.querySelector(".supplier-maintenance").open,
    ).toBe(false);
    expect(fixture.nativeElement.textContent).toContain(
      "Listas originales guardadas",
    );
  });

  it("opens setup for an empty installation and rejects a partial pair", () => {
    const { component, fixture, api } = setup();
    api.summary.mockReturnValue(of({ ...summary, initialized: false }));
    component.reload();
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(".supplier-originals").open,
    ).toBe(true);
    expect(
      fixture.nativeElement.querySelector(".supplier-maintenance"),
    ).toBeNull();
    component.nationalFile = new File(["n"], "national.xlsx");
    component.importLists();
    expect(api.importLists).not.toHaveBeenCalled();
  });

  it("imports both selected files and then closes the one-time form", () => {
    const { component, api } = setup();
    const national = new File(["national"], "national.xls");
    const foreign = new File(["foreign"], "foreign.xlsx");
    component.nationalFile = national;
    component.foreignFile = foreign;
    component.originalsOpen.set(true);
    component.importLists();
    expect(api.importLists).toHaveBeenCalledExactlyOnceWith(national, foreign);
    expect(component.originalsOpen()).toBe(false);
    expect(component.nationalFile).toBeNull();
    expect(component.foreignFile).toBeNull();
    expect(component.notice()).toContain("Excel están actualizados");
  });

  it("requires confirmation and preserves existing settings when a rebuild is rejected", () => {
    const { component, api } = setup();
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
    const pending = new Subject<typeof rebuilt>();
    api.rebuildFromSeptember.mockReturnValue(pending);
    component.confirmRebuild.set(true);
    component.rebuildFromSeptember();
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).toHaveBeenCalledOnce();
    expect(api.rebuildFromSeptember.mock.calls[0][0]).toBe(3);
    expect(api.rebuildFromSeptember.mock.calls[0][1]).toEqual(
      expect.any(String),
    );
    expect(component.busy()).toBe(true);
    pending.error({ status: 409, error: { detail: "Las listas cambiaron" } });
    expect(component.busy()).toBe(false);
    expect(component.confirmRebuild()).toBe(true);
    expect(component.summary()).toEqual(summary);
    expect(component.error()).toContain("Las listas cambiaron");
  });

  it("keeps the cutoff and downloadable backup after rebuilding and a later reload", () => {
    const { component, fixture, api } = setup();
    component.confirmRebuild.set(true);
    component.rebuildFromSeptember();
    fixture.detectChanges();
    expect(component.confirmRebuild()).toBe(false);
    expect(component.notice()).toContain("Respaldo guardado");
    expect(fixture.nativeElement.textContent).toContain("9/2026");
    expect(component.backupDocumentId()).toBe("backup-1");
    api.summary.mockReturnValue(of(rebuilt));
    component.reload();
    expect(component.backupDocumentId()).toBe("backup-1");
    component.downloadBackup();
    expect(api.downloadBackup).toHaveBeenCalledExactlyOnceWith("backup-1");
  });

  it("does not load or mutate supplier configuration without Admin access", () => {
    const { component, fixture, api } = setup(false);
    expect(api.summary).not.toHaveBeenCalled();
    expect(
      fixture.nativeElement.querySelector(".supplier-settings"),
    ).toBeNull();
    component.summary.set(rebuilt);
    component.confirmRebuild.set(true);
    component.nationalFile = new File(["n"], "national.xlsx");
    component.foreignFile = new File(["f"], "foreign.xlsx");
    component.importLists();
    component.rebuildFromSeptember();
    component.downloadBackup();
    expect(api.importLists).not.toHaveBeenCalled();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
    expect(api.downloadBackup).not.toHaveBeenCalled();
  });

  it("explains missing API metadata and keeps an unversioned reset blocked", () => {
    const { component, fixture, api } = setup();
    component.summary.set({ ...summary, catalogVersion: undefined });
    component.confirmRebuild.set(true);
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(".supplier-settings-warning")
        .textContent,
    ).toContain("Reinicia el backend");
    expect(
      fixture.nativeElement.querySelector(".supplier-reset-confirmation button")
        .disabled,
    ).toBe(true);
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
  });

  it("retains the files and saved configuration when import fails", () => {
    const { component, api } = setup();
    const national = new File(["n"], "national.xlsx");
    component.nationalFile = national;
    component.foreignFile = new File(["f"], "foreign.xlsx");
    api.importLists.mockReturnValue(
      throwError(() => ({ error: { detail: "Import failed" } })),
    );
    component.importLists();
    expect(component.summary()).toEqual(summary);
    expect(component.nationalFile).toBe(national);
    expect(component.busy()).toBe(false);
    expect(component.error()).toContain("Import failed");
  });

  it("translates setup and maintenance controls to English", () => {
    const { fixture } = setup();
    TestBed.inject(I18n).set("en");
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Original lists saved");
    expect(fixture.nativeElement.textContent).toContain("Choose Excel");
    expect(fixture.nativeElement.textContent).toContain(
      "Rebuild from September 2026",
    );
  });
});
