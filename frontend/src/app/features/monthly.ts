import { Component, DestroyRef, inject, signal } from "@angular/core";
import { ReactiveFormsModule, FormBuilder, Validators } from "@angular/forms";
import { Router, RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatSelectModule } from "@angular/material/select";
import { MatInputModule } from "@angular/material/input";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { errorText } from "../core/models";
import { Icon } from "../shared/ui";
export const MONTHS = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];
export function validateZip(file: File, maxMb: number): string {
  if (!file.name.toLowerCase().endsWith(".zip"))
    return "Selecciona un archivo con extensión .zip.";
  if (file.size === 0) return "El archivo está vacío.";
  if (file.size > maxMb * 1024 * 1024)
    return `El archivo supera el límite de ${maxMb} MB.`;
  return "";
}
@Component({
  selector: "ds-monthly",
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatProgressBarModule,
    Icon,
  ],
  template: `
    <div class="page-heading">
      <div>
        <span class="eyebrow">INGESTA DE ARCHIVOS</span>
        <h1>Nueva carga mensual</h1>
        <p>Selecciona el periodo y adjunta el ZIP con tus archivos ASC.</p>
      </div>
      <a mat-stroked-button routerLink="/runs">Ver historial</a>
    </div>
    <div class="form-columns">
      <section class="panel form-panel">
        <form [formGroup]="form" (ngSubmit)="submit()">
          <div class="step-heading">
            <span>1</span>
            <div>
              <h2>Define el periodo</h2>
              <p>El periodo se aplica a todos los archivos de esta carga.</p>
            </div>
          </div>
          <div class="field-row">
            <mat-form-field appearance="outline"
              ><mat-label>Mes</mat-label
              ><mat-select formControlName="month">
                @for (month of months; track month) {
                  <mat-option [value]="month">{{ month }}</mat-option>
                }
              </mat-select></mat-form-field
            ><mat-form-field appearance="outline"
              ><mat-label>Año</mat-label
              ><input
                matInput
                type="number"
                formControlName="year"
                min="1900"
                max="2100"
              /><mat-error
                >Introduce un año entre 1900 y 2100.</mat-error
              ></mat-form-field
            >
          </div>
          <div class="step-heading">
            <span>2</span>
            <div>
              <h2>Adjunta el archivo</h2>
              <p>Un ZIP por periodo, con los archivos ASC originales.</p>
            </div>
          </div>
          <div
            class="upload-zone"
            [class.upload-active]="dragging()"
            (dragover)="dragover($event)"
            (dragleave)="dragging.set(false)"
            (drop)="drop($event)"
          >
            <div class="upload-symbol"><ds-icon name="upload" /></div>
            @if (file()) {
              <strong class="file-name">{{ file()!.name }}</strong>
              <p>{{ fileSize() }} · Listo para procesar</p>
            } @else {
              <strong>Arrastra tu archivo ZIP aquí</strong>
              <p>o selecciónalo desde tu equipo</p>
            }
            <label class="file-select" [class.disabled]="busy()"
              >{{ file() ? "Cambiar archivo" : "Seleccionar archivo"
              }}<input
                type="file"
                accept=".zip,application/zip"
                [disabled]="busy()"
                (change)="select($event)"
                aria-label="Seleccionar archivo ZIP" /></label
            ><small
              >Tamaño máximo: {{ auth.config()?.maxUploadMb || 100 }} MB</small
            >
          </div>
          @if (error()) {
            <div class="error-message" role="alert">{{ error() }}</div>
          }
          @if (busy()) {
            <mat-progress-bar
              mode="indeterminate"
              aria-label="Enviando archivo"
            />
            <p class="muted" aria-live="polite">
              Guardando el archivo y creando la ejecución…
            </p>
          }
          <div class="form-actions">
            <span
              ><ds-icon name="shield" /> Tu archivo conserva su
              trazabilidad.</span
            ><button
              mat-flat-button
              type="submit"
              [disabled]="busy() || !file() || form.invalid"
            >
              {{ busy() ? "Enviando…" : "Iniciar procesamiento" }}
              <ds-icon name="arrow" />
            </button>
          </div>
        </form>
      </section>
      <aside>
        <section class="panel info-panel">
          <span class="eyebrow">ANTES DE COMENZAR</span>
          <h2>Una carga, todo conectado.</h2>
          <ul class="check-list">
            <li>
              <ds-icon name="check" />El nombre del ZIP no determina el periodo.
            </li>
            <li>
              <ds-icon name="check" />Los archivos se agrupan por código de
              tabla.
            </li>
            <li>
              <ds-icon name="check" />Puedes consultar cada incidencia y su
              origen.
            </li>
            <li>
              <ds-icon name="check" />El resultado estará disponible en formato
              Excel.
            </li>
          </ul>
          <div class="note">
            El procesamiento continúa en segundo plano. Podrás seguir su avance
            desde el historial.
          </div>
        </section>
        <div class="help-caption">
          <ds-icon name="file" /><span
            >Formatos de origen<br /><strong
              >Archivos ASC dentro de un ZIP</strong
            ></span
          >
        </div>
      </aside>
    </div>
  `,
})
export class Monthly {
  api = inject(Api);
  auth = inject(Auth);
  router = inject(Router);
  destroy = inject(DestroyRef);
  months = MONTHS;
  private fb = inject(FormBuilder);
  form = this.fb.nonNullable.group({
    month: [MONTHS[new Date().getMonth()], Validators.required],
    year: [
      new Date().getFullYear(),
      [Validators.required, Validators.min(1900), Validators.max(2100)],
    ],
  });
  file = signal<File | null>(null);
  error = signal("");
  busy = signal(false);
  dragging = signal(false);
  private key = crypto.randomUUID();
  constructor() {
    this.form.valueChanges
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe(() => (this.key = crypto.randomUUID()));
  }
  fileSize() {
    return this.file()
      ? `${(this.file()!.size / 1024 / 1024).toFixed(2)} MB`
      : "";
  }
  select(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) this.accept(file);
  }
  dragover(e: DragEvent) {
    e.preventDefault();
    if (!this.busy()) this.dragging.set(true);
  }
  drop(e: DragEvent) {
    e.preventDefault();
    this.dragging.set(false);
    if (!this.busy() && e.dataTransfer?.files[0])
      this.accept(e.dataTransfer.files[0]);
  }
  accept(file: File) {
    const error = validateZip(file, this.auth.config()?.maxUploadMb || 100);
    this.error.set(error);
    this.file.set(error ? null : file);
    this.key = crypto.randomUUID();
  }
  submit() {
    if (this.busy() || this.form.invalid || !this.file()) return;
    this.busy.set(true);
    this.error.set("");
    const f = this.form.getRawValue();
    this.form.disable({ emitEvent: false });
    this.api
      .monthly(`${f.month}_${f.year}`, this.file()!, this.key)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (run) => this.router.navigate(["/runs", run.id]),
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
          this.form.enable({ emitEvent: false });
        },
      });
  }
}
