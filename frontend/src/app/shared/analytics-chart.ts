import {
  Component,
  ElementRef,
  DestroyRef,
  afterRenderEffect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from "@angular/core";
import { Chart, ChartDataset, registerables } from "chart.js";
import { I18n } from "../core/i18n";
import { sheetSource } from "../core/analytics-metadata";
import { Icon } from "./ui";

Chart.register(...registerables);
export interface ChartSeries {
  label: string;
  values: (number | null)[];
  color: string;
  type?: "line" | "bar";
}

@Component({
  selector: "ds-analytics-chart",
  imports: [Icon],
  template: `<section
    class="viz"
    [class.expanded]="expanded()"
    [attr.aria-busy]="loading()"
    (keydown.escape)="expanded.set(false)"
  >
    <header class="viz-header">
      <div class="viz-title">
        <h2>{{ title() }}</h2>
        @if (unit()) {
          <span class="chart-unit">{{ unit() }}</span>
        }
      </div>
      <div class="viz-tools">
        <button
          type="button"
          [title]="i18n.choose('Ver datos', 'View data')"
          [attr.aria-label]="
            i18n.choose('Ver datos de ', 'View data for ') + title()
          "
          [attr.aria-pressed]="table()"
          [disabled]="loading()"
          (click)="table.set(!table())"
        >
          <ds-icon name="database" />
        </button>
        <button
          type="button"
          [title]="i18n.choose('Descargar PNG', 'Download PNG')"
          [attr.aria-label]="
            i18n.choose('Descargar gráfica ', 'Download chart ') + title()
          "
          (click)="download()"
          [disabled]="loading() || table() || !hasData()"
        >
          <ds-icon name="download" />
        </button>
        <button
          type="button"
          [title]="i18n.choose('Ampliar / cerrar', 'Expand / close')"
          [attr.aria-label]="
            i18n.choose('Ampliar gráfica ', 'Expand chart ') + title()
          "
          [attr.aria-pressed]="expanded()"
          [disabled]="loading() || !hasData()"
          (click)="expanded.set(!expanded())"
        >
          <ds-icon name="grid" />
        </button>
      </div>
    </header>
    <div
      class="plot"
      [class.hidden]="table()"
      [style.height.px]="
        expanded()
          ? null
          : horizontal()
            ? Math.max(280, labels().length * 48 + 48)
            : null
      "
    >
      <canvas
        #canvas
        role="img"
        [class.chart-loading]="loading()"
        [attr.aria-hidden]="loading()"
        [attr.aria-label]="title() + '. ' + sourceLabel() + '. ' + subtitle()"
      ></canvas>
      @if (loading()) {
        <div class="chart-loading-cover" aria-hidden="true">
          <div class="loading-skeleton loading-skeleton-chart"></div>
        </div>
      } @else if (!hasData()) {
        <div class="no-chart-data">
          {{
            i18n.choose(
              "Sin datos para esta selección",
              "No data for this selection"
            )
          }}
        </div>
      }
    </div>
    @if (table()) {
      <div class="viz-table">
        @if (loading()) {
          <div
            class="loading-skeleton loading-skeleton-chart"
            aria-hidden="true"
          ></div>
        } @else {
          <table>
            <thead>
              <tr>
                <th>
                  {{ categoryLabel() || i18n.choose("Categoría", "Category") }}
                </th>
                @for (s of series(); track s.label) {
                  <th>{{ s.label }}{{ unit() ? " · " + unit() : "" }}</th>
                }
              </tr>
            </thead>
            <tbody>
              @for (label of labels(); track $index; let n = $index) {
                <tr>
                  <td>{{ label }}</td>
                  @for (s of series(); track s.label) {
                    <td>{{ valueLabel(s.values[n]) }}</td>
                  }
                </tr>
              }
            </tbody>
          </table>
        }
      </div>
    }
    @if (
      sourceSheets().length ||
      hasDetails() ||
      (!loading() && (hasMissingData() || allZero()))
    ) {
      <footer>
        @if (sourceSheets().length) {
          <p class="chart-source">{{ sourceLabel() }}</p>
        }
        @if (hasDetails()) {
          <details class="chart-details">
            <summary>{{ i18n.choose("Detalles", "Details") }}</summary>
            <div class="chart-details-body">
              @if (subtitle() && subtitle() !== unit()) {
                <p>{{ subtitle() }}</p>
              }
              @if (context()) {
                <p>{{ context() }}</p>
              }
              @if (footnote()) {
                <p>{{ footnote() }}</p>
              }
            </div>
          </details>
        }
        @if (!loading() && hasMissingData()) {
          <p class="chart-data-status">
            {{ i18n.choose("Valores sin dato", "Unavailable values") }}
          </p>
        }
        @if (!loading() && allZero()) {
          <p class="chart-data-status">
            {{ i18n.choose("Valores disponibles: 0", "Available values: 0") }}
          </p>
        }
      </footer>
    }
  </section>`,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
      }
      .viz {
        background: #fff;
        border: 1px solid #e1e6e9;
        border-radius: 6px;
        overflow: hidden;
        height: 100%;
        display: flex;
        flex-direction: column;
      }
      .viz-header {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        padding: 18px 18px 10px;
      }
      .viz-header h2 {
        font-size: 14px;
        line-height: 1.4;
        letter-spacing: 0;
      }
      .viz-title {
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 6px 10px;
        min-width: 0;
      }
      .chart-unit {
        flex: none;
        padding: 2px 6px;
        border-radius: 3px;
        background: #f1f5f6;
        color: #657984;
        font-size: 10px;
      }
      .chart-details summary {
        width: fit-content;
        cursor: pointer;
        color: #526570;
        font-size: 11px;
        padding: 4px 0;
      }
      .chart-details summary:focus-visible {
        outline: 2px solid #0a8c80;
        outline-offset: 2px;
      }
      .chart-details-body {
        display: grid;
        gap: 5px;
        margin-top: 6px;
        padding: 10px 12px;
        border-radius: 4px;
        background: #f5f8f9;
        overflow-wrap: anywhere;
      }
      .viz footer p {
        margin: 0;
        line-height: 1.6;
      }
      .viz footer .chart-data-status {
        margin-top: 4px;
        color: #526570;
      }
      .viz-tools {
        display: flex;
        gap: 2px;
        flex: none;
        align-self: flex-start;
      }
      .viz-tools button {
        border: 0;
        background: transparent;
        width: 28px;
        height: 28px;
        display: grid;
        place-items: center;
        color: #708087;
        border-radius: 3px;
      }
      .viz-tools button:hover,
      .viz-tools button[aria-pressed="true"] {
        background: #eaf4f2;
        color: #087f75;
      }
      .viz-tools ds-icon {
        width: 15px;
        height: 15px;
      }
      .plot {
        height: 255px;
        position: relative;
        padding: 8px 18px 10px;
        min-width: 0;
      }
      .plot.hidden {
        display: none;
      }
      .chart-loading {
        opacity: 0;
      }
      .chart-loading-cover {
        position: absolute;
        inset: 8px 18px 10px;
      }
      .no-chart-data {
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        color: #77818a;
        font-size: 12px;
        background: #fffffff2;
      }
      .viz footer {
        padding: 8px 18px 13px;
        color: #75818a;
        font-size: 10px;
        min-height: 30px;
        margin-top: auto;
      }
      .chart-source {
        color: #526570;
        font-size: 11px;
        overflow-wrap: anywhere;
      }
      .chart-source + .chart-details {
        margin-top: 4px;
      }
      .viz-table {
        height: 255px;
        overflow: auto;
        padding: 10px 18px;
      }
      .viz-table table {
        border-collapse: collapse;
        width: 100%;
        font-size: 12px;
      }
      .viz-table th,
      .viz-table td {
        text-align: right;
        border-bottom: 1px solid #e6ecee;
        padding: 7px;
      }
      .viz-table th:first-child,
      .viz-table td:first-child {
        text-align: left;
      }
      .expanded {
        position: fixed;
        inset: 32px;
        z-index: 100;
        box-shadow: 0 0 0 100vmax #17212cb3;
        height: auto;
      }
      .expanded .plot,
      .expanded .viz-table {
        flex: 1;
        height: auto;
        min-height: 300px;
      }
      @media (max-width: 600px) {
        .viz-header {
          padding: 14px 12px 8px;
        }
        .plot {
          padding: 8px 12px;
          height: 250px;
        }
        .expanded {
          inset: 12px;
        }
        .viz-header h2 {
          font-size: 13px;
        }
      }
    `,
  ],
})
export class AnalyticsChart {
  readonly Math = Math;
  i18n = inject(I18n);
  title = input.required<string>();
  subtitle = input("");
  sourceSheets = input<readonly string[]>([]);
  footnote = input("");
  context = input("");
  unit = input("");
  categoryLabel = input("");
  loading = input(false);
  type = input<"bar" | "line" | "doughnut">("bar");
  horizontal = input(false);
  stacked = input(false);
  labels = input<string[]>([]);
  series = input<ChartSeries[]>([]);
  selected = output<number>();
  table = signal(false);
  expanded = signal(false);
  sourceLabel() {
    return sheetSource(this.sourceSheets(), this.i18n.language());
  }
  private canvas = viewChild<ElementRef<HTMLCanvasElement>>("canvas");
  private chart?: Chart;
  private signature = "";
  constructor() {
    const beforePrint = () => this.chart?.resize(480, 260);
    const afterPrint = () => this.chart?.resize();
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);
    inject(DestroyRef).onDestroy(() => {
      this.chart?.destroy();
      window.removeEventListener("beforeprint", beforePrint);
      window.removeEventListener("afterprint", afterPrint);
    });
    afterRenderEffect(() => {
      const canvas = this.canvas()?.nativeElement;
      const labels = this.labels();
      const series = this.series();
      const type = this.type();
      const horizontal = this.horizontal();
      const stacked = this.stacked();
      const locale = this.i18n.locale();
      const table = this.table();
      const expanded = this.expanded();
      const unit = this.unit();
      if (!canvas || table) return;
      const signature = JSON.stringify({
        labels,
        series,
        type,
        horizontal,
        stacked,
        locale,
        table,
        expanded,
        unit,
      });
      if (signature === this.signature) return;
      this.signature = signature;
      this.chart?.destroy();
      const colors = [
        "#11998b",
        "#447ec0",
        "#edb447",
        "#8b70ae",
        "#da7667",
        "#5eb3c4",
        "#7c9d60",
        "#a5aeb7",
        "#d0d6dc",
      ];
      this.chart = new Chart(canvas, {
        type,
        data: {
          labels,
          datasets: series.map(
            (s) =>
              ({
                label: s.label,
                data: s.values,
                type: s.type || type,
                backgroundColor:
                  type === "doughnut"
                    ? colors
                    : s.type === "line" || type === "line"
                      ? s.color + "16"
                      : s.color,
                borderColor: type === "doughnut" ? "#fff" : s.color,
                borderWidth: type === "doughnut" ? 3 : 2,
                borderRadius: type === "bar" ? 3 : 0,
                maxBarThickness: horizontal ? 24 : 30,
                pointRadius: 3,
                pointHoverRadius: 5,
                tension: 0,
                fill: false,
                spanGaps: false,
              }) as ChartDataset,
          ),
        },
        options: {
          locale,
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: {
            mode: "index",
            intersect: false,
            axis: horizontal ? "y" : "x",
          },
          indexAxis: horizontal ? "y" : "x",
          onClick: (_, elements) => {
            if (elements.length) this.selected.emit(elements[0].index);
          },
          plugins: {
            legend: {
              display: series.length > 1 || type === "doughnut",
              position: "bottom",
              labels: {
                usePointStyle: true,
                pointStyle: "circle",
                boxWidth: 7,
                boxHeight: 7,
                padding: 17,
                color: "#596770",
                font: { size: 11 },
              },
            },
            tooltip: {
              backgroundColor: "#263039",
              padding: 12,
              cornerRadius: 4,
              callbacks: {
                label: (ctx) =>
                  `${ctx.dataset.label}: ${this.valueLabel(
                    horizontal
                      ? ctx.parsed.x
                      : type === "doughnut"
                        ? Number(ctx.parsed)
                        : ctx.parsed.y,
                  )}${unit ? " " + unit : ""}`,
              },
            },
          },
          ...(type === "doughnut"
            ? { cutout: "73%" }
            : {
                scales: {
                  x: {
                    stacked,
                    beginAtZero: horizontal,
                    title: {
                      display: horizontal && !!unit,
                      text: unit,
                      color: "#526570",
                    },
                    grid: { display: horizontal, color: "#edf0f3" },
                    border: { display: false },
                    ticks: {
                      precision: this.decimalPlaces(),
                      color: "#76838c",
                      font: { size: 10 },
                      maxRotation: 0,
                      callback: horizontal
                        ? (v) =>
                            new Intl.NumberFormat(locale, {
                              notation: "compact",
                            }).format(Number(v))
                        : (v) => labels[Number(v)],
                    },
                  },
                  y: {
                    stacked,
                    beginAtZero: true,
                    title: {
                      display: !horizontal && !!unit,
                      text: unit,
                      color: "#526570",
                    },
                    grid: { display: !horizontal, color: "#edf0f3" },
                    border: { display: false },
                    ticks: {
                      autoSkip: !horizontal,
                      precision: this.decimalPlaces(),
                      color: "#76838c",
                      font: { size: 10 },
                      callback: !horizontal
                        ? (v) =>
                            new Intl.NumberFormat(locale, {
                              notation: "compact",
                            }).format(Number(v))
                        : (v) => {
                            const label = labels[Number(v)] || "";
                            // Keep the distinguishing code and wrap its description.
                            const words = label.split(" ");
                            const lines: string[] = [];
                            for (const word of words) {
                              const last = lines.length - 1;
                              if (
                                last < 0 ||
                                (lines[last] + " " + word).length > 25
                              )
                                lines.push(word);
                              else lines[last] += " " + word;
                            }
                            return lines;
                          },
                    },
                  },
                },
              }),
        },
      });
    });
  }
  hasData() {
    return this.series().some((s) =>
      s.values.some((v) => v != null && Number.isFinite(v)),
    );
  }
  hasDetails() {
    return !!(
      (this.subtitle() && this.subtitle() !== this.unit()) ||
      this.context() ||
      this.footnote()
    );
  }
  hasMissingData() {
    return this.series().some((s) =>
      this.labels().some(
        (_, n) => s.values[n] == null || !Number.isFinite(s.values[n]),
      ),
    );
  }
  allZero() {
    return (
      this.hasData() &&
      this.series().every((s) => s.values.every((v) => v == null || v === 0))
    );
  }
  decimalPlaces() {
    return ["USD", "MXN"].includes(this.unit())
      ? 2
      : this.unit() === "%"
        ? 1
        : 0;
  }
  valueLabel(value: number | null | undefined) {
    return value == null || !Number.isFinite(value)
      ? this.i18n.choose("Sin dato", "Unavailable")
      : new Intl.NumberFormat(this.i18n.locale(), {
          minimumFractionDigits: this.decimalPlaces(),
          maximumFractionDigits: this.decimalPlaces(),
        }).format(value);
  }
  download() {
    if (
      !this.chart ||
      this.loading() ||
      this.table() ||
      !this.chart.canvas.width ||
      !this.hasData()
    )
      return;
    // Exports keep scope and source notes from the optional details panel.
    const source = this.chart.canvas;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(900, source.width);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.font = "16px Arial";
    const wrap = (text: string) => {
      const lines: string[] = [];
      for (const word of text.split(/\s+/)) {
        const n = lines.length - 1;
        if (
          n < 0 ||
          ctx.measureText(lines[n] + " " + word).width > canvas.width - 48
        )
          lines.push(word);
        else lines[n] += " " + word;
      }
      return lines;
    };
    const header = [
      this.title(),
      this.sourceLabel(),
      this.subtitle(),
      this.context(),
    ]
      .filter(Boolean)
      .flatMap(wrap);
    const footer = wrap(
      [
        this.footnote(),
        this.hasMissingData()
          ? this.i18n.choose(
              "Sin dato no equivale a cero.",
              "Unavailable is not zero.",
            )
          : "",
      ]
        .filter(Boolean)
        .join(" "),
    );
    const chartHeight = source.height * (canvas.width / source.width);
    canvas.height = chartHeight + (header.length + footer.length) * 24 + 64;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#25343d";
    ctx.font = "16px Arial";
    header.forEach((line, n) => ctx.fillText(line, 24, 28 + n * 24));
    ctx.drawImage(
      source,
      0,
      header.length * 24 + 24,
      canvas.width,
      chartHeight,
    );
    footer.forEach((line, n) =>
      ctx.fillText(line, 24, header.length * 24 + chartHeight + 48 + n * 24),
    );
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `DataStage-${this.title().replace(/[^\p{L}\p{N}]+/gu, "-")}.png`;
    a.click();
  }
}
