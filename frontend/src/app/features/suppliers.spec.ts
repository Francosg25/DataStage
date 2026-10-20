import { TestBed } from "@angular/core/testing";
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
      of({ ...summary, backupDocumentId: "backup-1", startPeriod: { year: 2026, month: 9 } }),
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
  it("imports both chosen files and refreshes the available pair", () => {
    const { component, api } = setup();
    const national = new File(["national"], "national.xls");
    const foreign = new File(["foreign"], "foreign.xlsx");
    component.nationalFile = national;
    component.foreignFile = foreign;
    api.reports.mockReturnValue(of(page([{ ...report, id: "after-import" }])));
    component.importLists();
    expect(api.importLists).toHaveBeenCalledExactlyOnceWith(national, foreign);
    expect(component.selectedId()).toBe("after-import");
    expect(component.notice()).toContain("Excel están actualizados");
  });
  it("does not import a partial pair and keeps the original-list input open before initialization", () => {
    const { fixture, component, api } = setup();
    component.summary.set({ ...summary, initialized: false });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("details").open).toBe(true);
    component.nationalFile = new File(["n"], "national.xlsx");
    component.importLists();
    expect(api.importLists).not.toHaveBeenCalled();
  });
  it("lets readers download without offering import or update mutations", () => {
    const { fixture, component, api } = setup(false);
    expect(
      fixture.nativeElement.querySelectorAll("input[type=file]"),
    ).toHaveLength(0);
    expect(fixture.nativeElement.textContent).not.toContain(
      "Actualizar listas",
    );
    component.importLists();
    component.refresh();
    component.download("national");
    expect(api.importLists).not.toHaveBeenCalled();
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
    expect(fixture.nativeElement.textContent).toContain("Original lists");
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
  it("requires explicit confirmation and prevents simultaneous rebuilds", () => {
    const { component, api } = setup();
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
    component.confirmRebuild.set(true);
    const pending = new Subject<typeof summary & { backupDocumentId: string }>();
    api.rebuildFromSeptember.mockReturnValue(pending);
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).toHaveBeenCalledOnce();
    expect(api.rebuildFromSeptember.mock.calls[0][0]).toBe(3);
    expect(api.rebuildFromSeptember.mock.calls[0][1]).toEqual(expect.any(String));
    expect(component.busy()).toBe(true);
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).toHaveBeenCalledOnce();
    pending.error({ status: 409, error: { detail: "Las listas cambiaron" } });
    expect(component.busy()).toBe(false);
    expect(component.confirmRebuild()).toBe(true);
    expect(component.selectedId()).toBe(report.id);
    expect(component.error()).toContain("Las listas cambiaron");
  });

  it("reloads the rebuilt pair, displays the cutoff and retains the backup after a refresh", () => {
    const { component, fixture, api } = setup();
    const updated = { ...summary, catalogVersion: 9, backupDocumentId: "backup-1",
      startPeriod: { year: 2026, month: 9 } };
    api.summary.mockReturnValue(of(updated));
    api.reports.mockReturnValue(of(page([{ ...report, id: "september-cutoff" }])));
    component.confirmRebuild.set(true);
    component.rebuildFromSeptember();
    fixture.detectChanges();
    expect(component.selectedId()).toBe("september-cutoff");
    expect(component.confirmRebuild()).toBe(false);
    expect(component.notice()).toContain("Respaldo guardado");
    expect(fixture.nativeElement.textContent).toContain("9/2026");
    expect(component.backupDocumentId()).toBe("backup-1");
    component.backupDocumentId.set("");
    component.refresh();
    expect(component.backupDocumentId()).toBe("backup-1");
    component.downloadBackup();
    expect(api.downloadBackup).toHaveBeenCalledExactlyOnceWith("backup-1");
  });

  it("does not expose or execute the cleanup for readers", () => {
    const { fixture, component, api } = setup(false);
    component.confirmRebuild.set(true);
    component.rebuildFromSeptember();
    expect(api.rebuildFromSeptember).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelector(".supplier-reset")).toBeNull();
  });

  it("translates the rebuild controls to English", () => {
    const { fixture } = setup();
    TestBed.inject(I18n).set("en");
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain("Rebuild from September 2026");
  });

});
