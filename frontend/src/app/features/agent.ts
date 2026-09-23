import { MatCheckboxModule } from "@angular/material/checkbox";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { ReactiveFormsModule, FormControl, Validators } from "@angular/forms";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatInputModule } from "@angular/material/input";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { firstValueFrom } from "rxjs";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { DataRow, errorText } from "../core/models";
import { Icon, DataTable } from "../shared/ui";
interface Message {
  role: "user" | "assistant";
  text: string;
  evidence?: DataRow[];
}
@Component({
  selector: "ds-agent",
  imports: [
    ReactiveFormsModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatProgressBarModule,
    Icon,
    DataTable,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow">MICROSOFT FOUNDRY</span>
        <h1>Tu asistente de datos</h1>
        <p>
          Consulta resultados y entiende las incidencias con evidencia de
          origen.
        </p>
      </div>
      <span class="subtle-tag">{{
        auth.config()?.foundryEnabled
          ? "Habilitado"
          : "Pendiente de configuración"
      }}</span>
    </div>
    @if (!auth.config()?.foundryEnabled) {
      <section class="panel disabled-agent">
        <div class="assistant-symbol"><ds-icon name="spark" /></div>
        <h2>El asistente estará aquí.</h2>
        <p>
          La conexión con Microsoft Foundry aún no está configurada en este
          entorno. Tu equipo de IT debe habilitar el servicio y sus
          credenciales.
        </p>
        <span class="note"
          >Puedes procesar archivos y consultar tus resultados desde los demás
          módulos.</span
        >
      </section>
    } @else {
      <section class="panel chat-panel">
        <div class="chat-body" aria-live="polite">
          @if (!messages().length) {
            <div class="chat-welcome">
              <div class="assistant-symbol"><ds-icon name="spark" /></div>
              <h2>¿Qué quieres conocer de tus datos?</h2>
              <p>
                Puedes preguntar por ejecuciones, incidencias o periodos
                publicados.
              </p>
              <div class="suggestion-grid">
                @for (prompt of prompts; track prompt) {
                  <button mat-stroked-button (click)="usePrompt(prompt)">
                    {{ prompt }}
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
                message.role === "user" ? "Tú" : "Asistente DataStage"
              }}</span>
              <p>{{ message.text }}</p>
              @if (message.evidence?.length) {
                <details>
                  <summary>
                    Ver evidencia ({{ message.evidence!.length }})
                  </summary>
                  <ds-data-table [rows]="message.evidence || []" />
                </details>
              }
            </article>
          }
          @if (busy()) {
            <mat-progress-bar
              mode="indeterminate"
              aria-label="El asistente está consultando la información"
            />
          }
        </div>
        @if (error()) {
          <div class="error-message" role="alert">{{ error() }}</div>
        }
        <form class="chat-input" (ngSubmit)="send()">
          <mat-form-field appearance="outline"
            ><mat-label>Escribe tu consulta</mat-label
            ><textarea
              matInput
              [formControl]="message"
              rows="2"
              maxlength="4000"
            ></textarea></mat-form-field
          ><button
            mat-flat-button
            type="submit"
            [disabled]="busy() || message.invalid"
          >
            <ds-icon name="arrow" /><span class="sr-only">Enviar mensaje</span>
          </button>
        </form>
        @if (canAct()) {
          <div class="chat-permission">
            <mat-checkbox [formControl]="allowActions"
              >Permitir que esta consulta inicie un consolidado o reproceso
              autorizado</mat-checkbox
            ><small>Se aplica únicamente al siguiente mensaje.</small>
          </div>
        }
        <div class="chat-disclaimer">
          <ds-icon name="shield" />El asistente utiliza tu identidad y los
          permisos de tu cuenta. Verifica la evidencia antes de tomar
          decisiones.
        </div>
      </section>
    }`,
})
export class Agent {
  api = inject(Api);
  auth = inject(Auth);
  destroy = inject(DestroyRef);
  message = new FormControl("", {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(4000)],
  });
  allowActions = new FormControl(false, { nonNullable: true });
  messages = signal<Message[]>([]);
  busy = signal(false);
  error = signal("");
  private conversationId?: string;
  prompts = [
    "¿Qué periodos están disponibles?",
    "Resume las últimas ejecuciones.",
    "¿Qué incidencias requieren revisión?",
  ];
  usePrompt(prompt: string) {
    this.message.setValue(prompt);
  }
  canAct() {
    return (
      !!this.auth.config()?.allowAgentCommands &&
      this.auth.hasRole("Operator", "Reprocessor", "Admin")
    );
  }
  async send() {
    const text = this.message.value.trim();
    if (!text || this.busy() || !this.auth.config()?.foundryEnabled) return;
    const allowActions = this.canAct() && this.allowActions.value;
    this.busy.set(true);
    this.message.disable({ emitEvent: false });
    this.allowActions.disable({ emitEvent: false });
    this.error.set("");
    try {
      if (!this.conversationId)
        this.conversationId = (
          await firstValueFrom(this.api.conversation())
        ).id;
      const response = await firstValueFrom(
        this.api.message(this.conversationId, text, allowActions),
      );
      this.messages.update((m) => [
        ...m,
        { role: "user", text },
        {
          role: "assistant",
          text: response.message,
          evidence: response.evidence,
        },
      ]);
      this.message.reset();
    } catch (e) {
      this.error.set(errorText(e));
    } finally {
      this.busy.set(false);
      this.message.enable({ emitEvent: false });
      this.allowActions.reset(false);
      this.allowActions.enable({ emitEvent: false });
    }
  }
}
