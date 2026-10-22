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
});
