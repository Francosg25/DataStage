import { TestBed } from "@angular/core/testing";
import { afterEach, describe, expect, it } from "vitest";
import { AssistantText } from "./assistant-text";

afterEach(() => TestBed.resetTestingModule());

describe("respuestas del asistente", () => {
  it("presenta negritas, listas, código y tablas con celdas legibles", () => {
    const fixture = TestBed.createComponent(AssistantText);
    fixture.componentRef.setInput(
      "text",
      "## Resultado\n\n**Mayo** y `Junio_2025`.\n\n- Una fuente\n- Otra fuente\n\n| Mes | Total |\n| --- | ---: |\n| Mayo | 123 |\n\n```text\nDatos de ejemplo\n```",
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("strong").textContent).toBe(
      "Mayo",
    );
    expect(fixture.nativeElement.querySelectorAll("li")).toHaveLength(2);
    expect(fixture.nativeElement.querySelectorAll("tbody td")).toHaveLength(2);
    expect(fixture.nativeElement.querySelector("pre").textContent).toBe(
      "Datos de ejemplo",
    );
  });
  it("muestra HTML y enlaces no confiables como texto y nunca los ejecuta", () => {
    const fixture = TestBed.createComponent(AssistantText);
    fixture.componentRef.setInput(
      "text",
      '<img src=x onerror="alert(1)"><script>alert(1)</script> **texto** [link](javascript:alert(1))',
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("img")).toBeNull();
    expect(fixture.nativeElement.querySelector("script")).toBeNull();
    expect(fixture.nativeElement.querySelector("a")).toBeNull();
    expect(fixture.nativeElement.textContent).toContain("onerror");
  });
  it("sustituye los enlaces técnicos de archivos reales por sus tarjetas y conserva los enlaces sin verificar como texto", () => {
    const fixture = TestBed.createComponent(AssistantText);
    const url = "/api/v1/agent/conversations/chat/artifacts/document";
    fixture.componentRef.setInput("artifactUrls", [url]);
    fixture.componentRef.setInput(
      "text",
      `Archivo preparado.\n\n[Download the Excel file]( ${url} )\n\nConsulta [este archivo](${url}) abajo.\n\n[Unverified](https://unknown.invalid)\n\n\`\`\`text\n[Keep example](${url})\n\`\`\``,
    );
    fixture.detectChanges();
    const paragraphs = [...fixture.nativeElement.querySelectorAll("p")]
      .map((node) => (node as HTMLElement).textContent)
      .join(" ");
    expect(paragraphs).not.toContain(url);
    expect(paragraphs).toContain("este archivo abajo");
    expect(paragraphs).toContain("https://unknown.invalid");
    expect(fixture.nativeElement.querySelector("pre").textContent).toContain(
      url,
    );
    expect(fixture.nativeElement.querySelector("a")).toBeNull();
  });
});
