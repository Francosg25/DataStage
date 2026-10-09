import { Injectable, inject } from "@angular/core";
import { HttpClient, HttpParams } from "@angular/common/http";
import { Observable } from "rxjs";
import {
  AnalyticsFilters,
  AnalyticsOptions,
  AnalyticsReport,
} from "./analytics";
import { I18n } from "./i18n";
import { ProjectMapCatalog } from "./project-maps";
export interface BulkPeriodPreview {
  periods: PeriodDeletionPreview[];
  impact: {
    monthlyRuns: number;
    annualRuns: number;
    businessRows: number;
    documents: number;
  };
  token: string;
  confirmation: string;
}
import {
  AppConfig,
  ConsolidationRange,
  Identity,
  Page,
  Run,
  Period,
  PeriodDeletionPreview,
  Overview,
  CatalogTable,
  DataPage,
  DataRow,
} from "./models";
@Injectable({ providedIn: "root" })
export class Api {
  projectMaps() {
    return this.http.get<ProjectMapCatalog>(`${this.base}/project-maps`);
  }
  projectMapImage(id: string, thumbnail = false) {
    return this.http.get(
      `${this.base}/project-maps/${encodeURIComponent(id)}/image`,
      {
        params: { thumbnail },
        responseType: "blob",
      },
    );
  }
  private readonly http = inject(HttpClient);
  private readonly i18n = inject(I18n);
  readonly base = "/api/v1";
  config() {
    return this.http.get<AppConfig>(`${this.base}/config`);
  }
  me() {
    return this.http.get<Identity>(`${this.base}/me`);
  }
  periods() {
    return this.http.get<Period[]>(`${this.base}/periods`);
  }
  bulkPeriodPreview(periodIds: string[]) {
    return this.http.post<BulkPeriodPreview>(
      `${this.base}/periods/bulk-deletion-preview`,
      { periodIds },
    );
  }
  deletePeriods(
    preview: BulkPeriodPreview,
    confirmation: string,
    reason?: string,
  ) {
    return this.http.post<
      BulkPeriodPreview & { storageCleanupFailures: number }
    >(`${this.base}/periods/bulk-delete`, {
      periodIds: preview.periods.map((p) => p.periodId),
      expectedToken: preview.token,
      confirmation,
      reason,
    });
  }
  periodDeletionPreview(id: string) {
    return this.http.get<PeriodDeletionPreview>(
      `${this.base}/periods/${encodeURIComponent(id)}/deletion-preview`,
    );
  }

  deletePeriod(
    impact: PeriodDeletionPreview,
    confirmation: string,
    reason?: string,
  ) {
    return this.http.delete<PeriodDeletionPreview>(
      `${this.base}/periods/${encodeURIComponent(impact.periodId)}`,
      {
        body: {
          expectedVersion: impact.version,
          confirmation,
          reason,
          expectedMonthlyRuns: impact.monthlyRuns,
          expectedAnnualRuns: impact.annualRuns,
          expectedBusinessRows: impact.businessRows,
          expectedDocuments: impact.documents,
        },
      },
    );
  }

  runs(offset = 0, limit = 20) {
    return this.http.get<Page<Run>>(`${this.base}/runs`, {
      params: { offset, limit },
    });
  }
  run(id: string) {
    return this.http.get<Run>(`${this.base}/runs/${encodeURIComponent(id)}`);
  }
  section(id: string, section: string, offset = 0, limit = 50) {
    return this.http.get<Page<DataRow>>(
      `${this.base}/runs/${encodeURIComponent(id)}/${section}`,
      { params: { limit, offset } },
    );
  }
  overview() {
    return this.http.get<Overview>(`${this.base}/reports/overview`);
  }
  analyticsOptions() {
    return this.http.get<AnalyticsOptions>(
      `${this.base}/reports/analytics/options`,
    );
  }
  analytics(filters: AnalyticsFilters) {
    return this.http.get<AnalyticsReport>(`${this.base}/reports/analytics`, {
      params: { ...filters },
    });
  }
  analyticsPdf(
    filters: AnalyticsFilters,
    language: "es" | "en",
    snapshot: string,
  ) {
    return this.http.get(`${this.base}/reports/analytics/pdf`, {
      params: { ...filters, language, snapshot },
      responseType: "blob",
    });
  }
  catalog() {
    return this.http.get<CatalogTable[]>(`${this.base}/catalog/tables`);
  }
  monthly(period: string, zip: File, key: string) {
    const body = new FormData();
    body.append("periodo", period);
    body.append("zip", zip);
    return this.http.post<Run>(`${this.base}/monthly-runs`, body, {
      headers: { "Idempotency-Key": key },
    });
  }
  annual(range: ConsolidationRange, key: string) {
    return this.http.post<Run>(`${this.base}/annual-runs`, range, {
      headers: { "Idempotency-Key": key },
    });
  }
  reprocess(id: string, reason: string, expectedVersion: number, key: string) {
    return this.http.post<Run>(
      `${this.base}/runs/${encodeURIComponent(id)}/reprocess`,
      { reason, expectedVersion },
      { headers: { "Idempotency-Key": key } },
    );
  }
  export(id: string, key: string) {
    return this.http.post<Run>(
      `${this.base}/runs/${encodeURIComponent(id)}/exports`,
      {},
      { headers: { "Idempotency-Key": key } },
    );
  }
  download(id: string) {
    return this.http.get(
      `${this.base}/documents/${encodeURIComponent(id)}/download`,
      { responseType: "blob", observe: "response" },
    );
  }
  data(code: string, period: string, offset = 0, limit = 50) {
    let params = new HttpParams().set("offset", offset).set("limit", limit);
    if (period) params = params.set("period", period);
    return this.http.get<DataPage>(
      `${this.base}/data/${encodeURIComponent(code)}`,
      { params },
    );
  }
  audit(offset = 0) {
    return this.http.get<Page<DataRow>>(`${this.base}/audit`, {
      params: { offset, limit: 50 },
    });
  }
  conversation() {
    return this.http.post<{ id: string }>(
      `${this.base}/agent/conversations`,
      {},
    );
  }
  message(id: string, message: string, allowActions = false) {
    return this.http.post<{ message: string; evidence: DataRow[] }>(
      `${this.base}/agent/conversations/${encodeURIComponent(id)}/messages`,
      { message, allowActions, language: this.i18n.language() },
    );
  }
}
