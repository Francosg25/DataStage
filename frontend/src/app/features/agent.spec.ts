import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of, Subject, throwError } from "rxjs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { Agent } from "./agent";
function createAgent(enabled: boolean, permitted: boolean) {
  const message = vi
    .fn<Api["message"]>()
    .mockReturnValue(of({ message: "Consulta completada", evidence: [] }));
  const conversation = vi.fn<Api["conversation"]>(() =>
    of({ id: "conversation-1" }),
  );
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      {
        provide: Api,
        useValue: { conversation, message },
      },
      {
        provide: Auth,
        useValue: {
          config: () => ({ foundryEnabled: true, allowAgentCommands: enabled }),
          hasRole: () => permitted,
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(Agent);
  const component = fixture.componentInstance;
  component.message.setValue("Consolida el periodo");
  component.allowActions.setValue(true);
  fixture.detectChanges();
  return { component, fixture, conversation, message };
}

afterEach(() => {
  localStorage.removeItem("datastage.language");
  TestBed.resetTestingModule();
});

describe("envío del formulario del asistente", () => {
  it("evita la recarga, conserva la consulta durante la espera y muestra la respuesta", async () => {
    const { component, fixture, conversation, message } = createAgent(
      false,
      false,
    );
    const pending = new Subject<{ message: string; evidence: [] }>();
    message.mockReturnValue(pending);
    component.message.setValue("Resume las últimas ejecuciones");
    fixture.detectChanges();
    const form: HTMLFormElement =
      fixture.nativeElement.querySelector("form.chat-input");
    const submit = new Event("submit", { bubbles: true, cancelable: true });
    expect(form.dispatchEvent(submit)).toBe(false);
    expect(submit.defaultPrevented).toBe(true);
    await vi.waitFor(() => expect(message).toHaveBeenCalledOnce());
    fixture.detectChanges();
    expect(component.busy()).toBe(true);
    expect(fixture.nativeElement.querySelector("textarea").value).toBe(
      "Resume las últimas ejecuciones",
    );
    expect(
      fixture.nativeElement.querySelector("button[type=submit]").disabled,
    ).toBe(true);
    expect(
      fixture.nativeElement.querySelector("mat-progress-bar"),
    ).not.toBeNull();
    const duplicate = new Event("submit", { bubbles: true, cancelable: true });
    form.dispatchEvent(duplicate);
    expect(duplicate.defaultPrevented).toBe(true);
    expect(message).toHaveBeenCalledOnce();
    pending.next({ message: "Ejecución run-1 completada", evidence: [] });
    pending.complete();
    await vi.waitFor(() => expect(component.busy()).toBe(false));
    fixture.detectChanges();
    const displayed = [
      ...fixture.nativeElement.querySelectorAll(".chat-message p"),
    ].map((node: unknown) => (node as HTMLElement).textContent);
    expect(displayed).toEqual([
      "Resume las últimas ejecuciones",
      "Ejecución run-1 completada",
    ]);
    expect(component.message.value).toBe("");
    expect(conversation).toHaveBeenCalledOnce();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Resume las últimas ejecuciones",
      false,
    );
  });

  it("muestra el error, conserva el texto y permite reintentar en la misma conversación", async () => {
    const { component, fixture, conversation, message } = createAgent(
      true,
      true,
    );
    message.mockReturnValueOnce(
      throwError(() => ({
        status: 503,
        error: { detail: "Renueva tu sesión local con --login" },
      })),
    );
    const form: HTMLFormElement =
      fixture.nativeElement.querySelector("form.chat-input");
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    await vi.waitFor(() => expect(component.error()).toContain("--login"));
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector("[role=alert]").textContent,
    ).toContain("--login");
    expect(component.message.value).toBe("Consolida el periodo");
    expect(component.message.enabled).toBe(true);
    expect(component.allowActions.value).toBe(false);
    expect(component.busy()).toBe(false);
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    await vi.waitFor(() => expect(component.messages()).toHaveLength(2));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("[role=alert]")).toBeNull();
    expect(message).toHaveBeenNthCalledWith(
      1,
      "conversation-1",
      "Consolida el periodo",
      true,
    );
    expect(message).toHaveBeenNthCalledWith(
      2,
      "conversation-1",
      "Consolida el periodo",
      false,
    );
    expect(conversation).toHaveBeenCalledOnce();
  });
});

describe("autorización por consulta del asistente", () => {
  it("envía acciones únicamente cuando el entorno y el rol lo permiten y reinicia el consentimiento", async () => {
    const { component, message } = createAgent(true, true);
    await component.send();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Consolida el periodo",
      true,
    );
    expect(component.allowActions.value).toBe(false);
  });
  it("no habilita acciones si falta el rol aunque el control estuviera marcado", async () => {
    const { component, message } = createAgent(true, false);
    await component.send();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Consolida el periodo",
      false,
    );
  });
  it("respeta el bloqueo del entorno aunque el usuario tenga permisos", async () => {
    const { component, message } = createAgent(false, true);
    await component.send();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Consolida el periodo",
      false,
    );
  });
});
