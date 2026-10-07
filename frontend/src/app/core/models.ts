export interface AppConfig {
  environment: string;
  authMode: "development" | "entra";
  entra?: { tenantId: string; clientId: string; apiScope: string };
  foundryEnabled: boolean;
  allowAgentCommands?: boolean;
  engineVersion: string;
  maxUploadMb: number;
  scopeId: string;
}
export interface Identity {
  id: string;
  name: string;
  roles: string[];
  scopeId: string;
}
export interface Counts {
  receivedFiles: number;
  processedFiles: number;
  skippedFiles: number;
  processedTables: number;
  rows: number;
  warnings: number;
  errors: number;
}
export interface ConsolidationRange {
  startYear: number;
  startMonth: number;
  endYear: number;
  endMonth: number;
}
export interface Run {
  id: string;
  kind: string;
  period: string | null;
  year: number | null;
  rangeName: string | null;
  periodRange?: ConsolidationRange | null;
  status: string;
  phase: string;
  progress: number;
  functionalResult: string | null;
  publicationStatus: string;
  exportStatus: string;
  createdAt: string;
  updatedAt: string;
  counts: Counts;
  exportDocumentId: string | null;
  errorMessage: string | null;
  periodVersion: number;
}
export interface Page<T> {
  items: T[];
  total: number;
}
export interface Period {
  id: string;
  year: number;
  month: number;
  name: string;
  activeRunId: string | null;
  version: number;
}
export interface CatalogTable {
  code: string;
  name: string;
  order: number;
}

export interface PeriodDeletionPreview {
  periodId: string;
  periodName: string;
  version: number;
  monthlyRuns: number;
  annualRuns: number;
  businessRows: number;
  documents: number;
  storageCleanupFailures?: number;
}

export interface Overview {
  periodsCount: number;
  runsCount: number;
  rowsCount: number;
  warningCount: number;
  errorCount: number;
  monthly: { period: string; rows: number; files: number; warnings: number }[];
  recentRuns: Run[];
}
export type DataRow = Record<string, unknown>;
export interface DataPage {
  headers: string[];
  items: DataRow[];
  total: number;
}
export function isTerminal(run: Run): boolean {
  return (
    (run.status.toUpperCase() === "NEEDS_ATTENTION" &&
      ["READY", "FAILED"].includes(run.exportStatus.toUpperCase())) ||
    [
      "COMPLETED",
      "FAILED",
      "CANCELLED",
      "SUCCEEDED",
      "DONE",
      "ERROR",
      "FINISHED",
    ].includes(run.status.toUpperCase())
  );
}
export function runLabel(run: Run): string {
  return (
    run.period ||
    (run.periodRange && run.rangeName) ||
    [run.year, run.rangeName].filter(Boolean).join(" · ") ||
    "Sin periodo"
  );
}
export function errorText(error: unknown): string {
  const e = error as {
    status?: number;
    error?: { detail?: unknown; title?: string };
    message?: string;
  };
  if (e.status === 0)
    return "No se pudo conectar con la API. Verifica que el servicio esté disponible.";
  if (e.status === 403)
    return "Tu cuenta no tiene permiso para esta operación.";
  if (typeof e.error?.detail === "string") return e.error.detail;
  return (
    e.error?.title || "No se pudo completar la operación. Intenta nuevamente."
  );
}
