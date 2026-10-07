import {
  Component,
  DestroyRef,
  ElementRef,
  afterRenderEffect,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from "@angular/core";
import { DOCUMENT } from "@angular/common";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { MatButtonModule } from "@angular/material/button";
import { MatTooltipModule } from "@angular/material/tooltip";
import { MatProgressBarModule } from "@angular/material/progress-bar";
import { finalize } from "rxjs";
import {
  LucideChevronLeft,
  LucideChevronRight,
  LucideZoomIn,
  LucideZoomOut,
  LucideMaximize,
  LucideMinimize,
  LucideScan,
  LucideDownload,
  LucideRotateCw,
} from "@lucide/angular";
import { Api } from "../core/api";
import { I18n } from "../core/i18n";
import { ProjectMap, ProjectMapCatalog } from "../core/project-maps";

@Component({
  selector: "ds-project-maps",
  imports: [
    MatButtonModule,
    MatTooltipModule,
    MatProgressBarModule,
    LucideChevronLeft,
    LucideChevronRight,
    LucideZoomIn,
    LucideZoomOut,
    LucideMaximize,
    LucideMinimize,
    LucideScan,
    LucideDownload,
    LucideRotateCw,
  ],
  templateUrl: "./project-maps.html",
  styleUrl: "./project-maps.scss",
})
export class ProjectMaps {
  readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  private readonly destroy = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  readonly catalog = signal<ProjectMapCatalog | null>(null);
  readonly loading = signal(false);
  readonly catalogError = signal(false);
  readonly index = signal(0);
  readonly zoom = signal(1);
  readonly direction = signal(1);
  readonly fullscreen = signal(false);
  readonly notice = signal("");
  readonly urls = signal<Record<string, string>>({});
  readonly failed = signal<ReadonlySet<string>>(new Set());
  readonly pages = computed(() => this.catalog()?.pages ?? []);
  readonly current = computed(() => this.pages()[this.index()]);
  readonly selectedPages = computed(() =>
    this.current() ? [this.current()!] : [],
  );
  readonly sourceDate = computed(() => {
    const date = this.catalog()?.date;
    return date
      ? new Intl.DateTimeFormat(this.i18n.locale(), {
          day: "numeric",
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        }).format(new Date(`${date}T00:00:00Z`))
      : "";
  });
  readonly viewport = viewChild<ElementRef<HTMLDivElement>>("viewport");
  readonly viewer = viewChild<ElementRef<HTMLElement>>("viewer");
  private readonly viewportSize = signal({ width: 800, height: 450 });
  readonly sheetWidth = computed(() => {
    const page = this.current();
    const size = this.viewportSize();
    const ratio = page ? page.width / page.height : 16 / 9;
    return (
      Math.max(1, Math.min(size.width - 32, (size.height - 32) * ratio)) *
      this.zoom()
    );
  });
  private readonly pending = new Set<string>();
  private drag?: {
    id: number;
    x: number;
    y: number;
    left: number;
    top: number;
  };

  constructor() {
    afterRenderEffect(() => {
      this.index();
      this.viewportSize();
      const selected = this.viewer()?.nativeElement.querySelector<HTMLElement>(
        '.map-thumbnail[aria-current="page"]',
      );
      const rail = selected?.parentElement;
      if (!selected || !rail) return;
      const item = selected.getBoundingClientRect();
      const bounds = rail.getBoundingClientRect();
      const delta =
        item.left < bounds.left + 12
          ? item.left - bounds.left - 12
          : item.right > bounds.right - 12
            ? item.right - bounds.right + 12
            : 0;
      if (delta) rail.scrollBy({ left: delta, behavior: "instant" });
    });
    effect((cleanup) => {
      const viewport = this.viewport()?.nativeElement;
      if (!viewport) return;
      const measure = () =>
        this.viewportSize.set({
          width: viewport.clientWidth,
          height: viewport.clientHeight,
        });
      measure();
      const observer = new ResizeObserver(measure);
      observer.observe(viewport);
      cleanup(() => observer.disconnect());
    });
    const onFullscreen = () =>
      this.fullscreen.set(
        this.document.fullscreenElement === this.viewer()?.nativeElement,
      );
    this.document.addEventListener("fullscreenchange", onFullscreen);
    this.destroy.onDestroy(() => {
      this.document.removeEventListener("fullscreenchange", onFullscreen);
      Object.values(this.urls()).forEach((url) => URL.revokeObjectURL(url));
    });
    this.loadCatalog();
  }

  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
  title(page: ProjectMap) {
    return this.t(page.es, page.en);
  }
  key(page: ProjectMap, thumbnail = false) {
    return `${page.id}:${thumbnail ? "thumb" : "full"}`;
  }
  image(page: ProjectMap, thumbnail = false) {
    return this.urls()[this.key(page, thumbnail)];
  }

  loadCatalog() {
    if (this.loading()) return;
    this.loading.set(true);
    this.catalogError.set(false);
    this.api
      .projectMaps()
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (catalog) => {
          this.catalog.set(catalog);
          this.index.set(0);
          catalog.pages.forEach((page) => this.loadImage(page, true));
          this.preload();
        },
        error: () => this.catalogError.set(true),
      });
  }

  loadImage(page: ProjectMap, thumbnail = false) {
    const key = this.key(page, thumbnail);
    if (this.urls()[key] || this.pending.has(key)) return;
    this.pending.add(key);
    this.failed.update((values) => {
      const next = new Set(values);
      next.delete(key);
      return next;
    });
    this.api
      .projectMapImage(page.id, thumbnail)
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.pending.delete(key)),
      )
      .subscribe({
        next: (blob) =>
          this.urls.update((urls) => ({
            ...urls,
            [key]: URL.createObjectURL(blob),
          })),
        error: () => this.failed.update((values) => new Set([...values, key])),
      });
  }

  imageFailed(page: ProjectMap, thumbnail = false) {
    const key = this.key(page, thumbnail);
    const url = this.urls()[key];
    if (url) URL.revokeObjectURL(url);
    this.urls.update((urls) => {
      const next = { ...urls };
      delete next[key];
      return next;
    });
    this.failed.update((values) => new Set([...values, key]));
  }

  private preload() {
    for (const index of [this.index(), this.index() + 1, this.index() - 1]) {
      const page = this.pages()[index];
      if (page) this.loadImage(page);
    }
  }

  goTo(index: number) {
    if (
      !Number.isInteger(index) ||
      index < 0 ||
      index >= this.pages().length ||
      index === this.index()
    )
      return;
    this.direction.set(index > this.index() ? 1 : -1);
    this.index.set(index);
    this.fit();
    this.notice.set("");
    this.preload();
  }

  changeZoom(delta: number) {
    this.zoom.set(
      Math.min(4, Math.max(1, Math.round((this.zoom() + delta) * 100) / 100)),
    );
    if (this.zoom() === 1) this.fit();
  }

  fit() {
    this.zoom.set(1);
    this.viewport()?.nativeElement.scrollTo({
      left: 0,
      top: 0,
      behavior: "instant",
    });
  }

  onKey(event: KeyboardEvent) {
    if (
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      (event.target instanceof Element &&
        event.target.closest("select,input,textarea"))
    )
      return;
    const next = (
      {
        ArrowRight: this.index() + 1,
        PageDown: this.index() + 1,
        ArrowLeft: this.index() - 1,
        PageUp: this.index() - 1,
        Home: 0,
        End: this.pages().length - 1,
      } as Record<string, number>
    )[event.key];
    if (next !== undefined) {
      event.preventDefault();
      this.goTo(next);
    }
  }

  startPan(event: PointerEvent) {
    if (this.zoom() <= 1 || event.button !== 0 || event.pointerType === "touch")
      return;
    const viewport = this.viewport()!.nativeElement;
    event.preventDefault();
    viewport.focus({ preventScroll: true });
    this.drag = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.setPointerCapture(event.pointerId);
  }

  pan(event: PointerEvent) {
    if (!this.drag || this.drag.id !== event.pointerId) return;
    const viewport = this.viewport()!.nativeElement;
    viewport.scrollLeft = this.drag.left + this.drag.x - event.clientX;
    viewport.scrollTop = this.drag.top + this.drag.y - event.clientY;
  }

  endPan() {
    this.drag = undefined;
  }

  async toggleFullscreen() {
    this.notice.set("");
    try {
      if (this.document.fullscreenElement === this.viewer()?.nativeElement)
        await this.document.exitFullscreen();
      else await this.viewer()?.nativeElement.requestFullscreen();
    } catch {
      this.notice.set(
        this.t(
          "El navegador no permite pantalla completa en este momento.",
          "Fullscreen is not available in this browser right now.",
        ),
      );
    }
  }

  download() {
    const page = this.current();
    const url = page && this.image(page);
    if (!url || !page) return;
    const anchor = this.document.createElement("a");
    anchor.href = url;
    anchor.download = `DataStage_${page.id}_${this.catalog()!.date}.png`;
    anchor.click();
  }
}
