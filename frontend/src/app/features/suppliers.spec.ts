import { TestBed } from "@angular/core/testing";
import {
  ActivatedRoute,
  convertToParamMap,
  provideRouter,
} from "@angular/router";
import { HttpHeaders, HttpResponse } from "@angular/common/http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { of, Subject, throwError } from "rxjs";
import { Auth } from "../core/auth";
import { I18n } from "../core/i18n";
import { Page } from "../core/models";
import {
  Supplier,
  SupplierReport,
  SupplierReview,
  SuppliersApi,
} from "../core/suppliers";
import { Suppliers } from "./suppliers";

const supplier: Supplier = {
  id: "supplier-1",
  version: 4,
  kind: "national",
  name: "Proveedor Águila",
  taxId: "PAG010101AB1",
  country: "MEX",
  address: "Calle 1",
  externalNumber: "12",
  internalNumber: "",
  postalCode: "64000",
  municipality: "Monterrey",
  state: "NL",
  virtualConfirmation: true,
  virtualOperations: true,
  evidence: [],
};
const review: SupplierReview = {
  id: "review-1",
  version: 2,
  reason: "similar_name",
  candidate: { ...supplier, name: "PROVEEDOR AGUILA" },
  suggestions: [supplier],
  evidence: [],
};
const report: SupplierReport = {
  id: "snapshot-1",
  label: "Septiembre",
  createdAt: "2026-10-16T01:00:00Z",
  nationalCount: 1,
  foreignCount: 1,
  sourceFingerprint: "fixed",
};

function setup(
  operator = true,
  overrides: Record<string, unknown> = {},
  initialTab?: string,
) {
  const api = {
    summary: vi.fn<SuppliersApi["summary"]>(() =>
      of({ national: 1, foreign: 1, pending: 1, reports: 1, equivalences: 1 }),
    ),
    reviews: vi.fn<SuppliersApi["reviews"]>(() =>
      of({ items: [review], total: 1 }),
    ),
    catalog: vi.fn<SuppliersApi["catalog"]>(() =>
      of({ items: [supplier], total: 1 }),
    ),
    reports: vi.fn<SuppliersApi["reports"]>(() =>
      of({ items: [report], total: 1 }),
    ),
    reportRequests: vi.fn<SuppliersApi["reportRequests"]>(() =>
      of({ items: [], total: 0 }),
    ),
    equivalences: vi.fn<SuppliersApi["equivalences"]>(() =>
      of({ items: [], total: 0 }),
    ),
    detail: vi.fn<SuppliersApi["detail"]>(() => of(supplier)),
    reviewEvidence: vi.fn<SuppliersApi["reviewEvidence"]>(() =>
      of({ items: [], total: 0 }),
    ),
    supplierEvidence: vi.fn<SuppliersApi["supplierEvidence"]>(() =>
      of({ items: [], total: 0 }),
    ),
    create: vi.fn<SuppliersApi["create"]>(() => of(supplier)),
    update: vi.fn<SuppliersApi["update"]>(() => of(supplier)),
    resolve: vi.fn<SuppliersApi["resolve"]>(() => of(supplier)),
    updateEquivalence: vi.fn(() => of({})),
    createReport: vi.fn<SuppliersApi["createReport"]>(() => of(report)),
    sync: vi.fn<SuppliersApi["sync"]>(() => of({})),
    download: vi.fn<SuppliersApi["download"]>(() =>
      of(
        new HttpResponse({
          body: new Blob(["xlsx"]),
          headers: new HttpHeaders(),
        }),
      ),
    ),
    ...overrides,
  };
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: SuppliersApi, useValue: api },
      { provide: Auth, useValue: { hasRole: () => operator } },
      ...(initialTab
        ? [
            {
              provide: ActivatedRoute,
              useValue: {
                snapshot: {
                  queryParamMap: convertToParamMap({ tab: initialTab }),
                },
              },
            },
          ]
        : []),
    ],
  });
  const component = TestBed.runInInjectionContext(() => new Suppliers());
  return { component, api };
}

afterEach(() => {
  localStorage.removeItem("datastage.language");
  sessionStorage.clear();
  vi.restoreAllMocks();
  TestBed.resetTestingModule();
});

describe("cumulative suppliers", () => {
  it("resolves a match with the reviewed supplier, version, explicit confirmation and audit reason", () => {
    const { component, api } = setup();
    component.openReview(review);
    component.reason = "Mismo RFC y domicilio";
    component.reviewVirtual = true;
    component.resolveReview();
    expect(api.resolve).toHaveBeenCalledWith("review-1", {
      decision: "same",
      supplierId: "supplier-1",
      expectedVersion: 2,
      reason: "Mismo RFC y domicilio",
      virtualOperations: true,
    });
    expect(component.editorOpen()).toBe(false);
  });

  it("requires an explicit virtual decision for a new domestic supplier and allows correcting the candidate", () => {
    const { component, api } = setup();
    component.openReview({
      ...review,
      reason: "virtual_confirmation",
      candidate: {
        ...supplier,
        virtualConfirmation: null,
        virtualOperations: null,
      },
      suggestions: [],
    });
    component.reason = "Validado con documentación";
    component.resolveReview();
    expect(api.resolve).not.toHaveBeenCalled();
    expect(component.detailError()).toContain("Confirma Sí o No");
    component.reviewVirtual = false;
    component.fields.name = "Razón social corregida";
    component.resolveReview();
    const payload = api.resolve.mock.calls[0][1];
    expect(payload.decision).toBe("new");
    expect(payload.supplier?.name).toBe("Razón social corregida");
    expect(payload.supplier?.virtualConfirmation).toBe(false);
    expect(payload.supplier).not.toHaveProperty("id");
  });

  it("does not send server-managed supplier data on edit and permits withdrawing a previous confirmation", () => {
    const { component, api } = setup();
    component.openSupplier(supplier);
    component.fields.virtualConfirmation = null;
    component.reason = "Retiro de confirmación previa";
    component.saveSupplier();
    expect(api.update).toHaveBeenCalledWith(
      "supplier-1",
      expect.objectContaining({ virtualConfirmation: null }),
      4,
      component.reason || "Retiro de confirmación previa",
    );
    expect(api.update.mock.calls[0][1]).not.toHaveProperty("id");
    expect(api.update.mock.calls[0][1]).not.toHaveProperty("version");
    expect(api.update.mock.calls[0][1]).not.toHaveProperty("virtualOperations");
  });

  it("preserves the report idempotency key on retry and uses a new one for a changed request", () => {
    const createReport = vi.fn<SuppliersApi["createReport"]>(() =>
      throwError(() => ({ status: 0 })),
    );
    const { component } = setup(true, { createReport });
    component.createReport();
    component.createReport();
    expect(createReport.mock.calls[0][1]).toBe(createReport.mock.calls[1][1]);
    component.reportLabel = "Otro reporte";
    component.createReport();
    expect(createReport.mock.calls[2][1]).not.toBe(
      createReport.mock.calls[1][1],
    );
    expect(component.busy()).toBe(false);
    expect(component.error()).toContain("API");
  });

  it("recovers a pending report key after leaving and reopening the view", () => {
    const createReport = vi.fn<SuppliersApi["createReport"]>(() =>
      throwError(() => ({ status: 0 })),
    );
    const { component } = setup(true, { createReport });
    component.createReport();
    const reopened = TestBed.runInInjectionContext(() => new Suppliers());
    reopened.createReport();
    expect(createReport.mock.calls[0][1]).toBe(createReport.mock.calls[1][1]);
  });

  it("loads more evidence without losing the first records or allowing duplicate in-flight requests", () => {
    const next = new Subject<
      Page<import("../core/suppliers").SupplierEvidence>
    >();
    const reviewEvidence = vi.fn<SuppliersApi["reviewEvidence"]>(() => next);
    const { component } = setup(true, { reviewEvidence });
    component.openReview({
      ...review,
      evidence: [{ id: "e1" }],
      evidenceCount: 2,
    });
    component.moreEvidence();
    component.moreEvidence();
    expect(reviewEvidence).toHaveBeenCalledExactlyOnceWith("review-1", 1);
    next.next({ items: [{ id: "e2" }], total: 2 });
    next.complete();
    expect(component.evidence().map((entry) => entry.id)).toEqual(["e1", "e2"]);
    expect(component.evidenceLoading()).toBe(false);
  });

  it("paginates supplier history using the full total including seed and inactive evidence", () => {
    const supplierEvidence = vi.fn<SuppliersApi["supplierEvidence"]>(() =>
      of({ items: [{ id: "historical-1", active: false }], total: 2 }),
    );
    const { component } = setup(true, {
      detail: () =>
        of({
          ...supplier,
          evidence: [{ id: "seed-1" }],
          evidenceCount: 0,
          evidenceTotal: 2,
        }),
      supplierEvidence,
    });
    component.openSupplier(supplier);
    expect(component.evidenceTotal()).toBe(2);
    component.moreEvidence();
    expect(supplierEvidence).toHaveBeenCalledExactlyOnceWith("supplier-1", 1);
    expect(component.evidence().map((entry) => entry.id)).toEqual([
      "seed-1",
      "historical-1",
    ]);
    component.moreEvidence();
    expect(supplierEvidence).toHaveBeenCalledOnce();
  });

  it("does not append an old evidence page after reopening the same supplier", () => {
    const oldPage = new Subject<
      Page<import("../core/suppliers").SupplierEvidence>
    >();
    const { component } = setup(true, {
      detail: () =>
        of({ ...supplier, evidence: [{ id: "first" }], evidenceTotal: 2 }),
      supplierEvidence: () => oldPage,
    });
    component.openSupplier(supplier);
    component.moreEvidence();
    component.openSupplier(supplier);
    oldPage.next({ items: [{ id: "obsolete" }], total: 2 });
    oldPage.complete();
    expect(component.evidence().map((entry) => entry.id)).toEqual(["first"]);
    expect(component.evidenceLoading()).toBe(false);
  });

  it("keeps a loaded list available after an action error and marks list fetch failures separately", () => {
    const { component } = setup(true, {
      createReport: () => throwError(() => ({ status: 0 })),
      reports: () => throwError(() => ({ status: 0 })),
    });
    component.createReport();
    expect(component.error()).not.toBe("");
    expect(component.listError()).toBe(false);
    component.switchTab("reports");
    expect(component.listError()).toBe(true);
    expect(component.loading()).toBe(false);
  });

  it("opens monthly report deep links and loads durable requests separately from completed snapshots", () => {
    const { component, api } = setup(true, {}, "reports");
    expect(component.tab()).toBe("reports");
    expect(api.reports).toHaveBeenCalledOnce();
    expect(api.reportRequests).toHaveBeenCalledExactlyOnceWith(0, 25);
    expect(api.createReport).not.toHaveBeenCalled();
  });

  it("downloads only completed monthly request snapshots", () => {
    const { component, api } = setup();
    vi.spyOn(
      component as unknown as { saveDownload: () => void },
      "saveDownload",
    ).mockImplementation(() => undefined);
    const request = {
      id: "request-1",
      runId: "run-1",
      period: "Octubre_2026",
      createdAt: "2026-10-15",
      pending: 1,
      reportId: null,
      status: "pending_review" as const,
    };
    component.downloadMonthly(request);
    expect(api.download).not.toHaveBeenCalled();
    component.downloadMonthly({
      ...request,
      status: "ready",
      reportId: "snapshot-1",
      pending: 0,
    });
    expect(api.download.mock.calls).toEqual([
      ["snapshot-1", "national"],
      ["snapshot-1", "foreign"],
    ]);
    expect(api.createReport).not.toHaveBeenCalled();
  });

  it("downloads both lists from the same immutable report without creating a report", () => {
    const { component, api } = setup();
    vi.spyOn(
      component as unknown as { saveDownload: () => void },
      "saveDownload",
    ).mockImplementation(() => undefined);
    component.download(report);
    component.download(report, "national");
    expect(api.download.mock.calls).toEqual([
      ["snapshot-1", "national"],
      ["snapshot-1", "foreign"],
      ["snapshot-1", "national"],
    ]);
    expect(api.createReport).not.toHaveBeenCalled();
  });

  it("guards all mutations for readers while allowing evidence and downloads", () => {
    const { component, api } = setup(false);
    component.addSupplier();
    component.openReview(review);
    component.reason = "No puede escribir";
    component.resolveReview();
    component.saveSupplier();
    component.createReport();
    component.sync();
    expect(api.resolve).not.toHaveBeenCalled();
    expect(api.create).not.toHaveBeenCalled();
    expect(api.createReport).not.toHaveBeenCalled();
    expect(api.sync).not.toHaveBeenCalled();
    component.openSupplier(supplier);
    expect(api.detail).toHaveBeenCalledWith(supplier.id);
  });

  it("retains a failed review and handles authorization or stale-version errors for correction", () => {
    const resolve = vi.fn<SuppliersApi["resolve"]>(() =>
      throwError(() => ({
        status: 409,
        error: { detail: "La revisión cambió. Actualiza." },
      })),
    );
    const { component } = setup(true, { resolve });
    component.openReview(review);
    component.reason = "Identidad validada";
    component.resolveReview();
    expect(component.editorOpen()).toBe(true);
    expect(component.busy()).toBe(false);
    expect(component.detailError()).toContain("Actualiza");
  });

  it("ignores stale list responses after changing tabs", () => {
    const pending = new Subject<Page<SupplierReview>>();
    const { component } = setup(true, { reviews: () => pending });
    expect(component.loading()).toBe(true);
    component.switchTab("catalog");
    pending.next({ items: [], total: 99 });
    pending.complete();
    expect(component.total()).toBe(1);
    expect(component.suppliers()[0].id).toBe(supplier.id);
    expect(component.loading()).toBe(false);
  });

  it("blocks supplier edits when detail loading fails so an edit cannot become a new supplier", () => {
    const { component, api } = setup(true, {
      detail: () => throwError(() => ({ status: 403 })),
    });
    component.openSupplier(supplier);
    component.reason = "Cambiar nombre";
    component.saveSupplier();
    expect(api.create).not.toHaveBeenCalled();
    expect(api.update).not.toHaveBeenCalled();
    expect(component.detailLoading()).toBe(false);
    expect(component.detailError()).toContain("permiso");
  });

  it("renders all four tabs in English and preserves supplier names", async () => {
    setup();
    TestBed.inject(I18n).set("en");
    const fixture = TestBed.createComponent(Suppliers);
    fixture.detectChanges();
    await fixture.whenStable();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain("Suppliers");
    expect(text).toContain("To review");
    expect(text).toContain("Catalog");
    expect(text).toContain("Reports");
    expect(text).toContain("Equivalences");
    expect(text).toContain("PROVEEDOR AGUILA");
  });
});
