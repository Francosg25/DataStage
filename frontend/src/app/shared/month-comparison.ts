import { Component, DestroyRef, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Subject, catchError, forkJoin, of, switchMap, tap } from "rxjs";
import { Api } from "../core/api";
import {
  AnalyticsFilters,
  AnalyticsOptions,
  AnalyticsReport,
} from "../core/analytics";
import { I18n } from "../core/i18n";
import { errorText } from "../core/models";
import { AnalyticsChart, ChartSeries } from "./analytics-chart";

@Component({
  selector: "ds-month-comparison",
  imports: [FormsModule, AnalyticsChart],
  template: `
    <div class="selectors">
      <label
        >{{ t("Fuente", "Source")
        }}<select [(ngModel)]="source" (ngModelChange)="sourceChanged()">
          @for (s of options()?.sources || []; track s.id) {
            <option [value]="s.id">
              {{
                s.id === "reference"
                  ? t("Excel de referencia", "Reference workbook")
                  : t("Cargas publicadas", "Published runs")
              }}
            </option>
          }
        </select></label
      >
      @for (side of dateSides; track side.key) {
        <fieldset class="date-selector"><legend>{{ t(side.es,side.en) }}</legend>
          <div class="date-fields">
            <select [attr.aria-label]="t(side.es,side.en)" [ngModel]="datePart(this[side.key],1)" (ngModelChange)="setDate(side.key,1,$event)">
              @for (m of months; track m) { <option [ngValue]="m">{{ i18n.month(m) }}</option> }
            </select>
            <input type="number" [attr.aria-label]="t(side.yearEs,side.yearEn)" [ngModel]="datePart(this[side.key],0)" (ngModelChange)="setDate(side.key,0,$event)" min="1900" max="2100" />
          </div>
        </fieldset>
      }
      <label
        >{{ t("Moneda", "Currency")
        }}<select [(ngModel)]="currency" (ngModelChange)="load()">
          <option>USD</option>
          <option>MXN</option>
        </select></label
      >
    </div>
    @if (loading()) {
      <p role="status">
        {{ t("Actualizando comparativa...", "Updating comparison...") }}
      </p>
    }
    @if (error()) {
      <div class="error-message" role="alert">
        {{ error() }}
        <button (click)="load()">{{ t("Reintentar", "Retry") }}</button>
      </div>
    }
    @if (result(); as reports) {
      @if (
        !reports[0].coverage.availableMonths.length ||
        !reports[1].coverage.availableMonths.length
      ) {
        <p class="notice">
          {{
            t(
              "Uno de los meses no tiene fuente disponible. No se sustituye por cero.",
              "One month has no available source. Missing data is not replaced with zero."
            )
          }}
        </p>
      }
      <div class="metric-select">
        <label
          >{{ t("Indicador", "Metric")
          }}<select [(ngModel)]="metric">
            @for (m of metrics(); track m.key) {
              <option [value]="m.key">{{ m.name }} {{ m.unit }}</option>
            }
          </select></label
        >
      </div>
      <ds-analytics-chart
        [title]="metricName()"
        [subtitle]="metricUnit()"
        [labels]="labels()"
        [series]="series()"
      />
      <div class="comparisons">
        @for (m of metrics(); track m.key) {
          <section>
            <h3>
              {{ m.name }} <small>{{ m.unit }}</small>
            </h3>
            <div>
              <span
                >{{ labels()[0]
                }}<b>{{ value(reports[0].totals[m.key], m.unit) }}</b></span
              ><span
                >{{ labels()[1]
                }}<b>{{ value(reports[1].totals[m.key], m.unit) }}</b></span
              >
            </div>
            <p>
              {{ t("Diferencia", "Difference") }}:
              <strong>{{ value(difference(m.key), m.unit) }}</strong> ·
              {{ percentage(m.key) }}
            </p>
          </section>
        }
      </div>
    }
  `,
  styles: `
    .date-selector { border: 0; padding: 0; margin: 0; min-width: 220px; flex: 1; }
    .date-selector legend { color: #405761; font-size: 12px; margin-bottom: 7px; }
    .date-fields { display: grid; grid-template-columns: minmax(100px,1fr) 85px; gap: 8px; }
    :host {
      display: block;
      margin: 0 0 30px;
    }
    .selectors {
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      padding: 16px 0 22px;
      border-top: 1px solid #d9e1e5;
      border-bottom: 1px solid #d9e1e5;
    }
    label {
      display: grid;
      gap: 7px;
      font-size: 12px;
      min-width: 140px;
      flex: 1;
      color: #405761;
    }
    input,
    select {
      height: 38px;
      max-width: 100%;
      width: 100%;
      min-width: 0;
      border: 1px solid #bacbd1;
      border-radius: 4px;
      padding: 0 10px;
      background: white;
      color: #25343d;
    }
    .metric-select {
      max-width: 340px;
      margin: 20px 0;
    }
    .comparisons {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 24px;
      margin-top: 24px;
    }
    .comparisons section {
      border-top: 1px solid #d9e1e5;
      padding: 16px 0;
      min-width: 0;
    }
    h3 {
      font-size: 14px;
      margin-bottom: 12px;
    }
    small {
      font-weight: 400;
    }
    section > div {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 15px;
    }
    span {
      font-size: 12px;
      color: #405761;
    }
    b {
      display: block;
      font-size: 18px;
      color: #25343d;
      margin: 5px 0;
      overflow-wrap: anywhere;
    }
    section p {
      font-size: 12px;
      margin-top: 15px;
    }
    .notice {
      padding: 12px 0;
      color: #975c14;
    }
    @media (max-width: 850px) {
      .comparisons {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
    @media (max-width: 520px) {
      .comparisons {
        grid-template-columns: 1fr;
      }
      .selectors label {
        min-width: 100%;
      }
      .date-selector { min-width: 100%; }
    }
  `,
})
export class MonthComparison {
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  readonly i18n = inject(I18n);
  options = signal<AnalyticsOptions | null>(null);
  result = signal<[AnalyticsReport, AnalyticsReport] | null>(null);
  loading = signal(true);
  error = signal("");
  source = "published";
  baseline = `${new Date().getFullYear()}-01`;
  comparison = `${new Date().getFullYear()}-02`;
  currency: "USD" | "MXN" = "USD";
  metric = "igiPaid";
  months = Array.from({length:12},(_,i)=>i+1);
  readonly dateSides = [
    {key:'baseline',es:'Mes base',en:'Baseline month',yearEs:'Año base',yearEn:'Baseline year'},
    {key:'comparison',es:'Mes comparado',en:'Comparison month',yearEs:'Año comparado',yearEn:'Comparison year'},
  ] as const;
  datePart(value: string, index: number) { const part = value.split('-')[index]; return part ? Number(part) : null; }
  setDate(side: 'baseline' | 'comparison', index: number, value: number | null) {
    const date = this[side].split('-');
    date[index] = String(value ?? '').padStart(index === 1 ? 2 : 1,'0');
    this[side] = date.join('-'); this.load();
  }
  private requests = new Subject<[AnalyticsFilters, AnalyticsFilters] | null>();
  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
  constructor() {
    this.requests
      .pipe(
        tap((pair) => {
          this.loading.set(!!pair);
          if (pair) this.error.set("");
          this.result.set(null);
        }),
        switchMap((pair) => pair ?
          forkJoin([this.api.analytics(pair[0]), this.api.analytics(pair[1])]).pipe(
            catchError((e) => {
              this.error.set(errorText(e));
              return of(null);
            }),
          ) : of(null),
        ),
        takeUntilDestroyed(this.destroy),
      )
      .subscribe((r) => {
        this.result.set(r);
        this.loading.set(false);
      });
    this.api
      .analyticsOptions()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (o) => {
          this.options.set(o);
          this.source = o.defaultSource;
          this.sourceChanged();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
        },
      });
  }
  sourceChanged() {
    const year =
      this.options()?.sources.find((s) => s.id === this.source)?.years[0] ||
      new Date().getFullYear();
    this.baseline = `${year}-01`;
    this.comparison = `${year}-02`;
    this.load();
  }
  load() {
    if (this.metric.startsWith("trade"))
      this.metric = "trade" + (this.currency === "USD" ? "Usd" : "Mxn");
    const parse = (month: string): AnalyticsFilters | null => {
      if (!/^(19\d{2}|20\d{2}|2100)-(0[1-9]|1[0-2])$/.test(month)) return null;
      const [year, m] = month.split("-").map(Number);
      return {
        source: this.source,
        year,
        startMonth: m,
        endMonth: m,
        currency: this.currency,
        operation: "",
        customs: "",
        document: "",
      };
    };
    const a = parse(this.baseline),
      b = parse(this.comparison);
    if (a && b) this.requests.next([a, b]);
    else {
      this.requests.next(null);
      this.error.set(
        this.t("Selecciona dos meses válidos.", "Select two valid months."),
      );
    }
  }
  metrics() {
    const currency = this.result()?.[0].currency || this.currency;
    return [
      {
        key: "declarations",
        name: this.t("Pedimentos", "Declarations"),
        unit: "",
      },
      {
        key: "trade" + (currency === "USD" ? "Usd" : "Mxn"),
        name: this.t("Valor de mercancías", "Trade value"),
        unit: currency,
      },
      {
        key: "igiPaid",
        name: this.t("IGI pagado", "Import duty paid"),
        unit: currency,
      },
      {
        key: "ivaPaid",
        name: this.t("IVA pagado", "VAT paid"),
        unit: currency,
      },
      { key: "items", name: this.t("Partidas", "Line items"), unit: "" },
      {
        key: "rectifications",
        name: this.t("Rectificaciones", "Amendments"),
        unit: "",
      },
    ];
  }
  metricName() {
    return this.metrics().find((m) => m.key === this.metric)?.name || "";
  }
  metricUnit() {
    return this.metrics().find((m) => m.key === this.metric)?.unit || "";
  }
  labels() {
    return (this.result() || []).map(
      (r) => `${this.i18n.month(r.startMonth, true)} ${r.year}`,
    );
  }
  series(): ChartSeries[] {
    return [
      {
        label: this.metricName(),
        color: "#2877b5",
        values: (this.result() || []).map((r) => r.totals[this.metric] ?? null),
      },
    ];
  }
  value(v: number | null | undefined, unit: string) {
    return v == null
      ? "—"
      : new Intl.NumberFormat(this.i18n.locale(), {
          minimumFractionDigits: unit ? 2 : 0,
          maximumFractionDigits: unit ? 2 : 0,
        }).format(v);
  }
  difference(key: string) {
    const r = this.result();
    const a = r?.[0].totals[key],
      b = r?.[1].totals[key];
    return a == null || b == null ? null : b - a;
  }
  percentage(key: string) {
    const a = this.result()?.[0].totals[key],
      d = this.difference(key);
    return !a || d == null
      ? this.t("Sin base comparable", "No comparable baseline")
      : this.i18n.number((d / Math.abs(a)) * 100, false, 1) + "%";
  }
}
