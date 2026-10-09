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
  pickerOpen = signal(false);
  years = computed(() =>
    [...new Set(this.periods().map((p) => p.year))].sort((a, b) => b - a),
  );
  months = computed(() =>
    this.periods()
      .filter((p) => p.year === this.activeYear())
      .sort((a, b) => a.month - b.month),
  );
  selectedPeriods = computed(() =>
    this.periods()
      .filter((p) => this.selected().includes(p.id))
      .sort((a, b) => b.year - a.year || a.month - b.month),
  );
  selected = signal<string[]>([]);
  selectedByYear = computed(() =>
    this.years()
      .map((year) => ({
        year,
        periods: this.selectedPeriods().filter((p) => p.year === year),
      }))
      .filter((group) => group.periods.length),
  );
  allYearSelected = computed(
    () =>
      this.months().length > 0 &&
      this.months().every((p) => this.selected().includes(p.id)),
  );
  canSelectYear = computed(
    () =>
      this.selected().length +
        this.months().filter((p) => !this.selected().includes(p.id)).length <=
      24,
  );
  impact = signal<BulkPeriodPreview | null>(null);
  busy = signal(false);
  error = signal("");
  message = signal("");
  confirmation = "";
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
      this.loading() ||
      !this.periods().some((p) => p.id === id) ||
      (!this.selected().includes(id) && this.selected().length >= 24)
    )
      return;
    this.selected.update((ids) =>
      ids.includes(id) ? ids.filter((p) => p !== id) : [...ids, id],
    );
    this.selectionChanged();
  }
  togglePicker() {
    if (!this.busy()) this.pickerOpen.update((open) => !open);
  }
  showYear(year: number) {
    if (this.busy()) return;
    this.activeYear.set(year);
    this.pickerOpen.set(true);
  }
  toggleYear() {
    if (this.busy() || this.loading() || !this.months().length) return;
    const ids = this.months().map((p) => p.id);
    if (this.allYearSelected()) {
      this.selected.update((selected) =>
        selected.filter((id) => !ids.includes(id)),
      );
    } else {
      // Select the entire year or none of it; never silently select a partial year.
      if (!this.canSelectYear()) return;
      this.selected.update((selected) => [...new Set([...selected, ...ids])]);
    }
    this.selectionChanged();
  }
  private selectionChanged() {
    this.cancelPreview();
    this.error.set("");
    this.message.set("");
  }
  clearSelection() {
    if (this.busy()) return;
    this.selected.set([]);
    this.selectionChanged();
  }
  cancelPreview() {
    if (this.busy()) return;
    this.impact.set(null);
    this.confirmation = "";
  }
  preview() {
    if (this.busy() || this.loading() || !this.selected().length) return;
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
          this.pickerOpen.set(false);
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
    if (this.busy() || !p || this.confirmation !== p.confirmation) return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .deletePeriods(p, this.confirmation)
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (r) => {
          this.busy.set(false);
          this.impact.set(null);
          this.selected.set([]);
          this.confirmation = "";
          this.pickerOpen.set(false);
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
