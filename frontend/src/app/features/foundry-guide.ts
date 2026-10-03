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
              "Del proyecto de Azure a las respuestas y tareas de DataStage.",
              "From your Azure project to DataStage answers and actions."
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
          <h2>1. {{ t("Proyecto y modelo", "Project and model") }}</h2>
          <p>
            {{
              t(
                "Abre Microsoft Foundry, selecciona tu directorio corporativo y entra a tu proyecto. Despliega un modelo compatible con agentes y llamadas a funciones. Anota el nombre exacto del despliegue y el endpoint del proyecto.",
                "Open Microsoft Foundry, select your corporate directory and open your project. Deploy a model that supports agents and function calling. Record the exact deployment name and project endpoint."
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
          <h2>
            2. {{ t("Identidad y permisos", "Identity and permissions") }}
          </h2>
          <p>
            {{
              t(
                "El desarrollador necesita permisos para crear versiones del agente, por ejemplo Foundry User en el proyecto. Para el backend que sólo invoca agentes, revisa Foundry Agent Consumer. Tu administrador debe verificar los permisos y el ámbito.",
                "The developer needs permission to create agent versions, such as Foundry User at project scope. For a backend that only invokes agents, review Foundry Agent Consumer. Your administrator should verify permissions and scope."
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
                "En desarrollo, autentícate con Azure CLI. En Azure, usa una identidad administrada para el backend. La identidad de Azure y los roles del usuario de DataStage son controles distintos.",
                "In development, authenticate with Azure CLI. In Azure, use a managed identity for the backend. The Azure identity and DataStage user roles are separate controls."
              )
            }}
          </p>
          <div class="command">
            <button
              (click)="copy('login')"
              [attr.aria-label]="
                t('Copiar comandos de acceso', 'Copy sign-in commands')
              "
            >
              {{
                copied() === "login"
                  ? t("Copiado", "Copied")
                  : t("Copiar", "Copy")
              }}
            </button>
            <pre>{{ commands.login }}</pre>
          </div>
        </section>
        <section id="step-3">
          <h2>3. {{ t("Variables del entorno", "Environment variables") }}</h2>
          <p>
            {{
              t(
                "Desde PowerShell, en la raíz de DataStage, sustituye los marcadores por tus valores. Mantén esta terminal abierta para que los procesos hereden la configuración.",
                "In PowerShell, at the DataStage root, replace the placeholders with your values. Keep this terminal open so the processes inherit the configuration."
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
                "Primero revisa la definición sin conectarte a Azure. Después ejecuta --apply para crear una versión con las herramientas de esta aplicación. Guarda el nombre y la versión que devuelve.",
                "First preview the definition without connecting to Azure. Then run --apply to create a version with this application’s tools. Record the returned name and version."
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
                "Cada --apply crea una nueva versión. Las funciones se ejecutan en el backend DataStage con los permisos del usuario.",
                "Each --apply creates a new version. Functions run in the DataStage backend with the user’s permissions."
              )
            }}
          </p>
        </section>
        <section id="step-5">
          <h2>5. {{ t("Activar y verificar", "Enable and verify") }}</h2>
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
                "Abre el asistente y compara julio con agosto de 2026 usando la referencia Excel. Verifica que los resultados y las fuentes coincidan con el dashboard. get_analytics comparte exactamente los cálculos de las gráficas.",
                "Open the assistant and compare July with August 2026 using the reference workbook. Verify that results and sources match the dashboard. get_analytics uses exactly the same calculations as the charts."
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
                "Las acciones conservan idempotencia y auditoría. La guía descargable contiene las nueve herramientas, diagnóstico de errores y preparación para Azure.",
                "Actions retain idempotency and audit logs. The downloadable guide includes all nine tools, troubleshooting and Azure deployment preparation."
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
    { number: 2, es: "Identidad y permisos", en: "Identity and permissions" },
    { number: 3, es: "Variables del entorno", en: "Environment variables" },
    { number: 4, es: "Registrar el agente", en: "Register the agent" },
    { number: 5, es: "Activar y verificar", en: "Enable and verify" },
    { number: 6, es: "Habilitar tareas", en: "Enable actions" },
  ];
  commands = {
    login:
      "winget install --exact --id Microsoft.AzureCLI\n# Reopen PowerShell after installing Azure CLI\naz login --tenant '<TENANT_ID>'\naz account set --subscription '<SUBSCRIPTION_ID>'",
    environment:
      "$env:DATASTAGE_FOUNDRY_PROJECT_ENDPOINT = 'https://<RESOURCE>.services.ai.azure.com/api/projects/<PROJECT>'\n$env:DATASTAGE_FOUNDRY_MODEL = '<DEPLOYMENT_NAME>'\n$env:DATASTAGE_FOUNDRY_AGENT_NAME = 'datastage-assistant'\n$env:DATASTAGE_FOUNDRY_ENABLED = 'false'\n$env:DATASTAGE_ALLOW_AGENT_COMMANDS = 'false'",
    register:
      "Push-Location backend\n..\\.venv\\Scripts\\python.exe -m app.modules.foundry.setup\n..\\.venv\\Scripts\\python.exe -m app.modules.foundry.setup --apply\nPop-Location",
    enable:
      "$env:DATASTAGE_FOUNDRY_AGENT_VERSION = '<RETURNED_VERSION>'\n$env:DATASTAGE_FOUNDRY_ENABLED = 'true'\n.\\scripts\\stop-dev.ps1\n.\\scripts\\start-dev.ps1 -SkipInstall",
  };
  async copy(key: "login" | "environment" | "register" | "enable") {
    try {
      await navigator.clipboard.writeText(this.commands[key]);
      this.copied.set(key);
      this.copyError.set(false);
    } catch {
      this.copyError.set(true);
    }
  }
}
