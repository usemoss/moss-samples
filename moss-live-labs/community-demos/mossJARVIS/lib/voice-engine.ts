import { CheetahWorker, type CheetahTranscript } from "@picovoice/cheetah-web";
import { BuiltInKeyword, PorcupineWorker } from "@picovoice/porcupine-web";
import { WebVoiceProcessor } from "@picovoice/web-voice-processor";

type VoiceCallbacks = {
  onWake: () => void;
  onPartial: (text: string) => void;
  onUtterance: (text: string) => void;
  onError: (message: string) => void;
};

export class JarvisVoiceEngine {
  private porcupine: PorcupineWorker | null = null;
  private cheetah: CheetahWorker | null = null;
  private transcript = "";
  private listening = false;
  private endpointTimer: number | null = null;

  constructor(private callbacks: VoiceCallbacks) {}

  async initialize(accessKey: string) {
    if (!accessKey.trim()) throw new Error("Add NEXT_PUBLIC_PICOVOICE_ACCESS_KEY to enable wake-word mode.");
    if (this.porcupine && this.cheetah) return;

    this.porcupine = await PorcupineWorker.create(
      accessKey,
      BuiltInKeyword.Jarvis,
      () => {
        this.callbacks.onWake();
        void this.listenOnce();
      },
      { publicPath: "/models/porcupine_params.pv", version: 1 },
      { processErrorCallback: (error) => this.callbacks.onError(String(error)) },
    );

    this.cheetah = await CheetahWorker.create(
      accessKey,
      (result: CheetahTranscript) => void this.handleTranscript(result),
      { publicPath: "/models/cheetah_params.pv", version: 1 },
      {
        endpointDurationSec: 1.15,
        enableAutomaticPunctuation: true,
        processErrorCallback: (error) => this.callbacks.onError(String(error)),
      },
    );
    await WebVoiceProcessor.subscribe(this.porcupine);
  }

  async listenOnce() {
    if (!this.porcupine || !this.cheetah || this.listening) return;
    this.listening = true;
    this.transcript = "";
    await WebVoiceProcessor.unsubscribe(this.porcupine);
    await WebVoiceProcessor.subscribe(this.cheetah);
    this.endpointTimer = window.setTimeout(() => this.cheetah?.flush(), 12_000);
  }

  private async handleTranscript(result: CheetahTranscript) {
    if (result.transcript) {
      this.transcript = `${this.transcript}${result.transcript}`.trimStart();
      this.callbacks.onPartial(this.transcript);
    }
    if ((result.isEndpoint || result.isFlushed) && this.transcript.trim()) {
      const finalText = this.transcript.trim();
      await this.returnToWakeMode();
      this.callbacks.onUtterance(finalText);
    }
  }

  private async returnToWakeMode() {
    if (this.endpointTimer) window.clearTimeout(this.endpointTimer);
    this.endpointTimer = null;
    if (this.cheetah) await WebVoiceProcessor.unsubscribe(this.cheetah);
    this.listening = false;
    this.transcript = "";
    if (this.porcupine) await WebVoiceProcessor.subscribe(this.porcupine);
  }

  async pause() {
    if (this.endpointTimer) window.clearTimeout(this.endpointTimer);
    this.endpointTimer = null;
    if (this.cheetah && this.listening) await WebVoiceProcessor.unsubscribe(this.cheetah);
    if (this.porcupine && !this.listening) await WebVoiceProcessor.unsubscribe(this.porcupine);
  }

  async resumeWake() {
    this.listening = false;
    if (this.porcupine) await WebVoiceProcessor.subscribe(this.porcupine);
  }

  async destroy() {
    await WebVoiceProcessor.reset();
    await this.porcupine?.release();
    await this.cheetah?.release();
    this.porcupine?.terminate();
    this.cheetah?.terminate();
    this.porcupine = null;
    this.cheetah = null;
  }
}

