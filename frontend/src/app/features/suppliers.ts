import { Component, DestroyRef, computed, inject, signal } from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { HttpResponse } from "@angular/common/http";
import { Observable, finalize, forkJoin } from "rxjs";
import { Auth } from "../core/auth";
import { I18n, LocalizedDatePipe, TranslatePipe } from "../core/i18n";
import { Page, errorText } from "../core/models";
import {
  Supplier,
  SupplierEquivalence,
  SupplierEvidence,
  SupplierFields,
  SupplierKind,
  SupplierReport,
  SupplierReportRequest,
  SupplierReview,
  SupplierSummary,
  SupplierTab,
  SuppliersApi,
} from "../core/suppliers";
import { Icon } from "../shared/ui";
import { saveSupplierDownload } from "../shared/supplier-download";

const emptyFields = (): SupplierFields => ({
  kind: "national",
  name: "",
  taxId: "",
  country: "MEX",
  address: "",
  externalNumber: "",
  internalNumber: "",
  postalCode: "",
  municipality: "",
  state: "",
  virtualConfirmation: null,
});

@Component({
  selector: "ds-suppliers",
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    TranslatePipe,
    LocalizedDatePipe,
    Icon,
  ],
  templateUrl: "./suppliers.html",
  styleUrl: "./suppliers.scss",
})
export class Suppliers {
  readonly auth = inject(Auth);
  readonly i18n = inject(I18n);
  private readonly api = inject(SuppliersApi);
  private readonly destroy = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  private readonly route = inject(ActivatedRoute, { optional: true });
  readonly tabs: { id: SupplierTab; label: string }[] = [
    { id: "reviews", label: "Por revisar" },
    { id: "catalog", label: "Catálogo" },
    { id: "reports", label: "Reportes" },
    { id: "equivalences", label: "Equivalencias" },
  ];
  readonly tab = signal<SupplierTab>("reviews");
  readonly summary = signal<SupplierSummary | null>(null);
  readonly suppliers = signal<Supplier[]>([]);
  readonly reviews = signal<SupplierReview[]>([]);
  readonly reports = signal<SupplierReport[]>([]);
  readonly reportRequests = signal<SupplierReportRequest[]>([]);
  readonly requestsLoading = signal(false);
  readonly requestsError = signal("");
  readonly requestsTotal = signal(0);
  readonly requestPage = signal(0);
  readonly equivalences = signal<SupplierEquivalence[]>([]);
  readonly loading = signal(false);
  readonly summaryLoading = signal(false);
  readonly summaryError = signal("");
  readonly busy = signal(false);
  readonly downloading = signal("");
  readonly detailLoading = signal(false);
  readonly error = signal("");
  readonly listError = signal(false);
  readonly detailError = signal("");
  readonly notice = signal("");
  readonly total = signal(0);
  readonly page = signal(0);
  readonly pageSize = 25;
  readonly pages = computed(() =>
    Math.max(1, Math.ceil(this.total() / this.pageSize)),
  );
  readonly canEdit = computed(() => this.auth.hasRole("Operator", "Admin"));
  readonly selected = signal<Supplier | null>(null);
  readonly review = signal<SupplierReview | null>(null);
  readonly equivalence = signal<SupplierEquivalence | null>(null);
  readonly editorOpen = signal(false);
  readonly existingRequested = signal(false);
  readonly targetLoading = signal(false);
  readonly targets = signal<Supplier[]>([]);
  readonly selectableTargets = computed(() =>
    this.targets().filter(
      (target) => target.id !== this.equivalence()?.supplierId,
    ),
  );
  readonly evidence = signal<SupplierEvidence[]>([]);
  readonly evidenceTotal = signal(0);
  readonly evidenceLoading = signal(false);
  search = "";
  kind: SupplierKind | "" = "";
  reportLabel = "";
  fields = emptyFields();
  reason = "";
  decision: "same" | "new" = "same";
  targetId = "";
  targetSearch = "";
  reviewVirtual: boolean | null = null;
  equivalenceActive = true;
  private listRequest = 0;
  private detailRequest = 0;
  private targetRequest = 0;
  private reportKey = "";
  private reportKeyLabel = "";

  constructor() {
    const initialTab = this.route?.snapshot.queryParamMap.get("tab");
    if (this.tabs.some((tab) => tab.id === initialTab))
      this.tab.set(initialTab as SupplierTab);
    this.loadSummary();
    this.load();
    if (this.tab() === "reports") this.loadRequests();
  }

  labelKind(kind: SupplierKind) {
    return this.i18n.t(kind === "national" ? "Nacional" : "Extranjero");
  }
  virtualLabel(value: boolean | null | undefined) {
    return this.i18n.t(
      value === true ? "Sí" : value === false ? "No" : "Por confirmar",
    );
  }
  reasonLabel(value: string) {
    return this.i18n.t(
      (
        {
          similar_name: "Nombre similar",
          conflicting_data: "Datos contradictorios",
          virtual_confirmation: "Confirmar operaciones virtuales",
          missing_identity: "Identificación incompleta",
          equivalence_revoked: "Equivalencia retirada",
        } as Record<string, string>
      )[value] || value,
    );
  }
  count(tab: SupplierTab) {
    const summary = this.summary();
    if (!summary) return "—";
    return this.i18n.number(
      tab === "reviews"
        ? summary.pending
        : tab === "catalog"
          ? summary.national + summary.foreign
          : summary[tab],
    );
  }
  switchTab(tab: SupplierTab) {
    if (this.busy()) return;
    this.tab.set(tab);
    this.page.set(0);
    this.search = "";
    this.kind = "";
    this.closeEditor();
    this.load();
    if (tab === "reports") this.loadRequests();
  }
  tabKey(event: KeyboardEvent, index: number) {
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % this.tabs.length
        : event.key === "ArrowLeft"
          ? (index + this.tabs.length - 1) % this.tabs.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? this.tabs.length - 1
              : -1;
    if (next < 0 || this.busy()) return;
    event.preventDefault();
    this.switchTab(this.tabs[next].id);
    this.document.getElementById(`supplier-tab-${this.tabs[next].id}`)?.focus();
  }
  searchList() {
    this.page.set(0);
    this.load();
  }
  changePage(delta: number) {
    if (this.loading()) return;
    this.page.set(Math.max(0, Math.min(this.pages() - 1, this.page() + delta)));
    this.load();
  }
  refresh() {
    if (this.busy()) return;
    this.loadSummary();
    this.load();
    if (this.tab() === "reports") this.loadRequests();
  }
  loadRequests() {
    if (this.requestsLoading()) return;
    this.requestsLoading.set(true);
    this.requestsError.set("");
    this.api
      .reportRequests(this.requestPage() * this.pageSize, this.pageSize)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.requestsLoading.set(false)),
      )
      .subscribe({
        next: (page) => {
          this.reportRequests.set(page.items);
          this.requestsTotal.set(page.total);
        },
        error: (error) => this.requestsError.set(errorText(error)),
      });
  }
  changeRequestPage(delta: number) {
    if (this.requestsLoading()) return;
    const page = this.requestPage() + delta;
    if (page < 0 || page * this.pageSize >= this.requestsTotal()) return;
    this.requestPage.set(page);
    this.loadRequests();
  }
  downloadMonthly(request: SupplierReportRequest) {
    if (request.status === "ready" && request.reportId)
      this.download({ id: request.reportId });
  }
  loadSummary() {
    this.summaryLoading.set(true);
    this.summaryError.set("");
    this.api
      .summary()
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.summaryLoading.set(false)),
      )
      .subscribe({
        next: (summary) => this.summary.set(summary),
        error: (error) => this.summaryError.set(errorText(error)),
      });
  }
  load() {
    const request = ++this.listRequest;
    this.loading.set(true);
    this.listError.set(false);
    this.error.set("");
    const tab = this.tab();
    const query = {
      search: this.search.trim(),
      type: this.kind,
      offset: this.page() * this.pageSize,
      limit: this.pageSize,
    };
    const source: Observable<
      Page<Supplier | SupplierReview | SupplierReport | SupplierEquivalence>
    > =
      tab === "catalog"
        ? this.api.catalog(query)
        : tab === "reviews"
          ? this.api.reviews(query)
          : tab === "reports"
            ? this.api.reports(query)
            : this.api.equivalences(query);
    source
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => {
          if (request === this.listRequest) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (result) => {
          if (request !== this.listRequest) return;
          this.total.set(result.total);
          if (tab === "catalog") this.suppliers.set(result.items as Supplier[]);
          else if (tab === "reviews")
            this.reviews.set(result.items as SupplierReview[]);
          else if (tab === "reports")
            this.reports.set(result.items as SupplierReport[]);
          else this.equivalences.set(result.items as SupplierEquivalence[]);
        },
        error: (error) => {
          if (request === this.listRequest) {
            this.listError.set(true);
            this.error.set(errorText(error));
          }
        },
      });
  }
  closeEditor() {
    if (this.busy()) return;
    ++this.detailRequest;
    ++this.targetRequest;
    this.editorOpen.set(false);
    this.selected.set(null);
    this.existingRequested.set(false);
    this.review.set(null);
    this.equivalence.set(null);
    this.detailLoading.set(false);
    this.detailError.set("");
    this.reason = "";
    this.targetId = "";
    this.targetSearch = "";
    this.targets.set([]);
    this.evidence.set([]);
    this.evidenceTotal.set(0);
    this.evidenceLoading.set(false);
  }
  addSupplier() {
    if (!this.canEdit() || this.busy()) return;
    this.closeEditor();
    this.fields = emptyFields();
    this.editorOpen.set(true);
    this.revealEditor();
  }
  openSupplier(supplier: Supplier) {
    if (this.busy()) return;
    this.closeEditor();
    this.editorOpen.set(true);
    this.existingRequested.set(true);
    this.revealEditor();
    this.detailLoading.set(true);
    const request = ++this.detailRequest;
    this.api
      .detail(supplier.id)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => {
          if (request === this.detailRequest) this.detailLoading.set(false);
        }),
      )
      .subscribe({
        next: (detail) => {
          if (request !== this.detailRequest) return;
          this.selected.set(detail);
          this.fields = this.supplierFields(detail);
          this.evidence.set(detail.evidence || []);
          this.evidenceTotal.set(
            detail.evidenceTotal ??
              Math.max(detail.evidenceCount ?? 0, detail.evidence?.length ?? 0),
          );
        },
        error: (error) => {
          if (request === this.detailRequest)
            this.detailError.set(errorText(error));
        },
      });
  }
  openReview(review: SupplierReview) {
    if (this.busy()) return;
    this.closeEditor();
    this.review.set(review);
    this.evidence.set(review.evidence || []);
    this.evidenceTotal.set(
      review.evidenceCount ?? review.evidence?.length ?? 0,
    );
    this.fields = this.supplierFields(review.candidate);
    this.targets.set(review.suggestions || []);
    this.decision = review.suggestions?.length ? "same" : "new";
    this.targetId = review.suggestions?.[0]?.id || "";
    this.reviewVirtual =
      review.virtualConfirmed === true
        ? true
        : (review.candidate.virtualOperations ?? null);
    this.editorOpen.set(true);
    this.revealEditor();
  }
  openEquivalence(equivalence: SupplierEquivalence) {
    if (this.busy() || !this.canEdit()) return;
    this.closeEditor();
    this.equivalence.set(equivalence);
    this.targetId = equivalence.supplierId;
    this.equivalenceActive = equivalence.active;
    this.editorOpen.set(true);
    this.revealEditor();
    this.findTargets();
  }
  findTargets() {
    const request = ++this.targetRequest;
    this.targetLoading.set(true);
    this.detailError.set("");
    this.api
      .catalog({
        search: this.targetSearch.trim(),
        type: "",
        offset: 0,
        limit: 50,
      })
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => {
          if (request === this.targetRequest) this.targetLoading.set(false);
        }),
      )
      .subscribe({
        next: (result) => {
          if (request !== this.targetRequest) return;
          const suggestions = this.review()?.suggestions || [];
          this.targets.set([
            ...new Map(
              [...suggestions, ...result.items].map((s) => [s.id, s]),
            ).values(),
          ]);
        },
        error: (error) => {
          if (request === this.targetRequest)
            this.detailError.set(errorText(error));
        },
      });
  }
  private supplierFields(fields: Partial<SupplierFields>): SupplierFields {
    const allowed = emptyFields();
    for (const key of Object.keys(allowed) as (keyof SupplierFields)[]) {
      const value = fields[key];
      if (value !== undefined && value !== null)
        Object.assign(allowed, { [key]: value });
    }
    return allowed;
  }
  moreEvidence() {
    const current = this.review() ?? this.selected();
    if (
      !current ||
      this.evidenceLoading() ||
      this.evidence().length >= this.evidenceTotal()
    )
      return;
    this.evidenceLoading.set(true);
    this.detailError.set("");
    const request = this.detailRequest;
    const source = this.review()
      ? this.api.reviewEvidence(current.id, this.evidence().length)
      : this.api.supplierEvidence(current.id, this.evidence().length);
    source
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => {
          if (request === this.detailRequest) this.evidenceLoading.set(false);
        }),
      )
      .subscribe({
        next: (page) => {
          if (request !== this.detailRequest) return;
          this.evidence.update((items) => [...items, ...page.items]);
          this.evidenceTotal.set(page.total);
        },
        error: (error) => {
          if (request === this.detailRequest)
            this.detailError.set(errorText(error));
        },
      });
  }
  private revealEditor() {
    setTimeout(() => {
      const heading = this.document.getElementById("supplier-editor-title");
      heading?.focus({ preventScroll: true });
      heading?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    });
  }
  private validFields() {
    if (!this.fields.name.trim()) {
      this.detailError.set("Introduce el nombre del proveedor.");
      return false;
    }
    if (
      !this.selected() &&
      this.fields.kind === "national" &&
      this.fields.virtualConfirmation === null
    ) {
      this.detailError.set(
        "Confirma Sí o No en operaciones virtuales para el proveedor nacional.",
      );
      return false;
    }
    return true;
  }
  saveSupplier() {
    if (
      !this.canEdit() ||
      this.busy() ||
      this.detailLoading() ||
      (this.existingRequested() && !this.selected())
    )
      return;
    this.detailError.set("");
    if (!this.validFields() || !this.validReason()) return;
    const selected = this.selected();
    this.mutate(
      () =>
        selected
          ? this.api.update(
              selected.id,
              this.fields,
              selected.version,
              this.reason,
            )
          : this.api.create(this.fields, this.reason),
      "Proveedor guardado.",
    );
  }
  private validReason() {
    if (this.reason.trim().length >= 5) return true;
    this.detailError.set(
      "Indica un motivo de al menos 5 caracteres para la auditoría.",
    );
    return false;
  }
  resolveReview() {
    const review = this.review();
    if (!review || !this.canEdit() || this.busy()) return;
    this.detailError.set("");
    if (!this.validReason()) return;
    if (this.decision === "same" && !this.targetId) {
      this.detailError.set("Selecciona el proveedor del catálogo.");
      return;
    }
    if (
      this.decision === "new" &&
      (!this.fields.name.trim() ||
        (this.fields.kind === "national" &&
          this.reviewVirtual === null &&
          review.virtualConfirmed !== true &&
          review.candidate.virtualOperations !== true))
    ) {
      this.detailError.set(
        !this.fields.name.trim()
          ? "Introduce el nombre del proveedor."
          : "Confirma Sí o No en operaciones virtuales para el proveedor nacional.",
      );
      return;
    }
    if (
      review.reason === "virtual_confirmation" &&
      this.reviewVirtual === null
    ) {
      this.detailError.set(
        "Confirma Sí o No en operaciones virtuales para el proveedor nacional.",
      );
      return;
    }
    this.mutate(
      () =>
        this.api.resolve(review.id, {
          decision: this.decision,
          expectedVersion: review.version,
          reason: this.reason.trim(),
          ...(this.decision === "same"
            ? { supplierId: this.targetId }
            : {
                supplier: {
                  ...this.fields,
                  virtualConfirmation: this.reviewVirtual,
                },
              }),
          ...(this.reviewVirtual !== null
            ? { virtualOperations: this.reviewVirtual }
            : {}),
        }),
      "Revisión resuelta y equivalencia guardada.",
    );
  }
  saveEquivalence() {
    const equivalence = this.equivalence();
    if (!equivalence || !this.canEdit() || this.busy()) return;
    this.detailError.set("");
    if (!this.validReason()) return;
    if (!this.targetId && this.equivalenceActive) {
      this.detailError.set("Selecciona el proveedor del catálogo.");
      return;
    }
    this.mutate(
      () =>
        this.api.updateEquivalence(
          equivalence.id,
          equivalence.version,
          this.reason.trim(),
          {
            supplierId: this.targetId || undefined,
            active: this.equivalenceActive,
          },
        ),
      this.equivalenceActive
        ? "Equivalencia guardada."
        : "Equivalencia retirada.",
    );
  }
  sync() {
    if (!this.canEdit() || this.busy()) return;
    this.mutate(
      () => this.api.sync(),
      "Catálogo actualizado desde el historial publicado.",
    );
  }
  private mutate<T>(request: () => Observable<T>, success: string) {
    this.busy.set(true);
    this.detailError.set("");
    this.error.set("");
    this.notice.set("");
    request()
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.busy.set(false)),
      )
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.closeEditor();
          this.notice.set(success);
          this.refresh();
        },
        error: (error) =>
          (this.editorOpen() ? this.detailError : this.error).set(
            errorText(error),
          ),
      });
  }
  createReport() {
    if (
      !this.canEdit() ||
      this.busy() ||
      this.loading() ||
      this.summaryLoading()
    )
      return;
    const label = this.reportLabel.trim();
    if (!this.reportKey) {
      try {
        const pending = JSON.parse(
          sessionStorage.getItem(this.reportStorageKey()) || "null",
        );
        if (pending?.key && pending.label === label) {
          this.reportKey = pending.key;
          this.reportKeyLabel = label;
        }
      } catch {
        /* Retry remains available if browser storage is unavailable. */
      }
    }
    if (!this.reportKey || label !== this.reportKeyLabel) {
      this.reportKey = crypto.randomUUID();
      this.reportKeyLabel = label;
    }
    try {
      sessionStorage.setItem(
        this.reportStorageKey(),
        JSON.stringify({ key: this.reportKey, label }),
      );
    } catch {
      /* The in-memory key still protects retries in this view. */
    }
    this.busy.set(true);
    this.error.set("");
    this.notice.set("");
    this.api
      .createReport(label, this.reportKey)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.busy.set(false)),
      )
      .subscribe({
        next: () => {
          try {
            sessionStorage.removeItem(this.reportStorageKey());
          } catch {
            /* Optional storage. */
          }
          this.reportKey = "";
          this.reportLabel = "";
          this.busy.set(false);
          this.notice.set(
            "Reporte creado. Ambas listas comparten la misma instantánea.",
          );
          this.switchTab("reports");
          this.loadSummary();
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  private reportStorageKey() {
    const identity = this.auth.user?.();
    return `datastage.suppliers.pending-report:${identity?.scopeId || ""}:${identity?.id || ""}`;
  }
  download(report: Pick<SupplierReport, "id">, kind?: SupplierKind) {
    if (this.downloading()) return;
    this.downloading.set(report.id);
    this.error.set("");
    const kinds: SupplierKind[] = kind ? [kind] : ["national", "foreign"];
    forkJoin(kinds.map((value) => this.api.download(report.id, value)))
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.downloading.set("")),
      )
      .subscribe({
        next: (responses) =>
          responses.forEach((response, index) => {
            this.saveDownload(response, `${report.id}-${kinds[index]}.xlsx`);
          }),
        error: (error) => this.error.set(errorText(error)),
      });
  }
  private saveDownload(response: HttpResponse<Blob>, fallback: string) {
    saveSupplierDownload(this.document, response, fallback);
  }
  evidenceJson(evidence: SupplierEvidence) {
    return JSON.stringify(evidence.data ?? evidence, null, 2);
  }
}
