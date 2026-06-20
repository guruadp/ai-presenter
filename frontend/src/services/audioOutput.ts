export interface AudioOutput {
  play(url: string, onEnded: () => void): void;
  pause(): void;
  resume(): void;
  stop(): void;
}

/** Plays audio through the browser's default output device. */
export class LaptopSpeaker implements AudioOutput {
  private audio: HTMLAudioElement | null = null;

  play(url: string, onEnded: () => void): void {
    this.stop();
    const audio = new Audio(url);
    this.audio = audio;
    audio.onended = onEnded;
    audio.onerror = onEnded;
    audio.play().catch(onEnded);
  }

  pause(): void {
    this.audio?.pause();
  }

  resume(): void {
    this.audio?.play().catch(() => {});
  }

  stop(): void {
    if (this.audio) {
      this.audio.onended = null;
      this.audio.onerror = null;
      this.audio.pause();
      this.audio.src = "";
      this.audio = null;
    }
  }
}
