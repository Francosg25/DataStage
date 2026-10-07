import { TranslatePipe } from "../core/i18n";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { ReactiveFormsModule, FormBuilder, Validators } from "@angular/forms";
import { Router } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatSelectModule } from "@angular/material/select";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Period, errorText } from "../core/models";
import { Icon, Empty, Status } from "../shared/ui";
import { MONTHS } from "./monthly";
import { I18n } from "../core/i18n";
@Component({
  selector: "ds-consolidated",
  imports: [
    TranslatePipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressBarModule,
    Icon,
    Empty,
    Status,
  ],
  template: `<div class="form-columns">
      <section class="form-panel">
        <h2>{{ "Configura tu consolidado" | t }}</h2>
        <form [formGroup]="form" (ngSubmit)="submit()">
          <fieldset>
            <legend>{{ "Desde" | t }}</legend>
            <div class="field-row">
              <mat-form-field appearance="outline"
                ><mat-label>{{ "Año inicial" | t }}</mat-label>
                <mat-select formControlName="startYear">
                  @for (year of years; track year) {
                    <mat-option [value]="year">{{ year }}</mat-option>
                  }
                </mat-select></mat-form-field
              ><mat-form-field appearance="outline"
                ><mat-label>{{ "Mes inicial" | t }}</mat-label>
                <mat-select formControlName="startMonth">
                  @for (month of months; track month; let i = $index) {
                    <mat-option [value]="i + 1">{{ month | t }}</mat-option>
                  }
                </mat-select></mat-form-field
              >
            </div>
          </fieldset>
          <fieldset>
            <legend>{{ "Hasta" | t }}</legend>
            <div class="field-row">
              <mat-form-field appearance="outline">
                <mat-label>{{ "Año final" | t }}</mat-label>
                <mat-select
                  formControlName="endYear"
                  [attr.aria-describedby]="
                    form.hasError('rangeOrder') ? 'range-error' : null
                  "
                >
                  @for (year of years; track year) {
                    <mat-option [value]="year">{{ year }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>{{ "Mes final" | t }}</mat-label>
                <mat-select
                  formControlName="endMonth"
                  [attr.aria-describedby]="
                    form.hasError('rangeOrder') ? 'range-error' : null
                  "
                >
                  @for (month of months; track month; let i = $index) {
                    <mat-option [value]="i + 1">{{ month | t }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            </div>
          </fieldset>
          @if (form.hasError("rangeOrder")) {
            <div class="error-message" role="alert" id="range-error">
              {{ "El mes final no puede ser anterior al mes inicial." | t }}
            </div>
          }
          <div class="annual-summary">
            <ds-icon name="calendar" />
            <div>
              <strong>
                {{ months[form.controls.startMonth.value - 1] | t }}
                {{ form.controls.startYear.value }}
                -
                {{ months[form.controls.endMonth.value - 1] | t }}
                {{ form.controls.endYear.value }}
              </strong>
              @if (!loading() && !form.hasError("rangeOrder")) {
                <p>
                  {{ sources().length }} / {{ monthCount() }}
                  {{ "meses con versión publicada" | t }}
                </p>
              }
            </div>
          </div>
          @if (error()) {
            <div class="error-message" role="alert">{{ error() | t }}</div>
          }
          @if (busy()) {
            <mat-progress-bar
              mode="indeterminate"
              [attr.aria-label]="'Creando consolidado' | t"
            />
          }
          <div class="form-actions">
            <span>
              {{ "Las fuentes se fijan al crear la ejecución." | t }} </span
            ><button
              mat-flat-button
              type="submit"
              [disabled]="
                busy() || loading() || form.invalid || !sources().length
              "
            >
              {{ "Crear consolidado" | t }} <ds-icon name="arrow" />
            </button>
          </div>
        </form>
      </section>
      <aside class="info-panel">
        <span class="eyebrow"> {{ "VERSIONES REPRODUCIBLES" | t }} </span>
        <h2>{{ i18n.choose("Versiones de origen", "Source versions") }}</h2>
        <p>
          {{
            "Cada consolidado conserva las versiones mensuales exactas que lo componen."
              | t
          }}
        </p>
        <div class="note">
          {{
            "Si corriges un mes, crea un nuevo consolidado para incluir esa versión. Los resultados anteriores seguirán disponibles."
              | t
          }}
        </div>
      </aside>
    </div>
    <section class="source-section">
      <div class="panel-heading">
        <div>
          <h2>{{ i18n.choose("Meses incluidos", "Included months") }}</h2>
          <p>
            {{
              "Versiones mensuales que estarán disponibles para consolidar" | t
            }}
          </p>
        </div>
      </div>
      @if (loading()) {
        <mat-progress-bar
          mode="indeterminate"
          [attr.aria-label]="'Cargando periodos' | t"
        />
      } @else if (sources().length) {
        <div class="period-grid">
          @for (period of sources(); track period.id) {
            <article class="period-tile">
              <ds-icon name="calendar" /><strong>{{
                period.name.replace("_", " ") | t
              }}</strong
              ><span> {{ "Versión" | t }} {{ period.version | t }}</span
              ><ds-status value="PUBLISHED" />
            </article>
          }
        </div>
      } @else {
        <ds-empty
          [title]="'No hay fuentes publicadas en este rango' | t"
          [message]="
            'No hay versiones mensuales disponibles entre estas fechas.' | t
          "
          icon="calendar"
        />
      }
    </section> `,
  styles: `
    fieldset {
      border: 0;
      padding: 0;
      margin: 0;
      min-width: 0;
    }
    legend {
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 14px;
    }
    .field-row {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    mat-form-field {
      min-width: 0;
    }
    .annual-summary > div {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .annual-summary ds-icon {
      flex-shrink: 0;
    }
  `,
})
export class Consolidated {
  i18n = inject(I18n);
  api = inject(Api);
  destroy = inject(DestroyRef);
  router = inject(Router);
  fb = inject(FormBuilder);
  months = MONTHS;
  years = Array.from({ length: 201 }, (_, i) => 2100 - i);
  private yearValidators = [
    Validators.required,
    Validators.min(1900),
    Validators.max(2100),
    Validators.pattern(/^\d+$/),
  ];
  private monthValidators = [
    Validators.required,
    Validators.min(1),
    Validators.max(12),
    Validators.pattern(/^\d+$/),
  ];
  form = this.fb.nonNullable.group(
    {
      startYear: [new Date().getFullYear(), this.yearValidators],
      startMonth: [1, this.monthValidators],
      endYear: [new Date().getFullYear(), this.yearValidators],
      endMonth: [new Date().getMonth() + 1, this.monthValidators],
    },
    {
      validators: (control) => {
        const f = control.getRawValue();
        return f.startYear * 12 + f.startMonth > f.endYear * 12 + f.endMonth
          ? { rangeOrder: true }
          : null;
      },
    },
  );
  periods = signal<Period[]>([]);
  loading = signal(true);
  busy = signal(false);
  error = signal("");
  private key = crypto.randomUUID();
  constructor() {
    this.form.valueChanges
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe(() => (this.key = crypto.randomUUID()));
    this.api
      .periods()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.periods.set(p);
          this.loading.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
  sources() {
    const f = this.form.getRawValue();
    const start = f.startYear * 12 + f.startMonth;
    const end = f.endYear * 12 + f.endMonth;
    return this.periods()
      .filter(
        (p) =>
          p.activeRunId &&
          p.year * 12 + p.month >= start &&
          p.year * 12 + p.month <= end,
      )
      .sort((a, b) => a.year - b.year || a.month - b.month);
  }
  monthCount() {
    const f = this.form.getRawValue();
    return Math.max(
      0,
      (f.endYear - f.startYear) * 12 + f.endMonth - f.startMonth + 1,
    );
  }
  submit() {
    if (
      this.busy() ||
      this.loading() ||
      this.form.invalid ||
      !this.sources().length
    )
      return;
    this.busy.set(true);
    this.error.set("");
    const f = this.form.getRawValue();
    this.form.disable({ emitEvent: false });
    this.api
      .annual(f, this.key)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (r) => this.router.navigate(["/runs", r.id]),
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
          this.form.enable({ emitEvent: false });
        },
      });
  }
}
