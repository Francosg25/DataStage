import { DOCUMENT } from "@angular/common";
import { DestroyRef, Injectable, inject, signal } from "@angular/core";
import {
  assistantBlocks,
  inlineText,
  withoutArtifactLinks,
} from "./assistant-text";

type VoiceError =
  | "unsupported"
  | "no-local-voice"
  | "blocked"
  | "failed"
  | "empty";

export function speechText(
  text: string,
  language: string,
  artifactUrls: string[] = [],
): string {
  const plain = (value: string) =>
    inlineText(value)
      .map((part) => part.text)
      .join("")
      .replace(/\[([^\]\n]+)\]\([^\n]*?\)/g, "$1");
  return assistantBlocks(withoutArtifactLinks(text, artifactUrls))
    .map((block) => {
      if (block.type === "code")
        return language.startsWith("es")
          ? "Bloque de código disponible en pantalla."
          : "Code block available on screen.";
      if (block.type === "table") {
        const [headers, ...rows] = block.rows;
        return rows
          .map(
            (row) =>
              row
                .map(
                  (value, index) =>
                    `${plain(headers[index] || "")}: ${plain(value)}`,
                )
                .join("; ") + ".",
          )
          .join(" ");
      }
      return block.lines.map(plain).join(". ");
    })
    .join(". ")
    .replace(/\s+/g, " ")
    .trim();
}

export function speechChunks(text: string): string[] {
  const chunks: string[] = [];
  let remaining = Array.from(text);
  while (remaining.length) {
    let length = Math.min(220, remaining.length);
    if (remaining.length > length) {
      const space = remaining.slice(0, length).lastIndexOf(" ");
      if (space > 100) length = space;
    }
    const chunk = remaining.slice(0, length).join("").trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(length);
  }
  return chunks;
}

// Scoped to the chat component. Never fall back to a remote browser voice.
@Injectable()
export class AssistantSpeech {
  private window = inject(DOCUMENT).defaultView;
  private destroy = inject(DestroyRef);
  private synthesis = this.window?.speechSynthesis;
  private Utterance = this.window?.SpeechSynthesisUtterance;
  private voices = signal<SpeechSynthesisVoice[]>([]);
  private generation = 0;
  private utterance?: SpeechSynthesisUtterance;
  private disposed = false;
  readonly supported = signal(!!this.synthesis && !!this.Utterance);
  readonly active = signal<string | null>(null);
  readonly error = signal<VoiceError | null>(null);

  constructor() {
    const refresh = () => this.refreshVoices();
    if (this.supported()) {
      refresh();
      this.synthesis!.addEventListener("voiceschanged", refresh);
    }
    this.destroy.onDestroy(() => {
      this.disposed = true;
      this.stop();
      this.synthesis?.removeEventListener("voiceschanged", refresh);
    });
  }
  private refreshVoices() {
    try {
      this.voices.set(
        (this.synthesis?.getVoices() || []).filter(
          (voice) => voice.localService === true,
        ),
      );
    } catch {
      this.voices.set([]);
    }
  }
  private voice(locale: string) {
    const normalized = (value: string) =>
      value.toLowerCase().replace(/_/g, "-");
    const language = normalized(locale).split("-")[0];
    return (
      this.voices().find(
        (voice) => normalized(voice.lang) === normalized(locale),
      ) ||
      this.voices().find(
        (voice) => normalized(voice.lang).split("-")[0] === language,
      )
    );
  }
  available(locale: string) {
    return this.supported() && !!this.voice(locale);
  }
  stop() {
    this.generation++;
    const current = this.utterance;
    this.utterance = undefined;
    this.active.set(null);
    if (current) {
      current.onend = current.onerror = null;
      try {
        this.synthesis?.cancel();
      } catch {
        /* Playback is already stopped. */
      }
    }
  }
  read(text: string, key: string, locale: string, artifactUrls: string[] = []) {
    if (this.disposed) return;
    this.stop();
    this.error.set(null);
    if (!this.supported()) {
      this.error.set("unsupported");
      return;
    }
    this.refreshVoices();
    const voice = this.voice(locale);
    if (!voice) {
      this.error.set("no-local-voice");
      return;
    }
    const chunks = speechChunks(speechText(text, locale, artifactUrls));
    if (!chunks.length) {
      this.error.set("empty");
      return;
    }
    const generation = this.generation;
    this.active.set(key);
    const next = (index: number) => {
      if (this.disposed || generation !== this.generation) return;
      if (index === chunks.length) {
        this.utterance = undefined;
        this.active.set(null);
        return;
      }
      const utterance = new this.Utterance!(chunks[index]);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = 1;
      utterance.onend = () => {
        utterance.onend = utterance.onerror = null;
        next(index + 1);
      };
      utterance.onerror = (event) => {
        if (generation !== this.generation || this.disposed) return;
        this.stop();
        if (event.error !== "canceled" && event.error !== "interrupted")
          this.error.set(event.error === "not-allowed" ? "blocked" : "failed");
      };
      this.utterance = utterance;
      try {
        this.synthesis!.speak(utterance);
      } catch {
        this.stop();
        this.error.set("failed");
      }
    };
    next(0);
  }
}
