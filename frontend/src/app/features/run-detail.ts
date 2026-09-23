import { MatPaginatorModule, PageEvent } from "@angular/material/paginator";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { DatePipe, DecimalPipe } from "@angular/common";
import { ActivatedRoute, Router, RouterLink } from "@angular/router";
import { ReactiveFormsModule, FormControl, Validators } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatTabsModule } from "@angular/material/tabs";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatInputModule } from "@angular/material/input";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { timer, switchMap, takeWhile, catchError, EMPTY } from "rxjs";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { Run, DataRow, errorText, isTerminal, runLabel } from "../core/models";
import { Icon, Status, DataTable } from "../shared/ui";
@Component({
  selector: "ds-run-detail",
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    ReactiveFormsModule,
    MatButtonModule,
    MatTabsModule,
    MatPaginatorModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    Icon,
    Status,
    DataTable,
  ],
  template: `
    <a routerLink="/runs" class="back-link">← Volver al historial</a>
    @if (run(); as r) {
      <div class="page-heading">
        <div>
          <span class="eyebrow">{{
            r.kind.toUpperCase() === "ANNUAL"
              ? "CONSOLIDACIÓN ANUAL"
              : "PROCESAMIENTO MENSUAL"
          }}</span>
          <h1>{{ label(r) }}</h1>
          <p>
            Creado el {{ r.createdAt | date: "dd/MM/yyyy HH:mm" }} ·
            <span class="mono">{{ r.id }}</span>
          </p>
        </div>
        <div class="heading-actions">
          <ds-status [value]="r.functionalResult || r.status" />
          @if (r.exportDocumentId) {
            <button mat-flat-button (click)="download()" [disabled]="busy()">
              <ds-icon name="download" /> Descargar Excel
            </button>
          } @else if (terminal(r)) {
            <button mat-stroked-button (click)="export()" [disabled]="busy()">
              Generar Excel
            </button>
          }
        </div>
      </div>
      @if (error()) {
        <div class="error-message" role="alert">
          {{ error() }}
          <button mat-button (click)="reload()">Actualizar</button>
        </div>
      }
      @if (r.errorMessage) {
        <div class="error-message" role="alert">{{ r.errorMessage }}</div>
      }
      <section class="panel progress-panel">
        <div class="progress-heading">
          <div>
            <h2>
              {{
                terminal(r) ? "Resultado del proceso" : "Procesamiento en curso"
              }}
            </h2>
            <p>{{ phase(r.phase) }}</p>
          </div>
          <strong>{{ r.progress | number: "1.0-0" }}%</strong>
        </div>
        <mat-progress-bar
          mode="determinate"
          [value]="r.progress"
          aria-label="Avance del procesamiento"
        />
        <div class="progress-meta">
          <span>Publicación: <ds-status [value]="r.publicationStatus" /></span
          ><span>Exportación: <ds-status [value]="r.exportStatus" /></span>
        </div>
      </section>
      <div class="stats-grid compact-stats">
        <article class="stat-card">
          <span>Archivos recibidos</span
          ><strong>{{ r.counts.receivedFiles | number }}</strong
          ><small
            >{{ r.counts.processedFiles }} procesados ·
            {{ r.counts.skippedFiles }} omitidos</small
          >
        </article>
        <article class="stat-card">
          <span>Tablas procesadas</span
          ><strong>{{ r.counts.processedTables | number }}</strong
          ><small>Agrupadas por código</small>
        </article>
        <article class="stat-card">
          <span>Registros</span><strong>{{ r.counts.rows | number }}</strong
          ><small>Filas de datos procesadas</small>
        </article>
        <article class="stat-card">
          <span>Incidencias</span
          ><strong>{{ r.counts.errors + r.counts.warnings | number }}</strong
          ><small
            >{{ r.counts.errors }} errores ·
            {{ r.counts.warnings }} advertencias</small
          >
        </article>
      </div>
      <section class="panel">
        <mat-tab-group
          (selectedIndexChange)="changeTab($event)"
          animationDuration="0ms"
        >
          @for (tab of tabs; track tab.key) {
            <mat-tab [label]="tab.label"
              ><div class="tab-content">
                @if (sectionLoading()) {
                  <mat-progress-bar
                    mode="indeterminate"
                    aria-label="Cargando detalle"
                  />
                }
                @if (sectionError()) {
                  <div class="error-message" role="alert">
                    {{ sectionError() }}
                  </div>
                }
                <ds-data-table
                  [rows]="rows()"
                  [headers]="sectionHeaders()"
                  [emptyTitle]="
                    tab.key === 'issues'
                      ? 'Sin incidencias registradas'
                      : 'Sin registros disponibles'
                  "
                />
                @if (sectionTotal() > 50) {
                  <mat-paginator
                    [length]="sectionTotal()"
                    [pageSize]="50"
                    [pageIndex]="sectionPage()"
                    [hidePageSize]="true"
                    [disabled]="sectionLoading()"
                    (page)="changePage($event)"
                    aria-label="Paginación del detalle"
                  />
                }</div
            ></mat-tab>
          }
        </mat-tab-group>
      </section>
      @if (terminal(r) && canReprocess()) {
        <section class="panel reprocess-panel">
          <div>
            <h2>Crear una nueva versión</h2>
            <p>
              El reproceso conserva la ejecución original y registra el motivo
              en la auditoría.
            </p>
          </div>
          <form (ngSubmit)="reprocess()">
            <mat-form-field appearance="outline"
              ><mat-label>Motivo del reproceso</mat-label
              ><textarea
                matInput
                [formControl]="reason"
                rows="2"
                maxlength="1000"
              ></textarea
              ><mat-hint>Mínimo 5 caracteres</mat-hint></mat-form-field
            ><button
              mat-stroked-button
              type="submit"
              [disabled]="busy() || reason.invalid"
            >
              Solicitar reproceso
            </button>
          </form>
        </section>
      }
    } @else if (error()) {
      <div class="error-message" role="alert">
        {{ error() }} <button mat-button (click)="reload()">Reintentar</button>
      </div>
    } @else {
      <mat-progress-bar mode="indeterminate" aria-label="Cargando ejecución" />
    }
  `,
})
export class RunDetail {
  api = inject(Api);
  auth = inject(Auth);
  route = inject(ActivatedRoute);
  router = inject(Router);
  destroy = inject(DestroyRef);
  run = signal<Run | null>(null);
  error = signal("");
  busy = signal(false);
  rows = signal<DataRow[]>([]);
  sectionLoading = signal(false);
  sectionError = signal("");
  sectionTotal = signal(0);
  sectionPage = signal(0);
  tabs = [
    { key: "files", label: "Archivos" },
    { key: "tables", label: "Tablas" },
    { key: "issues", label: "Incidencias" },
    { key: "control", label: "Control del proceso" },
  ];
  selectedTab = 0;
  reason = new FormControl("", {
    nonNullable: true,
    validators: [
      Validators.required,
      Validators.minLength(5),
      Validators.maxLength(1000),
    ],
  });
  label = runLabel;
  terminal = isTerminal;
  private id = "";
  private poll?: { unsubscribe(): void };
  private exportKey = crypto.randomUUID();
  private reprocessKey = crypto.randomUUID();
  constructor() {
    this.route.paramMap
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe((params) => {
        this.id = params.get("id") || "";
        this.exportKey = crypto.randomUUID();
        this.reprocessKey = crypto.randomUUID();
        this.sectionPage.set(0);
        this.run.set(null);
        this.error.set("");
        this.startPolling();
        this.loadSection();
      });
    this.reason.valueChanges
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe(() => (this.reprocessKey = crypto.randomUUID()));
  }
  private startPolling() {
    this.poll?.unsubscribe();
    this.poll = timer(0, 2500)
      .pipe(
        switchMap(() => this.api.run(this.id)),
        takeWhile((r) => !isTerminal(r), true),
        takeUntilDestroyed(this.destroy),
        catchError((e) => {
          this.error.set(errorText(e));
          return EMPTY;
        }),
      )
      .subscribe((r) => {
        const previous = this.run();
        this.run.set(r);
        this.error.set("");
        if (isTerminal(r) && !previous?.functionalResult) this.loadSection();
      });
  }
  reload() {
    this.startPolling();
    this.loadSection();
  }
  changeTab(index: number) {
    this.selectedTab = index;
    this.sectionPage.set(0);
    this.loadSection();
  }
  changePage(event: PageEvent) {
    this.sectionPage.set(event.pageIndex);
    this.loadSection();
  }
  loadSection() {
    this.sectionLoading.set(true);
    this.sectionError.set("");
    const key = this.tabs[this.selectedTab].key;
    const runId = this.id;
    const page = this.sectionPage();
    this.api
      .section(this.id, key, page * 50, 50)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          if (
            key !== this.tabs[this.selectedTab].key ||
            runId !== this.id ||
            page !== this.sectionPage()
          )
            return;
          this.rows.set(p.items);
          this.sectionTotal.set(p.total);
          this.sectionLoading.set(false);
        },
        error: (e) => {
          this.sectionError.set(errorText(e));
          this.rows.set([]);
          this.sectionLoading.set(false);
        },
      });
  }
  phase(value: string) {
    return (
      (
        {
          QUEUED: "Esperando un worker disponible",
          INGESTION: "Registrando archivos de origen",
          EXTRACTING: "Extrayendo y verificando archivos",
          PROCESSING: "Procesando los archivos del periodo",
          PERSISTING: "Guardando la versión de los datos",
          EXPORTING: "Generando el archivo Excel",
          RETRY_PENDING: "Esperando un nuevo intento",
          FAILED: "El proceso no pudo completarse",
          PARSING: "Leyendo y normalizando archivos",
          VALIDATION: "Validando la información",
          PERSISTENCE: "Guardando los datos procesados",
          EXPORT: "Generando el archivo Excel",
          COMPLETED: "Proceso finalizado",
          DONE: "Proceso finalizado",
        } as Record<string, string>
      )[value.toUpperCase()] || value
    );
  }
  sectionHeaders(): string[] {
    return (
      (
        {
          files: [
            "fileName",
            "tableCode",
            "status",
            "rowCount",
            "columnCount",
            "dateColumnCount",
            "message",
          ],
          tables: [
            "tableCode",
            "sheetName",
            "rowCount",
            "columnCount",
            "dateColumnCount",
          ],
          issues: [
            "severity",
            "code",
            "message",
            "rowNumber",
            "columnName",
            "fileId",
          ],
        } as Record<string, string[]>
      )[this.tabs[this.selectedTab].key] || []
    );
  }
  canReprocess() {
    return this.auth.hasRole("Admin", "Reprocessor");
  }
  download() {
    const id = this.run()?.exportDocumentId;
    if (!id) return;
    this.busy.set(true);
    this.api
      .download(id)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (response) => {
          if (response.body) {
            const disposition =
              response.headers.get("Content-Disposition") || "";
            const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(
              disposition,
            );
            let name = `DataStage_${runLabel(this.run()!).replace(/[^a-z0-9_-]/gi, "_")}.xlsx`;
            if (match) {
              try {
                name = decodeURIComponent(match[1]);
              } catch {
                name = match[1];
              }
            }
            const url = URL.createObjectURL(response.body);
            const a = document.createElement("a");
            a.href = url;
            a.download = name;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }
          this.busy.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
        },
      });
  }
  export() {
    this.busy.set(true);
    this.api
      .export(this.id, this.exportKey)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (r) => {
          this.run.set(r);
          this.busy.set(false);
          this.exportKey = crypto.randomUUID();
          this.startPolling();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
        },
      });
  }
  reprocess() {
    if (this.reason.invalid || this.busy()) return;
    this.busy.set(true);
    this.api
      .reprocess(
        this.id,
        this.reason.value,
        this.run()?.periodVersion ?? 0,
        this.reprocessKey,
      )
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (r) => {
          this.busy.set(false);
          this.reason.reset();
          this.router.navigate(["/runs", r.id]);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
        },
      });
  }
}
