import { Component, DestroyRef, inject, signal } from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import {
  FormArray,
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from "@angular/forms";
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from "@angular/material/dialog";
import { MatButtonModule } from "@angular/material/button";
import { MatCheckboxModule } from "@angular/material/checkbox";
import { firstValueFrom } from "rxjs";
import { Api } from "../core/api";
import { I18n, TranslatePipe } from "../core/i18n";
import { AgentMemoryItem, AgentMemoryProfile, errorText } from "../core/models";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-agent-memory-dialog",
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatCheckboxModule,
    TranslatePipe,
    Icon,
  ],
  template: `
    <h2 mat-dialog-title>
      <ds-icon name="bookmark" />{{
        i18n.choose("Memoria personal", "Personal memory")
      }}
    </h2>
    <mat-dialog-content>
      <p class="memory-intro">
        {{
          i18n.choose(
            "Guarda preferencias para usarlas en otras conversaciones. Tú decides qué recordar.",
            "Save preferences to use in other conversations. You decide what to remember."
          )
        }}
      </p>
      @if (loading()) {
        <p role="status">
          {{ i18n.choose("Cargando memoria…", "Loading memory…") }}
        </p>
      } @else if (!loadFailed()) {
        <mat-checkbox [formControl]="enabled">{{
          i18n.choose(
            "Usar mis memorias en los chats",
            "Use my memories in chats"
          )
        }}</mat-checkbox>
        <div class="memory-list">
          @for (note of notes.controls; track note; let index = $index) {
            <section class="memory-note" [formGroup]="note">
              <div class="note-heading">
                <label [for]="'memory-title-' + index">{{
                  i18n.choose("Título", "Title")
                }}</label
                ><button
                  mat-icon-button
                  type="button"
                  (click)="remove(index)"
                  [disabled]="saving()"
                  [attr.aria-label]="
                    i18n.choose('Eliminar memoria: ', 'Delete memory: ') +
                    note.controls.title.value
                  "
                >
                  <ds-icon name="trash" />
                </button>
              </div>
              <input
                [id]="'memory-title-' + index"
                formControlName="title"
                maxlength="80"
                [readOnly]="saving()"
                [placeholder]="
                  i18n.choose(
                    'Ejemplo: Reporte mensual',
                    'Example: Monthly report'
                  )
                "
              />
              <label [for]="'memory-content-' + index">{{
                i18n.choose("Qué debe recordar", "What to remember")
              }}</label>
              <textarea
                [id]="'memory-content-' + index"
                formControlName="content"
                rows="3"
                maxlength="600"
                [readOnly]="saving()"
                [placeholder]="
                  i18n.choose(
                    'Ejemplo: Prefiero los reportes en USD y con una hoja de resumen por proveedor.',
                    'Example: I prefer reports in USD with a supplier summary sheet.'
                  )
                "
              ></textarea>
              @if (note.controls.content.value.length > 600) {
                <p class="memory-error">
                  {{
                    i18n.choose(
                      "Resume esta memoria a un máximo de 600 caracteres.",
                      "Shorten this memory to 600 characters or fewer."
                    )
                  }}
                </p>
              }
            </section>
          } @empty {
            <div class="memory-empty">
              <ds-icon name="bookmark" />
              <p>
                {{
                  i18n.choose(
                    "Aún no has guardado memorias.",
                    "You haven't saved any memories yet."
                  )
                }}
              </p>
              <span>{{
                i18n.choose(
                  "Puedes recordar moneda, columnas habituales o formatos de reporte.",
                  "Remember currency, usual columns or report formats."
                )
              }}</span>
            </div>
          }
        </div>
        <div class="memory-add">
          <button
            mat-stroked-button
            type="button"
            (click)="add()"
            [disabled]="saving() || notes.length >= maxItems()"
          >
            <ds-icon name="plus" />{{
              i18n.choose("Añadir memoria", "Add memory")
            }}</button
          ><small>{{ notes.length }} / {{ maxItems() }}</small>
        </div>
        @if (duplicateTitles()) {
          <p class="memory-error" role="alert">
            {{
              i18n.choose(
                "Usa un título distinto para cada memoria.",
                "Use a different title for each memory."
              )
            }}
          </p>
        }
        @if (characters() > maxCharacters()) {
          <p class="memory-error" role="alert">
            {{
              i18n.choose(
                "Reduce el texto: el límite conjunto es de 6,000 caracteres.",
                "Shorten the text: the combined limit is 6,000 characters."
              )
            }}
          </p>
        }
        <p class="memory-note-hint">
          {{
            i18n.choose(
              "Son preferencias personales: no cambian reglas fiscales ni datos originales. Borrar un chat conserva estas memorias; puedes eliminarlas aquí.",
              "These are personal preferences: they don't change tax rules or source data. Deleting a chat keeps these memories; you can remove them here."
            )
          }}
        </p>
      }
      @if (error()) {
        <p class="memory-error" role="alert">{{ error() | t }}</p>
      }
      @if (confirmClear()) {
        <div
          class="memory-confirm"
          role="group"
          [attr.aria-label]="
            i18n.choose(
              'Confirmar borrado de memoria',
              'Confirm memory deletion'
            )
          "
        >
          <p>
            {{
              i18n.choose(
                "¿Eliminar todas tus memorias? Los mensajes de tus chats se conservan.",
                "Delete all your memories? Your chat messages will be kept."
              )
            }}
          </p>
          <button
            mat-button
            type="button"
            (click)="confirmClear.set(false)"
            [disabled]="saving()"
          >
            {{ i18n.choose("Conservar", "Keep") }}</button
          ><button
            mat-button
            class="danger"
            type="button"
            (click)="clear()"
            [disabled]="saving()"
          >
            {{ i18n.choose("Sí, eliminar", "Yes, delete") }}
          </button>
        </div>
      }
    </mat-dialog-content>
    <mat-dialog-actions>
      @if (version() > 0 && !confirmClear()) {
        <button
          mat-button
          type="button"
          class="danger clear-memory"
          (click)="confirmClear.set(true)"
          [disabled]="saving() || loading()"
        >
          {{ i18n.choose("Borrar toda la memoria", "Clear all memory") }}
        </button>
      }
      <span class="actions-spacer"></span>
      <button
        mat-button
        type="button"
        [mat-dialog-close]="false"
        [disabled]="saving()"
      >
        {{ i18n.choose("Cancelar", "Cancel") }}
      </button>
      <button
        mat-flat-button
        type="button"
        (click)="save()"
        [disabled]="
          loading() ||
          saving() ||
          loadFailed() ||
          confirmClear() ||
          notes.invalid ||
          duplicateTitles() ||
          characters() > maxCharacters()
        "
      >
        {{
          saving()
            ? i18n.choose("Guardando…", "Saving…")
            : i18n.choose("Guardar", "Save")
        }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    h2 {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    h2 ds-icon {
      color: #318471;
    }
    .memory-intro {
      font-size: 14px;
      line-height: 1.65;
      margin: 0 0 16px;
    }
    .memory-list {
      display: grid;
      gap: 14px;
      margin: 16px 0;
    }
    .memory-note {
      display: grid;
      gap: 7px;
      background: #f8fbfa;
      border: 1px solid #dde9e5;
      border-radius: 12px;
      padding: 14px;
    }
    .note-heading {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .note-heading button {
      width: 30px;
      height: 30px;
      padding: 5px;
      color: #8a6267;
    }
    .note-heading ds-icon {
      width: 16px;
      height: 16px;
    }
    label {
      font-size: 12px;
      color: #526c74;
      font-weight: 600;
    }
    input,
    textarea {
      min-width: 0;
      width: 100%;
      box-sizing: border-box;
      padding: 10px 12px;
      border: 1px solid #ceded9;
      border-radius: 8px;
      font: inherit;
      font-size: 13px;
      color: #2c4851;
      background: #fff;
    }
    textarea {
      resize: vertical;
      line-height: 1.65;
    }
    input:focus,
    textarea:focus {
      outline: 2px solid #a4d8c9;
      outline-offset: 1px;
    }
    .memory-add {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .memory-add ds-icon {
      width: 16px;
      height: 16px;
      margin-right: 6px;
      vertical-align: middle;
    }
    small,
    .memory-note-hint {
      font-size: 11px;
      color: #71868d;
      line-height: 1.65;
    }
    .memory-note-hint {
      margin: 18px 0 0;
    }
    .memory-empty {
      text-align: center;
      padding: 24px 12px;
      border: 1px dashed #d5e3df;
      border-radius: 12px;
      font-size: 13px;
      color: #627b82;
    }
    .memory-empty ds-icon {
      color: #5e9a87;
    }
    .memory-empty p {
      margin: 10px 0 4px;
    }
    .memory-empty span {
      font-size: 12px;
    }
    .memory-error,
    .danger {
      color: #a03441 !important;
    }
    .memory-error {
      font-size: 12px;
      line-height: 1.65;
    }
    .memory-confirm {
      padding: 12px;
      background: #fff5f4;
      border: 1px solid #efcfcb;
      border-radius: 10px;
      margin-top: 16px;
      font-size: 13px;
      line-height: 1.65;
    }
    .memory-confirm p {
      margin: 0 0 8px;
    }
    mat-dialog-actions {
      padding: 12px 24px 20px;
      gap: 6px;
    }
    .actions-spacer {
      flex: 1;
    }
    @media (max-width: 520px) {
      .clear-memory {
        flex-basis: 100%;
      }
    }
  `,
})
export class AgentMemoryDialog {
  i18n = inject(I18n);
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  private dialog = inject(MatDialogRef<AgentMemoryDialog>);
  private seed = inject<string>(MAT_DIALOG_DATA);
  enabled = new FormControl(false, { nonNullable: true });
  notes = new FormArray<
    FormGroup<{
      id: FormControl<string>;
      title: FormControl<string>;
      content: FormControl<string>;
    }>
  >([]);
  loading = signal(true);
  saving = signal(false);
  loadFailed = signal(false);
  confirmClear = signal(false);
  error = signal("");
  version = signal(0);
  maxItems = signal(12);
  maxCharacters = signal(6000);

  constructor() {
    void this.load();
  }
  private note(item?: AgentMemoryItem) {
    return new FormGroup({
      id: new FormControl(item?.id || "", { nonNullable: true }),
      title: new FormControl(item?.title || "", {
        nonNullable: true,
        validators: [
          Validators.required,
          Validators.maxLength(80),
          Validators.pattern(/\S/),
        ],
      }),
      content: new FormControl(item?.content || "", {
        nonNullable: true,
        validators: [
          Validators.required,
          Validators.maxLength(600),
          Validators.pattern(/\S/),
        ],
      }),
    });
  }
  private async load() {
    try {
      const state = await firstValueFrom(
        this.api.agentMemory().pipe(takeUntilDestroyed(this.destroy)),
      );
      this.version.set(state.version);
      this.maxItems.set(state.maxItems);
      this.maxCharacters.set(state.maxCharacters);
      this.enabled.setValue(state.enabled);
      for (const item of state.items) this.notes.push(this.note(item));
      if (
        this.seed?.trim() &&
        !state.items.some((item) => item.content === this.seed.trim())
      ) {
        if (this.notes.length >= this.maxItems()) {
          this.error.set(
            this.i18n.choose(
              "Elimina o edita una memoria para añadir otra.",
              "Remove or edit a memory before adding another.",
            ),
          );
        } else {
          this.add(this.seed.trim());
        }
      }
    } catch (error) {
      if (!this.destroy.destroyed) {
        this.error.set(errorText(error));
        this.loadFailed.set(true);
      }
    } finally {
      this.loading.set(false);
    }
  }
  add(content = "") {
    if (this.saving() || this.notes.length >= this.maxItems()) return;
    const title = content ? content.replace(/\s+/g, " ").slice(0, 75) : "";
    this.notes.push(this.note({ id: "", title, content }));
    this.enabled.setValue(true);
  }
  remove(index: number) {
    if (!this.saving()) this.notes.removeAt(index);
  }
  characters() {
    return this.notes
      .getRawValue()
      .reduce((sum, item) => sum + item.title.length + item.content.length, 0);
  }
  async save() {
    if (
      this.loading() ||
      this.saving() ||
      this.loadFailed() ||
      this.confirmClear() ||
      this.notes.invalid ||
      this.duplicateTitles() ||
      this.characters() > this.maxCharacters()
    )
      return;
    await this.write(() =>
      this.api.saveAgentMemory(
        this.version(),
        this.enabled.value,
        this.notes.getRawValue(),
      ),
    );
  }
  async clear() {
    if (!this.confirmClear() || this.saving() || this.loading()) return;
    await this.write(() => this.api.clearAgentMemory(this.version()));
  }
  duplicateTitles() {
    const titles = this.notes
      .getRawValue()
      .map((item) => item.title.trim().toLowerCase())
      .filter(Boolean);
    return titles.length !== new Set(titles).size;
  }
  private async write(request: () => ReturnType<Api["agentMemory"]>) {
    this.saving.set(true);
    this.enabled.disable({ emitEvent: false });
    this.dialog.disableClose = true;
    this.error.set("");
    try {
      const result: AgentMemoryProfile = await firstValueFrom(request());
      this.dialog.close(result);
    } catch (error) {
      this.error.set(errorText(error));
    } finally {
      this.saving.set(false);
      this.enabled.enable({ emitEvent: false });
      this.dialog.disableClose = false;
    }
  }
}
