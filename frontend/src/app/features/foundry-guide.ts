import { Component, inject, signal } from "@angular/core";
import { RouterLink } from "@angular/router";
import { I18n } from "../core/i18n";
import { Auth } from "../core/auth";
import { Icon } from "../shared/ui";

@Component({
  selector: "ds-foundry-guide",
  imports: [RouterLink, Icon],
  template: `<a routerLink="/agent" class="back-link">{{
      t("Volver al asistente", "Back to assistant")
    }}</a>
    <header class="guide-heading">
      <div>
        <span class="eyebrow">MICROSOFT FOUNDRY</span>
        <h1>{{ t("Configurar el asistente", "Configure the assistant") }}</h1>
        <p>
          {{
            t(
              "Guía para cuentas corporativas, con una ruta sin Azure CLI en tu laptop.",
              "For corporate accounts, with a path that needs no Azure CLI on your laptop."
            )
          }}
        </p>
      </div>
      <a href="/guides/azure-foundry.md" download="DataStage-Azure-Foundry.md"
        ><ds-icon name="download" />{{
          t("Guía completa", "Full guide (Spanish)")
        }}</a
      >
    </header>
    <div class="guide-status">
      <ds-icon name="shield" /><span>{{
        auth.config()?.foundryEnabled
          ? t(
              "Conexión habilitada en este entorno",
              "Connection enabled in this environment"
            )
          : t(
              "Pendiente de configuración en este entorno",
              "Awaiting configuration in this environment"
            )
      }}</span
      ><span>{{
        t("Revisado: 3 de octubre de 2026", "Reviewed: October 3, 2026")
      }}</span>
    </div>
    <div class="guide-layout">
      <nav [attr.aria-label]="t('Pasos de configuración', 'Setup steps')">
        @for (step of steps; track step.number) {
          <a [href]="'#step-' + step.number"
            ><span>{{ step.number }}</span
            >{{ t(step.es, step.en) }}</a
          >
        }
      </nav>
      <div class="guide-content">
        <section id="step-1">
          <h2>1. {{ t("Entrar a Foundry", "Open Foundry") }}</h2>
          <p>
            {{
              t(
                "Desde el navegador corporativo, abre Microsoft Foundry, selecciona tu directorio y entra al proyecto autorizado. Comprueba que hay un modelo desplegado compatible con agentes y llamadas a funciones. Anota el nombre exacto del despliegue y el endpoint del proyecto. Si no puedes crear el proyecto o desplegar el modelo, solicítalo a TI.",
                "In your corporate browser, open Microsoft Foundry, select your directory and open the approved project. Check that a model supporting agents and function calling is deployed. Record its exact deployment name and project endpoint. Ask IT if you cannot create the project or deploy the model."
              )
            }}
          </p>
          <p>
            <a href="https://ai.azure.com/" target="_blank" rel="noopener"
              >Microsoft Foundry</a
            >
            ·
            <a
              href="https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/prompt-agent"
              target="_blank"
              rel="noopener"
              >{{ t("Documentación oficial", "Official documentation") }}</a
            >
          </p>
          <code class="endpoint"
            >https://RECURSO.services.ai.azure.com/api/projects/PROYECTO</code
          >
        </section>
        <section id="step-2">
          <h2>2. {{ t("Qué pedir a TI", "What to request from IT") }}</h2>
          <p>
            {{
              t(
                "Pide a TI el proyecto y endpoint de Foundry, el despliegue del modelo, la región y un entorno autorizado con Python, acceso al repositorio y red hacia Foundry. La identidad que registra versiones necesita permiso de creación, por ejemplo Foundry User; para la identidad del backend que sólo invoca el agente, revisa Foundry Agent Consumer. TI define el ámbito y prepara las identidades.",
                "Ask IT for the Foundry project and endpoint, model deployment, region, and an approved environment with Python, repository access and network access to Foundry. The version registration identity needs creation rights, such as Foundry User; for the backend identity that only invokes the agent, review Foundry Agent Consumer. IT sets the scope and identities."
              )
            }}
          </p>
          <p>
            <a
              href="https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry"
              target="_blank"
              rel="noopener"
              >{{
                t("Roles y ámbitos de Foundry", "Foundry roles and scopes")
              }}</a
            >
          </p>
          <p>
            {{
              t(
                "No necesitas instalar Azure CLI en tu laptop para preparar el proyecto. Iniciar sesión en el portal no autentica automáticamente al proceso Python. La identidad de Azure y los roles del usuario de DataStage son controles distintos.",
                "You do not need Azure CLI on your laptop to prepare the project. Signing in to the portal does not automatically authenticate the Python process. Azure identity and DataStage user roles are separate controls."
              )
            }}
          </p>
        </section>
        <section id="step-3">
          <h2>3. {{ t("Ruta sin Azure CLI", "Path without Azure CLI") }}</h2>
          <p>
            {{
              t(
                "Puedes revisar el proyecto y probar un agente básico en el portal. Para añadir las funciones de DataStage, el script Python debe ejecutarse en un entorno corporativo aprobado, por ejemplo una VM de Azure con identidad administrada o un proceso de integración con identidad federada. El portal no permite editar definiciones de funciones personalizadas.",
                "You can inspect the project and test a basic agent in the portal. To add DataStage functions, run the Python script in an approved corporate environment, such as an Azure VM with a managed identity or a build job with federated identity. The portal cannot edit custom function definitions."
              )
            }}
          </p>
          <p>
            {{
              t(
                "Configura estos valores en el entorno autorizado. Para registrar, deja desactivadas la invocación y las acciones hasta obtener la versión del agente.",
                "Set these values in the approved environment. Keep invocation and actions disabled until you have registered an agent version."
              )
            }}
          </p>
          <div class="command">
            <button
              (click)="copy('environment')"
              [attr.aria-label]="
                t('Copiar configuración', 'Copy configuration')
              "
            >
              {{
                copied() === "environment"
                  ? t("Copiado", "Copied")
                  : t("Copiar", "Copy")
              }}
            </button>
            <pre>{{ commands.environment }}</pre>
          </div>
        </section>
        <section id="step-4">
          <h2>
            4.
            {{
              t("Registrar la versión del agente", "Register an agent version")
            }}
          </h2>
          <p>
            {{
              t(
                "Puedes revisar la definición en tu laptop sin conectarte a Azure. Ejecuta --apply sólo en el entorno autorizado con identidad y acceso a Foundry: crea una versión con las herramientas de DataStage. Guarda el nombre y la versión que devuelve.",
                "You can preview the definition on your laptop without connecting to Azure. Run --apply only in the approved environment with an identity and Foundry access: it creates a version with DataStage tools. Save the returned name and version."
              )
            }}
          </p>
          <div class="command">
            <button
              (click)="copy('preview')"
              [attr.aria-label]="t('Copiar vista previa', 'Copy preview')"
            >
              {{
                copied() === "preview"
                  ? t("Copiado", "Copied")
                  : t("Copiar", "Copy")
              }}
            </button>
            <pre>{{ commands.preview }}</pre>
          </div>
          <p>
            {{
              t(
                "Cuando TI confirme el entorno y los permisos, ejecuta este comando allí para crear la versión:",
                "After IT confirms the environment and permissions, run this command there to create the version:"
              )
            }}
          </p>
          <div class="command">
            <button
              (click)="copy('register')"
              [attr.aria-label]="
                t('Copiar registro del agente', 'Copy agent registration')
              "
            >
              {{
                copied() === "register"
                  ? t("Copiado", "Copied")
                  : t("Copiar", "Copy")
              }}
            </button>
            <pre>{{ commands.register }}</pre>
          </div>
          <p>
            {{
              t(
                "Cada --apply crea una nueva versión. Las funciones se ejecutan en el backend DataStage con los permisos del usuario; el portal por sí solo no las ejecuta.",
                "Each --apply creates a new version. Functions run in the DataStage backend with the user’s permissions; the portal alone cannot execute them."
              )
            }}
          </p>
        </section>
        <section id="step-5">
          <h2>5. {{ t("Activar y verificar", "Enable and verify") }}</h2>
          <p>
            {{
              t(
                "Pon la versión devuelta en la configuración del backend y reinicia el proceso API. Ese proceso necesita una identidad con permiso para invocar el agente y acceso de red al endpoint del proyecto.",
                "Set the returned version in the backend configuration and restart the API process. That process needs an identity allowed to invoke the agent and network access to the project endpoint."
              )
            }}
          </p>
          <div class="command">
            <button
              (click)="copy('enable')"
              [attr.aria-label]="t('Copiar activación', 'Copy activation')"
            >
              {{
                copied() === "enable"
                  ? t("Copiado", "Copied")
                  : t("Copiar", "Copy")
              }}
            </button>
            <pre>{{ commands.enable }}</pre>
          </div>
          <p>
            {{
              t(
                "Abre el asistente en el entorno conectado. Si allí se configuró la referencia Excel privada, compara julio y agosto de 2026; si no, consulta los periodos publicados. Verifica las cifras contra el dashboard. get_analytics comparte sus cálculos.",
                "Open the assistant in the connected environment. If the private Excel reference is configured there, compare July and August 2026; otherwise query published periods. Check the figures against the dashboard. get_analytics shares its calculations."
              )
            }}
          </p>
          <p>
            {{
              t(
                "El dashboard funciona sin IA. La conexión Azure sólo queda verificada tras completar una consulta real con evidencia.",
                "The dashboard works without AI. The Azure connection is verified only after a real query returns supporting evidence."
              )
            }}
          </p>
        </section>
        <section id="step-6">
          <h2>6. {{ t("Habilitar tareas", "Enable actions") }}</h2>
          <p>
            {{
              t(
                "Cuando las consultas funcionen, activa DATASTAGE_ALLOW_AGENT_COMMANDS=true, registra una nueva versión y configura esa versión en el backend. En el chat, autoriza las acciones únicamente para el mensaje que inicia la tarea.",
                "Once queries work, set DATASTAGE_ALLOW_AGENT_COMMANDS=true, register a new version and configure that version in the backend. In the chat, authorize actions for the specific message that starts the task."
              )
            }}
          </p>
          <div class="tool-list">
            <div>
              <code>start_annual</code
              ><span>{{
                t(
                  "Consolidación anual · Operator / Admin",
                  "Annual consolidation · Operator / Admin"
                )
              }}</span>
            </div>
            <div>
              <code>reprocess_run</code
              ><span>{{
                t(
                  "Nueva versión con motivo · Reprocessor / Admin",
                  "New version with a reason · Reprocessor / Admin"
                )
              }}</span>
            </div>
            <div>
              <code>get_analytics</code
              ><span>{{
                t(
                  "Análisis con evidencia · Sólo lectura",
                  "Analysis with evidence · Read only"
                )
              }}</span>
            </div>
          </div>
          <p>
            {{
              t(
                "Las acciones conservan idempotencia y auditoría. La guía descargable incluye la ruta corporativa completa, la alternativa con Azure CLI autorizada por TI, las nueve herramientas y diagnóstico.",
                "Actions retain idempotency and audit logs. The downloadable guide covers the full corporate path, an IT-approved Azure CLI alternative, all nine tools and troubleshooting."
              )
            }}
          </p>
        </section>
        @if (copyError()) {
          <p role="status">
            {{
              t(
                "El navegador no permitió copiar el comando.",
                "The browser did not allow copying the command."
              )
            }}
          </p>
        }
      </div>
    </div>`,
  styles: [
    `
      :host {
        display: block;
      }
      .guide-heading {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 25px;
        margin: 18px 0 24px;
      }
      .guide-heading h1 {
        font-size: 28px;
        letter-spacing: 0;
      }
      .guide-heading p {
        font-size: 13px;
        margin-top: 9px;
      }
      .guide-heading > a {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        white-space: nowrap;
      }
      .guide-status {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 0;
        border-block: 1px solid #dfe7ea;
        font-size: 12px;
        color: #758891;
      }
      .guide-status > span:last-child {
        margin-left: auto;
        font-size: 10px;
      }
      .guide-layout {
        display: grid;
        grid-template-columns: 220px minmax(0, 1fr);
        gap: 40px;
        margin-top: 25px;
      }
      .guide-layout nav {
        position: sticky;
        top: 24px;
        align-self: start;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .guide-layout nav a {
        padding: 10px 0;
        color: #526b78;
        font-size: 12px;
      }
      .guide-layout nav span {
        display: inline-block;
        width: 22px;
        color: #0a8b7c;
        font-weight: 700;
      }
      .guide-content {
        max-width: 870px;
        min-width: 0;
      }
      .guide-content section {
        padding: 8px 0 28px;
        border-bottom: 1px solid #dfe7ea;
        margin-bottom: 18px;
        scroll-margin-top: 20px;
      }
      .guide-content h2 {
        font-size: 18px;
        letter-spacing: 0;
        margin-bottom: 14px;
      }
      .guide-content p {
        font-size: 13px;
        line-height: 1.9;
        margin: 12px 0;
      }
      .endpoint {
        display: block;
        word-break: break-all;
        font-size: 12px;
        padding: 13px;
        background: #eaf1f3;
      }
      .command {
        position: relative;
        margin: 18px 0;
        background: #25323b;
        border-radius: 5px;
        color: #dbeced;
        overflow: auto;
      }
      .command pre {
        margin: 0;
        padding: 48px 18px 18px;
        font-size: 12px;
        line-height: 1.8;
      }
      .command button {
        position: absolute;
        top: 9px;
        right: 10px;
        background: #3d4d55;
        color: white;
        font-size: 10px;
        border: 1px solid #56666e;
        border-radius: 3px;
        padding: 4px 9px;
      }
      .tool-list {
        border-block: 1px solid #e1e7eb;
      }
      .tool-list > div {
        display: flex;
        justify-content: space-between;
        gap: 20px;
        padding: 12px 0;
        border-bottom: 1px solid #e1e7eb;
        font-size: 12px;
      }
      .tool-list span {
        color: #72858d;
      }
      @media (max-width: 800px) {
        .guide-layout {
          grid-template-columns: minmax(0, 1fr);
          gap: 20px;
        }
        .guide-layout nav {
          position: static;
          display: grid;
          grid-template-columns: 1fr 1fr;
        }
        .guide-heading {
          align-items: flex-start;
          flex-direction: column;
        }
        .guide-status {
          flex-wrap: wrap;
        }
        .guide-status > span:last-child {
          margin: 0;
        }
        .guide-heading h1 {
          font-size: 24px;
        }
        .tool-list > div {
          flex-direction: column;
          gap: 4px;
        }
      }
    `,
  ],
})
export class FoundryGuide {
  i18n = inject(I18n);
  auth = inject(Auth);
  copied = signal("");
  copyError = signal(false);
  t(es: string, en: string) {
    return this.i18n.choose(es, en);
  }
  steps = [
    { number: 1, es: "Proyecto y modelo", en: "Project and model" },
    { number: 2, es: "Solicitud a TI", en: "Request to IT" },
    { number: 3, es: "Sin Azure CLI", en: "Without Azure CLI" },
    { number: 4, es: "Registrar el agente", en: "Register the agent" },
    { number: 5, es: "Activar y verificar", en: "Enable and verify" },
    { number: 6, es: "Habilitar tareas", en: "Enable actions" },
  ];
  commands = {
    environment:
      "$env:DATASTAGE_FOUNDRY_PROJECT_ENDPOINT = 'https://<RESOURCE>.services.ai.azure.com/api/projects/<PROJECT>'\n$env:DATASTAGE_FOUNDRY_MODEL = '<DEPLOYMENT_NAME>'\n$env:DATASTAGE_FOUNDRY_AGENT_NAME = 'datastage-assistant'\n$env:DATASTAGE_FOUNDRY_ENABLED = 'false'\n$env:DATASTAGE_ALLOW_AGENT_COMMANDS = 'false'",
    preview:
      "Push-Location backend\n..\\.venv\\Scripts\\python.exe -m app.modules.foundry.setup\nPop-Location",
    register:
      "Push-Location backend\n..\\.venv\\Scripts\\python.exe -m app.modules.foundry.setup --apply\nPop-Location",
    enable:
      "$env:DATASTAGE_FOUNDRY_AGENT_VERSION = '<RETURNED_VERSION>'\n$env:DATASTAGE_FOUNDRY_ENABLED = 'true'",
  };
  async copy(key: "environment" | "preview" | "register" | "enable") {
    try {
      await navigator.clipboard.writeText(this.commands[key]);
      this.copied.set(key);
      this.copyError.set(false);
    } catch {
      this.copyError.set(true);
    }
  }
}
