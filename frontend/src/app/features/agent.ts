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
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatInputModule } from "@angular/material/input";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { firstValueFrom } from "rxjs";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import {
  AgentAttachment,
  AgentChatMessage,
  AgentConversation,
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
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatProgressBarModule,
    Icon,
    DataTable,
    AssistantText,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow"> {{ "MICROSOFT FOUNDRY" | t }} </span>
        <h1>{{ "Tu asistente de datos" | t }}</h1>
        <p>
          {{
            i18n.choose(
              "Consulta tus datos y crea reportes y Excel desde esta conversación.",
              "Explore your data and create reports and Excel files in this conversation."
            )
          }}
        </p>
      </div>
      <span class="subtle-tag">{{
        (auth.config()?.foundryEnabled
          ? "Habilitado"
          : "Pendiente de configuración"
        ) | t
      }}</span>
    </div>
    <a
      routerLink="/foundry-guide"
      class="text-link"
      style="display:inline-flex;gap:8px;margin-bottom:20px"
      ><ds-icon name="file" />{{
        i18n.choose(
          "Guía de configuración de Azure Foundry",
          "Azure Foundry setup guide"
        )
      }}</a
    >
    @if (!auth.config()?.foundryEnabled) {
      <section class="panel disabled-agent">
        <div class="assistant-symbol"><ds-icon name="spark" /></div>
        <h2>{{ "El asistente estará aquí." | t }}</h2>
        <p>
          {{
            "La conexión con Microsoft Foundry aun no esta configurada en este entorno."
              | t
          }}
        </p>
        <span class="note">
          {{
            "Puedes procesar archivos y consultar tus resultados desde los demás módulos."
              | t
          }}
        </span>
      </section>
    } @else {
      <section class="panel chat-panel">
        <div class="chat-toolbar">
          <label>
            {{ i18n.choose("Conversaciones", "Conversations") }}
            <select
              [value]="conversationId() || ''"
              (change)="openConversation($any($event.target).value)"
              [disabled]="busy() || loadingHistory()"
              aria-label="Conversation"
            >
              <option value="">
                {{ i18n.choose("Nueva conversación", "New conversation") }}
              </option>
              @for (conversation of conversations(); track conversation.id) {
                <option [value]="conversation.id">
                  {{
                    conversation.title ||
                      i18n.choose("Sin mensajes", "No messages")
                  }}
                </option>
              }
            </select>
          </label>
          <button
            mat-stroked-button
            type="button"
            (click)="newConversation()"
            [disabled]="busy() || loadingHistory()"
          >
            {{ i18n.choose("Nueva conversación", "New conversation") }}
          </button>
        </div>
        <div
          class="chat-body"
          #chatBody
          aria-live="polite"
          [attr.aria-busy]="busy() || loadingHistory()"
        >
          @if (loadingHistory()) {
            <p role="status">
              {{
                i18n.choose(
                  "Recuperando conversación…",
                  "Loading conversation…"
                )
              }}
            </p>
          }
          @if (historyLimited()) {
            <p class="history-note">
              {{
                i18n.choose(
                  "Mostrando los últimos 100 mensajes. El modelo recibe los últimos 20 para esta consulta.",
                  "Showing the latest 100 messages. The model receives the latest 20 for this question."
                )
              }}
            </p>
          }
          @if (!messages().length) {
            <div class="chat-welcome">
              <div class="assistant-symbol"><ds-icon name="spark" /></div>
              <h2>{{ "¿Qué quieres conocer de tus datos?" | t }}</h2>
              <p>
                {{
                  i18n.choose(
                    "Pregunta por periodos, compara métricas o pide un archivo con las columnas que necesitas.",
                    "Ask about periods, compare metrics or request a file with the columns you need."
                  )
                }}
              </p>
              <div class="suggestion-grid">
                @for (prompt of prompts; track prompt) {
                  <button mat-stroked-button (click)="usePrompt(prompt)">
                    {{ prompt | t }}
                  </button>
                }
              </div>
            </div>
          }
          @for (message of messages(); track $index) {
            <article
              class="chat-message"
              [class.user-message]="message.role === 'user'"
            >
              <span class="chat-role">{{
                (message.role === "user" ? "Tú" : "Asistente DataStage") | t
              }}</span>
              @if (message.role === "assistant") {
                <ds-assistant-text [text]="message.text" />
              } @else {
                <p>{{ message.text }}</p>
              }
              @if (message.attachments?.length) {
                <div class="chat-attachments">
                  @for (file of message.attachments; track file.documentId) {
                    <button
                      mat-stroked-button
                      type="button"
                      class="chat-file"
                      (click)="download(file)"
                      [disabled]="downloading() === file.documentId"
                    >
                      <ds-icon name="file" />
                      <span
                        ><strong>{{ file.name }}</strong
                        ><small
                          >{{ file.format.toUpperCase() }} ·
                          {{ size(file.sizeBytes) }} ·
                          {{ i18n.choose("Descargar", "Download") }}</small
                        ></span
                      >
                    </button>
                  }
                </div>
              }
              @if (message.evidence?.length) {
                <details>
                  <summary>
                    {{ "Ver evidencia (" | t }}
                    {{ message.evidence!.length | t }})
                  </summary>
                  <ds-data-table [rows]="message.evidence || []" />
                </details>
              }
              @if (message.usage; as usage) {
                <details class="chat-usage">
                  <summary>
                    {{ i18n.choose("Uso del modelo", "Model usage") }} ·
                    {{
                      usage.available === false
                        ? i18n.choose("No disponible", "Not available")
                        : usage.totalTokens.toLocaleString() + " tokens"
                    }}
                  </summary>
                  <p>
                    {{ i18n.choose("Entrada", "Input") }}:
                    {{ usage.inputTokens.toLocaleString() }} ·
                    {{ i18n.choose("Salida", "Output") }}:
                    {{ usage.outputTokens.toLocaleString() }} ·
                    {{ i18n.choose("Llamadas", "Calls") }}:
                    {{ usage.modelCalls }}.
                  </p>
                  <p>
                    {{
                      i18n.choose(
                        "Uso reportado por Azure para esta respuesta; los costos se consultan en Azure Cost Management.",
                        "Usage reported by Azure for this response; check costs in Azure Cost Management."
                      )
                    }}
                  </p>
                </details>
              }
            </article>
          }
          @if (pendingText()) {
            <article class="chat-message user-message">
              <span class="chat-role">{{ "Tú" | t }}</span>
              <p>{{ pendingText() }}</p>
            </article>
          }
          @if (busy()) {
            <p class="assistant-working" role="status">
              {{
                i18n.choose(
                  "Consultando fuentes y preparando tu respuesta…",
                  "Checking sources and preparing your answer…"
                )
              }}
            </p>
            <mat-progress-bar
              mode="indeterminate"
              [attr.aria-label]="
                'El asistente está consultando la información' | t
              "
            />
          }
        </div>
        @if (error()) {
          <div class="error-message" role="alert">{{ error() | t }}</div>
        }
        <form class="chat-input" (submit)="$event.preventDefault(); send()">
          <mat-form-field appearance="outline"
            ><mat-label> {{ "Escribe tu consulta" | t }} </mat-label
            ><textarea
              matInput
              [formControl]="message"
              rows="2"
              maxlength="4000"
            ></textarea></mat-form-field
          ><button
            mat-flat-button
            type="submit"
            [disabled]="busy() || loadingHistory() || message.invalid"
          >
            <ds-icon name="arrow" /><span class="sr-only">
              {{ "Enviar mensaje" | t }}
            </span>
          </button>
        </form>
        @if (canAct()) {
          <div class="chat-permission">
            <mat-checkbox [formControl]="allowActions">
              {{
                "Permitir que esta consulta inicie un consolidado o reproceso autorizado"
                  | t
              }} </mat-checkbox
            ><small>
              {{ "Se aplica únicamente al siguiente mensaje." | t }}
            </small>
          </div>
        }
        <div class="chat-disclaimer">
          <ds-icon name="shield" />
          {{
            "El asistente utiliza tu identidad y los permisos de tu cuenta. Verifica la evidencia antes de tomar decisiones."
              | t
          }}
        </div>
      </section>
    }`,
})
export class Agent {
  i18n = inject(I18n);
  private route = inject(ActivatedRoute, { optional: true });
  api = inject(Api);
  auth = inject(Auth);
  destroy = inject(DestroyRef);
  private document = inject(DOCUMENT);
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
  busy = signal(false);
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
              !this.busy() &&
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
    if (this.busy() || this.loadingHistory()) return;
    this.conversationId.set(undefined);
    this.messages.set([]);
    this.historyLimited.set(false);
    this.error.set("");
  }
  async openConversation(id: string) {
    if (this.busy() || this.loadingHistory()) return;
    if (!id) {
      this.newConversation();
      return;
    }
    this.loadingHistory.set(true);
    this.error.set("");
    try {
      const history = await firstValueFrom(this.api.conversationMessages(id));
      this.conversationId.set(id);
      this.messages.set(history.items);
      this.historyLimited.set(history.historyLimited);
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.loadingHistory.set(false);
    }
  }
  async download(file: AgentAttachment) {
    const id = this.conversationId();
    if (!id || this.downloading()) return;
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
  canAct() {
    return (
      !!this.auth.config()?.allowAgentCommands &&
      this.auth.hasRole("Operator", "Reprocessor", "Admin")
    );
  }
  async send() {
    const text = this.message.value.trim();
    if (
      !text ||
      this.busy() ||
      this.loadingHistory() ||
      !this.auth.config()?.foundryEnabled
    )
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
        { role: "user", text },
        {
          role: "assistant",
          text: response.message,
          evidence: response.evidence,
          attachments: response.attachments,
          usage: response.usage,
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
