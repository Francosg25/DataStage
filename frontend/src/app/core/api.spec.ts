import { TestBed } from "@angular/core/testing";
import { provideHttpClient, withInterceptors } from "@angular/common/http";
import {
  HttpTestingController,
  provideHttpClientTesting,
} from "@angular/common/http/testing";
import { firstValueFrom } from "rxjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Api } from "./api";
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
});
