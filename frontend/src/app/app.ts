import { Component, inject, signal } from "@angular/core";
import { RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { Auth } from "./core/auth";
import { Icon } from "./shared/ui";
@Component({
  selector: "app-root",
  imports: [RouterLink, RouterLinkActive, RouterOutlet, MatButtonModule, Icon],
  template: `
    <a href="#main-content" class="skip-link">Saltar al contenido</a>
    @if (auth.user()) {
      <div class="app-shell">
        <aside
          class="sidebar"
          [class.sidebar-open]="navOpen()"
          aria-label="Navegación principal"
        >
          <a routerLink="/" class="brand" aria-label="DataStage inicio"
            ><span class="brand-symbol"
              ><span></span><span></span><span></span></span
            ><span>DataStage<small>TRADE OPERATIONS</small></span></a
          >
          <div class="workspace-label">ESPACIO DE TRABAJO</div>
          <nav>
            @for (item of allowedNavigation(); track item.path) {
              <a
                [routerLink]="item.path"
                routerLinkActive="nav-active"
                [routerLinkActiveOptions]="{ exact: item.path === '/' }"
                (click)="navOpen.set(false)"
                ><ds-icon [name]="item.icon" /><span>{{ item.label }}</span>
                @if (item.path === "/agent") {
                  <span class="nav-tag">AI</span>
                }
              </a>
            }
          </nav>
          <div class="sidebar-bottom">
            <div class="sidebar-note">
              <ds-icon name="shield" /><span
                >Acceso corporativo<br /><strong>{{
                  auth.user()?.scopeId
                }}</strong></span
              >
            </div>
            <span class="sidebar-version"
              >Motor {{ auth.config()?.engineVersion || "—" }}</span
            >
          </div>
        </aside>
        @if (navOpen()) {
          <button
            class="nav-scrim"
            aria-label="Cerrar navegación"
            (click)="navOpen.set(false)"
          ></button>
        }
        <div class="main-shell">
          <header class="topbar">
            <div class="topbar-start">
              <button
                mat-icon-button
                class="mobile-menu"
                (click)="navOpen.set(!navOpen())"
                aria-label="Abrir navegación"
              >
                <ds-icon name="menu" /></button
              ><span class="breadcrumb"
                >Operaciones <span>/</span> DataStage</span
              >
            </div>
            <div class="user-block">
              <span class="environment-pill"
                ><i></i>{{ auth.config()?.environment }}</span
              ><span class="avatar">{{
                auth.user()!.name.slice(0, 2).toUpperCase()
              }}</span
              ><span class="user-name"
                >{{ auth.user()?.name
                }}<small>{{ auth.user()?.roles?.join(" · ") }}</small></span
              >
              @if (auth.config()?.authMode === "entra") {
                <button
                  mat-icon-button
                  aria-label="Cerrar sesión"
                  (click)="auth.logout()"
                >
                  <ds-icon name="logout" />
                </button>
              }
            </div>
          </header>
          @if (auth.config()?.authMode === "development") {
            <div class="development-banner">
              <ds-icon name="shield" /><strong>Desarrollo local</strong
              ><span
                >Identidad de prueba habilitada. Configura Microsoft Entra ID
                antes de desplegar a producción.</span
              >
            </div>
          }
          <main id="main-content" tabindex="-1"><router-outlet /></main>
          <footer class="app-footer">
            <span>DataStage · Plataforma de procesamiento</span
            ><span>Trazabilidad en cada registro</span>
          </footer>
        </div>
      </div>
    } @else {
      <main id="main-content" class="login-shell"><router-outlet /></main>
    }
  `,
})
export class App {
  auth = inject(Auth);
  navOpen = signal(false);
  allowedNavigation() {
    return this.navigation.filter(
      (item) =>
        !["/monthly", "/annual"].includes(item.path) ||
        this.auth.hasRole("Operator", "Admin"),
    );
  }
  navigation = [
    { path: "/", label: "Resumen", icon: "grid" },
    { path: "/monthly", label: "Carga mensual", icon: "upload" },
    { path: "/runs", label: "Historial de procesos", icon: "history" },
    { path: "/annual", label: "Consolidado anual", icon: "calendar" },
    { path: "/data", label: "Consulta de datos", icon: "database" },
    { path: "/agent", label: "Asistente", icon: "spark" },
    { path: "/administration", label: "Administración", icon: "settings" },
  ];
}
