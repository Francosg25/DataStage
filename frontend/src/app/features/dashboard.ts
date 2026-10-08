import { TranslatePipe, LocalizedNumberPipe } from "../core/i18n";
import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  ViewChild,
  inject,
  signal,
  effect,
} from "@angular/core";
import { RouterLink } from "@angular/router";
import { FormsModule } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Chart, registerables } from "chart.js";
import { Api } from "../core/api";
import { Overview, errorText } from "../core/models";
import { Icon, Empty, RunList } from "../shared/ui";
import { I18n } from "../core/i18n";
Chart.register(...registerables);
@Component({
  selector: "ds-dashboard",
  imports: [
    TranslatePipe,
    FormsModule,
    LocalizedNumberPipe,
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    Icon,
    Empty,
    RunList,
  ],
  template: `
    <div class="page-heading">
      <div>
        <span class="eyebrow"> {{ "VISTA GENERAL" | t }} </span>
        <h1>
          {{ i18n.choose("Resumen operativo", "Operations overview") }}
        </h1>
        <p>
          {{
            i18n.choose(
              "Estado de cargas y versiones publicadas",
              "Upload and published-version status"
            )
          }}
        </p>
      </div>
      <a mat-flat-button routerLink="/monthly"
        ><ds-icon name="upload" /> {{ "Nueva carga mensual" | t }}
      </a>
    </div>
    @if (error()) {
      <div class="error-message" role="alert">
        {{ error() | t }}
        <button mat-button (click)="load()">{{ "Reintentar" | t }}</button>
      </div>
    }
    @if (loading()) {
      <mat-progress-bar
        mode="indeterminate"
        [attr.aria-label]="'Cargando resumen' | t"
      />
    }
    <div class="stats-grid">
      @for (card of cards(); track card.label) {
        <article class="stat-card">
          <div class="stat-top">
            <span>{{ card.label | t }}</span
            ><span class="stat-icon"><ds-icon [name]="card.icon" /></span>
          </div>
          <strong>{{
            (card.value === null ? "—" : (card.value | dsNumber)) | t
          }}</strong
          ><small>{{ card.description | t }}</small>
        </article>
      }
    </div>
    <div class="dashboard-columns">
      <section class="panel chart-panel">
        <div class="panel-heading">
          <div>
            <h2>{{ "Actividad por periodo" | t }}</h2>
            <p>{{ "Registros procesados en las cargas publicadas" | t }}</p>
          </div>
          <select
            class="activity-limit"
            [attr.aria-label]="i18n.choose('Meses visibles', 'Visible months')"
            [ngModel]="monthLimit()"
            (ngModelChange)="monthLimit.set(+$event)"
          >
            @for (count of [3, 6, 12]; track count) {
              <option [ngValue]="count">
                {{ i18n.choose("Últimos", "Latest") }} {{ count }}
                {{ i18n.choose("meses publicados", "published months") }}
              </option>
            }
          </select>
        </div>
        <div
          class="chart-container"
          [class.chart-empty]="!overview()?.monthly?.length"
        >
          <canvas
            #chart
            [attr.aria-label]="
              'Gráfico de registros procesados por periodo' | t
            "
            role="img"
          ></canvas>
          @if (!loading() && !overview()?.monthly?.length) {
            <ds-empty
              [title]="'Aún no hay actividad' | t"
              [message]="
                'Los periodos publicados darán forma a este gráfico.' | t
              "
              icon="calendar"
            />
          }
        </div>
      </section>
      <section class="panel next-panel">
        <span class="eyebrow"> {{ "TU FLUJO DE TRABAJO" | t }} </span>
        <h2>{{ i18n.choose("Cargas y resultados", "Uploads and results") }}</h2>
        <div class="workflow-step">
          <span>01</span>
          <div>
            <strong> {{ "Selecciona el periodo" | t }} </strong>
            <p>{{ "Cada carga corresponde a un mes." | t }}</p>
          </div>
        </div>
        <div class="workflow-step">
          <span>02</span>
          <div>
            <strong> {{ "Adjunta tu archivo ZIP" | t }} </strong>
            <p>{{ "Validamos y organizamos los ASC." | t }}</p>
          </div>
        </div>
        <div class="workflow-step">
          <span>03</span>
          <div>
            <strong> {{ "Consulta los resultados" | t }} </strong>
            <p>{{ "Revisa incidencias y descarga Excel." | t }}</p>
          </div>
        </div>
        <a routerLink="/monthly" class="text-link">
          {{ "Comenzar una carga" | t }} <ds-icon name="arrow"
        /></a>
      </section>
    </div>
    <section class="panel">
      <div class="panel-heading">
        <div>
          <h2>{{ "Procesos recientes" | t }}</h2>
          <p>{{ "El estado de tus últimas ejecuciones" | t }}</p>
        </div>
        <a mat-button routerLink="/runs">
          {{ "Ver historial" | t }} <ds-icon name="arrow"
        /></a>
      </div>
      <ds-run-list [runs]="overview()?.recentRuns || []" />
    </section>
  `,
  styles: [
    `
      .activity-limit {
        max-width: 100%;
        min-height: 36px;
        padding: 6px 28px 6px 10px;
        border: 1px solid #b9c9cc;
        border-radius: 4px;
        background: white;
        color: #234c57;
        font-size: 12px;
      }
      .panel-heading {
        flex-wrap: wrap;
        gap: 12px;
      }
    `,
  ],
})
export class Dashboard implements AfterViewInit {
  i18n = inject(I18n);
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  @ViewChild("chart") canvas?: ElementRef<HTMLCanvasElement>;
  private chart?: Chart;
  overview = signal<Overview | null>(null);
  loading = signal(true);
  error = signal("");
  monthLimit = signal(6);
  visibleMonths() {
    // The API returns published periods in ascending year/month order.
    return (this.overview()?.monthly || []).slice(-this.monthLimit());
  }
  constructor() {
    effect(() => {
      this.i18n.language();
      this.monthLimit();
      this.render();
    });
    this.destroy.onDestroy(() => this.chart?.destroy());
    this.load();
  }
  cards() {
    const d = this.overview();
    return [
      {
        label: "Periodos publicados",
        value: d?.periodsCount ?? null,
        icon: "calendar",
        description: "Información disponible para consulta",
      },
      {
        label: "Registros procesados",
        value: d?.rowsCount ?? null,
        icon: "database",
        description: "Volumen total de datos publicados",
      },
      {
        label: "Ejecuciones",
        value: d?.runsCount ?? null,
        icon: "history",
        description: "Historial mensual y anual",
      },
      {
        label: "Observaciones",
        value: d ? d.warningCount + d.errorCount : null,
        icon: "alert",
        description: "Advertencias y errores registrados",
      },
    ];
  }
  load() {
    this.loading.set(true);
    this.error.set("");
    this.api
      .overview()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (d) => {
          this.overview.set(d);
          this.loading.set(false);
          this.render();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
  ngAfterViewInit() {
    this.render();
  }
  private render() {
    if (!this.canvas) return;
    this.chart?.destroy();
    const rows = this.visibleMonths();
    this.chart = new Chart(this.canvas.nativeElement, {
      type: "bar",
      data: {
        labels: rows.map((r) => this.i18n.t(r.period.replace("_", " "))),
        datasets: [
          {
            label: this.i18n.t("Registros"),
            data: rows.map((r) => r.rows),
            backgroundColor: "#14968b",
            hoverBackgroundColor: "#0d756c",
            borderRadius: 5,
            maxBarThickness: 38,
          },
        ],
      },
      options: {
        locale: this.i18n.locale(),
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#75828a", font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            border: { display: false },
            grid: { color: "#edf1f3" },
            ticks: { color: "#75828a", precision: 0, font: { size: 11 } },
          },
        },
      },
    });
  }
}
