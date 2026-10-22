import { TestBed } from "@angular/core/testing";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsChart } from "./analytics-chart";

vi.mock("chart.js", () => ({
  Chart: class {
    constructor(readonly canvas: HTMLCanvasElement) {}
    static register() {}
    destroy() {}
    resize() {}
  },
  registerables: [],
}));

function createChart() {
  TestBed.configureTestingModule({ imports: [AnalyticsChart] });
  const fixture = TestBed.createComponent(AnalyticsChart);
  fixture.componentInstance.i18n.set("es");
  fixture.componentRef.setInput("title", "Valor de mercancías");
  fixture.componentRef.setInput("unit", "USD");
  fixture.componentRef.setInput("subtitle", "Partidas · 551");
  fixture.componentRef.setInput("context", "ene–dic 2026 · Cargas publicadas");
  fixture.componentRef.setInput(
    "footnote",
    "Criterios de agregación y cobertura.",
  );
  fixture.componentRef.setInput("labels", ["ene", "feb"]);
  fixture.componentRef.setInput("series", [
    { label: "Importaciones", color: "#447ec0", values: [100, 200] },
    { label: "Exportaciones", color: "#22978a", values: [50, 70] },
  ]);
  fixture.detectChanges();
  return fixture;
}

describe("concise chart presentation", () => {
  it("includes visible worksheet provenance in the exported PNG", () => {
    const fixture = createChart();
    fixture.componentRef.setInput("sourceSheets", ["551", "501"]);
    fixture.detectChanges();
    const fillText = vi.fn();
    const context = {
      measureText: (text: string) => ({ width: text.length * 8 }),
      fillRect: vi.fn(),
      drawImage: vi.fn(),
      fillText,
    } as unknown as CanvasRenderingContext2D;
    const getContext = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(context);
    const toDataURL = vi
      .spyOn(HTMLCanvasElement.prototype, "toDataURL")
      .mockReturnValue("data:image/png;base64,test");
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    try {
      fixture.componentInstance.download();
      expect(
        fillText.mock.calls.some(
          ([line]) => line === "Fuente: hojas 551 · 501",
        ),
      ).toBe(true);
      expect(click).toHaveBeenCalledOnce();
    } finally {
      getContext.mockRestore();
      toDataURL.mockRestore();
      click.mockRestore();
    }
  });
  it("keeps worksheet provenance visible with details closed, in the data view and in both languages", () => {
    const fixture = createChart();
    fixture.componentRef.setInput("sourceSheets", ["557", "551", "501"]);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    const source = () => element.querySelector(".chart-source");
    expect(source()?.textContent).toBe("Fuente: hojas 557 · 551 · 501");
    expect(source()?.closest("details")).toBeNull();
    expect(element.querySelector<HTMLDetailsElement>("details")?.open).toBe(
      false,
    );
    fixture.componentInstance.table.set(true);
    fixture.componentInstance.i18n.set("en");
    fixture.componentRef.setInput("sourceSheets", ["sel"]);
    fixture.detectChanges();
    expect(source()?.textContent).toBe("Source: sheet SEL");
    expect(element.querySelector(".viz-table")).not.toBeNull();
    expect(
      element.querySelector("canvas")?.getAttribute("aria-label"),
    ).toContain("Source: sheet SEL");
  });
  it("keeps title/unit visible and groups explanations into native details closed by default", () => {
    const fixture = createChart();
    const element: HTMLElement = fixture.nativeElement;
    const header = element.querySelector(".viz-header")!;
    expect(header.textContent).toContain("Valor de mercancías");
    expect(header.querySelector(".chart-unit")?.textContent).toBe("USD");
    expect(header.textContent).not.toContain("Partidas · 551");
    expect(header.textContent).not.toContain("ene–dic 2026");
    const details =
      element.querySelector<HTMLDetailsElement>(".chart-details")!;
    expect(details.open).toBe(false);
    expect(details.querySelector("summary")).not.toBeNull();
    expect(details.textContent).toContain("Partidas · 551");
    expect(details.textContent).toContain("ene–dic 2026");
    expect(details.textContent).toContain(
      "Criterios de agregación y cobertura.",
    );
  });
  it("keeps unavailable data visible as a concise state and preserves both series in the data table", () => {
    const fixture = createChart();
    fixture.componentRef.setInput("series", [
      { label: "Importaciones", color: "#447ec0", values: [100, null] },
      { label: "Exportaciones", color: "#22978a", values: [50, 70] },
    ]);
    fixture.componentInstance.i18n.set("en");
    fixture.componentInstance.table.set(true);
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector(".chart-data-status")?.textContent).toContain(
      "Unavailable values",
    );
    expect(element.querySelector("summary")?.textContent).toBe("Details");
    const headers = Array.from(element.querySelectorAll(".viz-table th")).map(
      (cell) => cell.textContent?.trim(),
    );
    expect(headers).toEqual([
      "Category",
      "Importaciones · USD",
      "Exportaciones · USD",
    ]);
    expect(element.querySelector(".viz-table tbody")?.textContent).toContain(
      "Unavailable",
    );
  });
  it("does not add redundant details when the subtitle only repeats the unit", () => {
    const fixture = createChart();
    fixture.componentRef.setInput("subtitle", "USD");
    fixture.componentRef.setInput("context", "");
    fixture.componentRef.setInput("footnote", "");
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector(".chart-details")).toBeNull();
    fixture.componentRef.setInput("series", [
      { label: "Importaciones", color: "#447ec0", values: [0, 0] },
    ]);
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(".chart-data-status")?.textContent,
    ).toContain("Valores disponibles: 0");
  });
});
