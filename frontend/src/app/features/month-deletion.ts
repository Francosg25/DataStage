import { Component, DestroyRef, inject, output, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api, BulkPeriodPreview } from "../core/api";
import { Period, errorText } from "../core/models";
import { I18n } from "../core/i18n";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-month-deletion",
  imports: [FormsModule, Icon],
  template: ` <section class="deletion">
    <h2>{{ t("Eliminar meses", "Delete months") }}</h2>
    <p>
      {{
        t(
          "Eliminación definitiva de datos, versiones y consolidados relacionados. Máximo 24 meses por operación.",
          "Permanently deletes data, versions and related consolidations. Up to 24 months per operation."
        )
      }}
    </p>
    @if (error()) {
      <div class="error-message" role="alert">{{ error() }}</div>
    }
    @if (message()) {
      <p role="status">{{ message() }}</p>
    }
    <fieldset [disabled]="busy()">
      <legend>
        {{ t("Meses seleccionados", "Selected months") }}:
        {{ selected().length }}
      </legend>
      <div class="months">
        @for (p of periods(); track p.id) {
          <label
            ><input
              type="checkbox"
              [checked]="selected().includes(p.id)"
              [disabled]="!selected().includes(p.id) && selected().length >= 24"
              (change)="toggle(p.id)"
            />{{ i18n.month(p.month) }} {{ p.year }}
            <small>v{{ p.version }}</small></label
          >
        } @empty {
          <p>{{ t("No hay meses cargados.", "No uploaded months.") }}</p>
        }
      </div>
      <button type="button" (click)="preview()" [disabled]="!selected().length">
        {{ t("Revisar impacto", "Review impact") }}
      </button>
      @if (impact(); as p) {
        <div class="impact" role="status">
          {{ p.impact.businessRows }} {{ t("registros", "records") }} ·
          {{ p.impact.monthlyRuns }}
          {{ t("versiones mensuales", "monthly versions") }} ·
          {{ p.impact.annualRuns }} {{ t("consolidados", "consolidations") }} ·
          {{ p.impact.documents }} {{ t("documentos", "documents") }}
        </div>
        <label class="field"
          >{{ t("Confirmación", "Confirmation") }}: <b>{{ p.confirmation }}</b
          ><input [(ngModel)]="confirmation" autocomplete="off"
        /></label>
        <label class="field"
          >{{ t("Motivo de eliminación", "Reason for deletion")
          }}<textarea
            [(ngModel)]="reason"
            minlength="8"
            maxlength="1000"
          ></textarea>
        </label>
        <button
          type="button"
          class="danger"
          (click)="remove()"
          [disabled]="
            confirmation !== p.confirmation || reason.trim().length < 8
          "
        >
          <ds-icon name="alert" />{{
            t("Eliminar definitivamente", "Delete permanently")
          }}
        </button>
      }
    </fieldset>
    @if (busy()) {
      <p role="status">
        {{ t("Procesando solicitud...", "Processing request...") }}
      </p>
    }
  </section>`,
  styles: `
    .deletion {
      border-top: 1px solid #d3dfe3;
      margin-top: 28px;
      padding-top: 24px;
    }
    h2 {
      font-size: 18px;
    }
    p {
      font-size: 13px;
      margin: 10px 0 18px;
    }
    fieldset {
      border: 0;
      padding: 0;
      min-width: 0;
    }
    legend {
      font-size: 13px;
      margin-bottom: 12px;
    }
    .months {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(185px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }
    .months label {
      display: flex;
      gap: 9px;
      align-items: center;
      font-size: 13px;
    }
    .field {
      display: grid;
      gap: 8px;
      max-width: 480px;
      margin: 16px 0;
      font-size: 13px;
    }
    .field input,
    textarea {
      border: 1px solid #bacbd1;
      border-radius: 4px;
      padding: 9px;
      font: inherit;
      max-width: 100%;
      min-width: 0;
    }
    button {
      border: 1px solid #bacbd1;
      border-radius: 4px;
      background: white;
      padding: 10px 14px;
      color: #234c57;
      display: inline-flex;
      gap: 8px;
      align-items: center;
    }
    button.danger {
      background: #a63535;
      color: white;
      border-color: #a63535;
    }
    button:disabled {
      opacity: 0.45;
      cursor: default;
    }
    .impact {
      padding: 14px 0;
      color: #963232;
      font-size: 13px;
    }
    ds-icon {
      width: 16px;
      height: 16px;
    }
  `,
})
export class MonthDeletion {
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  readonly i18n = inject(I18n);
  changed = output<void>();
  periods = signal<Period[]>([]);
  selected = signal<string[]>([]);
  impact = signal<BulkPeriodPreview | null>(null);
  busy = signal(false);
  error = signal("");
  message = signal("");
  confirmation = "";
  reason = "";
  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
  constructor() {
    this.load();
  }
  load() {
    this.api
      .periods()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => this.periods.set(p),
        error: (e) => this.error.set(errorText(e)),
      });
  }
  toggle(id: string) {
    if (this.busy()) return;
    this.selected.update((ids) =>
      ids.includes(id) ? ids.filter((p) => p !== id) : [...ids, id],
    );
    this.impact.set(null);
    this.confirmation = "";
    this.error.set("");
    this.message.set("");
  }
  preview() {
    if (this.busy() || !this.selected().length) return;
    this.busy.set(true);
    this.error.set("");
    this.impact.set(null);
    this.confirmation = "";
    this.api
      .bulkPeriodPreview(this.selected())
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.impact.set(p);
          this.busy.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
        },
      });
  }
  remove() {
    const p = this.impact();
    if (
      this.busy() ||
      !p ||
      this.confirmation !== p.confirmation ||
      this.reason.trim().length < 8
    )
      return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .deletePeriods(p, this.confirmation, this.reason.trim())
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (r) => {
          this.busy.set(false);
          this.impact.set(null);
          this.selected.set([]);
          this.confirmation = "";
          this.reason = "";
          this.message.set(
            r.storageCleanupFailures
              ? this.t(
                  "Meses eliminados; hay archivos pendientes de limpieza.",
                  "Months deleted; some files still require cleanup.",
                )
              : this.t("Meses eliminados.", "Months deleted."),
          );
          this.load();
          this.changed.emit();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
          this.impact.set(null);
        },
      });
  }
}
