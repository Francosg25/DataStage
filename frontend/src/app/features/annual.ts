import { Component, DestroyRef, inject, signal } from "@angular/core";
import { ReactiveFormsModule, FormBuilder, Validators } from "@angular/forms";
import { Router } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatInputModule } from "@angular/material/input";
import { MatSelectModule } from "@angular/material/select";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Period, errorText } from "../core/models";
import { Icon, Empty, Status } from "../shared/ui";
import { MONTHS } from "./monthly";
@Component({
  selector: "ds-annual",
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatProgressBarModule,
    Icon,
    Empty,
    Status,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow">VISIÓN ACUMULADA</span>
        <h1>Consolidado anual</h1>
        <p>Reúne tus versiones mensuales publicadas en un único resultado.</p>
      </div>
    </div>
    <div class="form-columns">
      <section class="panel form-panel">
        <h2>Configura tu consolidado</h2>
        <p class="muted">
          Se incluirán los periodos disponibles desde enero hasta el mes
          seleccionado.
        </p>
        <form [formGroup]="form" (ngSubmit)="submit()">
          <div class="field-row">
            <mat-form-field appearance="outline"
              ><mat-label>Año</mat-label
              ><input
                matInput
                type="number"
                min="1900"
                max="2100"
                formControlName="year" /></mat-form-field
            ><mat-form-field appearance="outline"
              ><mat-label>Hasta el mes</mat-label
              ><mat-select formControlName="month">
                @for (month of months; track month; let i = $index) {
                  <mat-option [value]="i">{{ month }}</mat-option>
                }
              </mat-select></mat-form-field
            >
          </div>
          <div class="annual-summary">
            <ds-icon name="calendar" />
            <div>
              <strong
                >Enero — {{ months[form.controls.month.value] }}
                {{ form.controls.year.value }}</strong
              >
              <p>
                {{ sources().length }} periodos con versión publicada
                disponibles
              </p>
            </div>
          </div>
          @if (error()) {
            <div class="error-message" role="alert">{{ error() }}</div>
          }
          @if (busy()) {
            <mat-progress-bar
              mode="indeterminate"
              aria-label="Creando consolidado"
            />
          }
          <div class="form-actions">
            <span>Las fuentes se fijan al crear la ejecución.</span
            ><button
              mat-flat-button
              type="submit"
              [disabled]="busy() || form.invalid || !sources().length"
            >
              Crear consolidado <ds-icon name="arrow" />
            </button>
          </div>
        </form>
      </section>
      <aside class="panel info-panel">
        <span class="eyebrow">VERSIONES REPRODUCIBLES</span>
        <h2>Un resultado con historia.</h2>
        <p>
          Cada consolidado conserva las versiones mensuales exactas que lo
          componen.
        </p>
        <div class="note">
          Si corriges un mes, crea un nuevo consolidado para incluir esa
          versión. Los resultados anteriores seguirán disponibles.
        </div>
      </aside>
    </div>
    <section class="panel">
      <div class="panel-heading">
        <div>
          <h2>Fuentes del periodo</h2>
          <p>Versiones mensuales que estarán disponibles para consolidar</p>
        </div>
      </div>
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" aria-label="Cargando periodos" />
      }
      @if (sources().length) {
        <div class="period-grid">
          @for (period of sources(); track period.id) {
            <article class="period-tile">
              <ds-icon name="calendar" /><strong>{{
                period.name.replace("_", " ")
              }}</strong
              ><span>Versión {{ period.version }}</span
              ><ds-status value="PUBLISHED" />
            </article>
          }
        </div>
      } @else {
        <ds-empty
          title="No hay fuentes publicadas en este rango"
          message="Procesa una carga mensual o selecciona otro año."
          icon="calendar"
        />
      }
    </section>`,
})
export class Annual {
  api = inject(Api);
  destroy = inject(DestroyRef);
  router = inject(Router);
  fb = inject(FormBuilder);
  months = MONTHS;
  form = this.fb.nonNullable.group({
    year: [
      new Date().getFullYear(),
      [Validators.required, Validators.min(1900), Validators.max(2100)],
    ],
    month: [new Date().getMonth(), Validators.required],
  });
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
    return this.periods()
      .filter(
        (p) => p.year === f.year && p.month <= f.month + 1 && p.activeRunId,
      )
      .sort((a, b) => a.month - b.month);
  }
  submit() {
    if (this.busy() || this.form.invalid || !this.sources().length) return;
    this.busy.set(true);
    this.error.set("");
    const f = this.form.getRawValue();
    this.form.disable({ emitEvent: false });
    this.api
      .annual(
        f.year,
        `Ene-${["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"][f.month]}`,
        this.key,
      )
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
