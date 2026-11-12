/**
 * Push-to-talk microphone capture.
 *
 * Uses getUserMedia + a ScriptProcessorNode so we receive raw float samples and
 * can guarantee a 16 kHz mono WAV, which every speech provider accepts. We do
 * not use MediaRecorder because WebM/Opus output needs an external decoder.
 */

import {
  bufferToBase64,
  downmixToMono,
  encodeWav,
  isSilent,
  peakAmplitude,
  resampleMono,
  TARGET_SAMPLE_RATE,
} from './wav';

export interface RecordingResult {
  /** 16 kHz mono 16-bit PCM WAV, base64 encoded. */
  audioBase64: string;
  /** Recording length in seconds. */
  durationSeconds: number;
  /** True when the microphone captured only room noise. */
  silent: boolean;
  peak: number;
}

export interface RecorderOptions {
  /** Receives a 0..1 input level roughly every 100 ms. */
  onLevel?: (level: number) => void;
  /** Auto-stop guard so a forgotten push-to-talk cannot record forever. */
  maxDurationMs?: number;
  /** Called when the guard trips. */
  onAutoStop?: () => void;
}

const SCRIPT_BUFFER_SIZE = 4096;
const DEFAULT_MAX_DURATION_MS = 60_000;

export class MicrophoneRecorder {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private chunks: Float32Array[] = [];
  private sampleRate = TARGET_SAMPLE_RATE;
  private startedAt = 0;
  private autoStopTimer: ReturnType<typeof setTimeout> | null = null;
  private options: RecorderOptions;

  constructor(options: RecorderOptions = {}) {
    this.options = options;
  }

  get isRecording(): boolean {
    return this.stream !== null;
  }

  async start(): Promise<void> {
    if (this.stream) return;

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        'This environment cannot access a microphone. Use the FRIDAY desktop app.'
      );
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
    } catch (error) {
      throw new Error(describeMicrophoneError(error));
    }

    const AudioContextCtor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;

    if (!AudioContextCtor) {
      releaseStream(stream);
      throw new Error('Audio capture is not supported in this environment.');
    }

    let context: AudioContext;
    try {
      context = new AudioContextCtor();
      if (context.state === 'suspended') {
        await context.resume();
      }
    } catch {
      releaseStream(stream);
      throw new Error('Could not start the audio engine.');
    }

    this.stream = stream;
    this.context = context;
    this.sampleRate = context.sampleRate;
    this.chunks = [];
    this.startedAt = performance.now();

    try {
      this.source = context.createMediaStreamSource(stream);
      this.processor = context.createScriptProcessor(SCRIPT_BUFFER_SIZE, 1, 1);

      this.processor.onaudioprocess = (event) => {
        const channel = event.inputBuffer.getChannelData(0);
        // Copy: the buffer is reused by the audio engine after this callback.
        this.chunks.push(new Float32Array(channel));
        this.options.onLevel?.(Math.min(1, peakAmplitude(channel) * 3));
      };

      this.source.connect(this.processor);
      // ScriptProcessor only runs while connected to a destination. Route it
      // through a muted gain node so nothing is played back through the speakers.
      const mute = context.createGain();
      mute.gain.value = 0;
      this.processor.connect(mute);
      mute.connect(context.destination);
    } catch (error) {
      this.dispose();
      throw new Error(
        error instanceof Error ? error.message : 'Could not open the microphone stream.'
      );
    }

    const maxDuration = this.options.maxDurationMs ?? DEFAULT_MAX_DURATION_MS;
    this.autoStopTimer = setTimeout(() => {
      this.options.onAutoStop?.();
    }, maxDuration);
  }

  /** Stops capture and returns the encoded recording. */
  async stop(): Promise<RecordingResult> {
    if (!this.stream) {
      throw new Error('The microphone is not recording.');
    }

    const durationSeconds = Math.max(0, (performance.now() - this.startedAt) / 1000);
    const chunks = this.chunks;
    const sampleRate = this.sampleRate;

    this.dispose();

    const mono = downmixToMono(chunks);
    const resampled = resampleMono(mono, sampleRate, TARGET_SAMPLE_RATE);
    const silent = isSilent(resampled);
    const wav = encodeWav(resampled, TARGET_SAMPLE_RATE);

    return {
      audioBase64: bufferToBase64(wav),
      durationSeconds,
      silent,
      peak: peakAmplitude(resampled),
    };
  }

  /** Stops capture and throws the audio away. */
  cancel(): void {
    this.dispose();
  }

  private dispose(): void {
    if (this.autoStopTimer) {
      clearTimeout(this.autoStopTimer);
      this.autoStopTimer = null;
    }

    if (this.processor) {
      this.processor.onaudioprocess = null;
      try {
        this.processor.disconnect();
      } catch {
        // Already disconnected.
      }
      this.processor = null;
    }

    if (this.source) {
      try {
        this.source.disconnect();
      } catch {
        // Already disconnected.
      }
      this.source = null;
    }

    const context = this.context;
    this.context = null;
    if (context && context.state !== 'closed') {
      void context.close().catch(() => undefined);
    }

    if (this.stream) {
      releaseStream(this.stream);
      this.stream = null;
    }

    this.chunks = [];
    this.options.onLevel?.(0);
  }
}

function releaseStream(stream: MediaStream): void {
  for (const track of stream.getTracks()) {
    track.stop();
  }
}

/** Maps a DOMException from getUserMedia to an actionable message. */
export function describeMicrophoneError(error: unknown): string {
  const name =
    error && typeof error === 'object' && 'name' in error
      ? String((error as { name?: unknown }).name)
      : '';

  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Microphone access was denied. Allow the microphone for FRIDAY in Windows Settings, Privacy & security, Microphone.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No microphone was detected. Connect a microphone and try again.';
    case 'NotReadableError':
      return 'The microphone is in use by another application. Close it or pick another device.';
    case 'AbortError':
      return 'The microphone stopped before recording could start.';
    default:
      return error instanceof Error && error.message
        ? `Microphone error: ${error.message}`
        : 'The microphone could not be started.';
  }
}
