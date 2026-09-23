import { MatPaginatorIntl } from "@angular/material/paginator";
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
