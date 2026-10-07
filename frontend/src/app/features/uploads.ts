import { Component, inject } from "@angular/core";
import { RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { MatButtonModule } from "@angular/material/button";
import { MatTabsModule } from "@angular/material/tabs";
import { I18n, TranslatePipe } from "../core/i18n";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-uploads",
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    MatButtonModule,
    MatTabsModule,
    TranslatePipe,
    Icon,
  ],
  template: `
    <div class="page-heading">
      <div>
        <span class="eyebrow">{{
          i18n.choose("PROCESAMIENTO DE ARCHIVOS", "FILE PROCESSING")
        }}</span>
        <h1>{{ "Cargas" | t }}</h1>
      </div>
      <a mat-stroked-button routerLink="/runs"
        ><ds-icon name="history" />{{ "Ver historial" | t }}</a
      >
    </div>
    <nav
      mat-tab-nav-bar
      [tabPanel]="content"
      [mat-stretch-tabs]="false"
      [attr.aria-label]="i18n.choose('Tipo de carga', 'Upload type')"
    >
      <a
        mat-tab-link
        routerLink="/uploads/monthly"
        routerLinkActive
        #monthly="routerLinkActive"
        [active]="monthly.isActive"
      >
        <ds-icon name="upload" />{{ i18n.choose("Mensuales", "Monthly") }}
      </a>
      <a
        mat-tab-link
        routerLink="/uploads/consolidated"
        routerLinkActive
        #consolidated="routerLinkActive"
        [active]="consolidated.isActive"
      >
        <ds-icon name="file" />{{ i18n.choose("Consolidados", "Consolidated") }}
      </a>
    </nav>
    <mat-tab-nav-panel #content>
      <router-outlet />
    </mat-tab-nav-panel>
  `,
  styles: `
    :host {
      display: block;
      min-width: 0;
    }
    mat-tab-nav-panel {
      display: block;
      padding-top: 28px;
    }
    ds-icon {
      margin-right: 8px;
    }
    @media (max-width: 600px) {
      mat-tab-nav-panel {
        padding-top: 20px;
      }
    }
  `,
})
export class Uploads {
  i18n = inject(I18n);
}
