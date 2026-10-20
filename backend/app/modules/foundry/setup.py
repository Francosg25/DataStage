"""Register an immutable Foundry agent version only through this explicit CLI.

Preview: python -m app.modules.foundry.setup
Apply:   python -m app.modules.foundry.setup --apply
Required DATASTAGE_FOUNDRY_PROJECT_ENDPOINT and DATASTAGE_FOUNDRY_MODEL.
Browser sign-in is an explicit development-only --login action.
"""
import argparse
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition

from app.core.config import Settings
from .agent import INSTRUCTIONS
from .auth import credential, login
from .local import validate_project, write_env
from .tools import tool_definitions


def register_agent(settings: Settings) -> dict:
    validate_project(settings.foundry_project_endpoint)
    if not settings.foundry_model.strip():
        raise ValueError("Se requieren DATASTAGE_FOUNDRY_PROJECT_ENDPOINT HTTPS y DATASTAGE_FOUNDRY_MODEL.")
    definitions = tool_definitions(settings.allow_agent_commands)
    tools = [FunctionTool(name=t["name"], description=t["description"], parameters=t["parameters"], strict=True) for t in definitions]
    with credential(settings) as identity:
        with AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=identity) as project:
            agent = project.agents.create_version(
                agent_name=settings.foundry_agent_name,
                definition=PromptAgentDefinition(model=settings.foundry_model, instructions=INSTRUCTIONS, tools=tools),
            )
    return {"name": agent.name, "version": agent.version}


def check_agent(settings):
    validate_project(settings.foundry_project_endpoint)
    with credential(settings) as identity:
        with AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=identity) as project:
            agent = project.agents.get_version(
                agent_name=settings.foundry_agent_name, agent_version=settings.foundry_agent_version)
    return {"name": agent.name, "version": agent.version}


def main():
    parser = argparse.ArgumentParser(description="Registra una nueva versión del agente Foundry DataStage.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply", action="store_true", help="Crear una versión en el proyecto Foundry configurado.")
    actions.add_argument("--configure-local", action="store_true", help="Preparar .env local con el asistente desactivado; sin llamadas a Azure.")
    actions.add_argument("--login", action="store_true", help="Iniciar sesión corporativa en el navegador (desarrollo).")
    actions.add_argument("--check", action="store_true", help="Leer la versión configurada; no crea versiones ni genera respuestas.")
    parser.add_argument("--save-env", action="store_true", help="Con --apply: guardar la versión devuelta y habilitar el asistente local.")
    parser.add_argument("--project-endpoint", help="Endpoint del proyecto, para --configure-local.")
    parser.add_argument("--model", help="Nombre exacto del despliegue, para --configure-local.")
    parser.add_argument("--auth-mode", choices=["browser", "default"], default="browser")
    parser.add_argument("--tenant-id", help="Directorio corporativo opcional, para --configure-local.")
    args = parser.parse_args()
    settings = Settings()
    if args.save_env and not args.apply:
        parser.error("--save-env solo puede usarse con --apply")
    if args.save_env and settings.environment == "production":
        parser.error("En producción configura la versión mediante las variables del servicio")
    if args.configure_local:
        if settings.environment == "production":
            parser.error("Configura producción mediante las variables del servicio Azure")
        endpoint = validate_project(args.project_endpoint or settings.foundry_project_endpoint)
        model = (args.model or input("Nombre exacto del despliegue de Foundry: ")).strip()
        if not model or len(model) > 200 or any(ord(c) < 32 for c in model):
            parser.error("Indica el nombre exacto de un despliegue existente")
        write_env(Path(".env"), {
            "DATASTAGE_FOUNDRY_PROJECT_ENDPOINT": endpoint,
            "DATASTAGE_FOUNDRY_MODEL": model,
            "DATASTAGE_FOUNDRY_AGENT_NAME": settings.foundry_agent_name,
            "DATASTAGE_FOUNDRY_AUTH_MODE": args.auth_mode,
            "DATASTAGE_FOUNDRY_TENANT_ID": args.tenant_id or settings.foundry_tenant_id,
            "DATASTAGE_FOUNDRY_ENABLED": "false", "DATASTAGE_ALLOW_AGENT_COMMANDS": "false",
        })
        print("Configuración guardada en backend/.env. Asistente desactivado. No se llamó a Azure.")
        print("Siguiente paso: python -m app.modules.foundry.setup --login")
        return
    if args.login:
        login(settings)
        print("Sesión guardada mediante la caché cifrada de Azure Identity. No se registró ningún agente.")
        return
    if args.check:
        print(json.dumps(check_agent(settings), ensure_ascii=False))
        print("La versión existe y tu identidad puede leerla. Falta probar una pregunta desde DataStage.")
        return
    if not args.apply:
        print(json.dumps({"projectEndpoint": settings.foundry_project_endpoint, "authMode": settings.foundry_auth_mode,
                          "agentName": settings.foundry_agent_name, "model": settings.foundry_model,
                          "tools": tool_definitions(settings.allow_agent_commands)}, ensure_ascii=False, indent=2))
        print("Para registrar esta definición: python -m app.modules.foundry.setup --apply")
        return
    result = register_agent(settings)
    if args.save_env:
        write_env(Path(".env"), {"DATASTAGE_FOUNDRY_AGENT_NAME": result["name"],
                               "DATASTAGE_FOUNDRY_AGENT_VERSION": result["version"],
                               "DATASTAGE_FOUNDRY_ENABLED": "true"})
    print(json.dumps(result, ensure_ascii=False))
    if args.save_env:
        print("Versión guardada y asistente habilitado. Reinicia el backend y prueba la pantalla del asistente.")
    else:
        print(f"Configura DATASTAGE_FOUNDRY_AGENT_VERSION={result['version']} y DATASTAGE_FOUNDRY_ENABLED=true.")


if __name__ == "__main__":
    main()
