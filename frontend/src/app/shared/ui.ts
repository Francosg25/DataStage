import {
  TranslatePipe,
  LocalizedNumberPipe,
  LocalizedDatePipe,
} from "../core/i18n";
import { Component, input, computed } from "@angular/core";
import { RouterLink } from "@angular/router";
import { Run, DataRow, runLabel } from "../core/models";
@Component({
  selector: "ds-icon",
  template: `<svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path [attr.d]="path()" />
  </svg>`,
  styles: [
    `
      :host {
        display: inline-flex;
        width: 20px;
        height: 20px;
        flex: none;
      }
      svg {
        width: 100%;
        height: 100%;
      }
    `,
  ],
})
export class Icon {
  name = input("grid");
  path = computed(
    () =>
      (
        ({
          grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
          upload: "M12 16V3m-5 5 5-5 5 5 M4 15v6h16v-6",
          history: "M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v5l3 2",
          calendar:
            "M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2 M8 18h2",
          database:
            "M20 5c0 2-4 3-8 3S4 7 4 5s4-3 8-3 8 1 8 3z M4 5v14c0 2 4 3 8 3s8-1 8-3V5 M4 12c0 2 4 3 8 3s8-1 8-3",
          spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
          settings:
            "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
          arrow: "M5 12h14 M13 6l6 6-6 6",
          download: "M12 3v12m-5-5 5 5 5-5 M4 16v5h16v-5",
          check: "m5 12 4 4 10-10",
          menu: "M4 6h16 M4 12h16 M4 18h16",
          file: "M6 2h8l4 4v16H6z M14 2v5h4 M9 12h6 M9 16h6",
          shield: "M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6z m-5 10 3 3 7-7",
          logout: "M9 4H4v16h5 M10 12h11 M17 8l4 4-4 4",
          chevron: "m9 5 7 7-7 7",
          alert: "M12 3 2 21h20z M12 9v5 M12 18h.01",
          search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 m5 12 6 6",
        }) as Record<string, string>
      )[this.name()] || "",
  );
}
export function statusLabel(value: string | null | undefined): string {
  if (!value) return "Pendiente";
  return (
    (
      {
        NEEDS_ATTENTION: "Requiere revisión",
        QUEUED: "En cola",
        PENDING: "Pendiente",
        RUNNING: "Procesando",
        PROCESSING: "Procesando",
        COMPLETED: "Completado",
        SUCCEEDED: "Completado",
        FAILED: "Fallido",
        ERROR: "Error",
        WARNING: "Con observaciones",
        OK: "Correcto",
        READY: "Disponible",
        PUBLISHED: "Publicado",
        UNPUBLISHED: "Sin publicar",
        NOT_STARTED: "Pendiente",
        CANCELLED: "Cancelado",
        SKIPPED: "Omitido",
        SUCCESS: "Correcto",
      } as Record<string, string>
    )[value.toUpperCase()] || value
  );
}
@Component({
  selector: "ds-status",
  imports: [TranslatePipe],
  template: `<span
    class="status"
    [class.status-ok]="good()"
    [class.status-bad]="bad()"
    [class.status-warn]="warn()"
    ><span class="status-dot"></span>{{ label() | t }}</span
  >`,
})
export class Status {
  value = input<string | null | undefined>("");
  label = computed(() => statusLabel(this.value()));
  good = computed(() =>
    ["OK", "COMPLETED", "SUCCEEDED", "READY", "PUBLISHED", "SUCCESS"].includes(
      this.value()?.toUpperCase() || "",
    ),
  );
  bad = computed(() =>
    ["ERROR", "FAILED"].includes(this.value()?.toUpperCase() || ""),
  );
  warn = computed(() =>
    ["WARNING", "SKIPPED"].includes(this.value()?.toUpperCase() || ""),
  );
}
@Component({
  selector: "ds-empty",
  imports: [TranslatePipe, Icon],
  template: `<div class="empty-state">
    <div class="empty-icon"><ds-icon [name]="icon()" /></div>
    <h3>{{ title() | t }}</h3>
    <p>{{ message() | t }}</p>
    <ng-content />
  </div>`,
})
export class Empty {
  title = input("Todavía no hay datos");
  message = input(
    "Los resultados aparecerán aquí cuando completes tu primera carga.",
  );
  icon = input("database");
}
@Component({
  selector: "ds-run-list",
  imports: [
    TranslatePipe,
    RouterLink,
    LocalizedDatePipe,
    LocalizedNumberPipe,
    Status,
    Icon,
    Empty,
  ],
  template: `@if (runs().length) {
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ "Periodo / ejecución" | t }}</th>
              <th>{{ "Tipo" | t }}</th>
              <th>{{ "Estado" | t }}</th>
              <th class="numeric">{{ "Registros" | t }}</th>
              <th>{{ "Fecha de carga" | t }}</th>
              <th>
                <span class="sr-only"> {{ "Detalle" | t }} </span>
              </th>
            </tr>
          </thead>
          <tbody>
            @for (run of runs(); track run.id) {
              <tr>
                <td>
                  <a [routerLink]="['/runs', run.id]" class="table-title">{{
                    label(run) | t
                  }}</a>
                  <div class="muted mono">{{ run.id.slice(0, 8) | t }}</div>
                </td>
                <td>
                  {{
                    (run.kind.toUpperCase() === "ANNUAL" ? "Anual" : "Mensual")
                      | t
                  }}
                </td>
                <td>
                  <ds-status [value]="run.functionalResult || run.status" />
                </td>
                <td class="numeric">{{ run.counts.rows | dsNumber | t }}</td>
                <td class="muted">
                  {{ run.createdAt | dsDate: "dd MMM yyyy, HH:mm" | t }}
                </td>
                <td>
                  <a
                    [routerLink]="['/runs', run.id]"
                    class="icon-link"
                    [attr.aria-label]="'Ver ejecución ' + label(run) | t"
                    ><ds-icon name="chevron"
                  /></a>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    } @else {
      <ds-empty
        [title]="'Tu historial comienza aquí' | t"
        [message]="'Carga un archivo ZIP para procesar tu primer periodo.' | t"
      />
    }`,
})
export class RunList {
  runs = input<Run[]>([]);
  label = runLabel;
}
@Component({
  selector: "ds-data-table",
  imports: [TranslatePipe, Empty],
  template: `@if (rows().length) {
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              @for (key of columns(); track key) {
                <th>{{ label(key) | t }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (row of rows(); track $index) {
              <tr>
                @for (key of columns(); track key) {
                  <td [title]="display(row[key]) | t">
                    {{ display(row[key]) }}
                  </td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
    } @else {
      <ds-empty
        [title]="emptyTitle() | t"
        [message]="'No hay registros para esta selección.' | t"
      />
    }`,
})
export class DataTable {
  rows = input<DataRow[]>([]);
  headers = input<string[]>([]);
  emptyTitle = input("Sin registros");
  columns = computed(() =>
    this.headers().length
      ? this.headers()
      : Array.from(new Set(this.rows().flatMap((r) => Object.keys(r)))),
  );
  label(key: string): string {
    return (
      (
        {
          id: "Identificador",
          fileName: "Archivo",
          tableCode: "Tabla",
          status: "Estado",
          message: "Mensaje",
          rowCount: "Filas",
          columnCount: "Columnas",
          dateColumnCount: "Columnas fecha",
          sheetName: "Hoja de Excel",
          headers: "Encabezados",
          severity: "Severidad",
          code: "Código",
          fileId: "Archivo de origen",
          rowNumber: "Fila",
          columnName: "Columna",
          actor: "Actor",
          action: "Acción",
          runId: "Ejecución",
          details: "Detalle",
          createdAt: "Fecha y hora",
        } as Record<string, string>
      )[key] || key
    );
  }
  display(value: unknown): string {
    if (value === null || value === undefined) return "—";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }
}
