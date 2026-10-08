import { Component, inject } from "@angular/core";
import { Auth } from "../core/auth";
import { I18n } from "../core/i18n";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-entra-setup",
  imports: [Icon],
  template: `<section>
    <div class="setup-heading">
      <h2>Microsoft Entra ID</h2>
      <a href="/guides/microsoft-entra-id.txt" download
        ><ds-icon name="download" />
        {{ t("Guía para TI", "IT guide (Spanish)") }}</a
      >
    </div>
    <dl>
      <div>
        <dt>{{ t("Inicio de sesión actual", "Current sign-in") }}</dt>
        <dd>
          {{
            auth.config()?.authMode === "entra"
              ? "Microsoft Entra ID"
              : t("Desarrollo local", "Local development")
          }}
        </dd>
      </div>
      <div>
        <dt>Tenant ID</dt>
        <dd>
          {{
            auth.config()?.entra?.tenantId ||
              t("Pendiente de TI", "Pending IT input")
          }}
        </dd>
      </div>
      <div>
        <dt>{{ t("Cliente SPA", "SPA client") }}</dt>
        <dd>
          {{
            auth.config()?.entra?.clientId ||
              t("Pendiente de TI", "Pending IT input")
          }}
        </dd>
      </div>
      <div>
        <dt>{{ t("Permiso delegado de API", "Delegated API permission") }}</dt>
        <dd>
          {{
            auth.config()?.entra?.apiScope ||
              t("Pendiente de TI", "Pending IT input")
          }}
        </dd>
      </div>
      <div>
        <dt>Redirect URI (SPA)</dt>
        <dd>{{ redirectUri }}</dd>
      </div>
    </dl>
    <details>
      <summary>
        {{
          t(
            "Preparación con la cuenta corporativa",
            "Corporate account preparation"
          )
        }}
      </summary>
      <ol>
        <li>
          {{
            t(
              "TI debe confirmar el tenant y autorizar dos registros de aplicación: DataStage API y DataStage Web, ambos de un solo tenant.",
              "IT must confirm the tenant and authorize two single-tenant app registrations: DataStage API and DataStage Web."
            )
          }}
        </li>
        <li>
          {{
            t(
              "En la API: tokens v2, permiso delegado access_as_user y roles Reader, Operator, Reprocessor, Auditor y Admin. Asignar a cada usuario solo los roles necesarios.",
              "For the API: v2 tokens, the access_as_user delegated permission, and Reader, Operator, Reprocessor, Auditor and Admin roles. Assign only the roles each user needs."
            )
          }}
        </li>
        <li>
          {{
            t(
              "En Web: plataforma SPA, URI de retorno exacta y permiso delegado de DataStage API. El consentimiento administrativo debe seguir la política de TI.",
              "For Web: SPA platform, exact redirect URI and the DataStage API delegated permission. Admin consent must follow IT policy."
            )
          }}
        </li>
        <li>
          {{
            t(
              "Validar la configuración en un entorno de prueba antes de activar Entra. No se requieren Azure CLI ni secretos en Angular. No se modifican MFA ni acceso condicional.",
              "Validate configuration in a test environment before enabling Entra. Azure CLI and Angular client secrets are not required. MFA and Conditional Access remain unchanged."
            )
          }}
        </li>
      </ol>
      <a
        href="https://entra.microsoft.com/"
        target="_blank"
        rel="noopener noreferrer"
        >{{
          t("Abrir portal de Microsoft Entra", "Open Microsoft Entra portal")
        }}
        <ds-icon name="arrow"
      /></a>
    </details>
  </section>`,
  styles: [
    `
      section {
        margin: 0 24px 24px;
        padding-top: 24px;
        border-top: 1px solid #dbe3e7;
      }
      .setup-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
      }
      h2 {
        margin: 0;
        font-size: 18px;
      }
      a {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        color: #146c62;
        font-size: 13px;
      }
      ds-icon {
        width: 16px;
        height: 16px;
      }
      dl {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
        gap: 20px;
        margin: 24px 0;
      }
      dt {
        font-size: 12px;
        color: #586a73;
        margin-bottom: 5px;
      }
      dd {
        font-size: 13px;
        font-weight: 600;
        margin: 0;
        overflow-wrap: anywhere;
      }
      details {
        border-top: 1px solid #dbe3e7;
        padding-top: 16px;
      }
      summary {
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
      }
      ol {
        padding-left: 22px;
        font-size: 13px;
        line-height: 1.7;
      }
      li {
        padding: 6px 0;
      }
    `,
  ],
})
export class EntraSetup {
  readonly auth = inject(Auth);
  private readonly i18n = inject(I18n);
  readonly redirectUri = window.location.origin + "/login";
  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
}
