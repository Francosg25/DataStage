import { Injectable, inject } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { Page } from "./models";
import { map } from "rxjs";

export type SupplierKind = "national" | "foreign";
export type SupplierTab =
  | "national"
  | "foreign"
  | "reviews"
  | "catalog"
  | "reports"
  | "equivalences";
export interface SupplierFields {
  kind: SupplierKind;
  name: string;
  taxId: string;
  country: string;
  address: string;
  externalNumber: string;
  internalNumber: string;
  postalCode: string;
  municipality: string;
  state: string;
  virtualConfirmation: boolean | null;
}
export interface Supplier extends SupplierFields {
  id: string;
  version: number;
  virtualOperations: boolean | null;
  evidenceCount?: number;
  evidenceTotal?: number;
  evidenceHasMore?: boolean;
  status?: string;
  createdAt?: string;
  updatedAt?: string;
  evidence?: SupplierEvidence[];
}
export interface SupplierEvidence {
  id?: string;
  code?: string;
  tableCode?: string;
  period?: string;
  runId?: string;
  sourceFile?: string;
  sourceRow?: number;
  rowNumber?: number;
  active?: boolean;
  virtual?: boolean;
  virtualOperations?: boolean;
  virtualConfirmed?: boolean;
  sourceKind?: string;
  records?: {
    table: string;
    rowId?: string;
    fileId?: string;
    fileName?: string;
    rowNumber?: number;
    pedimento?: string;
    values?: Record<string, unknown>;
    source?: Record<string, unknown>;
  }[];
  data?: Record<string, unknown>;
  [key: string]: unknown;
}
export interface SupplierReview {
  id: string;
  version: number;
  reason: string;
  candidate: SupplierFields & { virtualOperations?: boolean | null };
  suggestions: Supplier[];
  evidence: SupplierEvidence[];
  runId?: string;
  period?: string;
  virtualConfirmed?: boolean;
  evidenceCount?: number;
  evidenceHasMore?: boolean;
}
export interface SupplierEquivalence {
  id: string;
  version: number;
  identityName: string;
  identityTaxId: string;
  identityCountry: string;
  supplierId: string;
  supplierName: string;
  active: boolean;
  decision?: string;
  createdAt?: string;
}
export interface SupplierReport {
  id: string;
  label: string;
  createdAt: string;
  nationalCount: number;
  foreignCount: number;
  sourceFingerprint: string;
  status?: "ready" | "pending_review";
  runId?: string;
  pending?: number;
}
export interface SupplierRunReportState {
  runId: string;
  status: "pending_review" | "ready" | "unavailable";
  report: SupplierReport | null;
  pending: number;
}
export interface SupplierReportRequest {
  id: string;
  runId: string;
  period: string;
  createdAt: string;
  status: "pending_review" | "ready" | "cancelled";
  reportId: string | null;
  pending: number;
}
export interface SupplierSummary {
  catalogVersion?: number;
  startPeriod?: { year: number; month: number } | null;
  backupDocumentId?: string | null;
  initialized?: boolean;
  catalog?: number;
  national: number;
  foreign: number;
  pending: number;
  reports: number;
  equivalences: number;
}
export interface SupplierQuery {
  search: string;
  type: SupplierKind | "";
  offset: number;
  limit: number;
}
export interface SupplierResolution {
  decision: "same" | "new";
  supplierId?: string;
  virtualOperations?: boolean;
  expectedVersion: number;
  reason: string;
  supplier?: SupplierFields;
}

// The domain also exposes the existing type/city vocabulary to API clients.
function supplier<T extends Partial<Supplier>>(value: T): T {
  const aliases = value as T & {
    type?: SupplierKind;
    city?: string;
    originalStatus?: string;
  };
  return {
    ...value,
    kind: value.kind || aliases.type || "foreign",
    municipality: value.municipality ?? aliases.city ?? "",
    status: value.status ?? aliases.originalStatus,
  };
}

function queryParams(query: SupplierQuery) {
  const { type, ...params } = query;
  return type ? { ...params, type } : params;
}

@Injectable({ providedIn: "root" })
export class SuppliersApi {
  private readonly http = inject(HttpClient);
  private readonly base = "/api/v1/suppliers";

  summary() {
    return this.http.get<SupplierSummary>(`${this.base}/summary`);
  }
  importLists(national: File, foreign: File) {
    const body = new FormData();
    body.append("national", national);
    body.append("foreign", foreign);
    return this.http.post<SupplierSummary>(`${this.base}/import`, body);
  }
  catalog(query: SupplierQuery) {
    return this.http
      .get<Page<Supplier>>(this.base, { params: queryParams(query) })
      .pipe(map((page) => ({ ...page, items: page.items.map(supplier) })));
  }
  reviews(query: SupplierQuery) {
    return this.http
      .get<Page<SupplierReview>>(`${this.base}/reviews`, {
        params: queryParams(query),
      })
      .pipe(
        map((page) => ({
          ...page,
          items: page.items.map((review) => ({
            ...review,
            candidate: supplier(review.candidate),
            suggestions: (review.suggestions || []).map(supplier),
            evidence: review.evidence || [],
          })),
        })),
      );
  }
  reports(query: SupplierQuery) {
    return this.http.get<Page<SupplierReport>>(`${this.base}/reports`, {
      params: queryParams(query),
    });
  }
  runReport(runId: string) {
    return this.http.get<SupplierRunReportState>(
      `${this.base}/runs/${encodeURIComponent(runId)}/report`,
    );
  }
  reportRequests(offset = 0, limit = 25) {
    return this.http.get<Page<SupplierReportRequest>>(
      `${this.base}/report-requests`,
      {
        params: { offset, limit },
      },
    );
  }
  equivalences(query: SupplierQuery) {
    return this.http.get<Page<SupplierEquivalence>>(
      `${this.base}/equivalences`,
      {
        params: queryParams(query),
      },
    );
  }
  detail(id: string) {
    return this.http
      .get<Supplier>(`${this.base}/${encodeURIComponent(id)}`)
      .pipe(map(supplier));
  }
  reviewEvidence(id: string, offset: number, limit = 50) {
    return this.http.get<Page<SupplierEvidence>>(
      `${this.base}/reviews/${encodeURIComponent(id)}/evidence`,
      {
        params: { offset, limit },
      },
    );
  }
  supplierEvidence(id: string, offset: number, limit = 50) {
    return this.http.get<Page<SupplierEvidence>>(
      `${this.base}/${encodeURIComponent(id)}/evidence`,
      { params: { offset, limit } },
    );
  }
  create(fields: SupplierFields, reason: string) {
    return this.http.post<Supplier>(this.base, { ...fields, reason });
  }
  update(id: string, fields: SupplierFields, version: number, reason: string) {
    return this.http.patch<Supplier>(`${this.base}/${encodeURIComponent(id)}`, {
      ...fields,
      expectedVersion: version,
      reason,
    });
  }
  resolve(id: string, resolution: SupplierResolution) {
    return this.http.post<Supplier>(
      `${this.base}/reviews/${encodeURIComponent(id)}/resolve`,
      resolution,
    );
  }
  updateEquivalence(
    id: string,
    version: number,
    reason: string,
    changes: { supplierId?: string; active?: boolean },
  ) {
    return this.http.patch<SupplierEquivalence>(
      `${this.base}/equivalences/${encodeURIComponent(id)}`,
      { ...changes, expectedVersion: version, reason },
    );
  }
  createReport(label: string, key: string) {
    return this.http.post<SupplierReport>(
      `${this.base}/reports`,
      { label: label.trim() || undefined },
      { headers: { "Idempotency-Key": key } },
    );
  }
  download(id: string, kind: SupplierKind) {
    return this.http.get(
      `${this.base}/reports/${encodeURIComponent(id)}/${kind}.xlsx`,
      { responseType: "blob", observe: "response" },
    );
  }
  rebuildFromSeptember(expectedVersion: number, key: string) {
    return this.http.post<SupplierSummary & { backupDocumentId: string }>(
      `${this.base}/rebuild`,
      { startYear: 2026, startMonth: 9, expectedVersion, confirmation: "REINICIAR LISTAS" },
      { headers: { "Idempotency-Key": key } },
    );
  }
  downloadBackup(id: string) {
    return this.http.get(
      `${this.base}/backups/${encodeURIComponent(id)}`,
      { responseType: "blob", observe: "response" },
    );
  }
  sync() {
    return this.http.post(`${this.base}/sync`, {});
  }
}
