export type MetricValues = Record<string, number | null>;
export interface PaymentMethods {
  cash: { igi: number | null; iva: number | null; unmatchedRows: number };
  certiva: { igi: number | null; iva: number | null; unmatchedRows: number };
  otherPaymentRows: number;
}
export interface RectificationRow {
  r1: number | null;
  declarations: number | null;
  officeRate: number | null;
  globalRate: number | null;
}
export interface AnalyticsMonth {
  month: number;
  available: boolean;
  metrics: MetricValues;
  paymentMethods: PaymentMethods;
  rows: number | null;
  files: number | null;
  warnings: number | null;
  errors: number | null;
  tables: Record<string, number>;
  runId: string | null;
  version: number | null;
}
export interface Ranking {
  key: string;
  value: number | null;
  rows: number;
}
export interface AnalyticsReport {
  appliedFilters: AnalyticsFilters;
  snapshotId: string;
  paymentMethods: PaymentMethods;
  rectificationsByCustoms: {
    rows: (RectificationRow & { customs: string })[];
    totals: RectificationRow;
    globalDeclarations: number | null;
    available: boolean;
    unmatchedAmendments: number;
    invalidKeys: number;
  };
  currency: "USD" | "MXN";
  partTaxes: PartTaxes;
  rectifications: { patent: string; values: (number | null)[] }[];
  source: string;
  year: number;
  startMonth: number;
  endMonth: number;
  generatedAt: string;
  sources: { file: string; sha256: string }[];
  reconciliation: {
    file: string;
    matched: boolean;
    comparedTables: number;
    differences: { period: string; table: string }[];
  } | null;
  monthly: AnalyticsMonth[];
  totals: MetricValues;
  latest: MetricValues;
  previous: MetricValues;
  deltas: MetricValues;
  latestMonth: number | null;
  previousMonth: number | null;
  breakdowns: Record<string, Ranking[]>;
  coverage: {
    availableMonths: number[];
    requestedMonths: number;
    tables: Record<string, number>;
    invalidNumericValues: number;
    orphanItems: number;
    duplicateDeclarationRows: number;
    processingFiltersApplied: boolean;
    missingExchangeRates: number;
  };
  filters: { customs: string[]; documents: string[]; operations: string[] };
}
export interface AnalyticsOptions {
  sources: { id: string; years: number[] }[];
  defaultSource: string;
}
export interface AnalyticsFilters {
  currency?: "USD" | "MXN";
  source: string;
  year: number;
  startMonth: number;
  endMonth: number;
  operation: string;
  customs: string;
  document: string;
}

export interface PartTaxRow {
  partNumber: string | null;
  alternatePartNumbers?: string[];
  tariff: string;
  items: number;
  igi: number | null;
  iva: number | null;
  months: Record<string, { igi: number | null; iva: number | null }>;
}
export interface PartAlert {
  year: number;
  month: number;
  patent: string;
  declaration: string;
  customs: string;
  tariff: string;
  sequence: string;
  status: "missing" | "ambiguous";
  candidates: string[];
  observations: string[];
}
export interface PartTaxes {
  rows: PartTaxRow[];
  alerts: PartAlert[];
  missingParts: number;
  ambiguousParts: number;
  invalidItemKeys: number;
  unmatchedTaxRows: number;
  observationSourceAvailable: boolean;
  available: boolean;
  currency: string;
  totals: { igi: number | null; iva: number | null };
}
