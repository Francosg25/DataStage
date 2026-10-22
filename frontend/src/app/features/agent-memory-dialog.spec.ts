import { Component } from "@angular/core";
import { TestBed } from "@angular/core/testing";
import { MatDialog, MatDialogModule } from "@angular/material/dialog";
import { of, Subject, throwError } from "rxjs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { AgentMemoryProfile } from "../core/models";
import { AgentMemoryDialog } from "./agent-memory-dialog";

@Component({ imports: [MatDialogModule], template: "" })
class MemoryHost {}

const EMPTY: AgentMemoryProfile = {
  enabled: false,
  version: 0,
  items: [],
  maxItems: 12,
  maxCharacters: 6000,
};
const SAVED: AgentMemoryProfile = {
  ...EMPTY,
  enabled: true,
  version: 3,
  items: [{ id: "memory-1", title: "Moneda", content: "Prefiero USD" }],
};

async function createMemory(state = EMPTY, seed = "") {
  const agentMemory = vi.fn<Api["agentMemory"]>(() =>
    of(structuredClone(state)),
  );
  const saveAgentMemory = vi.fn<Api["saveAgentMemory"]>(() =>
    of({ ...state, version: state.version + 1 }),
  );
  const clearAgentMemory = vi.fn<Api["clearAgentMemory"]>(() =>
    of({ ...EMPTY, version: state.version + 1 }),
  );
  TestBed.configureTestingModule({
    providers: [
      {
        provide: Api,
        useValue: { agentMemory, saveAgentMemory, clearAgentMemory },
      },
    ],
  });
  const fixture = TestBed.createComponent(MemoryHost);
  fixture.detectChanges();
  const dialog = fixture.debugElement.injector.get(MatDialog);
  const ref = dialog.open(AgentMemoryDialog, { data: seed });
  TestBed.tick();
  await fixture.whenStable();
  TestBed.tick();
  return {
    fixture,
    ref,
    component: ref.componentInstance,
    element: ref.componentRef!.location.nativeElement as HTMLElement,
    agentMemory,
    saveAgentMemory,
    clearAgentMemory,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  TestBed.resetTestingModule();
  localStorage.removeItem("datastage.language");
});

describe("memoria personal del asistente", () => {
  it("consulta la memoria guardada y permite cancelar sin escribir nada", async () => {
    const {
      component,
      ref,
      element,
      agentMemory,
      saveAgentMemory,
      clearAgentMemory,
    } = await createMemory(SAVED);
    expect(agentMemory).toHaveBeenCalledOnce();
    expect(component.notes.getRawValue()).toEqual([
      { id: "memory-1", title: "Moneda", content: "Prefiero USD" },
    ]);
    expect(element.querySelector("textarea")!.value).toBe("Prefiero USD");
    const close = vi.spyOn(ref, "close");
    Array.from(element.querySelectorAll("button"))
      .find((button) => button.textContent?.trim() === "Cancelar")!
      .click();
    expect(close).toHaveBeenCalledWith(false);
    expect(saveAgentMemory).not.toHaveBeenCalled();
    expect(clearAgentMemory).not.toHaveBeenCalled();
  });

  it("Recordar prellena una propuesta revisable y sólo guarda cuando el usuario lo confirma", async () => {
    const { component, ref, saveAgentMemory, clearAgentMemory } =
      await createMemory(EMPTY, "Prefiero Excel en USD.");
    expect(component.notes.at(0).controls.content.value).toBe(
      "Prefiero Excel en USD.",
    );
    expect(component.enabled.value).toBe(true);
    expect(saveAgentMemory).not.toHaveBeenCalled();
    component.notes.at(0).controls.title.setValue("Mis reportes");
    const pending = new Subject<AgentMemoryProfile>();
    saveAgentMemory.mockReturnValue(pending);
    const close = vi.spyOn(ref, "close");
    const saving = component.save();
    expect(ref.disableClose).toBe(true);
    expect(component.saving()).toBe(true);
    await component.save();
    expect(saveAgentMemory).toHaveBeenCalledOnce();
    expect(saveAgentMemory).toHaveBeenCalledWith(0, true, [
      { id: "", title: "Mis reportes", content: "Prefiero Excel en USD." },
    ]);
    const saved = { ...SAVED, version: 1 };
    pending.next(saved);
    pending.complete();
    await saving;
    expect(close).toHaveBeenCalledWith(saved);
    expect(clearAgentMemory).not.toHaveBeenCalled();
  });

  it("desactiva el uso sin borrar las notas y conserva el borrador si hay conflicto", async () => {
    const { component, saveAgentMemory } = await createMemory(SAVED);
    component.enabled.setValue(false);
    component.notes.at(0).controls.content.setValue("Prefiero MXN");
    saveAgentMemory.mockReturnValue(
      throwError(() => ({
        status: 409,
        error: {
          detail: "La memoria cambió. Vuelve a abrirla antes de guardar.",
        },
      })),
    );
    await component.save();
    expect(saveAgentMemory).toHaveBeenCalledWith(3, false, [
      { id: "memory-1", title: "Moneda", content: "Prefiero MXN" },
    ]);
    expect(component.notes.at(0).controls.content.value).toBe("Prefiero MXN");
    expect(component.error()).toContain("La memoria cambió");
    expect(component.saving()).toBe(false);
    expect(component.enabled.enabled).toBe(true);
  });

  it("exige confirmar el borrado y conserva los chats", async () => {
    const { component, element, clearAgentMemory } = await createMemory(SAVED);
    await component.clear();
    expect(clearAgentMemory).not.toHaveBeenCalled();
    (element.querySelector(".clear-memory") as HTMLButtonElement).click();
    TestBed.tick();
    expect(element.querySelector(".memory-confirm")!.textContent).toContain(
      "Los mensajes de tus chats se conservan",
    );
    (
      element.querySelector(".memory-confirm button") as HTMLButtonElement
    ).click();
    await component.clear();
    expect(clearAgentMemory).not.toHaveBeenCalled();
    component.confirmClear.set(true);
    await component.clear();
    expect(clearAgentMemory).toHaveBeenCalledOnce();
    expect(clearAgentMemory).toHaveBeenCalledWith(3);
  });

  it("no trunca un mensaje largo al proponer guardarlo como memoria", async () => {
    const text = "x".repeat(1000);
    const { component, element, saveAgentMemory } = await createMemory(
      EMPTY,
      text,
    );
    expect(component.notes.at(0).controls.content.value).toBe(text);
    expect(element.textContent).toContain("Resume esta memoria");
    expect(component.notes.invalid).toBe(true);
    await component.save();
    expect(saveAgentMemory).not.toHaveBeenCalled();
  });

  it("evita duplicados, respeta límites y muestra los controles en inglés", async () => {
    const { component, element, saveAgentMemory } = await createMemory(
      SAVED,
      "Prefiero USD",
    );
    expect(component.notes.length).toBe(1);
    component.i18n.set("en");
    TestBed.tick();
    expect(element.textContent).toContain("Personal memory");
    component.add("Otra preferencia");
    component.notes.at(1).controls.title.setValue(" moneda ");
    expect(component.duplicateTitles()).toBe(true);
    await component.save();
    expect(saveAgentMemory).not.toHaveBeenCalled();
    for (let index = component.notes.length; index < 15; index++)
      component.add("Preference " + index);
    expect(component.notes.length).toBe(12);
  });
});
