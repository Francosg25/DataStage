import { TestBed } from "@angular/core/testing";
import { provideRouter } from "@angular/router";
import { of, Subject, throwError } from "rxjs";
import { HttpResponse } from "@angular/common/http";
import { MatDialog, MatDialogRef } from "@angular/material/dialog";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { AgentReply } from "../core/models";
import { Auth } from "../core/auth";
import { Agent } from "./agent";
import { ConversationDeleteDialog } from "./conversation-delete-dialog";
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
  const deleteConversation = vi.fn<Api["deleteConversation"]>(() =>
    of(undefined),
  );
  const agentFiles = vi.fn<Api["agentFiles"]>(() =>
    of({
      items: [],
      maxFiles: 5,
      maxFileBytes: 10485760,
      maxTotalBytes: 26214400,
    }),
  );
  const uploadAgentFile = vi.fn<Api["uploadAgentFile"]>();
  const removeAgentFile = vi.fn<Api["removeAgentFile"]>(() => of(undefined));
  const downloadAgentFile = vi.fn<Api["downloadAgentFile"]>();
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
          deleteConversation,
          agentFiles,
          uploadAgentFile,
          removeAgentFile,
          downloadAgentFile,
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
    deleteConversation,
    agentFiles,
    uploadAgentFile,
    removeAgentFile,
    downloadAgentFile,
    dialog: fixture.debugElement.injector.get(MatDialog),
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
  it("adjunta desde el clip, conserva el texto, muestra el archivo y permite retirarlo", async () => {
    const {
      component,
      fixture,
      uploadAgentFile,
      removeAgentFile,
      conversation,
      message,
    } = createAgent(false, false);
    const pending = new Subject<any>();
    uploadAgentFile.mockReturnValue(pending);
    const file = new File(["Name,Amount\nAlpha,10"], "vendors.csv", {
      type: "text/csv",
    });
    const input: HTMLInputElement =
      fixture.nativeElement.querySelector("input[type=file]");
    const click = vi.spyOn(input, "click").mockImplementation(() => {});
    fixture.nativeElement.querySelector(".attach-button").click();
    expect(click).toHaveBeenCalledOnce();
    Object.defineProperty(input, "files", {
      value: [file],
      configurable: true,
    });
    input.dispatchEvent(new Event("change"));
    await vi.waitFor(() =>
      expect(uploadAgentFile).toHaveBeenCalledWith("conversation-1", file),
    );
    fixture.detectChanges();
    expect(component.interacting()).toBe(true);
    expect(
      fixture.nativeElement.querySelector(".attachment-reading").textContent,
    ).toContain("vendors.csv");
    expect(message).not.toHaveBeenCalled();
    const uploaded = {
      fileId: "file-1",
      name: file.name,
      format: "csv",
      sizeBytes: file.size,
      sha256: "abc",
      createdAt: "2026-10-22T00:00:00Z",
      complete: true,
      warnings: [],
      sheets: [
        {
          name: "CSV",
          headers: ["Name", "Amount"],
          types: ["text", "number"],
          rows: 1,
        },
      ],
    };
    pending.next(uploaded);
    pending.complete();
    await vi.waitFor(() => expect(component.uploading()).toBe(""));
    fixture.detectChanges();
    expect(component.message.value).toBe("Consolida el periodo");
    expect(
      fixture.nativeElement.querySelector(".source-name strong").textContent,
    ).toBe("vendors.csv");
    fixture.nativeElement.querySelector(".remove-source").click();
    await vi.waitFor(() => expect(component.sourceFiles()).toEqual([]));
    expect(removeAgentFile).toHaveBeenCalledWith("conversation-1", "file-1");
    expect(conversation).toHaveBeenCalledOnce();
  });

  it("rechaza formatos y tamaños no admitidos antes de cargar y muestra controles en inglés", async () => {
    const { component, fixture, uploadAgentFile } = createAgent(false, false);
    component.i18n.set("en");
    fixture.detectChanges();
    expect(
      fixture.nativeElement
        .querySelector(".attach-button")
        .getAttribute("aria-label"),
    ).toBe("Attach files");
    const input: HTMLInputElement =
      fixture.nativeElement.querySelector("input[type=file]");
    Object.defineProperty(input, "files", {
      value: [new File(["x"], "program.exe")],
      configurable: true,
    });
    await component.attach({ target: input } as unknown as Event);
    expect(component.error()).toContain("Attach XLSX");
    const large = new File(["x"], "large.xlsx");
    Object.defineProperty(large, "size", { value: 10485761 });
    Object.defineProperty(input, "files", {
      value: [large],
      configurable: true,
    });
    await component.attach({ target: input } as unknown as Event);
    expect(component.error()).toContain("10 MiB");
    expect(uploadAgentFile).not.toHaveBeenCalled();
  });

  it("conserva los archivos ya cargados ante un error y recupera los adjuntos al abrir el historial", async () => {
    const {
      component,
      fixture,
      uploadAgentFile,
      agentFiles,
      conversationMessages,
    } = createAgent(false, false);
    const uploaded = {
      fileId: "f",
      name: "source.pdf",
      format: "pdf",
      sizeBytes: 100,
      sha256: "abc",
      createdAt: "2026-10-22T00:00:00Z",
      complete: true,
      warnings: ["pdf_requires_ocr"],
      sheets: [
        {
          name: "Pages",
          headers: ["Page", "Text"],
          types: ["number", "text"],
          rows: 1,
        },
      ],
    };
    component.sourceFiles.set([uploaded]);
    uploadAgentFile.mockReturnValue(
      throwError(() => ({ error: { detail: "Archivo no válido" } })),
    );
    const input: HTMLInputElement =
      fixture.nativeElement.querySelector("input[type=file]");
    Object.defineProperty(input, "files", {
      value: [new File(["x"], "bad.csv")],
      configurable: true,
    });
    await component.attach({ target: input } as unknown as Event);
    expect(component.sourceFiles()).toEqual([uploaded]);
    expect(component.message.value).toBe("Consolida el periodo");
    component.newConversation();
    expect(component.sourceFiles()).toEqual([]);
    agentFiles.mockReturnValue(
      of({
        items: [uploaded],
        maxFiles: 5,
        maxFileBytes: 10485760,
        maxTotalBytes: 26214400,
      }),
    );
    conversationMessages.mockReturnValue(
      of({
        items: [{ role: "user", text: "Review PDF", sourceFiles: [uploaded] }],
        total: 1,
        historyLimited: false,
      }),
    );
    await component.openConversation("saved");
    fixture.detectChanges();
    expect(component.sourceFiles()).toEqual([uploaded]);
    expect(
      fixture.nativeElement.querySelector(".file-warning").textContent,
    ).toContain("OCR");
    expect(
      fixture.nativeElement.querySelector(".message-source-files").textContent,
    ).toContain("source.pdf");
  });
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

describe("eliminación de conversaciones", () => {
  it("pide confirmación, permite cancelar y conserva los mensajes", async () => {
    const { component, fixture, deleteConversation } = createAgent(
      false,
      false,
    );
    component.conversationId.set("saved-chat");
    component.messages.set([{ role: "assistant", text: "Keep this" }]);
    fixture.detectChanges();
    const button: HTMLButtonElement = fixture.nativeElement.querySelector(
      ".delete-conversation",
    );
    button.click();
    TestBed.tick();
    await fixture.whenStable();
    await vi.waitFor(() =>
      expect(document.querySelector("mat-dialog-container")).not.toBeNull(),
    );
    expect(deleteConversation).not.toHaveBeenCalled();
    expect(
      document.querySelector("mat-dialog-container")!.textContent,
    ).toContain("Los meses cargados");
    (document.querySelector("[data-cancel]") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(component.confirmingDelete()).toBe(false));
    expect(deleteConversation).not.toHaveBeenCalled();
    expect(component.messages()[0].text).toBe("Keep this");
  });

  it("borra únicamente la conversación confirmada y bloquea envíos duplicados durante la eliminación", async () => {
    const {
      component,
      fixture,
      deleteConversation,
      conversations,
      message,
      dialog,
    } = createAgent(false, false);
    component.conversationId.set("saved-chat");
    component.messages.set([{ role: "assistant", text: "Saved answer" }]);
    const remaining = {
      id: "other-chat",
      title: "Other",
      createdAt: "2026-01-01",
      lastMessageAt: "2026-01-01",
    };
    component.conversations.set([
      { ...remaining, id: "saved-chat" },
      remaining,
    ]);
    conversations.mockReturnValue(of({ items: [remaining] }));
    const open = vi.spyOn(dialog, "open").mockReturnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<ConversationDeleteDialog>);
    const pending = new Subject<void>();
    deleteConversation.mockReturnValue(pending);
    const deleting = component.deleteConversation();
    await vi.waitFor(() =>
      expect(deleteConversation).toHaveBeenCalledWith("saved-chat"),
    );
    fixture.detectChanges();
    expect(component.deleting()).toBe(true);
    expect(
      fixture.nativeElement.querySelector("button[type=submit]").disabled,
    ).toBe(true);
    await component.send();
    await component.deleteConversation();
    component.newConversation();
    expect(component.conversationId()).toBe("saved-chat");
    expect(message).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledOnce();
    pending.next();
    pending.complete();
    await deleting;
    expect(component.conversationId()).toBeUndefined();
    expect(component.messages()).toEqual([]);
    expect(component.conversations()).toEqual([remaining]);
    expect(component.deleting()).toBe(false);
  });

  it("conserva el historial y muestra el error si el servidor rechaza el borrado", async () => {
    const { component, deleteConversation, dialog } = createAgent(false, false);
    component.conversationId.set("saved-chat");
    component.messages.set([{ role: "assistant", text: "Saved answer" }]);
    vi.spyOn(dialog, "open").mockReturnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<ConversationDeleteDialog>);
    deleteConversation.mockReturnValue(
      throwError(() => ({
        status: 503,
        error: { detail: "Reintenta más tarde" },
      })),
    );
    await component.deleteConversation();
    expect(component.conversationId()).toBe("saved-chat");
    expect(component.messages()[0].text).toBe("Saved answer");
    expect(component.error()).toContain("Reintenta");
    expect(component.deleting()).toBe(false);
  });
});

describe("lectura y escritura del chat", () => {
  it("abre un recuerdo revisable y muestra cuánto contexto personal se incluyó en la respuesta", async () => {
    const { component, fixture, dialog, message } = createAgent(false, false);
    const closed = new Subject<undefined>();
    const open = vi.spyOn(dialog, "open").mockReturnValue({
      afterClosed: () => closed,
    } as unknown as MatDialogRef<unknown>);
    const reviewing = component.openMemory("Prefiero USD");
    expect(open.mock.calls[0][1]).toMatchObject({ data: "Prefiero USD" });
    expect(component.managingMemory()).toBe(true);
    await component.send();
    expect(message).not.toHaveBeenCalled();
    closed.next(undefined);
    closed.complete();
    await reviewing;
    message.mockReturnValue(
      of({ message: "Reporte listo", evidence: [], memoryContextCount: 2 }),
    );
    await component.send();
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(".memory-context").textContent,
    ).toContain("Contexto personal · 2");
  });
  it("presenta los controles y la confirmación en inglés sin enviar consultas al modelo", async () => {
    const { component, fixture, deleteConversation, message } = createAgent(
      false,
      false,
    );
    component.i18n.set("en");
    component.conversationId.set("saved-chat");
    component.message.reset();
    fixture.detectChanges();
    const button: HTMLButtonElement = fixture.nativeElement.querySelector(
      ".delete-conversation",
    );
    expect(button.getAttribute("aria-label")).toBe("Delete conversation");
    expect(
      fixture.nativeElement.querySelector("textarea").placeholder,
    ).toContain("Ask about your data");
    expect(
      fixture.nativeElement.querySelector("button[type=submit]").disabled,
    ).toBe(true);
    button.click();
    TestBed.tick();
    await fixture.whenStable();
    expect(
      document.querySelector("mat-dialog-container")!.textContent,
    ).toContain("Uploaded months and source data will be kept");
    (document.querySelector("[data-cancel]") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(component.confirmingDelete()).toBe(false));
    expect(deleteConversation).not.toHaveBeenCalled();
    expect(message).not.toHaveBeenCalled();
  });

  it("envía con Enter, conserva Shift+Enter y no interrumpe un teclado en composición", async () => {
    const { component, fixture, message } = createAgent(false, false);
    const textarea: HTMLTextAreaElement =
      fixture.nativeElement.querySelector("textarea");
    for (const options of [{ shiftKey: true }, { isComposing: true }]) {
      const event = new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
        cancelable: true,
        ...options,
      });
      textarea.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(false);
    }
    expect(message).not.toHaveBeenCalled();
    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });
    textarea.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    await vi.waitFor(() => expect(message).toHaveBeenCalledOnce());
    expect(component.message.value).toBe("");
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector("mat-form-field")).toBeNull();
  });
});
