import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  ViewChild,
  inject,
  signal,
} from "@angular/core";
import { DecimalPipe } from "@angular/common";
import { RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Chart, registerables } from "chart.js";
import { Api } from "../core/api";
import { Overview, errorText } from "../core/models";
import { Icon, Empty, RunList } from "../shared/ui";
Chart.register(...registerables);
@Component({
  selector: "ds-dashboard",
  imports: [
    DecimalPipe,
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
        <span class="eyebrow">VISTA GENERAL</span>
        <h1>
          El control de tus datos,<br class="desktop-break" />
          en un solo lugar.
        </h1>
        <p>Supervisa tus cargas, valida resultados y consulta cada periodo.</p>
      </div>
      <a mat-flat-button routerLink="/monthly"
        ><ds-icon name="upload" /> Nueva carga mensual</a
      >
    </div>
    @if (error()) {
      <div class="error-message" role="alert">
        {{ error() }} <button mat-button (click)="load()">Reintentar</button>
      </div>
    }
    @if (loading()) {
      <mat-progress-bar mode="indeterminate" aria-label="Cargando resumen" />
    }
    <div class="stats-grid">
      @for (card of cards(); track card.label) {
        <article class="stat-card">
          <div class="stat-top">
            <span>{{ card.label }}</span
            ><span class="stat-icon"><ds-icon [name]="card.icon" /></span>
          </div>
          <strong>{{
            card.value === null ? "—" : (card.value | number)
          }}</strong
          ><small>{{ card.description }}</small>
        </article>
      }
    </div>
    <div class="dashboard-columns">
      <section class="panel chart-panel">
        <div class="panel-heading">
          <div>
            <h2>Actividad por periodo</h2>
            <p>Registros procesados en las cargas publicadas</p>
          </div>
          <span class="subtle-tag">Mensual</span>
        </div>
        <div
          class="chart-container"
          [class.chart-empty]="!overview()?.monthly?.length"
        >
          <canvas
            #chart
            aria-label="Gráfico de registros procesados por periodo"
            role="img"
          ></canvas>
          @if (!loading() && !overview()?.monthly?.length) {
            <ds-empty
              title="Aún no hay actividad"
              message="Los periodos publicados darán forma a este gráfico."
              icon="calendar"
            />
          }
        </div>
      </section>
      <section class="panel next-panel">
        <span class="eyebrow">TU FLUJO DE TRABAJO</span>
        <h2>Del archivo<br />al dato confiable.</h2>
        <div class="workflow-step">
          <span>01</span>
          <div>
            <strong>Selecciona el periodo</strong>
            <p>Cada carga corresponde a un mes.</p>
          </div>
        </div>
        <div class="workflow-step">
          <span>02</span>
          <div>
            <strong>Adjunta tu archivo ZIP</strong>
            <p>Validamos y organizamos los ASC.</p>
          </div>
        </div>
        <div class="workflow-step">
          <span>03</span>
          <div>
            <strong>Consulta los resultados</strong>
            <p>Revisa incidencias y descarga Excel.</p>
          </div>
        </div>
        <a routerLink="/monthly" class="text-link"
          >Comenzar una carga <ds-icon name="arrow"
        /></a>
      </section>
    </div>
    <section class="panel">
      <div class="panel-heading">
        <div>
          <h2>Procesos recientes</h2>
          <p>El estado de tus últimas ejecuciones</p>
        </div>
        <a mat-button routerLink="/runs"
          >Ver historial <ds-icon name="arrow"
        /></a>
      </div>
      <ds-run-list [runs]="overview()?.recentRuns || []" />
    </section>
  `,
})
export class Dashboard implements AfterViewInit {
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  @ViewChild("chart") canvas?: ElementRef<HTMLCanvasElement>;
  private chart?: Chart;
  overview = signal<Overview | null>(null);
  loading = signal(true);
  error = signal("");
  constructor() {
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
    const rows = this.overview()?.monthly || [];
    this.chart = new Chart(this.canvas.nativeElement, {
      type: "bar",
      data: {
        labels: rows.map((r) => r.period.replace("_", " ")),
        datasets: [
          {
            label: "Registros",
            data: rows.map((r) => r.rows),
            backgroundColor: "#14968b",
            hoverBackgroundColor: "#0d756c",
            borderRadius: 5,
            maxBarThickness: 38,
          },
        ],
      },
      options: {
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
