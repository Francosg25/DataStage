import { TranslatePipe } from "./core/i18n";
import { Component, inject, signal } from "@angular/core";
import { RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { Auth } from "./core/auth";
import { Icon } from "./shared/ui";
import { I18n } from "./core/i18n";
@Component({
  selector: "app-root",
  imports: [
    TranslatePipe,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    MatButtonModule,
    Icon,
  ],
  template: `
    <a href="#main-content" class="skip-link">
      {{ "Saltar al contenido" | t }}
    </a>
    @if (auth.user()) {
      <div class="app-shell">
        <aside
          class="sidebar"
          [class.sidebar-open]="navOpen()"
          [attr.aria-label]="'Navegación principal' | t"
        >
          <a
            routerLink="/"
            class="brand"
            [attr.aria-label]="'DataStage inicio' | t"
            ><span class="brand-symbol"
              ><span></span><span></span><span></span></span
            ><span>
              {{ "DataStage" | t }}
              <small> {{ "TRADE OPERATIONS" | t }} </small></span
            ></a
          >
          <div class="workspace-label">{{ "ESPACIO DE TRABAJO" | t }}</div>
          <nav>
            @for (item of allowedNavigation(); track item.path) {
              <a
                [routerLink]="item.path"
                routerLinkActive="nav-active"
                [routerLinkActiveOptions]="{ exact: item.path === '/' }"
                (click)="navOpen.set(false)"
                ><ds-icon [name]="item.icon" /><span>{{ item.label | t }}</span>
                @if (item.path === "/agent") {
                  <span class="nav-tag"> {{ "AI" | t }} </span>
                }
              </a>
            }
          </nav>
          <div class="sidebar-bottom">
            <div class="sidebar-note">
              <ds-icon name="shield" /><span>
                {{ "Acceso corporativo" | t }} <br /><strong>{{
                  auth.user()?.scopeId | t
                }}</strong></span
              >
            </div>
            <span class="sidebar-version">
              {{ "Motor" | t }}
              {{ auth.config()?.engineVersion || "—" | t }}</span
            >
          </div>
        </aside>
        @if (navOpen()) {
          <button
            class="nav-scrim"
            [attr.aria-label]="'Cerrar navegación' | t"
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
                [attr.aria-label]="'Abrir navegación' | t"
              >
                <ds-icon name="menu" /></button
              ><span class="breadcrumb">
                {{ "Operaciones" | t }} <span>/</span> {{ "DataStage" | t }}
              </span>
            </div>
            <div class="user-block">
              <select
                class="language-select"
                [attr.aria-label]="'Idioma / Language' | t"
                [value]="i18n.language()"
                (change)="i18n.set($any($event.target).value)"
              >
                <option value="es">{{ "Español" | t }}</option>
                <option value="en">{{ "English" | t }}</option>
              </select>
              <span class="environment-pill"
                ><i></i>{{ auth.config()?.environment | t }}</span
              ><span class="avatar">{{
                auth.user()!.name.slice(0, 2).toUpperCase() | t
              }}</span
              ><span class="user-name"
                >{{ auth.user()?.name | t
                }}<small>{{ auth.user()?.roles?.join(" · ") | t }}</small></span
              >
              @if (auth.config()?.authMode === "entra") {
                <button
                  mat-icon-button
                  [attr.aria-label]="'Cerrar sesión' | t"
                  (click)="auth.logout()"
                >
                  <ds-icon name="logout" />
                </button>
              }
            </div>
          </header>
          @if (auth.config()?.authMode === "development") {
            <div class="development-banner">
              <ds-icon name="shield" /><strong>
                {{ "Desarrollo local" | t }} </strong
              ><span>
                {{
                  "Identidad de prueba habilitada. Configura Microsoft Entra ID antes de desplegar a producción."
                    | t
                }}
              </span>
            </div>
          }
          <main id="main-content" tabindex="-1"><router-outlet /></main>
          <footer class="app-footer">
            <span> {{ "DataStage · Plataforma de procesamiento" | t }} </span
            ><span> {{ "Trazabilidad en cada registro" | t }} </span>
          </footer>
        </div>
      </div>
    } @else {
      <select
        class="language-select login-language"
        aria-label="Idioma / Language"
        [value]="i18n.language()"
        (change)="i18n.set($any($event.target).value)"
      >
        <option value="es">Español</option>
        <option value="en">English</option>
      </select>
      <main id="main-content" class="login-shell"><router-outlet /></main>
    }
  `,
})
export class App {
  i18n = inject(I18n);
  auth = inject(Auth);
  navOpen = signal(false);
  allowedNavigation() {
    return this.navigation.filter(
      (item) =>
        item.path !== "/uploads" || this.auth.hasRole("Operator", "Admin"),
    );
  }
  navigation = [
    { path: "/", label: "Resumen", icon: "grid" },
    { path: "/analytics", label: "Análisis de operaciones", icon: "chart" },
    { path: "/uploads", label: "Cargas", icon: "upload" },
    { path: "/runs", label: "Historial de procesos", icon: "history" },
    { path: "/annual", label: "Comparativa mensual", icon: "calendar" },
    { path: "/data", label: "Consulta de datos", icon: "database" },
    { path: "/agent", label: "Asistente", icon: "spark" },
    { path: "/project-maps", label: "Mapas del proyecto", icon: "map" },
    { path: "/administration", label: "Administración", icon: "settings" },
  ];
}
