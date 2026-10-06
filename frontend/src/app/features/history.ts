import { TranslatePipe } from "../core/i18n";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatPaginatorModule, PageEvent } from "@angular/material/paginator";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import {
  Period,
  PeriodDeletionPreview,
  Run,
  errorText,
} from "../core/models";
import { RunList, Icon } from "../shared/ui";

@Component({
  selector: "ds-history",
  imports: [
    TranslatePipe,
    RouterLink,
    MatButtonModule,
    MatPaginatorModule,
    MatProgressBarModule,
    RunList,
    Icon,
  ],
  template: `
    <div class="page-heading">
      <div>
        <span class="eyebrow">{{ "TRAZABILIDAD" | t }}</span>
        <h1>{{ "Historial de procesos" | t }}</h1>
        <p>{{ "Cada ejecución, su versión y sus resultados." | t }}</p>
      </div>
      <a mat-flat-button routerLink="/monthly">
        <ds-icon name="upload" /> {{ "Nueva carga" | t }}
      </a>
    </div>

    @if (error()) {
      <div class="error-message" role="alert">
        {{ error() | t }}
        <button mat-button (click)="load()">
          {{ "Reintentar" | t }}
        </button>
      </div>
    }

    <section class="panel">
      <div class="panel-heading">
        <div>
          <h2>{{ "Todas las ejecuciones" | t }}</h2>
          <p>{{ total() }} {{ "procesos registrados" | t }}</p>
        </div>
        <button mat-stroked-button (click)="load()" [disabled]="loading()">
          {{ "Actualizar" | t }}
        </button>
      </div>

      @if (loading()) {
        <mat-progress-bar mode="indeterminate" />
      }

      <ds-run-list [runs]="runs()" />

      <mat-paginator
        [length]="total()"
        [pageSize]="20"
        [pageIndex]="page()"
        [hidePageSize]="true"
        [disabled]="loading()"
        (page)="change($event)"
      />
    </section>

    @if (auth.hasRole("Admin")) {
      <section class="panel">
        <div class="panel-heading">
          <div>
            <h2>Eliminar un mes</h2>
            <p>
              Se eliminarán sus datos, versiones y consolidados anuales
              relacionados.
            </p>
          </div>
        </div>

        <label for="delete-period">Mes que deseas eliminar</label>
        <select
          id="delete-period"
          [value]="selectedPeriodId()"
          (change)="choosePeriod($any($event.target).value)"
        >
          <option value="">Selecciona un mes</option>
          @for (period of periods(); track period.id) {
            <option [value]="period.id">{{ period.name }}</option>
          }
        </select>

        <button
          mat-stroked-button
          (click)="previewDeletion()"
          [disabled]="!selectedPeriodId() || deleting()"
        >
          Ver impacto
        </button>

        @if (deletionPreview(); as impact) {
          <p>
            Se eliminarán: {{ impact.businessRows }} registros,
            {{ impact.monthlyRuns }} versiones mensuales y
            {{ impact.annualRuns }} consolidados anuales.
          </p>

          <label for="delete-confirmation">
            Escribe {{ impact.periodName }} para confirmar
          </label>
          <input
            id="delete-confirmation"
            [value]="confirmation()"
            (input)="confirmation.set($any($event.target).value)"
          />

          <label for="delete-reason">Motivo de eliminación</label>
          <textarea
            id="delete-reason"
            [value]="reason()"
            (input)="reason.set($any($event.target).value)"
          ></textarea>

          <button
            mat-flat-button
            (click)="deleteSelectedPeriod()"
            [disabled]="
              deleting() ||
              confirmation() !== impact.periodName ||
              reason().trim().length < 8
            "
          >
            Eliminar mes definitivamente
          </button>
        }

        @if (deletionError()) {
          <div class="error-message" role="alert">
            {{ deletionError() }}
          </div>
        }
      </section>
    }
  `,
})
export class History {
  api = inject(Api);
  auth = inject(Auth);
  destroy = inject(DestroyRef);

  runs = signal<Run[]>([]);
  total = signal(0);
  page = signal(0);
  loading = signal(true);
  error = signal("");

  periods = signal<Period[]>([]);
  selectedPeriodId = signal("");
  deletionPreview = signal<PeriodDeletionPreview | null>(null);
  confirmation = signal("");
  reason = signal("");
  deletionError = signal("");
  deleting = signal(false);

  constructor() {
    this.load();
  }

  change(event: PageEvent) {
    this.page.set(event.pageIndex);
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set("");

    this.api
      .runs(this.page() * 20)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (response) => {
          this.runs.set(response.items);
          this.total.set(response.total);
          this.loading.set(false);
        },
        error: (error) => {
          this.error.set(errorText(error));
          this.loading.set(false);
        },
      });

    if (this.auth.hasRole("Admin")) {
      this.api
        .periods()
        .pipe(takeUntilDestroyed(this.destroy))
        .subscribe({
          next: (periods) => this.periods.set(periods),
          error: (error) => this.deletionError.set(errorText(error)),
        });
    }
  }

  choosePeriod(id: string) {
    this.selectedPeriodId.set(id);
    this.deletionPreview.set(null);
    this.confirmation.set("");
    this.reason.set("");
    this.deletionError.set("");
  }

  previewDeletion() {
    if (!this.selectedPeriodId()) return;

    this.deletionError.set("");
    this.api
      .periodDeletionPreview(this.selectedPeriodId())
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (impact) => this.deletionPreview.set(impact),
        error: (error) => this.deletionError.set(errorText(error)),
      });
  }

  deleteSelectedPeriod() {
    const impact = this.deletionPreview();

    if (
      !impact ||
      this.deleting() ||
      this.confirmation() !== impact.periodName ||
      this.reason().trim().length < 8
    ) {
      return;
    }

    this.deleting.set(true);
    this.deletionError.set("");

    this.api
      .deletePeriod(
        impact,
        this.confirmation(),
        this.reason().trim(),
      )
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (result) => {
          this.deleting.set(false);
          this.choosePeriod("");

          if (result.storageCleanupFailures) {
            this.deletionError.set(
              "Se eliminó el mes, pero quedaron archivos pendientes de limpieza.",
            );
          }

          this.load();
        },
        error: (error) => {
          this.deleting.set(false);
          this.deletionError.set(errorText(error));
        },
      });
  }
}