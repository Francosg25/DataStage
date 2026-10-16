import { HttpResponse } from "@angular/common/http";

export function saveSupplierDownload(
  document: Document,
  response: HttpResponse<Blob>,
  fallback: string,
) {
  if (!response.body) return;
  const disposition = response.headers.get("Content-Disposition") || "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  let filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1] || fallback;
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded);
    } catch {
      /* Use the fallback filename. */
    }
  }
  const url = URL.createObjectURL(response.body);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename.replace(/[\\/]/g, "_");
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
