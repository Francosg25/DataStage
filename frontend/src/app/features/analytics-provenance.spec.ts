import { TestBed } from "@angular/core/testing";
import { registerLocaleData } from "@angular/common";
import esMx from "@angular/common/locales/es-MX";
import { provideRouter } from "@angular/router";
import { of } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { AnalyticsReport } from "../core/analytics";
import { Analytics } from "./analytics";
import { Dashboard } from "./dashboard";
import { MonthComparison } from "../shared/month-comparison";

registerLocaleData(esMx);

vi.mock("chart.js", () => ({
  Chart: class {
    static register() {}
    destroy() {}
    resize() {}
  },
  registerables: [],
}));

function sampleReport(): AnalyticsReport {
  const values = {
    declarations: 2,
    importUsd: 100,
    exportUsd: 200,
    importMxn: 1700,
    exportMxn: 3400,
    igiPaid: 10,
    ivaPaid: 20,
    ivaFp21: 30,
    rectifications: 1,
    redRate: 5,
    items: 3,
  };
  const payment = {
    cash: { igi: 10, iva: 20, unmatchedRows: 0 },
    certiva: { igi: 0, iva: 30, unmatchedRows: 0 },
    other: [],
    otherPaymentRows: 0,
  };
  const filters = {
    source: "published",
    year: 2026,
    startMonth: 1,
    endMonth: 2,
    operation: "",
    customs: "",
    document: "",
    currency: "USD" as const,
  };
  return {
    ...filters,
    appliedFilters: filters,
    snapshotId: "test",
    generatedAt: "2026-10-22",
    sources: [],
    reconciliation: null,
    totals: values,
    latest: values,
    previous: values,
    deltas: {},
    latestMonth: 2,
    previousMonth: 1,
    monthly: [1, 2].map((month) => ({
      month,
      available: true,
      metrics: values,
      paymentMethods: payment,
      rows: 3,
      files: 1,
      warnings: 0,
      errors: 0,
      tables: {},
      runId: "test",
      version: 1,
    })),
    paymentMethods: payment,
    rectifications: [],
    rectificationsByCustoms: {
      rows: [],
      customsPatentRows: [],
      patentRows: [],
      globalDeclarations: 2,
      available: true,
      unmatchedAmendments: 0,
      invalidKeys: 0,
      totals: { r1: 1, declarations: 2, officeRate: 50, globalRate: 50 },
    },
    breakdowns: {
      customs: [{ key: "730", value: 2, rows: 2 }],
      documents: [],
      tariffs: [],
    },
    coverage: {
      availableMonths: [1, 2],
      requestedMonths: 2,
      tables: {},
      invalidNumericValues: 0,
      orphanItems: 0,
      duplicateDeclarationRows: 0,
      processingFiltersApplied: false,
      missingExchangeRates: 0,
    },
    filters: { customs: [], documents: [], operations: [] },
    partTaxes: {
      rows: [
        {
          partNumber: "TEST-PN",
          tariff: "85045091",
          items: 1,
          igi: 10,
          iva: 20,
          months: {},
        },
      ],
      alerts: [],
      missingParts: 0,
      ambiguousParts: 0,
      invalidItemKeys: 0,
      unmatchedTaxRows: 0,
      observationSourceAvailable: true,
      available: true,
      currency: "USD",
      totals: { igi: 10, iva: 20 },
    },
  };
}

const options = () =>
  of({
    defaultSource: "published",
    sources: [{ id: "published", years: [2026] }],
  });

async function createAnalytics() {
  await TestBed.configureTestingModule({
    imports: [Analytics],
    providers: [
      provideRouter([]),
      {
        provide: Api,
        useValue: {
          analyticsOptions: options,
          analytics: () => of(sampleReport()),
        },
      },
    ],
  }).compileComponents();
  const fixture = TestBed.createComponent(Analytics);
  fixture.componentInstance.i18n.set("es");
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe("visible metric explanations and worksheet provenance", () => {
  it("explains all eight KPI cards and distinguishes cash, credit, amendments and selection events in ES/EN", async () => {
    const fixture = await createAnalytics();
    const element: HTMLElement = fixture.nativeElement;
    const descriptions = () =>
      Array.from(
        element.querySelectorAll(".kpi-description"),
        (p) => p.textContent || "",
      );
    expect(descriptions()).toHaveLength(8);
    expect(descriptions().every((text) => text.trim().length > 15)).toBe(true);
    expect(descriptions().join(" ")).toContain("en efectivo (FP 0)");
    expect(descriptions().join(" ")).toContain("crédito IVA/IEPS (FP 21)");
    expect(descriptions().join(" ")).toContain("modificación o corrección");
    expect(descriptions().join(" ")).toContain("eventos de selección");
    const sources = () =>
      Array.from(element.querySelectorAll(".metric-source"), (p) =>
        p.textContent?.trim(),
      );
    expect(sources()).toEqual([
      "Fuente: hoja 501",
      "Fuente: hoja 551",
      "Fuente: hoja 551",
      "Fuente: hojas 557 · 551 · 501",
      "Fuente: hojas 557 · 551 · 501",
      "Fuente: hojas 557 · 551 · 501",
      "Fuente: hoja 701",
      "Fuente: hoja SEL",
    ]);
    fixture.componentInstance.i18n.set("en");
    fixture.detectChanges();
    expect(descriptions().join(" ")).toContain("paid in cash");
    expect(descriptions().join(" ")).toContain("VAT/excise tax credit");
    expect(descriptions().join(" ")).toContain("change or correction");
    expect(descriptions().join(" ")).toContain("customs selection events");
    expect(sources()[7]).toBe("Source: sheet SEL");
  });

  it("shows source sheets on every analytics chart and adjusts currency and PN-filter dependencies", async () => {
    const fixture = await createAnalytics();
    const component = fixture.componentInstance;
    const element: HTMLElement = fixture.nativeElement;
    const sources = () =>
      Array.from(
        element.querySelectorAll("ds-analytics-chart .chart-source"),
        (p) => p.textContent?.trim(),
      );
    expect(sources()).toEqual(["Fuente: hoja 551"]);
    component.tab.set("trade");
    fixture.detectChanges();
    expect(sources()).toEqual([
      "Fuente: hoja 501",
      "Fuente: hoja 501",
      "Fuente: hoja 551",
    ]);
    component.report.set({ ...sampleReport(), currency: "MXN" });
    fixture.detectChanges();
    expect(sources()).toEqual([
      "Fuente: hoja 501",
      "Fuente: hoja 501",
      "Fuente: hojas 551 · 501",
    ]);
    component.tab.set("taxes");
    fixture.detectChanges();
    expect(sources()).toEqual([
      "Fuente: hojas 557 · 551 · 558",
      "Fuente: hojas 557 · 551",
    ]);
    component.searchParts("TEST-PN");
    fixture.detectChanges();
    expect(sources()).toEqual([
      "Fuente: hojas 557 · 551 · 558",
      "Fuente: hojas 557 · 551 · 558",
    ]);
    component.tab.set("quality");
    fixture.detectChanges();
    expect(
      element
        .querySelector("#rectifications-title")
        ?.closest(".section-heading")?.textContent,
    ).toContain("Fuente: hojas 701 · 501");
    expect(
      element
        .querySelector("#rectifications-patent-title")
        ?.closest(".section-heading")?.textContent,
    ).toContain("Fuente: hojas 701 · 501");
  });

  it("updates monthly comparison provenance when changing metric and currency", async () => {
    await TestBed.configureTestingModule({
      imports: [MonthComparison],
      providers: [
        {
          provide: Api,
          useValue: {
            analyticsOptions: options,
            analyticsMonths: (request: { currency: "USD" | "MXN" }) =>
              of({ ...sampleReport(), currency: request.currency }),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(MonthComparison);
    const component = fixture.componentInstance;
    component.i18n.set("es");
    fixture.detectChanges();
    await fixture.whenStable();
    const element: HTMLElement = fixture.nativeElement;
    const source = () =>
      element.querySelector(".chart-source")?.textContent?.trim();
    expect(element.querySelectorAll(".comparison-description")).toHaveLength(8);
    const selectMetric = async (value: string) => {
      const select = element.querySelector<HTMLSelectElement>(
        ".metric-select select",
      )!;
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      fixture.detectChanges();
      await fixture.whenStable();
    };
    await selectMetric("igiPaid");
    expect(source()).toBe("Fuente: hojas 557 · 551 · 501");
    const currencySelect = element.querySelector<HTMLSelectElement>(
      ".selectors > label:last-child select",
    )!;
    currencySelect.value = "MXN";
    currencySelect.dispatchEvent(new Event("change", { bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(source()).toBe("Fuente: hojas 557 · 551");
    await selectMetric("importMxn");
    expect(source()).toBe("Fuente: hojas 551 · 501");
    await selectMetric("rectifications");
    component.i18n.set("en");
    fixture.detectChanges();
    expect(source()).toBe("Source: sheet 701");
    expect(
      element.querySelector(".comparison-description")?.textContent,
    ).toContain("Distinct customs declarations");
  });

  it("labels dashboard activity as all processed sheets rather than assigning an incorrect single worksheet", async () => {
    await TestBed.configureTestingModule({
      imports: [Dashboard],
      providers: [
        provideRouter([]),
        {
          provide: Api,
          useValue: {
            overview: () =>
              of({
                monthly: [{ period: "enero_2026", rows: 10 }],
                rowsCount: 10,
                periodsCount: 1,
                runsCount: 1,
                warningCount: 0,
                errorCount: 0,
                recentRuns: [],
              }),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(Dashboard);
    fixture.componentInstance.i18n.set("es");
    fixture.detectChanges();
    await fixture.whenStable();
    expect(
      fixture.nativeElement.querySelector(".activity-source")?.textContent,
    ).toContain("todas las hojas procesadas");
    fixture.componentInstance.i18n.set("en");
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(".activity-source")?.textContent,
    ).toContain("all processed sheets");
  });
});
