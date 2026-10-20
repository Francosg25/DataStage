import { TestBed } from "@angular/core/testing";
import { provideHttpClient, withInterceptors } from "@angular/common/http";
import {
  HttpTestingController,
  provideHttpClientTesting,
} from "@angular/common/http/testing";
import { firstValueFrom } from "rxjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Auth, bearerInterceptor } from "./auth";
import { SuppliersApi } from "./suppliers";

describe("supplier API contracts", () => {
  let api: SuppliersApi;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([bearerInterceptor])),
        provideHttpClientTesting(),
        {
          provide: Auth,
          useValue: {
            config: () => ({ authMode: "entra" }),
            token: vi.fn().mockResolvedValue("corporate-token"),
          },
        },
      ],
    });
    api = TestBed.inject(SuppliersApi);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    TestBed.resetTestingModule();
  });

  it("uploads both selected lists as files without choosing a scope from the browser", async () => {
    const national = new File(["national"], "national.xls");
    const foreign = new File(["foreign"], "foreign.xlsx");
    const promise = firstValueFrom(api.importLists(national, foreign));
    await Promise.resolve();
    const request = http.expectOne("/api/v1/suppliers/import");
    expect(request.request.body.get("national")).toBe(national);
    expect(request.request.body.get("foreign")).toBe(foreign);
    expect(request.request.body.has("scopeId")).toBe(false);
    request.flush({ initialized: true, national: 1, foreign: 1 });
    await promise;
  });

  it("preserves identification strings, accepts domain aliases and omits empty type filters", async () => {
    const promise = firstValueFrom(
      api.catalog({ search: "Águila", type: "", offset: 25, limit: 25 }),
    );
    await Promise.resolve();
    const request = http.expectOne((r) => r.url === "/api/v1/suppliers");
    expect(request.request.params.has("type")).toBe(false);
    expect(request.request.params.get("search")).toBe("Águila");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-token",
    );
    request.flush({
      items: [
        {
          id: "1",
          type: "national",
          name: "Águila",
          taxId: "000000123",
          city: "Monterrey",
        },
      ],
      total: 1,
    });
    const result = await promise;
    expect(result.items[0].kind).toBe("national");
    expect(result.items[0].municipality).toBe("Monterrey");
    expect(result.items[0].taxId).toBe("000000123");
  });

  it("submits explicit withdrawal and optimistic version with the audit reason", async () => {
    const promise = firstValueFrom(
      api.updateEquivalence("eq/1", 7, "Corrección validada", {
        supplierId: "supplier-2",
        active: false,
      }),
    );
    await Promise.resolve();
    const request = http.expectOne("/api/v1/suppliers/equivalences/eq%2F1");
    expect(request.request.method).toBe("PATCH");
    expect(request.request.body).toEqual({
      supplierId: "supplier-2",
      active: false,
      expectedVersion: 7,
      reason: "Corrección validada",
    });
    request.flush({});
    await promise;
  });

  it("uses authenticated immutable XLSX downloads for the specified report", async () => {
    const promise = firstValueFrom(api.download("snapshot-1", "foreign"));
    await Promise.resolve();
    const request = http.expectOne(
      "/api/v1/suppliers/reports/snapshot-1/foreign.xlsx",
    );
    expect(request.request.responseType).toBe("blob");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-token",
    );
    request.flush(new Blob(["xlsx"]));
    expect((await promise).body).toBeInstanceOf(Blob);
  });

  it("requests a bounded page of supplier history with the corporate token", async () => {
    const promise = firstValueFrom(api.supplierEvidence("supplier-1", 20));
    await Promise.resolve();
    const request = http.expectOne(
      (r) => r.url === "/api/v1/suppliers/supplier-1/evidence",
    );
    expect(request.request.params.get("offset")).toBe("20");
    expect(request.request.params.get("limit")).toBe("50");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-token",
    );
    request.flush({ items: [], total: 20 });
    expect((await promise).total).toBe(20);
  });

  it("loads the automatic report state for the exact published run", async () => {
    const promise = firstValueFrom(api.runReport("monthly-1"));
    await Promise.resolve();
    const request = http.expectOne("/api/v1/suppliers/runs/monthly-1/report");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-token",
    );
    request.flush({
      runId: "monthly-1",
      status: "pending_review",
      report: null,
      pending: 1,
    });
    expect((await promise).pending).toBe(1);
  });

  it("paginates durable monthly report requests separately from completed snapshots", async () => {
    const promise = firstValueFrom(api.reportRequests(25));
    await Promise.resolve();
    const request = http.expectOne(
      (r) => r.url === "/api/v1/suppliers/report-requests",
    );
    expect(request.request.params.get("offset")).toBe("25");
    expect(request.request.params.get("limit")).toBe("25");
    request.flush({ items: [], total: 25 });
    expect((await promise).total).toBe(25);
  });
  it("requests a version-checked September cutoff without allowing a browser-supplied scope", async () => {
    const promise = firstValueFrom(api.rebuildFromSeptember(12, "reset-key"));
    await Promise.resolve();
    const request = http.expectOne("/api/v1/suppliers/rebuild");
    expect(request.request.method).toBe("POST");
    expect(request.request.body).toEqual({
      startYear: 2026,
      startMonth: 9,
      expectedVersion: 12,
      confirmation: "REINICIAR LISTAS",
    });
    expect(request.request.headers.get("Idempotency-Key")).toBe("reset-key");
    expect(request.request.headers.get("Authorization")).toBe("Bearer corporate-token");
    request.flush({ catalogVersion: 16, startPeriod: { year: 2026, month: 9 }, backupDocumentId: "backup-1" });
    expect((await promise).backupDocumentId).toBe("backup-1");
  });

  it("downloads the retained backup through the protected supplier route", async () => {
    const promise = firstValueFrom(api.downloadBackup("backup/1"));
    await Promise.resolve();
    const request = http.expectOne("/api/v1/suppliers/backups/backup%2F1");
    expect(request.request.method).toBe("GET");
    expect(request.request.responseType).toBe("blob");
    expect(request.request.headers.get("Authorization")).toBe("Bearer corporate-token");
    request.flush(new Blob(["{}"], { type: "application/json" }));
    expect((await promise).body).toBeInstanceOf(Blob);
  });

});
