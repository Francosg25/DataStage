import { Routes } from "@angular/router";
import { authGuard, operatorGuard } from "./core/auth";
export const routes: Routes = [
  {
    path: "login",
    loadComponent: () => import("./features/login").then((m) => m.Login),
  },
  {
    path: "",
    canActivate: [authGuard],
    children: [
      {
        path: "access-denied",
        loadComponent: () =>
          import("./features/access-denied").then((m) => m.AccessDenied),
        title: "Acceso restringido · DataStage",
      },
      {
        path: "",
        pathMatch: "full",
        loadComponent: () =>
          import("./features/dashboard").then((m) => m.Dashboard),
        title: "Resumen · DataStage",
      },
      {
        path: "monthly",
        canActivate: [operatorGuard],
        loadComponent: () =>
          import("./features/monthly").then((m) => m.Monthly),
        title: "Carga mensual · DataStage",
      },
      {
        path: "runs",
        loadComponent: () =>
          import("./features/history").then((m) => m.History),
        title: "Historial · DataStage",
      },
      {
        path: "runs/:id",
        loadComponent: () =>
          import("./features/run-detail").then((m) => m.RunDetail),
        title: "Detalle de ejecución · DataStage",
      },
      {
        path: "annual",
        canActivate: [operatorGuard],
        loadComponent: () => import("./features/annual").then((m) => m.Annual),
        title: "Consolidado anual · DataStage",
      },
      {
        path: "data",
        loadComponent: () =>
          import("./features/data").then((m) => m.DataBrowser),
        title: "Consulta de datos · DataStage",
      },
      {
        path: "agent",
        loadComponent: () => import("./features/agent").then((m) => m.Agent),
        title: "Asistente · DataStage",
      },
      {
        path: "administration",
        loadComponent: () =>
          import("./features/administration").then((m) => m.Administration),
        title: "Administración · DataStage",
      },
    ],
  },
  { path: "**", redirectTo: "" },
];
