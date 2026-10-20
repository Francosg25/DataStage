import { Component, DestroyRef, computed, inject, signal } from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Observable, finalize, forkJoin, of, switchMap } from "rxjs";
import { Auth } from "../core/auth";
import { I18n, TranslatePipe } from "../core/i18n";
import { errorText } from "../core/models";
import {
  SupplierKind,
  SupplierReport,
  SupplierSummary,
  SuppliersApi,
} from "../core/suppliers";
import { Icon } from "../shared/ui";
import { saveSupplierDownload } from "../shared/supplier-download";

@Component({
  selector: "ds-suppliers",
  imports: [
    FormsModule,
    MatButtonModule,
    MatProgressBarModule,
    TranslatePipe,
    Icon,
  ],
  templateUrl: "./suppliers.html",
  styleUrl: "./suppliers.scss",
})
export class Suppliers {
  readonly i18n = inject(I18n);
  private readonly auth = inject(Auth);
  private readonly api = inject(SuppliersApi);
  private readonly destroy = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  readonly canUpdate = computed(() => this.auth.hasRole("Operator", "Admin"));
  readonly canImport = computed(() => this.auth.hasRole("Admin"));
  readonly summary = signal<SupplierSummary | null>(null);
  readonly reports = signal<SupplierReport[]>([]);
  readonly reportsTotal = signal(0);
  readonly selectedId = signal("");
  readonly selectedReport = computed(() =>
    this.reports().find((report) => report.id === this.selectedId()),
  );
  readonly loading = signal(false);
  readonly importing = signal(false);
  readonly rebuilding = signal(false);
  readonly confirmRebuild = signal(false);
  readonly backupDocumentId = signal("");
  readonly downloading = signal<SupplierKind | "both" | null>(null);
  readonly busy = computed(
    () => this.loading() || this.importing() || this.rebuilding() || !!this.downloading(),
  );
  readonly error = signal("");
  readonly notice = signal("");
  readonly kinds: { id: SupplierKind; label: string }[] = [
    { id: "foreign", label: "Extranjeros" },
    { id: "national", label: "Nacionales" },
  ];
  nationalFile: File | null = null;
  foreignFile: File | null = null;

  constructor() {
    this.loading.set(true);
    this.readLists()
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (value) => this.acceptLists(value),
        error: (error) => this.error.set(errorText(error)),
      });
  }

  private readLists() {
    return forkJoin({
      summary: this.api.summary(),
      reports: this.api.reports({ search: "", type: "", offset: 0, limit: 50 }),
    });
  }
  private acceptLists(value: {
    summary: SupplierSummary;
    reports: { items: SupplierReport[]; total: number };
  }) {
    this.summary.set(value.summary);
    this.backupDocumentId.set(value.summary.backupDocumentId || "");
    this.reports.set(value.reports.items);
    this.reportsTotal.set(value.reports.total);
    this.selectedId.set(value.reports.items[0]?.id || "");
  }
  refresh() {
    if (this.busy()) return;
    this.loading.set(true);
    this.error.set("");
    const start: Observable<unknown> = this.canUpdate()
      ? this.api.sync()
      : of(null);
    start
      .pipe(
        switchMap(() => this.readLists()),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (value) => this.acceptLists(value),
        error: (error) => this.error.set(errorText(error)),
      });
  }
  selectImport(event: Event, kind: SupplierKind) {
    const file = (event.target as HTMLInputElement).files?.[0] || null;
    if (kind === "national") this.nationalFile = file;
    else this.foreignFile = file;
  }
  importLists() {
    if (
      !this.canImport() ||
      this.busy() ||
      !this.nationalFile ||
      !this.foreignFile
    )
      return;
    this.importing.set(true);
    this.error.set("");
    this.notice.set("");
    this.api
      .importLists(this.nationalFile, this.foreignFile)
      .pipe(
        switchMap(() => this.readLists()),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.importing.set(false)),
      )
      .subscribe({
        next: (value) => {
          this.acceptLists(value);
          this.notice.set(
            "Listas originales incorporadas. Los Excel están actualizados.",
          );
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  rebuildFromSeptember() {
    const version = this.summary()?.catalogVersion;
    if (!this.canImport() || this.busy() || !this.confirmRebuild() || version == null) return;
    this.rebuilding.set(true);
    this.error.set("");
    this.notice.set("");
    this.api.rebuildFromSeptember(version, crypto.randomUUID())
      .pipe(
        switchMap((result) => {
          this.backupDocumentId.set(result.backupDocumentId);
          return this.readLists();
        }),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.rebuilding.set(false)),
      )
      .subscribe({
        next: (value) => {
          this.acceptLists(value);
          this.confirmRebuild.set(false);
          this.notice.set("Listas recalculadas desde septiembre de 2026. Respaldo guardado.");
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  downloadBackup() {
    const id = this.backupDocumentId();
    if (!id || this.busy()) return;
    this.loading.set(true);
    this.error.set("");
    this.api.downloadBackup(id)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => saveSupplierDownload(this.document, response, "proveedores-respaldo.json"),
        error: (error) => this.error.set(errorText(error)),
      });
  }
  loadMore() {
    if (this.busy()) return;
    this.loading.set(true);
    this.error.set("");
    this.api
      .reports({
        search: "",
        type: "",
        offset: this.reports().length,
        limit: 50,
      })
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (page) => {
          this.reports.update((items) => [
            ...items,
            ...page.items.filter(
              (item) => !items.some((old) => old.id === item.id),
            ),
          ]);
          this.reportsTotal.set(page.total);
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  count(kind: SupplierKind) {
    const report = this.selectedReport();
    return report
      ? kind === "national"
        ? report.nationalCount
        : report.foreignCount
      : null;
  }
  download(kind: SupplierKind | "both") {
    const report = this.selectedReport();
    if (!report || this.busy()) return;
    const kinds: SupplierKind[] =
      kind === "both" ? ["foreign", "national"] : [kind];
    this.downloading.set(kind);
    this.error.set("");
    forkJoin(kinds.map((value) => this.api.download(report.id, value)))
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.downloading.set(null)),
      )
      .subscribe({
        next: (responses) =>
          responses.forEach((response, index) =>
            saveSupplierDownload(
              this.document,
              response,
              `${report.id}-${kinds[index]}.xlsx`,
            ),
          ),
        error: (error) => this.error.set(errorText(error)),
      });
  }
}
