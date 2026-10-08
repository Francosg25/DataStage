import {
  Component,
  DestroyRef,
  computed,
  inject,
  output,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { Api, BulkPeriodPreview } from "../core/api";
import { Period, errorText } from "../core/models";
import { I18n } from "../core/i18n";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-month-deletion",
  imports: [FormsModule, Icon],
  templateUrl: "./month-deletion.html",
  styleUrl: "./month-deletion.scss",
})
export class MonthDeletion {
  private api = inject(Api);
  private destroy = inject(DestroyRef);
  readonly i18n = inject(I18n);
  changed = output<void>();
  periods = signal<Period[]>([]);
  loading = signal(true);
  loadFailed = signal(false);
  activeYear = signal<number | null>(null);
  years = computed(() =>
    [...new Set(this.periods().map((p) => p.year))].sort((a, b) => b - a),
  );
  months = computed(() =>
    Array.from({ length: 12 }, (_, index) => ({
      month: index + 1,
      period: this.periods().find(
        (p) => p.year === this.activeYear() && p.month === index + 1,
      ),
    })),
  );
  selectedPeriods = computed(() =>
    this.periods()
      .filter((p) => this.selected().includes(p.id))
      .sort((a, b) => b.year - a.year || a.month - b.month),
  );
  selected = signal<string[]>([]);
  impact = signal<BulkPeriodPreview | null>(null);
  busy = signal(false);
  error = signal("");
  message = signal("");
  confirmation = "";
  reason = "";
  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
  constructor() {
    this.load();
  }
  load() {
    this.loading.set(true);
    this.loadFailed.set(false);
    this.error.set("");
    this.api
      .periods()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.periods.set(p);
          if (!this.years().includes(this.activeYear() ?? 0))
            this.activeYear.set(this.years()[0] ?? null);
          this.loading.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.loading.set(false);
          this.loadFailed.set(true);
        },
      });
  }
  toggle(id: string) {
    if (
      this.busy() ||
      (!this.selected().includes(id) && this.selected().length >= 24)
    )
      return;
    this.selected.update((ids) =>
      ids.includes(id) ? ids.filter((p) => p !== id) : [...ids, id],
    );
    this.impact.set(null);
    this.confirmation = "";
    this.error.set("");
    this.message.set("");
  }
  clearSelection() {
    if (this.busy()) return;
    this.selected.set([]);
    this.cancelPreview();
    this.error.set("");
  }
  cancelPreview() {
    if (this.busy()) return;
    this.impact.set(null);
    this.confirmation = "";
    this.reason = "";
  }
  preview() {
    if (this.busy() || !this.selected().length) return;
    this.busy.set(true);
    this.error.set("");
    this.impact.set(null);
    this.confirmation = "";
    this.api
      .bulkPeriodPreview(this.selected())
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (p) => {
          this.impact.set(p);
          this.busy.set(false);
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
        },
      });
  }
  remove() {
    const p = this.impact();
    if (
      this.busy() ||
      !p ||
      this.confirmation !== p.confirmation ||
      this.reason.trim().length < 8
    )
      return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .deletePeriods(p, this.confirmation, this.reason.trim())
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (r) => {
          this.busy.set(false);
          this.impact.set(null);
          this.selected.set([]);
          this.confirmation = "";
          this.reason = "";
          this.message.set(
            r.storageCleanupFailures
              ? this.t(
                  "Meses eliminados; hay archivos pendientes de limpieza.",
                  "Months deleted; some files still require cleanup.",
                )
              : this.t("Meses eliminados.", "Months deleted."),
          );
          this.load();
          this.changed.emit();
        },
        error: (e) => {
          this.error.set(errorText(e));
          this.busy.set(false);
          this.impact.set(null);
        },
      });
  }
}
