import { TestBed } from "@angular/core/testing";
import { of } from "rxjs";
import { describe, expect, it, vi } from "vitest";
import { Api } from "../core/api";
import { Auth } from "../core/auth";
import { Agent } from "./agent";
function createAgent(enabled: boolean, permitted: boolean) {
  const message = vi
    .fn()
    .mockReturnValue(of({ message: "Consulta completada", evidence: [] }));
  TestBed.configureTestingModule({
    providers: [
      {
        provide: Api,
        useValue: { conversation: () => of({ id: "conversation-1" }), message },
      },
      {
        provide: Auth,
        useValue: {
          config: () => ({ foundryEnabled: true, allowAgentCommands: enabled }),
          hasRole: () => permitted,
        },
      },
    ],
  });
  const component = TestBed.runInInjectionContext(() => new Agent());
  component.message.setValue("Consolida el periodo");
  component.allowActions.setValue(true);
  return { component, message };
}
describe("autorización por consulta del asistente", () => {
  it("envía acciones únicamente cuando el entorno y el rol lo permiten y reinicia el consentimiento", async () => {
    const { component, message } = createAgent(true, true);
    await component.send();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Consolida el periodo",
      true,
    );
    expect(component.allowActions.value).toBe(false);
  });
  it("no habilita acciones si falta el rol aunque el control estuviera marcado", async () => {
    const { component, message } = createAgent(true, false);
    await component.send();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Consolida el periodo",
      false,
    );
  });
  it("respeta el bloqueo del entorno aunque el usuario tenga permisos", async () => {
    const { component, message } = createAgent(false, true);
    await component.send();
    expect(message).toHaveBeenCalledWith(
      "conversation-1",
      "Consolida el periodo",
      false,
    );
  });
});
