import { TestBed } from "@angular/core/testing";
import { provideHttpClient, withInterceptors } from "@angular/common/http";
import {
  HttpTestingController,
  provideHttpClientTesting,
} from "@angular/common/http/testing";
import { firstValueFrom } from "rxjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Api, BulkPeriodPreview } from "./api";
import { Auth, bearerInterceptor } from "./auth";
describe("contratos de la API", () => {
  let api: Api;
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
            token: vi.fn().mockResolvedValue("corporate-access-token"),
          },
        },
      ],
    });
    api = TestBed.inject(Api);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it("loads, updates and clears only the authenticated user's memory with a version guard", async () => {
    const profile = {
      enabled: true,
      version: 1,
      maxItems: 12,
      maxCharacters: 6000,
      items: [
        {
          id: "note-1",
          title: "Currency",
          content: "USD",
          createdAt: "2026-10-22",
        },
      ],
    };
    const loading = firstValueFrom(api.agentMemory());
    await Promise.resolve();
    const get = http.expectOne("/api/v1/agent/memory");
    expect(get.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    get.flush(profile);
    expect((await loading).items).toHaveLength(1);
    const saving = firstValueFrom(api.saveAgentMemory(1, false, profile.items));
    await Promise.resolve();
    const patch = http.expectOne("/api/v1/agent/memory");
    expect(patch.request.method).toBe("PATCH");
    expect(patch.request.body).toEqual({
      expectedVersion: 1,
      enabled: false,
      items: [{ id: "note-1", title: "Currency", content: "USD" }],
    });
    patch.flush({ ...profile, enabled: false, version: 2 });
    expect((await saving).enabled).toBe(false);
    const clearing = firstValueFrom(api.clearAgentMemory(2));
    await Promise.resolve();
    const deletion = http.expectOne("/api/v1/agent/memory?expectedVersion=2");
    expect(deletion.request.method).toBe("DELETE");
    expect(deletion.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    deletion.flush({ ...profile, enabled: false, items: [], version: 3 });
    expect((await clearing).items).toEqual([]);
  });
  it("deletes the selected conversation through the authenticated API and encodes its identifier", async () => {
    const promise = firstValueFrom(api.deleteConversation("chat/with space"));
    await Promise.resolve();
    const request = http.expectOne(
      "/api/v1/agent/conversations/chat%2Fwith%20space",
    );
    expect(request.request.method).toBe("DELETE");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    request.flush(null, { status: 204, statusText: "No Content" });
    expect(await promise).toBeNull();
  });
  it("requests the lightweight monthly summary through the authenticated API", async () => {
    const promise = firstValueFrom(
      api.analyticsMonths({ source: "published", year: 2026, currency: "MXN" }),
    );
    await Promise.resolve();
    const request = http.expectOne(
      (r) => r.url === "/api/v1/reports/analytics/months",
    );
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    expect(request.request.params.keys().sort()).toEqual([
      "currency",
      "source",
      "year",
    ]);
    request.flush({ year: 2026, currency: "MXN", monthly: [] });
    expect((await promise).currency).toBe("MXN");
  });
  it("deletes months with the reviewed token and confirmation without a reason", async () => {
    const preview = {
      periods: [{ periodId: "april" }, { periodId: "may" }],
      token: "a".repeat(64),
      confirmation: "DELETE 2 MONTHS",
    } as BulkPeriodPreview;
    const promise = firstValueFrom(
      api.deletePeriods(preview, preview.confirmation),
    );
    await Promise.resolve();
    const request = http.expectOne("/api/v1/periods/bulk-delete");
    expect(request.request.method).toBe("POST");
    expect(JSON.parse(request.request.serializeBody() as string)).toEqual({
      periodIds: ["april", "may"],
      expectedToken: preview.token,
      confirmation: preview.confirmation,
    });
    request.flush({ storageCleanupFailures: 0 });
    expect((await promise).storageCleanupFailures).toBe(0);
  });
  it("downloads filtered PDF reports with a corporate token and snapshot", async () => {
    const promise = firstValueFrom(
      api.analyticsPdf(
        {
          source: "reference",
          year: 2026,
          startMonth: 2,
          endMonth: 6,
          operation: "1",
          customs: "160",
          document: "AF",
          currency: "MXN",
        },
        "en",
        "abc",
      ),
    );
    await Promise.resolve();
    const request = http.expectOne(
      (r) => r.url === "/api/v1/reports/analytics/pdf",
    );
    expect(request.request.responseType).toBe("blob");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    expect(request.request.params.get("startMonth")).toBe("2");
    expect(request.request.params.get("endMonth")).toBe("6");
    expect(request.request.params.get("customs")).toBe("160");
    expect(request.request.params.get("snapshot")).toBe("abc");
    expect(request.request.params.get("language")).toBe("en");
    request.flush(new Blob(["%PDF-test"]));
    expect((await promise).size).toBe(9);
  });
  it("envía ZIP, periodo, token e idempotencia en la carga mensual", async () => {
    const file = new File(["abc"], "carga.zip");
    const promise = firstValueFrom(
      api.monthly("Abril_2026", file, "request-123"),
    );
    await Promise.resolve();
    const request = http.expectOne("/api/v1/monthly-runs");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    expect(request.request.headers.get("Idempotency-Key")).toBe("request-123");
    expect(request.request.headers.has("Content-Type")).toBe(false);
    expect(request.request.body.get("periodo")).toBe("Abril_2026");
    expect(request.request.body.get("zip")).toBe(file);
    request.flush({ id: "run-1" });
    expect((await promise).id).toBe("run-1");
  });
  it("descarga documentos por la API autenticada", async () => {
    const promise = firstValueFrom(api.download("document-1"));
    await Promise.resolve();
    const request = http.expectOne("/api/v1/documents/document-1/download");
    expect(request.request.responseType).toBe("blob");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    request.flush(new Blob(["xlsx"]));
    expect((await promise).body?.size).toBe(4);
  });
  it("carga los mapas con token corporativo, no como archivos públicos", async () => {
    const promise = firstValueFrom(api.projectMapImage("plant-1", true));
    await Promise.resolve();
    const request = http.expectOne(
      "/api/v1/project-maps/plant-1/image?thumbnail=true",
    );
    expect(request.request.responseType).toBe("blob");
    expect(request.request.headers.get("Authorization")).toBe(
      "Bearer corporate-access-token",
    );
    request.flush(new Blob(["png"], { type: "image/png" }));
    expect((await promise).size).toBe(3);
  });
});
