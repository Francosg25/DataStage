import { describe, it, expect } from "vitest";
import { isTerminal, Run } from "./models";
import { validateZip } from "../features/monthly";
import { isOwnApiUrl } from "./auth";
describe("límites de archivos de carga", () => {
  it("rechaza archivos vacíos y archivos que exceden el límite", () => {
    expect(validateZip(new File([], "carga.zip"), 1)).toContain("vacío");
    expect(
      validateZip(new File([new Uint8Array(1024 * 1024 + 1)], "carga.zip"), 1),
    ).toContain("supera");
  });
  it("acepta ZIP con extensión mayúscula y rechaza otros archivos", () => {
    expect(validateZip(new File(["datos"], "DATOS.ZIP"), 1)).toBe("");
    expect(validateZip(new File(["datos"], "datos.csv"), 1)).toContain(".zip");
  });
});
describe("límite de envío del token corporativo", () => {
  it("solo acepta la API del mismo origen", () => {
    expect(isOwnApiUrl("/api/v1/runs")).toBe(true);
    expect(isOwnApiUrl("https://external.example/api/v1/runs")).toBe(false);
    expect(isOwnApiUrl("//external.example/api/v1/runs")).toBe(false);
    expect(isOwnApiUrl("/assets/logo.svg")).toBe(false);
    expect(isOwnApiUrl("/apianother/runs")).toBe(false);
  });
});
describe("seguimiento de ejecución", () => {
  it("continúa consultando una ejecución con observaciones mientras se exporta", () => {
    expect(
      isTerminal({ status: "needs_attention", exportStatus: "pending" } as Run),
    ).toBe(false);
    expect(
      isTerminal({ status: "needs_attention", exportStatus: "ready" } as Run),
    ).toBe(true);
    expect(
      isTerminal({ status: "needs_attention", exportStatus: "failed" } as Run),
    ).toBe(true);
  });
  it("detiene el seguimiento al terminar o fallar", () => {
    expect(isTerminal({ status: "running" } as Run)).toBe(false);
    expect(isTerminal({ status: "completed" } as Run)).toBe(true);
    expect(isTerminal({ status: "failed" } as Run)).toBe(true);
  });
});
