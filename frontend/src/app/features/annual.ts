import { Component, inject } from "@angular/core";
import { I18n } from "../core/i18n";
import { MonthComparison } from "../shared/month-comparison";

@Component({
  selector: "ds-annual",
  imports: [MonthComparison],
  template: `
    <div class="page-heading">
      <div>
        <span class="eyebrow">{{
          i18n.choose("ANÁLISIS DE OPERACIONES", "OPERATIONS ANALYTICS")
        }}</span>
        <h1>{{ i18n.choose("Comparativa mensual", "Monthly comparison") }}</h1>
      </div>
    </div>
    <ds-month-comparison />
  `,
})
export class Annual {
  i18n = inject(I18n);
}
