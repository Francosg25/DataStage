import { MatPaginatorIntl } from "@angular/material/paginator";
import { effect, inject } from "@angular/core";
import { I18n } from "./i18n";
export function localizedPaginator(): MatPaginatorIntl {
  const i18n = inject(I18n);
  const paginator = new MatPaginatorIntl();
  effect(() => {
    paginator.itemsPerPageLabel = i18n.choose(
      "Registros por página",
      "Items per page",
    );
    paginator.nextPageLabel = i18n.choose("Página siguiente", "Next page");
    paginator.previousPageLabel = i18n.choose(
      "Página anterior",
      "Previous page",
    );
    paginator.firstPageLabel = i18n.choose("Primera página", "First page");
    paginator.lastPageLabel = i18n.choose("Última página", "Last page");
    paginator.getRangeLabel = (page, size, length) =>
      length === 0
        ? i18n.choose("0 registros", "0 records")
        : `${i18n.number(page * size + 1)}–${i18n.number(Math.min((page + 1) * size, length))} ${i18n.choose("de", "of")} ${i18n.number(length)}`;
    paginator.changes.next();
  });
  return paginator;
}
export function spanishPaginator(): MatPaginatorIntl {
  const paginator = new MatPaginatorIntl();
  paginator.itemsPerPageLabel = "Registros por página";
  paginator.nextPageLabel = "Página siguiente";
  paginator.previousPageLabel = "Página anterior";
  paginator.firstPageLabel = "Primera página";
  paginator.lastPageLabel = "Última página";
  paginator.getRangeLabel = (page, size, length) =>
    length === 0
      ? "0 registros"
      : `${page * size + 1}–${Math.min((page + 1) * size, length)} de ${length}`;
  return paginator;
}
