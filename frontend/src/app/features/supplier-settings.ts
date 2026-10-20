import { Component, DestroyRef, computed, inject, signal } from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { finalize } from "rxjs";
import { Auth } from "../core/auth";
import { TranslatePipe } from "../core/i18n";
import { errorText } from "../core/models";
import { SupplierKind, SupplierSummary, SuppliersApi } from "../core/suppliers";
import { Icon } from "../shared/ui";
import { saveSupplierDownload } from "../shared/supplier-download";

@Component({
  selector: "ds-supplier-settings",
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    TranslatePipe,
    Icon,
  ],
  templateUrl: "./supplier-settings.html",
  styleUrl: "./supplier-settings.scss",
})
export class SupplierSettings {
  private readonly auth = inject(Auth);
  private readonly api = inject(SuppliersApi);
  private readonly destroy = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  readonly canManage = computed(() => this.auth.hasRole("Admin"));
  readonly summary = signal<SupplierSummary | null>(null);
  readonly loading = signal(false);
  readonly importing = signal(false);
  readonly rebuilding = signal(false);
  readonly downloading = signal(false);
  readonly originalsOpen = signal(false);
  readonly confirmRebuild = signal(false);
  readonly error = signal("");
  readonly notice = signal("");
  readonly backupDocumentId = computed(
    () => this.summary()?.backupDocumentId || "",
  );
  readonly busy = computed(
    () =>
      this.loading() ||
      this.importing() ||
      this.rebuilding() ||
      this.downloading(),
  );
  nationalFile: File | null = null;
  foreignFile: File | null = null;

  constructor() {
    this.reload();
  }
  reload() {
    if (!this.canManage() || this.busy()) return;
    this.loading.set(true);
    this.error.set("");
    this.api
      .summary()
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (value) => {
          this.summary.set(value);
          this.originalsOpen.set(!value.initialized);
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  toggleOriginals(event: Event) {
    this.originalsOpen.set((event.target as HTMLDetailsElement).open);
  }
  selectImport(event: Event, kind: SupplierKind) {
    const file = (event.target as HTMLInputElement).files?.[0] || null;
    if (kind === "national") this.nationalFile = file;
    else this.foreignFile = file;
  }
  importLists(form?: HTMLFormElement) {
    if (
      !this.canManage() ||
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
        takeUntilDestroyed(this.destroy),
        finalize(() => this.importing.set(false)),
      )
      .subscribe({
        next: (value) => {
          this.summary.set(value);
          this.nationalFile = this.foreignFile = null;
          form?.reset();
          this.originalsOpen.set(false);
          this.confirmRebuild.set(false);
          this.notice.set(
            "Listas originales incorporadas. Los Excel están actualizados.",
          );
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  rebuildFromSeptember() {
    const version = this.summary()?.catalogVersion;
    if (
      !this.canManage() ||
      this.busy() ||
      !this.confirmRebuild() ||
      !this.summary()?.initialized ||
      version == null
    )
      return;
    this.rebuilding.set(true);
    this.error.set("");
    this.notice.set("");
    this.api
      .rebuildFromSeptember(version, crypto.randomUUID())
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.rebuilding.set(false)),
      )
      .subscribe({
        next: (value) => {
          this.summary.set(value);
          this.confirmRebuild.set(false);
          this.notice.set(
            "Listas recalculadas desde septiembre de 2026. Respaldo guardado.",
          );
        },
        error: (error) => this.error.set(errorText(error)),
      });
  }
  downloadBackup() {
    const id = this.backupDocumentId();
    if (!this.canManage() || !id || this.busy()) return;
    this.downloading.set(true);
    this.error.set("");
    this.api
      .downloadBackup(id)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.downloading.set(false)),
      )
      .subscribe({
        next: (response) =>
          saveSupplierDownload(
            this.document,
            response,
            "proveedores-respaldo.json",
          ),
        error: (error) => this.error.set(errorText(error)),
      });
  }
}
