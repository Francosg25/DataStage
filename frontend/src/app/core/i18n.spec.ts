import { TestBed } from "@angular/core/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { I18n, LocalizedNumberPipe } from "./i18n";

describe("application language", () => {
  beforeEach(() => localStorage.removeItem("datastage.language"));
  afterEach(() => localStorage.removeItem("datastage.language"));
  it("translates labels and period labels while preserving identifiers", () => {
    const i18n = TestBed.inject(I18n);
    i18n.set("en");
    expect(i18n.t("Carga mensual")).toBe("Monthly upload");
    expect(i18n.t("Agosto_2026")).toBe("August_2026");
    expect(i18n.t("0000123")).toBe("0000123");
    expect(i18n.number(null)).toBe("—");
    expect(i18n.number(0)).toBe("0");
    i18n.set("es");
    expect(i18n.t("Carga mensual")).toBe("Carga mensual");
  });
  it("restores the saved language without affecting data values", () => {
    localStorage.setItem("datastage.language", "en");
    const i18n = TestBed.inject(I18n);
    expect(i18n.language()).toBe("en");
    const pipe = TestBed.runInInjectionContext(() => new LocalizedNumberPipe());
    expect(pipe.transform(12345.5)).toBe("12,345.5");
  });
});
