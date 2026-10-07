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
    (keydown.escape)="expanded.set(false)"
  >
    <header class="viz-header">
      <div>
        <h2>{{ title() }}</h2>
        <p>{{ subtitle() }}</p>
      </div>
      <div class="viz-tools">
        <button
          type="button"
          [title]="i18n.choose('Ver datos', 'View data')"
          [attr.aria-label]="
            i18n.choose('Ver datos de ', 'View data for ') + title()
          "
          [attr.aria-pressed]="table()"
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
          (click)="expanded.set(!expanded())"
        >
          <ds-icon name="grid" />
        </button>
      </div>
    </header>
    <div class="plot" [class.hidden]="table()">
      <canvas
        #canvas
        role="img"
        [attr.aria-label]="title() + '. ' + subtitle()"
      ></canvas>
      @if (!hasData()) {
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
        <table>
          <thead>
            <tr>
              <th>{{ i18n.choose("Categoría", "Category") }}</th>
              @for (s of series(); track s.label) {
                <th>{{ s.label }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (label of labels(); track $index; let n = $index) {
              <tr>
                <td>{{ label }}</td>
                @for (s of series(); track s.label) {
                  <td>{{ i18n.number(s.values[n], false, 2) }}</td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
    <footer>{{ footnote() }}</footer>
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
      .viz-header p {
        font-size: 11px;
        margin-top: 3px;
        line-height: 1.5;
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
  i18n = inject(I18n);
  title = input.required<string>();
  subtitle = input("");
  footnote = input("");
  type = input<"bar" | "line" | "doughnut">("bar");
  horizontal = input(false);
  stacked = input(false);
  labels = input<string[]>([]);
  series = input<ChartSeries[]>([]);
  selected = output<number>();
  table = signal(false);
  expanded = signal(false);
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
      if (!canvas) return;
      const signature = JSON.stringify({
        labels,
        series,
        type,
        horizontal,
        stacked,
        locale,
        table,
        expanded,
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
                tension: 0.28,
                fill: type === "line",
                spanGaps: false,
              }) as ChartDataset,
          ),
        },
        options: {
          locale,
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
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
                  `${ctx.dataset.label}: ${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(Number(horizontal ? ctx.parsed.x : type === "doughnut" ? ctx.parsed : ctx.parsed.y))}`,
              },
            },
          },
          ...(type === "doughnut"
            ? { cutout: "73%" }
            : {
                scales: {
                  x: {
                    stacked,
                    grid: { display: horizontal, color: "#edf0f3" },
                    border: { display: false },
                    ticks: {
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
                    grid: { display: !horizontal, color: "#edf0f3" },
                    border: { display: false },
                    ticks: {
                      color: "#76838c",
                      font: { size: 10 },
                      callback: !horizontal
                        ? (v) =>
                            new Intl.NumberFormat(locale, {
                              notation: "compact",
                            }).format(Number(v))
                        : (v) => {
                            const label = labels[Number(v)] || "";
                            return label.length > 24
                              ? label.slice(0, 22) + "…"
                              : label;
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
      s.values.some((v) => v != null),
    );
  }
  download() {
    if (!this.chart) return;
    const a = document.createElement("a");
    a.href = this.chart.toBase64Image();
    a.download = "DataStage-chart.png";
    a.click();
  }
}
