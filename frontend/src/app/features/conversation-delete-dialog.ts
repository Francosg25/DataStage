import { Component, inject } from "@angular/core";
import { MAT_DIALOG_DATA, MatDialogModule } from "@angular/material/dialog";
import { MatButtonModule } from "@angular/material/button";
import { I18n } from "../core/i18n";

@Component({
  selector: "ds-conversation-delete-dialog",
  imports: [MatDialogModule, MatButtonModule],
  template: `
    <h2 mat-dialog-title>
      {{ i18n.choose("¿Eliminar conversación?", "Delete conversation?") }}
    </h2>
    <mat-dialog-content>
      <p class="conversation-title">{{ title }}</p>
      <p>
        {{
          i18n.choose(
            "Se eliminarán sus mensajes y archivos generados de DataStage. Esta acción no se puede deshacer.",
            "Its messages and generated files will be deleted from DataStage. This cannot be undone."
          )
        }}
      </p>
      <p>
        {{
          i18n.choose(
            "Los meses cargados y los datos originales se conservan.",
            "Uploaded months and source data will be kept."
          )
        }}
      </p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button data-cancel [mat-dialog-close]="false">
        {{ i18n.choose("Cancelar", "Cancel") }}
      </button>
      <button mat-flat-button class="delete-button" [mat-dialog-close]="true">
        {{ i18n.choose("Eliminar conversación", "Delete conversation") }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .conversation-title {
      font-weight: 600;
      color: #1b3944;
      overflow-wrap: anywhere;
    }
    p {
      line-height: 1.65;
    }
    .delete-button {
      --mat-button-filled-container-color: #aa353e;
      --mat-button-filled-label-text-color: #fff;
    }
    mat-dialog-actions {
      padding: 12px 24px 24px;
      gap: 8px;
    }
  `,
})
export class ConversationDeleteDialog {
  i18n = inject(I18n);
  title = inject<string>(MAT_DIALOG_DATA);
}
