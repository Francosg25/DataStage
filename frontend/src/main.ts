import { registerLocaleData } from "@angular/common";
import localeEsMx from "@angular/common/locales/es-MX";
import { MatPaginatorIntl } from "@angular/material/paginator";
import { localizedPaginator } from "./app/core/locale";
import { LocalizedTitle } from "./app/core/title";
import { bootstrapApplication } from "@angular/platform-browser";
import {
  provideAppInitializer,
  inject,
  provideBrowserGlobalErrorListeners,
  LOCALE_ID,
} from "@angular/core";
import {
  provideRouter,
  withComponentInputBinding,
  TitleStrategy,
} from "@angular/router";
import { provideHttpClient, withInterceptors } from "@angular/common/http";
import { App } from "./app/app";
import { routes } from "./app/routes";
import { Auth, bearerInterceptor } from "./app/core/auth";
registerLocaleData(localeEsMx);
bootstrapApplication(App, {
  providers: [
    { provide: LOCALE_ID, useValue: "es-MX" },
    { provide: MatPaginatorIntl, useFactory: localizedPaginator },
    { provide: TitleStrategy, useClass: LocalizedTitle },
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptors([bearerInterceptor])),
    provideRouter(routes, withComponentInputBinding()),
    provideAppInitializer(() => inject(Auth).initialize()),
  ],
}).catch((error) => {
  console.error("No se pudo iniciar DataStage", error);
  document.body.textContent =
    "No se pudo iniciar DataStage. Recarga la página o contacta a soporte.";
});
