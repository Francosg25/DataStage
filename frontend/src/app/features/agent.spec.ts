import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of, Subject, throwError } from "rxjs";
import { HttpResponse } from "@angular/common/http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { AgentReply } from "../core/models";
import { Auth } from "../core/auth";
import { Agent } from "./agent";
function createAgent(enabled: boolean, permitted: boolean) {
  const message = vi
    .fn<Api["message"]>()
    .mockReturnValue(of({ message: "Consulta completada", evidence: [] }));
  const conversation = vi.fn<Api["conversation"]>(() =>
    of({ id: "conversation-1" }),
  );
  const conversations = vi.fn<Api["conversations"]>(() => of({ items: [] }));
  const conversationMessages = vi.fn<Api["conversationMessages"]>(() =>
    of({ items: [], total: 0, historyLimited: false }),
  );
  const agentArtifact = vi.fn<Api["agentArtifact"]>();
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      {
        provide: Api,
        useValue: {
          conversation,
          message,
          conversations,
          conversationMessages,
          agentArtifact,
        },
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
  return {
    component,
    fixture,
    conversation,
    message,
    conversations,
    conversationMessages,
    agentArtifact,
  };
}

afterEach(() => {
  localStorage.removeItem("datastage.language");
  TestBed.resetTestingModule();
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("envío del formulario del asistente", () => {
  it("evita la recarga, conserva la consulta durante la espera y muestra la respuesta", async () => {
    const { component, fixture, conversation, message } = createAgent(
      false,
      false,
    );
    const pending = new Subject<AgentReply>();
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
    expect(
      fixture.nativeElement.querySelector(".user-message p").textContent,
    ).toBe("Resume las últimas ejecuciones");
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

describe("archivos e historial del asistente", () => {
  it("recupera archivos y uso de tokens, presenta tablas y descarga por identidad del documento", async () => {
    const { component, fixture, conversationMessages, agentArtifact } =
      createAgent(false, false);
    const file = {
      documentId: "document-1",
      name: "May.xlsx",
      format: "xlsx" as const,
      sizeBytes: 2048,
      sha256: "hash",
      downloadUrl: "https://untrusted.invalid",
    };
    conversationMessages.mockReturnValue(
      of({
        items: [
          { role: "user", text: "Dame un resumen" },
          {
            role: "assistant",
            text: "**Resumen**\n\n| Mes | USD |\n| --- | --- |\n| Mayo | 150 |",
            attachments: [file],
            usage: {
              inputTokens: 100,
              outputTokens: 20,
              totalTokens: 120,
              modelCalls: 2,
            },
          },
        ],
        total: 2,
        historyLimited: false,
      }),
    );
    await component.openConversation("saved-conversation");
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("tbody td").textContent).toBe(
      "Mayo",
    );
    expect(
      fixture.nativeElement.querySelector(".chat-file").textContent,
    ).toContain("May.xlsx");
    expect(
      fixture.nativeElement.querySelector(".chat-usage").textContent,
    ).toContain("120 tokens");
    vi.useFakeTimers();
    const createObjectURL = vi.fn(() => "blob:assistant-download");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    agentArtifact.mockReturnValue(
      of(new HttpResponse({ body: new Blob(["test"]) })),
    );
    await component.download(file);
    expect(agentArtifact).toHaveBeenCalledWith(
      "saved-conversation",
      "document-1",
    );
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe(
      "May.xlsx",
    );
    vi.runOnlyPendingTimers();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:assistant-download");
    expect(component.downloading()).toBe("");
  });

  it("continúa la conversación elegida y permite comenzar otra sin perder el historial guardado", async () => {
    const { component, conversationMessages, conversation, message } =
      createAgent(false, false);
    conversationMessages.mockReturnValue(
      of({
        items: [{ role: "user", text: "Mayo de 2025" }],
        total: 1,
        historyLimited: false,
      }),
    );
    await component.openConversation("saved-conversation");
    component.message.setValue("Ahora también junio");
    await component.send();
    expect(conversation).not.toHaveBeenCalled();
    expect(message).toHaveBeenCalledWith(
      "saved-conversation",
      "Ahora también junio",
      false,
    );
    component.newConversation();
    expect(component.messages()).toEqual([]);
    component.message.setValue("Una consulta nueva");
    await component.send();
    expect(conversation).toHaveBeenCalledOnce();
  });

  it("indica cuando Azure no reporta el uso en lugar de presentar un costo cero", async () => {
    const { component, fixture, message } = createAgent(false, false);
    message.mockReturnValue(
      of({
        message: "Resultado",
        evidence: [],
        usage: {
          inputTokens: 0,
          outputTokens: 0,
          totalTokens: 0,
          modelCalls: 1,
          available: false,
        },
      }),
    );
    await component.send();
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(".chat-usage summary").textContent,
    ).toContain("No disponible");
    expect(
      fixture.nativeElement.querySelector(".chat-usage summary").textContent,
    ).not.toContain("0 tokens");
  });
});
