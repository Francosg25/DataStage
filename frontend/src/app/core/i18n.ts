import {
  Injectable,
  Pipe,
  PipeTransform,
  computed,
  effect,
  inject,
  signal,
} from "@angular/core";
import { DOCUMENT, formatDate, formatNumber } from "@angular/common";
import { ENGLISH } from "./translations";

export type Language = "es" | "en";

@Injectable({ providedIn: "root" })
export class I18n {
  private document = inject(DOCUMENT);
  readonly language = signal<Language>(this.savedLanguage());
  readonly locale = computed(() =>
    this.language() === "es" ? "es-MX" : "en-US",
  );
  constructor() {
    effect(() => {
      this.document.documentElement.lang = this.language();
      try {
        localStorage.setItem("datastage.language", this.language());
      } catch {
        /* Storage may be disabled. */
      }
    });
  }
  private savedLanguage(): Language {
    try {
      return localStorage.getItem("datastage.language") === "en" ? "en" : "es";
    } catch {
      return "es";
    }
  }
  set(value: string) {
    this.language.set(value === "en" ? "en" : "es");
  }
  choose(es: string, en: string): string {
    return this.language() === "en" ? en : es;
  }
  t(value: unknown): string {
    if (value == null) return "";
    const text = String(value);
    if (this.language() === "es") return text;
    const key = text.replace(/\s+/g, " ").trim();
    if (ENGLISH[key]) return ENGLISH[key];
    const period =
      /^(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)([_ ])(\d{4})$/.exec(
        key,
      );
    if (period) return `${ENGLISH[period[1]]}${period[2]}${period[3]}`;
    const size = /^El archivo supera el límite de (\d+) MB\.$/.exec(key);
    if (size) return `The file exceeds the ${size[1]} MB limit.`;
    return text;
  }
  number(
    value: number | null | undefined,
    compact = false,
    digits = 0,
  ): string {
    if (value == null) return "—";
    return new Intl.NumberFormat(this.locale(), {
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: digits,
    }).format(value);
  }
  month(month: number, short = false): string {
    return new Intl.DateTimeFormat(this.locale(), {
      month: short ? "short" : "long",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(2026, month - 1, 1)));
  }
}

@Pipe({ name: "t", pure: false })
export class TranslatePipe implements PipeTransform {
  private i18n = inject(I18n);
  transform(value: unknown): string {
    return this.i18n.t(value);
  }
}

@Pipe({ name: "dsNumber", pure: false })
export class LocalizedNumberPipe implements PipeTransform {
  private i18n = inject(I18n);
  transform(value: number | null | undefined, digits = "1.0-3"): string {
    return value == null
      ? "—"
      : formatNumber(value, this.i18n.locale(), digits);
  }
}

@Pipe({ name: "dsDate", pure: false })
export class LocalizedDatePipe implements PipeTransform {
  private i18n = inject(I18n);
  transform(
    value: string | number | Date | null | undefined,
    format = "mediumDate",
  ): string {
    return value == null ? "—" : formatDate(value, format, this.i18n.locale());
  }
}
