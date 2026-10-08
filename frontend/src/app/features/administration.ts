import { TranslatePipe } from "../core/i18n";
import { Component, DestroyRef, inject, signal } from "@angular/core";
import { MatTabsModule } from "@angular/material/tabs";
import { MatButtonModule } from "@angular/material/button";
import { MatPaginatorModule, PageEvent } from "@angular/material/paginator";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { CatalogTable, DataRow, errorText } from "../core/models";
import { DataTable, Icon } from "../shared/ui";
import { EntraSetup } from "./entra-setup";
@Component({
  selector: "ds-administration",
  imports: [
    EntraSetup,
    TranslatePipe,
    MatTabsModule,
    MatButtonModule,
    MatPaginatorModule,
    MatProgressBarModule,
    DataTable,
    Icon,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow"> {{ "CONFIGURACIÓN Y GOBIERNO" | t }} </span>
        <h1>{{ "Administración" | t }}</h1>
        <p>
          {{
            "Consulta el entorno, el catálogo de tablas y la actividad registrada."
              | t
          }}
        </p>
      </div>
      <span class="subtle-tag">
        {{ "Configuración de solo lectura" | t }}
      </span>
    </div>
    <section class="panel">
      <mat-tab-group
        animationDuration="0ms"
        (selectedIndexChange)="tabChanged($event)"
        ><mat-tab [label]="'Entorno' | t"
          ><div class="settings-grid">
            <div class="setting">
              <span> {{ "Entorno" | t }} </span
              ><strong>{{ auth.config()?.environment | t }}</strong>
            </div>
            <div class="setting">
              <span> {{ "Motor de procesamiento" | t }} </span
              ><strong>{{ auth.config()?.engineVersion | t }}</strong>
            </div>
            <div class="setting">
              <span> {{ "Autenticación" | t }} </span
              ><strong>{{
                (auth.config()?.authMode === "entra"
                  ? "Microsoft Entra ID SSO"
                  : "Desarrollo local"
                ) | t
              }}</strong>
            </div>
            <div class="setting">
              <span> {{ "Ámbito de datos" | t }} </span
              ><strong>{{ auth.config()?.scopeId | t }}</strong>
            </div>
            <div class="setting">
              <span> {{ "Tamaño máximo de carga" | t }} </span
              ><strong
                >{{ auth.config()?.maxUploadMb | t }} {{ "MB" | t }}
              </strong>
            </div>
            <div class="setting">
              <span> {{ "Microsoft Foundry" | t }} </span
              ><strong>{{
                (auth.config()?.foundryEnabled
                  ? "Habilitado"
                  : "Sin configurar"
                ) | t
              }}</strong>
            </div>
          </div>
          <div class="settings-note">
            <ds-icon name="shield" />
            <p>
              {{
                "Los cambios de configuración se realizan mediante las variables del entorno y el proceso de despliegue autorizado."
                  | t
              }}
            </p>
          </div>
          <ds-entra-setup /></mat-tab
        ><mat-tab [label]="'Catálogo de tablas' | t"
          ><div class="panel-heading">
            <div>
              <h2>{{ "Tablas reconocidas" | t }}</h2>
              <p>
                {{ catalog().length | t }}
                {{ "códigos y su orden oficial de exportación" | t }}
              </p>
            </div>
          </div>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>{{ "Orden" | t }}</th>
                  <th>{{ "Código" | t }}</th>
                  <th>{{ "Nombre de hoja" | t }}</th>
                </tr>
              </thead>
              <tbody>
                @for (table of catalog(); track table.code) {
                  <tr>
                    <td>{{ table.order | t }}</td>
                    <td class="mono">{{ table.code | t }}</td>
                    <td>{{ table.name | t }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div></mat-tab
        ><mat-tab [label]="'Auditoría' | t"
          ><div class="panel-heading">
            <div>
              <h2>{{ "Actividad registrada" | t }}</h2>
              <p>{{ "Acciones de usuarios y del sistema" | t }}</p>
            </div>
            <button
              mat-stroked-button
              (click)="loadAudit()"
              [disabled]="loading()"
            >
              {{ "Actualizar" | t }}
            </button>
          </div>
          @if (loading()) {
            <mat-progress-bar
              mode="indeterminate"
              [attr.aria-label]="'Cargando auditoría' | t"
            />
          }
          <ds-data-table
            [rows]="audit()"
            [emptyTitle]="'Sin eventos de auditoría' | t" /><mat-paginator
            [length]="total()"
            [pageSize]="50"
            [pageIndex]="page()"
            [hidePageSize]="true"
            [disabled]="loading()"
            (page)="changePage($event)"
            [attr.aria-label]="'Paginación de auditoría' | t" /></mat-tab
      ></mat-tab-group>
    </section>
    @if (error()) {
      <div class="error-message" role="alert">{{ error() | t }}</div>
    }`,
})
export class Administration {
  api = inject(Api);
  auth = inject(Auth);
  destroy = inject(DestroyRef);
  catalog = signal<CatalogTable[]>([]);
  audit = signal<DataRow[]>([]);
  error = signal("");
  loading = signal(false);
  total = signal(0);
  page = signal(0);
  constructor() {
    this.api
      .catalog()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (t) => this.catalog.set(t),
        error: (e) => this.error.set(errorText(e)),
      });
  }
  tabChanged(index: number) {
    this.error.set("");
    if (index === 2) this.loadAudit();
  }
  changePage(e: PageEvent) {
    this.page.set(e.pageIndex);
    this.loadAudit();
  }
  loadAudit() {
    this.loading.set(true);
    this.error.set("");
    this.api
      .audit(this.page() * 50)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.audit.set(p.items);
          this.total.set(p.total);
          this.loading.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
}
