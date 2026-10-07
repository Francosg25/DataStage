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
        path: "foundry-guide",
        loadComponent: () =>
          import("./features/foundry-guide").then((m) => m.FoundryGuide),
        title: "Guía de Azure Foundry · DataStage",
      },
      {
        path: "analytics",
        loadComponent: () =>
          import("./features/analytics").then((m) => m.Analytics),
        title: "Análisis de operaciones · DataStage",
      },
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
        pathMatch: "full",
        redirectTo: "uploads/monthly",
      },
      {
        path: "uploads",
        canActivate: [operatorGuard],
        canActivateChild: [operatorGuard],
        loadComponent: () =>
          import("./features/uploads").then((m) => m.Uploads),
        title: "Cargas · DataStage",
        children: [
          { path: "", pathMatch: "full", redirectTo: "monthly" },
          {
            path: "monthly",
            loadComponent: () =>
              import("./features/monthly").then((m) => m.Monthly),
            title: "Cargas mensuales · DataStage",
          },
          {
            path: "consolidated",
            loadComponent: () =>
              import("./features/consolidated").then((m) => m.Consolidated),
            title: "Consolidados · DataStage",
          },
        ],
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
        loadComponent: () => import("./features/annual").then((m) => m.Annual),
        title: "Comparativa mensual · DataStage",
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
        path: "project-maps",
        loadComponent: () =>
          import("./features/project-maps").then((m) => m.ProjectMaps),
        title: "Mapas del proyecto · DataStage",
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
