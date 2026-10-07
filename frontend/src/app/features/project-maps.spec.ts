import { TestBed } from "@angular/core/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { of, Subject, throwError } from "rxjs";
import { Api } from "../core/api";
import { ProjectMapCatalog } from "../core/project-maps";
import { ProjectMaps } from "./project-maps";

const catalog: ProjectMapCatalog = {
  title: "Fixed assets",
  sourceFile: "source.pptx",
  sourceSha256: "abc",
  date: "2026-08-11",
  location: "Zacatecas",
  pages: Array.from({ length: 6 }, (_, i) => ({
    id: `map-${i}`,
    slide: i + 3,
    es: `Mapa ${i}`,
    en: `Map ${i}`,
    width: 2880,
    height: 1620,
    text: [`Source text ${i}`],
  })),
};

function setup(
  options: {
    catalog?: ReturnType<Api["projectMaps"]>;
    image?: Api["projectMapImage"];
  } = {},
) {
  const projectMaps = vi.fn(() => options.catalog ?? of(catalog));
  const projectMapImage = vi.fn(
    options.image ?? (() => of(new Blob(["png"], { type: "image/png" }))),
  );
  TestBed.configureTestingModule({
    providers: [{ provide: Api, useValue: { projectMaps, projectMapImage } }],
  });
  const component = TestBed.runInInjectionContext(() => new ProjectMaps());
  return { component, projectMaps, projectMapImage };
}

describe("project map viewer", () => {
  beforeEach(() => {
    let id = 0;
    vi.stubGlobal(
      "URL",
      class extends URL {
        static override createObjectURL = vi.fn(() => `blob:map-${++id}`);
        static override revokeObjectURL = vi.fn();
      },
    );
  });
  afterEach(() => {
    TestBed.resetTestingModule();
    vi.unstubAllGlobals();
  });

  it("loads six thumbnails and only the current and neighboring full pages", () => {
    const { component, projectMapImage } = setup();
    expect(component.pages()).toHaveLength(6);
    expect(
      projectMapImage.mock.calls.filter(([, thumbnail]) => thumbnail),
    ).toHaveLength(6);
    expect(
      projectMapImage.mock.calls
        .filter(([, thumbnail]) => !thumbnail)
        .map(([id]) => id),
    ).toEqual(["map-0", "map-1"]);
    expect(component.current()?.slide).toBe(3);
    expect(component.loading()).toBe(false);
  });

  it("navigates within bounds, resets zoom and keeps page caches", () => {
    const { component, projectMapImage } = setup();
    component.changeZoom(10);
    expect(component.zoom()).toBe(4);
    component.goTo(1);
    expect(component.zoom()).toBe(1);
    component.goTo(0);
    expect(component.direction()).toBe(-1);
    component.goTo(-1);
    component.goTo(6);
    component.goTo(1.5);
    expect(component.index()).toBe(0);
    expect(
      projectMapImage.mock.calls.filter(
        ([id, thumbnail]) => id === "map-0" && !thumbnail,
      ),
    ).toHaveLength(1);
    component.changeZoom(-10);
    expect(component.zoom()).toBe(1);
  });

  it("supports keyboard navigation without handling modified shortcuts", () => {
    const { component } = setup();
    component.onKey(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    expect(component.index()).toBe(1);
    component.onKey(new KeyboardEvent("keydown", { key: "End" }));
    expect(component.index()).toBe(5);
    component.onKey(
      new KeyboardEvent("keydown", { key: "Home", ctrlKey: true }),
    );
    expect(component.index()).toBe(5);
    component.onKey(new KeyboardEvent("keydown", { key: "Home" }));
    expect(component.index()).toBe(0);
  });

  it("keeps a late image response from replacing the selected page", () => {
    const first = new Subject<Blob>();
    const { component } = setup({
      image: (id, thumb) =>
        id === "map-0" && !thumb ? first : of(new Blob(["png"])),
    });
    component.goTo(3);
    first.next(new Blob(["first"]));
    first.complete();
    expect(component.current()?.id).toBe("map-3");
    expect(component.image(component.current()!)).toBeTruthy();
  });

  it("shows image failures and allows retry, including decode failures", () => {
    let fail = true;
    const { component } = setup({
      image: (id, thumb) =>
        fail && id === "map-0" && !thumb
          ? throwError(() => new Error("Network"))
          : of(new Blob(["png"])),
    });
    const page = component.current()!;
    expect(component.failed().has(component.key(page))).toBe(true);
    fail = false;
    component.loadImage(page);
    expect(component.failed().has(component.key(page))).toBe(false);
    const url = component.image(page);
    component.imageFailed(page);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(url);
    expect(component.image(page)).toBeUndefined();
    component.loadImage(page);
    expect(component.image(page)).toBeTruthy();
  });

  it("handles empty and failed catalogs without selecting a nonexistent page", () => {
    const { component } = setup({
      catalog: throwError(() => new Error("Offline")),
    });
    expect(component.catalogError()).toBe(true);
    expect(component.loading()).toBe(false);
    expect(component.current()).toBeUndefined();
    component.catalog.set({ ...catalog, pages: [] });
    component.goTo(0);
    expect(component.selectedPages()).toEqual([]);
  });

  it("releases every object URL when leaving the viewer", () => {
    const { component } = setup();
    const urls = Object.values(component.urls());
    TestBed.resetTestingModule();
    urls.forEach((url) =>
      expect(URL.revokeObjectURL).toHaveBeenCalledWith(url),
    );
  });
});
