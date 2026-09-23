import { Component, inject } from "@angular/core";
import { Router } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { Auth } from "../core/auth";
import { Icon } from "../shared/ui";
@Component({
  selector: "ds-login",
  imports: [MatButtonModule, Icon],
  template: `<section class="login-card">
    <div class="login-logo"><ds-icon name="database" /></div>
    <span class="eyebrow">OPERACIONES DE COMERCIO EXTERIOR</span>
    <h1>Bienvenido a DataStage</h1>
    <p>
      Un solo lugar para procesar tus periodos, consultar información y mantener
      la trazabilidad de tus datos.
    </p>
    @if (auth.error()) {
      <div class="error-message" role="alert">{{ auth.error() }}</div>
      <button mat-flat-button (click)="reload()">Reintentar conexión</button>
    } @else {
      <button mat-flat-button (click)="login()">
        Continuar con Microsoft <ds-icon name="arrow" />
      </button>
    }
    <small>Acceso exclusivo para usuarios autorizados.</small>
  </section>`,
})
export class Login {
  auth = inject(Auth);
  router = inject(Router);
  constructor() {
    if (this.auth.user()) this.router.navigateByUrl("/");
  }
  login() {
    this.auth
      .login()
      .catch(() =>
        this.auth.error.set("No se pudo iniciar sesión. Intenta nuevamente."),
      );
  }
  reload() {
    window.location.reload();
  }
}
