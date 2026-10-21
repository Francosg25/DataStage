import { TranslatePipe } from "./core/i18n";
import {
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from "@angular/core";
import { BreakpointObserver } from "@angular/cdk/layout";
import { toSignal } from "@angular/core/rxjs-interop";
import { map } from "rxjs";
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
      <div
        class="app-shell"
        [class.sidebar-collapsed]="sidebarCollapsed()"
        (keydown.escape)="closeMobileNavigation()"
      >
        <aside
          id="primary-navigation"
          class="sidebar"
          [class.sidebar-open]="navOpen()"
          [inert]="!navigationExpanded()"
          [attr.aria-hidden]="!navigationExpanded()"
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
                (click)="closeMobileNavigation()"
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
        @if (isMobile()) {
          <button
            class="nav-scrim"
            [class.scrim-visible]="navOpen()"
            [inert]="!navOpen()"
            [attr.aria-hidden]="!navOpen()"
            tabindex="-1"
            [attr.aria-label]="'Cerrar navegación' | t"
            (click)="closeMobileNavigation()"
          ></button>
        }
        <div class="main-shell">
          <header class="topbar">
            <div class="topbar-start">
              <button
                #navigationToggle
                mat-icon-button
                class="navigation-toggle"
                [class.navigation-mobile]="isMobile()"
                (click)="toggleNavigation()"
                [attr.aria-label]="navigationLabel()"
                [title]="navigationLabel()"
                aria-controls="primary-navigation"
                [attr.aria-expanded]="navigationExpanded()"
              >
                <span class="menu-lines" aria-hidden="true"
                  ><span></span><span></span
                ></span></button
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
              @if (auth.config()?.authMode === "entra") {
                <span class="avatar" aria-hidden="true">{{
                  auth.user()!.name.slice(0, 2).toUpperCase()
                }}</span>
                <span class="user-name" [title]="auth.user()!.name">{{
                  auth.user()?.name
                }}</span>
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
          <main id="main-content" tabindex="-1"><router-outlet /></main>
          <footer class="app-footer">
            <span> {{ "DataStage · Plataforma de procesamiento" | t }} </span>
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
  sidebarCollapsed = signal(this.savedSidebarCollapsed());
  isMobile = toSignal(
    inject(BreakpointObserver)
      .observe("(max-width: 900px)")
      .pipe(map((state) => state.matches)),
    { initialValue: false },
  );
  navigationExpanded = computed(() =>
    this.isMobile() ? this.navOpen() : !this.sidebarCollapsed(),
  );
  private navigationToggle =
    viewChild<ElementRef<HTMLButtonElement>>("navigationToggle");
  private savedSidebarCollapsed() {
    try {
      return localStorage.getItem("datastage.sidebarCollapsed") === "true";
    } catch {
      return false;
    }
  }
  navigationLabel() {
    if (this.isMobile()) {
      return this.navOpen()
        ? this.i18n.choose("Cerrar navegación", "Close navigation")
        : this.i18n.choose("Abrir navegación", "Open navigation");
    }
    return this.sidebarCollapsed()
      ? this.i18n.choose("Expandir menú lateral", "Expand sidebar")
      : this.i18n.choose("Minimizar menú lateral", "Collapse sidebar");
  }
  toggleNavigation() {
    if (this.isMobile()) {
      this.navOpen.update((open) => !open);
      return;
    }
    this.sidebarCollapsed.update((collapsed) => !collapsed);
    try {
      localStorage.setItem(
        "datastage.sidebarCollapsed",
        String(this.sidebarCollapsed()),
      );
    } catch {
      // Keep the current choice even when browser storage is unavailable.
    }
  }
  closeMobileNavigation() {
    if (!this.isMobile() || !this.navOpen()) return;
    this.navOpen.set(false);
    this.navigationToggle()?.nativeElement.focus();
  }
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
    { path: "/suppliers", label: "Proveedores", icon: "suppliers" },
    { path: "/agent", label: "Asistente", icon: "spark" },
    { path: "/project-maps", label: "Mapas del proyecto", icon: "map" },
    { path: "/administration", label: "Administración", icon: "settings" },
  ];
}
