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
