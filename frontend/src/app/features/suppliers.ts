import { Component, DestroyRef, computed, inject, signal } from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
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
    RouterLink,
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
  readonly downloading = signal<SupplierKind | "both" | null>(null);
  readonly busy = computed(() => this.loading() || !!this.downloading());
  readonly error = signal("");
  readonly kinds: { id: SupplierKind; label: string }[] = [
    { id: "foreign", label: "Extranjeros" },
    { id: "national", label: "Nacionales" },
  ];

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
