import { TestBed } from "@angular/core/testing";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantSpeech, speechText } from "./assistant-speech";

class Utterance {
  voice: SpeechSynthesisVoice | null = null;
  lang = "";
  rate = 1;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  constructor(readonly text: string) {}
}
const local = (lang = "es-MX") =>
  ({
    name: "Device voice",
    lang,
    localService: true,
    default: false,
    voiceURI: lang,
  }) as SpeechSynthesisVoice;
function setup(voices: SpeechSynthesisVoice[] = [local()]) {
  const synthesis = Object.assign(new EventTarget(), {
    getVoices: vi.fn(() => voices),
    speak: vi.fn<(value: Utterance) => void>(),
    cancel: vi.fn(),
  });
  vi.stubGlobal("speechSynthesis", synthesis);
  vi.stubGlobal("SpeechSynthesisUtterance", Utterance);
  TestBed.configureTestingModule({ providers: [AssistantSpeech] });
  return { speech: TestBed.inject(AssistantSpeech), synthesis };
}
afterEach(() => {
  TestBed.resetTestingModule();
  vi.unstubAllGlobals();
});

describe("lectura local de respuestas", () => {
  it("elige una voz local del idioma, conserva los importes y termina la reproducción", () => {
    const remote = { ...local(), name: "Cloud voice", localService: false };
    const { speech, synthesis } = setup([remote, local("es-ES"), local()]);
    speech.read("**Total**: 100.25 USD", "answer", "es-MX");
    const utterance = synthesis.speak.mock.calls[0][0];
    expect(utterance.text).toBe("Total: 100.25 USD");
    expect(utterance.voice?.lang).toBe("es-MX");
    expect(utterance.voice?.localService).toBe(true);
    expect(speech.active()).toBe("answer");
    utterance.onend?.();
    expect(speech.active()).toBeNull();
  });
  it("rechaza voces remotas y no cambia a otro idioma cuando falta una local", () => {
    const { speech, synthesis } = setup([
      { ...local(), localService: false },
      local("en-US"),
    ]);
    speech.read("Datos privados", "answer", "es-MX");
    expect(synthesis.speak).not.toHaveBeenCalled();
    expect(speech.error()).toBe("no-local-voice");
    expect(speech.available("es-MX")).toBe(false);
    synthesis.getVoices.mockReturnValue([local()]);
    synthesis.dispatchEvent(new Event("voiceschanged"));
    expect(speech.available("es-MX")).toBe(true);
  });
  it("lee todo el texto largo por fragmentos y detiene callbacks antiguos al cambiar de respuesta", () => {
    const { speech, synthesis } = setup();
    const text = "Importe 12500.25 y fracción 01234567. ".repeat(20).trim();
    speech.read(text, "first", "es-MX");
    const first = synthesis.speak.mock.calls[0][0];
    const staleEnd = first.onend;
    let index = 0;
    const heard: string[] = [];
    while (speech.active()) {
      const current = synthesis.speak.mock.calls[index++][0];
      expect(Array.from(current.text).length).toBeLessThanOrEqual(220);
      heard.push(current.text);
      current.onend?.();
    }
    expect(heard.join(" ")).toBe(text);
    speech.read("Otra respuesta", "second", "es-MX");
    const before = synthesis.speak.mock.calls.length;
    staleEnd?.();
    expect(synthesis.speak).toHaveBeenCalledTimes(before);
    expect(speech.active()).toBe("second");
    speech.stop();
    expect(synthesis.cancel).toHaveBeenCalledOnce();
    expect(speech.active()).toBeNull();
  });
  it("limpia la voz al destruir el chat y no reproduce respuestas que lleguen tarde", () => {
    const { speech, synthesis } = setup();
    speech.read("Respuesta", "answer", "es-MX");
    const oldEnd = synthesis.speak.mock.calls[0][0].onend;
    TestBed.resetTestingModule();
    oldEnd?.();
    speech.read("Respuesta tardía", "late", "es-MX");
    expect(synthesis.speak).toHaveBeenCalledOnce();
    expect(synthesis.cancel).toHaveBeenCalledOnce();
    expect(speech.active()).toBeNull();
  });
  it("presenta el bloqueo del navegador sin lanzar errores al chat", () => {
    const { speech, synthesis } = setup();
    speech.read("Respuesta", "answer", "es-MX");
    synthesis.speak.mock.calls[0][0].onerror?.({ error: "not-allowed" });
    expect(speech.active()).toBeNull();
    expect(speech.error()).toBe("blocked");
  });
  it("funciona sin API de voz y comunica la limitación", () => {
    vi.stubGlobal("speechSynthesis", undefined);
    vi.stubGlobal("SpeechSynthesisUtterance", undefined);
    TestBed.configureTestingModule({ providers: [AssistantSpeech] });
    const speech = TestBed.inject(AssistantSpeech);
    expect(speech.supported()).toBe(false);
    expect(() => speech.read("Respuesta", "answer", "es-MX")).not.toThrow();
    expect(speech.error()).toBe("unsupported");
  });
  it("convierte tablas en campos legibles sin recitar enlaces técnicos ni ejecutar código", () => {
    const url = "/api/v1/agent/conversations/chat/artifacts/file";
    const spoken = speechText(
      `## Resumen\n\n| Proveedor | Total |\n| --- | --- |\n| Alpha | 100.25 USD |\n\n[Descargar](${url})\n\n\`\`\`js\nalert(1)\n\`\`\``,
      "es-MX",
      [url],
    );
    expect(spoken).toContain("Proveedor: Alpha; Total: 100.25 USD");
    expect(spoken).toContain("Bloque de código disponible en pantalla");
    expect(spoken).not.toContain("alert(1)");
    expect(spoken).not.toContain(url);
  });
});
