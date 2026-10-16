import {
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  signal,
  untracked,
} from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { finalize, forkJoin } from "rxjs";
import { TranslatePipe } from "../core/i18n";
import { errorText } from "../core/models";
import { SupplierRunReportState, SuppliersApi } from "../core/suppliers";
import { saveSupplierDownload } from "../shared/supplier-download";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-supplier-run-report",
  imports: [
    TranslatePipe,
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    Icon,
  ],
  template: `
    <section
      class="panel"
      [attr.aria-busy]="loading()"
      aria-labelledby="monthly-suppliers-heading"
    >
      <div class="panel-heading">
        <div>
          <h2 id="monthly-suppliers-heading">
            {{ "Listas de proveedores del mes" | t }}
          </h2>
          <p>
            {{
              "Al publicar cada mes se detectan proveedores y se preparan las listas acumulativas."
                | t
            }}
          </p>
        </div>
        <button
          mat-button
          (click)="load()"
          [disabled]="loading() || downloading()"
        >
          {{ "Actualizar" | t }}
        </button>
      </div>
      @if (loading()) {
        <mat-progress-bar
          mode="indeterminate"
          [attr.aria-label]="'Cargando reporte de proveedores' | t"
        />
      }
      <div class="supplier-run-content">
        @if (error()) {
          <div class="error-message" role="alert">
            {{ error() | t
            }}<button mat-button (click)="load()">
              {{ "Reintentar" | t }}
            </button>
          </div>
        }
        @if (state(); as value) {
          @if (value.status === "ready" && value.report) {
            <p>
              {{
                "Ambas listas están listas y comparten la misma instantánea."
                  | t
              }}
              {{ value.report.label }}
            </p>
            <div class="supplier-run-actions">
              <button
                mat-flat-button
                (click)="download()"
                [disabled]="downloading()"
              >
                <ds-icon name="download" />{{
                  (downloading() ? "Descargando" : "Descargar ambas listas") | t
                }}
              </button>
              <a
                mat-stroked-button
                routerLink="/suppliers"
                [queryParams]="{ tab: 'reports' }"
                >{{ "Ver reportes de proveedores" | t }}</a
              >
            </div>
          } @else if (value.status === "pending_review") {
            <p class="supplier-run-pending" role="status">
              {{
                "El reporte espera decisiones de identificación u operaciones virtuales. Al resolverlas se generan automáticamente ambas listas."
                  | t
              }}
            </p>
            <p>{{ value.pending }} {{ "proveedores por revisar" | t }}</p>
            <a
              mat-flat-button
              routerLink="/suppliers"
              [queryParams]="{ tab: 'reviews' }"
              >{{ "Revisar proveedores" | t }}</a
            >
          } @else {
            <p>{{ "No hay un reporte automático para esta ejecución." | t }}</p>
            <a
              mat-stroked-button
              routerLink="/suppliers"
              [queryParams]="{ tab: 'reports' }"
              >{{ "Ver reportes de proveedores" | t }}</a
            >
          }
        }
      </div>
    </section>
  `,
  styles: [
    `
      .supplier-run-content {
        padding: 0 24px 24px;
      }
      .supplier-run-content p {
        margin-bottom: 14px;
      }
      .supplier-run-actions {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
      }
      .supplier-run-pending {
        padding: 14px;
        background: #fff5d9;
        border-radius: 5px;
        color: #7a5d14;
      }
      .panel-heading {
        align-items: start;
      }
    `,
  ],
})
export class SupplierRunReport {
  readonly runId = input.required<string>();
  private readonly api = inject(SuppliersApi);
  private readonly destroy = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  readonly state = signal<SupplierRunReportState | null>(null);
  readonly loading = signal(false);
  readonly downloading = signal(false);
  readonly error = signal("");
  private request = 0;
  private pendingPoll?: ReturnType<typeof setTimeout>;
  private fetching = false;

  constructor() {
    this.destroy.onDestroy(() => clearTimeout(this.pendingPoll));
    effect(() => {
      const runId = this.runId();
      untracked(() => this.loadRun(runId));
    });
  }
  load() {
    if (this.fetching) return;
    this.loadRun(this.runId());
  }
  private loadRun(runId: string, silent = false) {
    clearTimeout(this.pendingPoll);
    const request = ++this.request;
    this.fetching = true;
    if (!silent) this.loading.set(true);
    this.error.set("");
    if (this.state()?.runId !== runId) this.state.set(null);
    this.api
      .runReport(runId)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => {
          if (request === this.request) {
            this.loading.set(false);
            this.fetching = false;
          }
        }),
      )
      .subscribe({
        next: (state) => {
          if (request !== this.request) return;
          this.state.set(state);
          if (state.status === "pending_review") {
            this.pendingPoll = setTimeout(
              () => this.loadRun(runId, true),
              8000,
            );
          }
        },
        error: (error) => {
          if (request === this.request) this.error.set(errorText(error));
        },
      });
  }
  download() {
    const state = this.state();
    const id = state?.report?.id;
    if (!id || state.status !== "ready" || this.downloading()) return;
    this.downloading.set(true);
    this.error.set("");
    forkJoin([
      this.api.download(id, "national"),
      this.api.download(id, "foreign"),
    ])
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.downloading.set(false)),
      )
      .subscribe({
        next: (responses) =>
          responses.forEach((response, index) =>
            saveSupplierDownload(
              this.document,
              response,
              `${id}-${index === 0 ? "national" : "foreign"}.xlsx`,
            ),
          ),
        error: (error) => this.error.set(errorText(error)),
      });
  }
}
