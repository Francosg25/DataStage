"""Explicit Foundry setup. Preview/check never create an agent version."""
import argparse
import json

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.core.exceptions import AzureError

from app.core.config import Settings
from app.core.errors import ApplicationError
from .agent import INSTRUCTIONS
from .credentials import foundry_credential, login_local
from . import local_config
from .tools import tool_definitions


def register_agent(settings: Settings) -> dict:
    local_config.validate_endpoint(settings.foundry_project_endpoint)
    if not settings.foundry_model:
        raise ValueError("Se requiere DATASTAGE_FOUNDRY_MODEL")
    definitions = tool_definitions(settings.allow_agent_commands)
    tools = [FunctionTool(name=t["name"], description=t["description"], parameters=t["parameters"], strict=True) for t in definitions]
    with foundry_credential(settings) as credential:
        with AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=credential, retry_total=0) as project:
            agent = project.agents.create_version(
                agent_name=settings.foundry_agent_name,
                definition=PromptAgentDefinition(model=settings.foundry_model, instructions=INSTRUCTIONS, tools=tools),
            )
    return {"name": agent.name, "version": agent.version}


def check_agent(settings: Settings) -> dict:
    """GET the pinned version and compare its tool contracts; no model inference."""
    local_config.validate_endpoint(settings.foundry_project_endpoint)
    if not all((settings.foundry_model, settings.foundry_agent_name, settings.foundry_agent_version)):
        raise ValueError("Configura modelo, nombre y versión exacta del agente")
    with foundry_credential(settings) as credential:
        with AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=credential,
                             connection_timeout=10, read_timeout=30, retry_total=0) as project:
            agent = project.agents.get_version(agent_name=settings.foundry_agent_name,
                                               agent_version=settings.foundry_agent_version)
    definition = agent.definition.as_dict()
    expected = tool_definitions(settings.allow_agent_commands)
    actual = definition.get("tools", [])
    if (str(agent.name) != settings.foundry_agent_name or str(agent.version) != settings.foundry_agent_version
            or definition.get("kind") != "prompt" or definition.get("model") != settings.foundry_model
            or len(actual) != len(expected)):
        raise ValueError("La versión registrada no coincide con el modelo y las herramientas configurados")
    if definition.get("instructions") != INSTRUCTIONS:
        raise ValueError("Las instrucciones de la versión registrada difieren del contrato local; revisa la versión")
    by_name = {tool.get("name"): tool for tool in actual}
    for tool in expected:
        registered = by_name.get(tool["name"], {})
        if any(registered.get(key) != tool[key] for key in ("type", "strict", "parameters")):
            raise ValueError("Las herramientas registradas difieren del contrato local; revisa la versión")
    return {"name": agent.name, "version": agent.version, "model": settings.foundry_model,
            "tools": len(expected), "status": "verified", "modelCalled": False}


def enable_local(settings: Settings) -> dict:
    local_config.require_local(settings)
    if settings.foundry_auth_mode != "interactive" or settings.allow_agent_commands:
        raise ValueError("La activación local inicial requiere sesión interactiva y acciones deshabilitadas")
    result = check_agent(settings)
    return {**result, **local_config.update_foundry_env({"DATASTAGE_FOUNDRY_ENABLED": True}),
            "foundryEnabled": True, "restartApi": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Configura y comprueba el asistente Foundry DataStage.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--configure-local", action="store_true", help="Configurar backend/.env sin activar IA; conserva otros valores y guarda respaldo.")
    actions.add_argument("--login", action="store_true", help="Inicio de sesión explícito para desarrollo local con caché cifrada.")
    actions.add_argument("--check", action="store_true", help="Leer y comprobar la versión existente; no crea versiones ni ejecuta el modelo.")
    actions.add_argument("--enable-local", action="store_true", help="Comprobar la versión y habilitar las consultas en backend/.env.")
    actions.add_argument("--apply", action="store_true", help="Crear explícitamente una NUEVA versión en Foundry.")
    for option in ("project-endpoint", "tenant-id", "model", "agent-name", "agent-version", "client-id", "redirect-uri"):
        parser.add_argument("--" + option)
    args = parser.parse_args(argv)
    if not args.configure_local and any(value is not None for value in (
        args.project_endpoint, args.tenant_id, args.model, args.agent_name,
        args.agent_version, args.client_id, args.redirect_uri,
    )):
        parser.error("Los parámetros de configuración se utilizan únicamente con --configure-local")
    try:
        if args.configure_local:
            result = local_config.configure_local(
                endpoint=args.project_endpoint, tenant_id=args.tenant_id, model=args.model,
                agent_name=args.agent_name, agent_version=args.agent_version,
                client_id=args.client_id, redirect_uri=args.redirect_uri,
            )
        else:
            settings = Settings(_env_file=local_config.ENV_PATH)
            if args.login:
                result = login_local(settings)
            elif args.check:
                result = check_agent(settings)
            elif args.enable_local:
                result = enable_local(settings)
            elif args.apply:
                result = register_agent(settings)
            else:
                result = {"agentName": settings.foundry_agent_name, "version": settings.foundry_agent_version,
                          "model": settings.foundry_model, "authMode": settings.foundry_auth_mode,
                          "tools": tool_definitions(settings.allow_agent_commands)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ApplicationError as error:
        parser.exit(1, error.detail + "\n")
    except (ValueError, OSError, AzureError) as error:
        parser.exit(1, f"No se completó el paso: {error}\n")


if __name__ == "__main__":
    main()
