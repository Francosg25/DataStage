export type MetricValues = Record<string, number | null>;
export interface AnalyticsMonth {
  month: number;
  available: boolean;
  metrics: MetricValues;
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
  };
  filters: { customs: string[]; documents: string[]; operations: string[] };
}
export interface AnalyticsOptions {
  sources: { id: string; years: number[] }[];
  defaultSource: string;
}
export interface AnalyticsFilters {
  source: string;
  year: number;
  startMonth: number;
  endMonth: number;
  operation: string;
  customs: string;
  document: string;
}
