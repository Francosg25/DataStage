import { TestBed } from "@angular/core/testing";
import { FormBuilder } from "@angular/forms";
import { Router } from "@angular/router";
import { throwError } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { Monthly } from "./monthly";

describe("reintentos de una carga mensual", () => {
  it("conserva la clave idempotente tras un fallo de red y la renueva al cambiar el archivo", () => {
    const monthly = vi
      .fn()
      .mockImplementation(() => throwError(() => ({ status: 0 })));
    TestBed.configureTestingModule({
      providers: [
        FormBuilder,
        { provide: Api, useValue: { monthly } },
        { provide: Auth, useValue: { config: () => ({ maxUploadMb: 10 }) } },
        { provide: Router, useValue: { navigate: vi.fn() } },
      ],
    });
    const component = TestBed.runInInjectionContext(() => new Monthly());
    component.accept(new File(["datos"], "carga.zip"));
    component.submit();
    expect(component.busy()).toBe(false);
    expect(component.form.enabled).toBe(true);
    component.submit();
    expect(monthly.mock.calls[0][2]).toBe(monthly.mock.calls[1][2]);
    component.accept(new File(["otra carga"], "otra.zip"));
    component.submit();
    expect(monthly.mock.calls[2][2]).not.toBe(monthly.mock.calls[1][2]);
  });
});
