"""Register an immutable Foundry agent version only through this explicit CLI.

Preview: python -m app.modules.foundry.setup
Apply:   python -m app.modules.foundry.setup --apply
Required DATASTAGE_FOUNDRY_PROJECT_ENDPOINT and DATASTAGE_FOUNDRY_MODEL.
Authentication uses DefaultAzureCredential (managed identity or developer az login).
"""
import argparse
import json

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

from app.core.config import Settings
from .agent import INSTRUCTIONS
from .tools import tool_definitions


def register_agent(settings: Settings) -> dict:
    if not settings.foundry_project_endpoint.startswith("https://") or not settings.foundry_model:
        raise ValueError("Se requieren DATASTAGE_FOUNDRY_PROJECT_ENDPOINT HTTPS y DATASTAGE_FOUNDRY_MODEL.")
    definitions = tool_definitions(settings.allow_agent_commands)
    tools = [FunctionTool(name=t["name"], description=t["description"], parameters=t["parameters"], strict=True) for t in definitions]
    with DefaultAzureCredential(exclude_interactive_browser_credential=True) as credential:
        with AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=credential) as project:
            agent = project.agents.create_version(
                agent_name=settings.foundry_agent_name,
                definition=PromptAgentDefinition(model=settings.foundry_model, instructions=INSTRUCTIONS, tools=tools),
            )
    return {"name": agent.name, "version": agent.version}


def main():
    parser = argparse.ArgumentParser(description="Registra una nueva versión del agente Foundry DataStage.")
    parser.add_argument("--apply", action="store_true", help="Crear la versión en el proyecto Foundry configurado.")
    args = parser.parse_args()
    settings = Settings()
    if not args.apply:
        print(json.dumps({"agentName": settings.foundry_agent_name, "model": settings.foundry_model, "tools": tool_definitions(settings.allow_agent_commands)}, ensure_ascii=False, indent=2))
        print("Para registrar esta definición: python -m app.modules.foundry.setup --apply")
        return
    result = register_agent(settings)
    print(json.dumps(result, ensure_ascii=False))
    print(f"Configura DATASTAGE_FOUNDRY_AGENT_VERSION={result['version']} y DATASTAGE_FOUNDRY_ENABLED=true.")


if __name__ == "__main__":
    main()
