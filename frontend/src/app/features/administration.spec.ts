import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { RouterTestingHarness } from "@angular/router/testing";
import { afterEach, describe, expect, it, vi } from "vitest";
import { of } from "rxjs";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { SuppliersApi } from "../core/suppliers";
import { Administration } from "./administration";

async function setup(url = "/administration", admin = true) {
  const suppliers = {
    summary: vi.fn<SuppliersApi["summary"]>(() =>
      of({
        initialized: true,
        catalogVersion: 3,
        national: 46,
        foreign: 235,
        pending: 0,
        reports: 1,
        equivalences: 0,
      }),
    ),
  };
  TestBed.configureTestingModule({
    providers: [
      provideRouter([{ path: "administration", component: Administration }]),
      { provide: Auth, useValue: { hasRole: () => admin, config: () => null } },
      {
        provide: Api,
        useValue: {
          catalog: () => of([]),
          audit: () => of({ items: [], total: 0 }),
        },
      },
      { provide: SuppliersApi, useValue: suppliers },
    ],
  });
  const harness = await RouterTestingHarness.create(url);
  harness.detectChanges();
  await harness.fixture.whenStable();
  harness.detectChanges();
  return {
    harness,
    suppliers,
    component: harness.routeDebugElement!.componentInstance as Administration,
  };
}
afterEach(() => {
  localStorage.removeItem("datastage.language");
  TestBed.resetTestingModule();
});

describe("supplier configuration navigation", () => {
  it("opens the supplier tab directly from the Suppliers settings link", async () => {
    const { harness, component, suppliers } = await setup(
      "/administration?section=suppliers",
    );
    expect(component.selectedTab()).toBe(3);
    expect(suppliers.summary).toHaveBeenCalledOnce();
    expect(
      harness.routeNativeElement!.querySelector("ds-supplier-settings"),
    ).not.toBeNull();
    expect(harness.routeNativeElement!.textContent).not.toContain(
      "Configuración de solo lectura",
    );
  });

  it("loads supplier configuration only after its tab is selected", async () => {
    const { harness, component, suppliers } = await setup();
    expect(suppliers.summary).not.toHaveBeenCalled();
    component.selectedTab.set(3);
    harness.detectChanges();
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(suppliers.summary).toHaveBeenCalledOnce();
  });

  it("does not expose supplier administration through a direct link to a reader", async () => {
    const { harness, component, suppliers } = await setup(
      "/administration?section=suppliers",
      false,
    );
    expect(component.selectedTab()).toBe(0);
    expect(suppliers.summary).not.toHaveBeenCalled();
    expect(
      harness.routeNativeElement!.querySelector("ds-supplier-settings"),
    ).toBeNull();
  });
});
