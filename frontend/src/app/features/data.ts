import { TranslatePipe } from "../core/i18n";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { ReactiveFormsModule, FormBuilder } from "@angular/forms";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatSelectModule } from "@angular/material/select";
import { MatButtonModule } from "@angular/material/button";
import { MatPaginatorModule, PageEvent } from "@angular/material/paginator";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { forkJoin } from "rxjs";
import { Api } from "../core/api";
import { CatalogTable, Period, DataPage, errorText } from "../core/models";
import { DataTable, Icon } from "../shared/ui";
@Component({
  selector: "ds-data",
  imports: [
    TranslatePipe,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatButtonModule,
    MatPaginatorModule,
    MatProgressBarModule,
    DataTable,
    Icon,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow"> {{ "INFORMACIÓN PUBLICADA" | t }} </span>
        <h1>{{ "Consulta de datos" | t }}</h1>
        <p>
          {{ "Explora los registros de las versiones mensuales vigentes." | t }}
        </p>
      </div>
    </div>
    <section class="panel filter-panel">
      <form [formGroup]="form" (ngSubmit)="search()">
        <mat-form-field appearance="outline"
          ><mat-label> {{ "Tabla" | t }} </mat-label
          ><mat-select formControlName="table">
            @for (table of catalog(); track table.code) {
              <mat-option [value]="table.code"
                >{{ table.code | t }} · {{ table.name | t }}</mat-option
              >
            }
          </mat-select></mat-form-field
        ><mat-form-field appearance="outline"
          ><mat-label> {{ "Periodo" | t }} </mat-label
          ><mat-select formControlName="period"
            ><mat-option value=""> {{ "Todos los periodos" | t }} </mat-option>
            @for (period of periods(); track period.id) {
              <mat-option [value]="period.name">{{
                period.name.replace("_", " ") | t
              }}</mat-option>
            }
          </mat-select></mat-form-field
        ><button
          mat-flat-button
          type="submit"
          [disabled]="loading() || !form.controls.table.value"
        >
          <ds-icon name="search" /> {{ "Consultar" | t }}
        </button>
      </form>
    </section>
    @if (error()) {
      <div class="error-message" role="alert">{{ error() | t }}</div>
    }
    <section class="panel">
      <div class="panel-heading">
        <div>
          <h2>{{ selectedName() | t }}</h2>
          <p>{{ data().total | t }} {{ "registros encontrados" | t }}</p>
        </div>
        <span class="subtle-tag"> {{ "Solo lectura" | t }} </span>
      </div>
      @if (loading()) {
        <mat-progress-bar
          mode="indeterminate"
          [attr.aria-label]="'Consultando datos' | t"
        />
      }
      <ds-data-table
        [rows]="data().items"
        [headers]="data().headers"
        [emptyTitle]="'No hay datos para esta consulta' | t"
      /><mat-paginator
        [length]="data().total"
        [pageSize]="50"
        [pageIndex]="page()"
        [hidePageSize]="true"
        [disabled]="loading()"
        (page)="change($event)"
        [attr.aria-label]="'Paginación de datos' | t"
      />
    </section>`,
})
export class DataBrowser {
  api = inject(Api);
  destroy = inject(DestroyRef);
  fb = inject(FormBuilder);
  form = this.fb.nonNullable.group({ table: ["501"], period: [""] });
  catalog = signal<CatalogTable[]>([]);
  periods = signal<Period[]>([]);
  data = signal<DataPage>({ headers: [], items: [], total: 0 });
  loading = signal(true);
  error = signal("");
  page = signal(0);
  private selection = { table: "501", period: "" };
  constructor() {
    forkJoin({ catalog: this.api.catalog(), periods: this.api.periods() })
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.catalog.set(p.catalog);
          this.periods.set(p.periods);
          this.search();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
  selectedName() {
    const t = this.catalog().find((t) => t.code === this.selection.table);
    return t ? `${t.code} · ${t.name}` : "Registros publicados";
  }
  search() {
    this.page.set(0);
    this.selection = this.form.getRawValue();
    this.load();
  }
  change(e: PageEvent) {
    this.page.set(e.pageIndex);
    this.load();
  }
  load() {
    this.loading.set(true);
    this.error.set("");
    this.api
      .data(this.selection.table, this.selection.period, this.page() * 50)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.data.set(p);
          this.loading.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
}
