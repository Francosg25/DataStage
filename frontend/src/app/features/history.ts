import { TranslatePipe } from "../core/i18n";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatPaginatorModule, PageEvent } from "@angular/material/paginator";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { Run, errorText } from "../core/models";
import { MonthDeletion } from "./month-deletion";
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
    MonthDeletion,
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
      <ds-month-deletion (changed)="load()" />
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
  }
}
