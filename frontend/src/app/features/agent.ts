import { TranslatePipe } from "../core/i18n";
import { MatCheckboxModule } from "@angular/material/checkbox";
import {
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  signal,
  viewChild,
} from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { ReactiveFormsModule, FormControl, Validators } from "@angular/forms";
import { TextFieldModule } from "@angular/cdk/text-field";
import { MatDialog, MatDialogModule } from "@angular/material/dialog";
import { ConversationDeleteDialog } from "./conversation-delete-dialog";
import { AgentMemoryDialog } from "./agent-memory-dialog";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { firstValueFrom } from "rxjs";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import {
  AgentAttachment,
  AgentChatMessage,
  AgentConversation,
  AgentSourceFile,
  AgentUpload,
  errorText,
} from "../core/models";
import { Icon, DataTable } from "../shared/ui";
import { AssistantText } from "../shared/assistant-text";
import { saveSupplierDownload } from "../shared/supplier-download";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { I18n } from "../core/i18n";
@Component({
  selector: "ds-agent",
  styleUrl: "./agent.scss",
  imports: [
    TranslatePipe,
    RouterLink,
    ReactiveFormsModule,
    MatCheckboxModule,
    TextFieldModule,
    MatDialogModule,
    MatButtonModule,
    MatProgressBarModule,
    Icon,
    DataTable,
    AssistantText,
  ],
  templateUrl: "./agent.html",
})
export class Agent {
  i18n = inject(I18n);
  private route = inject(ActivatedRoute, { optional: true });
  api = inject(Api);
  auth = inject(Auth);
  destroy = inject(DestroyRef);
  private document = inject(DOCUMENT);
  private dialog = inject(MatDialog);
  private chatBody = viewChild<ElementRef<HTMLDivElement>>("chatBody");
  message = new FormControl("", {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(4000)],
  });
  allowActions = new FormControl(false, { nonNullable: true });
  messages = signal<AgentChatMessage[]>([]);
  conversations = signal<AgentConversation[]>([]);
  conversationId = signal<string | undefined>(undefined);
  loadingHistory = signal(false);
  historyLimited = signal(false);
  pendingText = signal("");
  downloading = signal("");
  sourceFiles = signal<AgentUpload[]>([]);
  uploading = signal("");
  removingFile = signal("");
  busy = signal(false);
  deleting = signal(false);
  confirmingDelete = signal(false);
  managingMemory = signal(false);
  error = signal("");
  prompts = [
    "¿Qué periodos están disponibles?",
    "Resume las últimas ejecuciones.",
    "Crea un Excel del último mes publicado con pedimento, patente, aduana y fecha de pago.",
    "Genera un informe PDF con los KPI del último mes publicado en USD.",
  ];
  usePrompt(prompt: string) {
    this.message.setValue(this.i18n.t(prompt));
  }
  constructor() {
    const prompt = this.route?.snapshot.queryParamMap.get("prompt");
    if (prompt) this.message.setValue(prompt.slice(0, 4000));
    if (this.auth.config()?.foundryEnabled) {
      this.api
        .conversations()
        .pipe(takeUntilDestroyed(this.destroy))
        .subscribe({
          next: ({ items }) => {
            this.conversations.set(items);
            if (
              items.length &&
              !prompt &&
              !this.interacting() &&
              !this.conversationId() &&
              !this.messages().length
            )
              void this.openConversation(items[0].id);
          },
          error: (error) => this.error.set(errorText(error)),
        });
    }
    effect(() => {
      this.messages();
      this.pendingText();
      this.busy();
      const body = this.chatBody()?.nativeElement;
      if (body)
        queueMicrotask(() => {
          body.scrollTop = body.scrollHeight;
        });
    });
  }
  newConversation() {
    if (this.interacting()) return;
    this.conversationId.set(undefined);
    this.messages.set([]);
    this.sourceFiles.set([]);
    this.historyLimited.set(false);
    this.error.set("");
    this.message.reset();
    this.allowActions.reset(false);
  }
  async openConversation(id: string) {
    if (this.interacting()) return;
    if (!id) {
      this.newConversation();
      return;
    }
    this.loadingHistory.set(true);
    this.error.set("");
    try {
      const [history, files] = await Promise.all([
        firstValueFrom(this.api.conversationMessages(id)),
        firstValueFrom(this.api.agentFiles(id)),
      ]);
      this.conversationId.set(id);
      this.messages.set(history.items);
      this.sourceFiles.set(files.items);
      this.historyLimited.set(history.historyLimited);
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.loadingHistory.set(false);
    }
  }
  async download(file: AgentAttachment) {
    const id = this.conversationId();
    if (!id || this.downloading() || this.deleting() || this.confirmingDelete())
      return;
    this.downloading.set(file.documentId);
    this.error.set("");
    try {
      const response = await firstValueFrom(
        this.api.agentArtifact(id, file.documentId),
      );
      saveSupplierDownload(this.document, response, file.name);
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.downloading.set("");
    }
  }
  size(bytes: number) {
    return bytes >= 1048576
      ? `${(bytes / 1048576).toFixed(1)} MB`
      : `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
  }
  async attach(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files || []);
    input.value = "";
    if (
      !files.length ||
      this.interacting() ||
      !this.auth.config()?.foundryEnabled
    )
      return;
    if (
      files.length + this.sourceFiles().length > 5 ||
      files.some((file) => file.size > 10 * 1048576) ||
      files.reduce(
        (sum, file) => sum + file.size,
        this.sourceFiles().reduce((sum, file) => sum + file.sizeBytes, 0),
      ) >
        25 * 1048576
    ) {
      this.error.set(
        this.i18n.choose(
          "Puedes adjuntar 5 archivos: 10 MiB por archivo y 25 MiB en total.",
          "Attach up to 5 files: 10 MiB each and 25 MiB in total.",
        ),
      );
      return;
    }
    if (files.some((file) => !/\.(xlsx|csv|pdf|docx|pptx)$/i.test(file.name))) {
      this.error.set(
        this.i18n.choose(
          "Adjunta archivos XLSX, CSV, PDF, DOCX o PPTX.",
          "Attach XLSX, CSV, PDF, DOCX or PPTX files.",
        ),
      );
      return;
    }
    this.uploading.set(files[0].name);
    this.error.set("");
    try {
      if (!this.conversationId())
        this.conversationId.set(
          (await firstValueFrom(this.api.conversation())).id,
        );
      for (const file of files) {
        this.uploading.set(file.name);
        const result = await firstValueFrom(
          this.api.uploadAgentFile(this.conversationId()!, file),
        );
        this.sourceFiles.update((items) => [
          ...items.filter((item) => item.fileId !== result.fileId),
          result,
        ]);
      }
      const list = await firstValueFrom(this.api.conversations());
      this.conversations.set(list.items);
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.uploading.set("");
    }
  }
  async removeFile(file: AgentUpload) {
    const id = this.conversationId();
    if (!id || this.interacting() || this.downloading()) return;
    this.removingFile.set(file.fileId);
    this.error.set("");
    try {
      await firstValueFrom(this.api.removeAgentFile(id, file.fileId));
      this.sourceFiles.update((items) =>
        items.filter((item) => item.fileId !== file.fileId),
      );
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.removingFile.set("");
    }
  }
  fileAvailable(file: AgentSourceFile) {
    return this.sourceFiles().some((item) => item.fileId === file.fileId);
  }
  async downloadSource(file: AgentSourceFile) {
    const id = this.conversationId();
    if (
      !id ||
      this.interacting() ||
      this.downloading() ||
      !this.fileAvailable(file)
    )
      return;
    this.downloading.set(file.fileId);
    this.error.set("");
    try {
      const response = await firstValueFrom(
        this.api.downloadAgentFile(id, file.fileId),
      );
      saveSupplierDownload(this.document, response, file.name);
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.downloading.set("");
    }
  }
  fileNote(file: AgentUpload) {
    if (file.warnings.includes("pdf_some_pages_without_text"))
      return this.i18n.choose(
        "Hay páginas sin texto detectado",
        "Some pages have no detected text",
      );
    if (file.warnings.includes("pdf_requires_ocr"))
      return this.i18n.choose(
        "PDF sin texto: requiere OCR",
        "PDF has no text: OCR required",
      );
    if (file.warnings.includes("formulas_preserved_as_text"))
      return this.i18n.choose(
        "Fórmulas conservadas como texto",
        "Formulas preserved as text",
      );
    if (file.format === "docx" || file.format === "pptx")
      return this.i18n.choose(
        "Lectura de texto y tablas",
        "Text and table reading",
      );
    return `${file.sheets.length} ${this.i18n.choose("hojas", "sheets")} · ${file.sheets.reduce((sum, page) => sum + page.rows, 0).toLocaleString()} ${this.i18n.choose("filas", "rows")}`;
  }
  interacting() {
    return (
      this.busy() ||
      this.loadingHistory() ||
      this.deleting() ||
      this.confirmingDelete() ||
      this.managingMemory() ||
      !!this.uploading() ||
      !!this.removingFile()
    );
  }
  artifactUrls(message: AgentChatMessage) {
    return (message.attachments || []).map((file) => file.downloadUrl);
  }
  filename(name: string) {
    return name.replace(/_/g, " ");
  }
  keydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void this.send();
    }
  }
  async deleteConversation() {
    const id = this.conversationId();
    if (!id || this.interacting() || this.downloading()) return;
    const title =
      this.conversations().find((item) => item.id === id)?.title ||
      this.i18n.choose("Esta conversación", "This conversation");
    this.confirmingDelete.set(true);
    let confirmed = false;
    try {
      confirmed = await firstValueFrom(
        this.dialog
          .open(ConversationDeleteDialog, {
            data: title,
            width: "460px",
            maxWidth: "calc(100vw - 32px)",
            autoFocus: "[data-cancel]",
          })
          .afterClosed(),
      );
    } finally {
      this.confirmingDelete.set(false);
    }
    if (!confirmed || this.conversationId() !== id || this.interacting())
      return;
    this.deleting.set(true);
    this.error.set("");
    try {
      await firstValueFrom(this.api.deleteConversation(id));
      this.conversations.update((items) =>
        items.filter((item) => item.id !== id),
      );
      this.conversationId.set(undefined);
      this.messages.set([]);
      this.sourceFiles.set([]);
      this.historyLimited.set(false);
      this.message.reset();
      this.allowActions.reset(false);
      this.api
        .conversations()
        .pipe(takeUntilDestroyed(this.destroy))
        .subscribe({
          next: ({ items }) => this.conversations.set(items),
          error: () => {},
        });
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.deleting.set(false);
    }
  }
  async openMemory(text = "") {
    if (this.interacting() || this.downloading()) return;
    this.managingMemory.set(true);
    try {
      await firstValueFrom(
        this.dialog
          .open(AgentMemoryDialog, {
            data: text,
            width: "640px",
            maxWidth: "calc(100vw - 24px)",
          })
          .afterClosed(),
      );
    } finally {
      this.managingMemory.set(false);
    }
  }
  canAct() {
    return (
      !!this.auth.config()?.allowAgentCommands &&
      this.auth.hasRole("Operator", "Reprocessor", "Admin")
    );
  }
  async send() {
    const text = this.message.value.trim();
    if (!text || this.interacting() || !this.auth.config()?.foundryEnabled)
      return;
    const allowActions = this.canAct() && this.allowActions.value;
    this.busy.set(true);
    this.pendingText.set(text);
    this.message.disable({ emitEvent: false });
    this.allowActions.disable({ emitEvent: false });
    this.error.set("");
    try {
      if (!this.conversationId())
        this.conversationId.set(
          (await firstValueFrom(this.api.conversation())).id,
        );
      const response = await firstValueFrom(
        this.api.message(this.conversationId()!, text, allowActions),
      );
      this.messages.update((m) => [
        ...m,
        { role: "user", text, sourceFiles: response.sourceFiles },
        {
          role: "assistant",
          text: response.message,
          evidence: response.evidence,
          attachments: response.attachments,
          usage: response.usage,
          memoryContextCount: response.memoryContextCount,
        },
      ]);
      this.message.reset();
      this.api
        .conversations()
        .pipe(takeUntilDestroyed(this.destroy))
        .subscribe({
          next: ({ items }) => this.conversations.set(items),
          error: () => {},
        });
    } catch (e) {
      this.error.set(errorText(e));
    } finally {
      this.busy.set(false);
      this.pendingText.set("");
      this.message.enable({ emitEvent: false });
      this.allowActions.reset(false);
      this.allowActions.enable({ emitEvent: false });
    }
  }
}
