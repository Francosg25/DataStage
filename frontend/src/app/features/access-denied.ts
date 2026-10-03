import { TranslatePipe } from "../core/i18n";
import { Component } from "@angular/core";
import { RouterLink } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { Icon } from "../shared/ui";
@Component({
  selector: "ds-access-denied",
  imports: [TranslatePipe, RouterLink, MatButtonModule, Icon],
  template: `<section class="panel disabled-agent">
    <div class="assistant-symbol"><ds-icon name="shield" /></div>
    <h1>{{ "Acceso restringido" | t }}</h1>
    <p>
      {{
        "Tu cuenta tiene acceso de consulta. Para iniciar este proceso necesitas el rol de operador asignado por el administrador."
          | t
      }}
    </p>
    <a mat-flat-button routerLink="/" style="margin-top:24px">
      {{ "Volver al resumen" | t }}
    </a>
  </section>`,
})
export class AccessDenied {}
