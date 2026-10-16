import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { HttpHeaders, HttpResponse } from "@angular/common/http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { of, Subject, throwError } from "rxjs";
import { I18n } from "../core/i18n";
import { SupplierRunReportState, SuppliersApi } from "../core/suppliers";
import { SupplierRunReport } from "./supplier-run-report";

const ready: SupplierRunReportState = {
  runId: "month-1",
  status: "ready",
  pending: 0,
  report: {
    id: "snapshot-1",
    label: "Octubre",
    createdAt: "2026-10-15",
    nationalCount: 1,
    foreignCount: 2,
    sourceFingerprint: "fixed",
  },
};

function setup(source = of(ready)) {
  const api = {
    runReport: vi.fn<SuppliersApi["runReport"]>(() => source),
    download: vi.fn<SuppliersApi["download"]>(() =>
      of(
        new HttpResponse<Blob>({
          body: null,
          headers: new HttpHeaders(),
        }),
      ),
    ),
  };
  TestBed.configureTestingModule({
    providers: [provideRouter([]), { provide: SuppliersApi, useValue: api }],
  });
  const fixture = TestBed.createComponent(SupplierRunReport);
  fixture.componentRef.setInput("runId", "month-1");
  fixture.detectChanges();
  return { fixture, component: fixture.componentInstance, api };
}

afterEach(() => {
  localStorage.removeItem("datastage.language");
  vi.clearAllMocks();
  vi.restoreAllMocks();
  TestBed.resetTestingModule();
});

describe("automatic monthly supplier report", () => {
  it("offers both lists from the report already created during publication", async () => {
    const { fixture, component, api } = setup();
    await fixture.whenStable();
    component.download();
    expect(api.runReport).toHaveBeenCalledExactlyOnceWith("month-1");
    expect(api.download.mock.calls).toEqual([
      ["snapshot-1", "national"],
      ["snapshot-1", "foreign"],
    ]);
    expect(fixture.nativeElement.textContent).toContain(
      "Descargar ambas listas",
    );
  });

  it("directs unresolved identity decisions to review and does not download an incomplete snapshot", async () => {
    const { fixture, component, api } = setup(
      of({ ...ready, status: "pending_review", pending: 2, report: null }),
    );
    TestBed.inject(I18n).set("en");
    fixture.detectChanges();
    await fixture.whenStable();
    component.download();
    expect(api.download).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain(
      "automatically generates both lists",
    );
    expect(fixture.nativeElement.querySelector("a").getAttribute("href")).toBe(
      "/suppliers?tab=reviews",
    );
  });

  it("translates supplier-specific errors and allows retrying the automatic state request", async () => {
    const { fixture, component, api } = setup(
      throwError(() => ({
        status: 400,
        error: { detail: "El RFC del proveedor nacional no es válido" },
      })),
    );
    TestBed.inject(I18n).set("en");
    fixture.detectChanges();
    await fixture.whenStable();
    expect(component.loading()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain(
      "The domestic supplier's RFC is invalid",
    );
    api.runReport.mockReturnValue(of(ready));
    component.load();
    expect(component.state()?.status).toBe("ready");
  });

  it("refreshes only pending reports and stops polling as soon as both lists are ready", async () => {
    const timeouts = vi.spyOn(globalThis, "setTimeout");
    const { fixture, component, api } = setup(
      of({ ...ready, status: "pending_review", pending: 1, report: null }),
    );
    await fixture.whenStable();
    const poll = timeouts.mock.calls.find(([, delay]) => delay === 8000)?.[0];
    expect(poll).toBeTypeOf("function");
    api.runReport.mockReturnValue(of(ready));
    if (typeof poll === "function") poll();
    expect(component.state()?.status).toBe("ready");
    expect(
      timeouts.mock.calls.filter(([, delay]) => delay === 8000),
    ).toHaveLength(1);
  });

  it("ignores a response for a previous month after the run changes", async () => {
    const old = new Subject<SupplierRunReportState>();
    const { fixture, component, api } = setup(old);
    api.runReport.mockReturnValue(of({ ...ready, runId: "month-2" }));
    fixture.componentRef.setInput("runId", "month-2");
    fixture.detectChanges();
    await fixture.whenStable();
    old.next(ready);
    old.complete();
    expect(component.state()?.runId).toBe("month-2");
    expect(component.loading()).toBe(false);
  });
});
