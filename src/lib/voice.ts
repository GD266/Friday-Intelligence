import {
  getVoices as getNativeVoices,
  onSpeechEvent,
  previewVoice as previewNativeVoice,
  speak as speakNative,
  stop as stopNative,
} from 'tauri-plugin-tts-api';
import type { EdgeVoice, ElevenLabsVoice, FridaySettings, VoiceOption } from '@/types';

export type { EdgeVoice };
import { getErrorMessage, invokeCommand, isTauriRuntime } from './runtime';
import { pickPreferredVoice } from './voice-profile';

interface ElevenLabsAudioResult {
  audioBase64: string;
  mimeType: string;
  voiceId: string;
}

let activeAudio: HTMLAudioElement | null = null;
let activeAudioUrl: string | null = null;

function stopActiveAudio(): void {
  if (activeAudio) {
    activeAudio.onended = null;
    activeAudio.onerror = null;
    activeAudio.pause();
    activeAudio.src = '';
    activeAudio = null;
  }
  if (activeAudioUrl) {
    URL.revokeObjectURL(activeAudioUrl);
    activeAudioUrl = null;
  }
}

function decodeBase64(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return buffer;
}

/**
 * Plays studio-quality ElevenLabs speech through the webview audio pipeline.
 * The key and the audio request stay in the Rust backend.
 */
async function speakWithElevenLabs(
  text: string,
  settings: FridaySettings,
  onEnd?: () => void
): Promise<SpeakResult> {
  if (!settings.elevenLabsApiKey.trim()) {
    return { ok: false, error: 'Add an ElevenLabs API key in Settings to use the studio voice.' };
  }
  if (!isTauriRuntime()) {
    return { ok: false, error: 'The ElevenLabs studio voice is available in the desktop app.' };
  }

  try {
    const result = await invokeCommand<ElevenLabsAudioResult>('elevenlabs_speak', {
      request: {
        text: text.slice(0, 5_000),
        apiKey: settings.elevenLabsApiKey,
        voiceId: settings.elevenLabsVoiceId,
        modelId: settings.elevenLabsModelId,
        stability: settings.elevenLabsStability,
        similarity: settings.elevenLabsSimilarity,
      },
    });

    stopActiveAudio();
    const blob = new Blob([decodeBase64(result.audioBase64)], {
      type: result.mimeType || 'audio/mpeg',
    });
    const url = URL.createObjectURL(blob);
    activeAudioUrl = url;

    const audio = new Audio(url);
    activeAudio = audio;

    const finish = () => {
      stopActiveAudio();
      onEnd?.();
    };
    audio.onended = finish;
    audio.onerror = finish;

    await audio.play();
    return { ok: true, provider: 'elevenlabs' };
  } catch (error) {
    stopActiveAudio();
    return { ok: false, error: getErrorMessage(error) };
  }
}

export async function listElevenLabsVoices(settings: FridaySettings): Promise<ElevenLabsVoice[]> {
  if (!isTauriRuntime() || !settings.elevenLabsApiKey.trim()) return [];

  try {
    return await invokeCommand<ElevenLabsVoice[]>('elevenlabs_voices', {
      request: { apiKey: settings.elevenLabsApiKey },
    });
  } catch {
    return [];
  }
}

/**
 * Lists Edge neural voices (Microsoft read-aloud).
 * No API key required — always available in the Tauri desktop app.
 */
export async function listEdgeVoices(): Promise<EdgeVoice[]> {
  if (!isTauriRuntime()) return [];

  try {
    return await invokeCommand<EdgeVoice[]>('edge_voices');
  } catch {
    return [];
  }
}

/**
 * Speaks text using Edge neural TTS (Microsoft read-aloud voices).
 * Free, no key, high quality. Returns base64 MP3.
 */
export async function speakWithEdge(
  text: string,
  settings: FridaySettings,
  onEnd?: () => void
): Promise<SpeakResult> {
  if (!isTauriRuntime()) {
    return { ok: false, error: 'Edge neural voice is available in the desktop app.' };
  }

  try {
    const result = await invokeCommand<{
      audio_base64: string;
      mime_type: string;
      voice: string;
    }>('edge_speak', {
      request: {
        text: text.slice(0, 5_000),
        voice: settings.ttsVoice,
        rate: Math.round((settings.voiceRate - 1) * 50),
        pitch: Math.round((settings.voicePitch - 1) * 50),
        volume: 0,
      },
    });

    stopActiveAudio();
    const blob = new Blob([decodeBase64(result.audio_base64)], {
      type: result.mime_type || 'audio/mpeg',
    });
    const url = URL.createObjectURL(blob);
    activeAudioUrl = url;

    const audio = new Audio(url);
    activeAudio = audio;

    const finish = () => {
      stopActiveAudio();
      onEnd?.();
    };
    audio.onended = finish;
    audio.onerror = finish;

    await audio.play();
    return { ok: true, provider: 'edge' };
  } catch (error) {
    stopActiveAudio();
    return { ok: false, error: getErrorMessage(error) };
  }
}

/**
 * Previews an Edge neural voice.
 */
export async function previewEdgeVoice(voiceId: string): Promise<SpeakResult> {
  if (!voiceId) return { ok: false, error: 'Select a voice first.' };

  if (!isTauriRuntime()) {
    return { ok: false, error: 'Voice preview is available in the desktop app.' };
  }

  try {
    const result = await invokeCommand<{
      audio_base64: string;
      mime_type: string;
      voice: string;
    }>('edge_preview', {
      request: { voice: voiceId },
    });

    const blob = new Blob([decodeBase64(result.audio_base64)], {
      type: result.mime_type || 'audio/mpeg',
    });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.onerror = () => URL.revokeObjectURL(url);
    await audio.play();
    return { ok: true };
  } catch (error) {
    return { ok: false, error: getErrorMessage(error) };
  }
}

/**
 * Transcribes audio using the local Whisper engine (on-device, no key).
 * The audio must be a base64-encoded 16 kHz mono 16-bit PCM WAV.
 */
export async function transcribeLocal(
  audioBase64: string,
  settings: FridaySettings,
  prompt?: string
): Promise<{ text: string; empty: boolean; provider: string; model: string; elapsedMs: number }> {
  if (!isTauriRuntime()) {
    throw new Error('Local transcription is only available in the desktop app.');
  }

  const result = await invokeCommand<{
    text: string;
    empty: boolean;
    provider: string;
    model: string;
    elapsed_ms: number;
  }>('stt_transcribe_local', {
    request: {
      audio_base64: audioBase64,
      language: settings.voiceLocale,
      prompt: prompt ?? 'FRIDAY Intelligence. Open Notepad. Open Calculator. Open File Explorer. VS Code. GitHub. OpenCode. Tauri. Open Chrome. Take a screenshot.',
      model: settings.sttModel,
    },
  });

  return {
    text: result.text,
    empty: result.empty,
    provider: result.provider,
    model: result.model,
    elapsedMs: result.elapsed_ms,
  };
}

/**
 * Transcribes audio using Groq's hosted Whisper (requires API key).
 */
export async function transcribeGroq(
  audioBase64: string,
  settings: FridaySettings,
  prompt?: string
): Promise<{ text: string; empty: boolean; provider: string; model: string; elapsedMs: number }> {
  if (!isTauriRuntime()) {
    throw new Error('Groq transcription is only available in the desktop app.');
  }

  if (!settings.groqApiKey?.trim()) {
    throw new Error('Add a Groq API key in Settings to use Groq Whisper.');
  }

  const result = await invokeCommand<{
    text: string;
    empty: boolean;
    provider: string;
    model: string;
    elapsed_ms: number;
  }>('stt_transcribe_groq', {
    request: {
      audio_base64: audioBase64,
      api_key: settings.groqApiKey,
      language: settings.voiceLocale,
      prompt: prompt ?? 'FRIDAY Intelligence. Open Notepad. Open Calculator. Open File Explorer. VS Code. GitHub. OpenCode. Tauri. Open Chrome. Take a screenshot.',
      model: 'whisper-large-v3-turbo',
    },
  });

  return {
    text: result.text,
    empty: result.empty,
    provider: result.provider,
    model: result.model,
    elapsedMs: result.elapsed_ms,
  };
}

/**
 * Gets the install status of the local Whisper engine.
 */
export async function sttLocalStatus(model?: string): Promise<{
  engineReady: boolean;
  modelReady: boolean;
  ready: boolean;
  model: string;
  modelPath: string;
  enginePath: string;
  message: string;
}> {
  if (!isTauriRuntime()) {
    return {
      engineReady: false,
      modelReady: false,
      ready: false,
      model: model ?? 'small.en',
      modelPath: '',
      enginePath: '',
      message: 'Local Whisper is only available in the desktop app.',
    };
  }

  return await invokeCommand('stt_local_status', {
    model: model ?? 'small.en',
  });
}

/**
 * Installs or updates the local Whisper engine and model.
 */
export async function sttInstallLocal(model?: string): Promise<{
  engineReady: boolean;
  modelReady: boolean;
  ready: boolean;
  model: string;
  modelPath: string;
  enginePath: string;
  message: string;
}> {
  if (!isTauriRuntime()) {
    throw new Error('Local Whisper is only available in the desktop app.');
  }

  return await invokeCommand('stt_install_local', {
    model: model ?? 'small.en',
  });
}

/**
 * Lists available Whisper models.
 */
export async function sttModels(): Promise<Array<{
  id: string;
  label: string;
  file: string;
  approxMb: number;
  description: string;
}>> {
  if (!isTauriRuntime()) return [];

  return await invokeCommand('stt_models');
}

export function clampRate(value: number): number {
  if (!Number.isFinite(value)) return 0.94;
  return Math.min(4, Math.max(0.1, value));
}

export function clampPitch(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(2, Math.max(0.5, value));
}

export function canUseSpeech(): boolean {
  if (typeof window === 'undefined') return false;
  return isTauriRuntime() || 'speechSynthesis' in window;
}

export function canUseDictation(): boolean {
  if (typeof window === 'undefined') return false;
  if (isTauriRuntime()) return true;
  const scope = window as unknown as {
    SpeechRecognition?: unknown;
    webkitSpeechRecognition?: unknown;
  };
  return Boolean(scope.SpeechRecognition ?? scope.webkitSpeechRecognition);
}

/** Removes formatting that should not be read aloud. */
export function toSpeechText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' code block omitted. ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/g, 'link')
    .replace(/\s+/g, ' ')
    .trim();
}

export async function listVoices(): Promise<VoiceOption[]> {
  if (isTauriRuntime()) {
    try {
      const voices = await getNativeVoices();
      return voices.map((voice) => ({
        id: voice.id,
        name: voice.name,
        language: voice.language,
      }));
    } catch {
      return [];
    }
  }

  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return [];

  return window.speechSynthesis.getVoices().map((voice) => ({
    id: voice.voiceURI,
    name: voice.name,
    language: voice.lang,
  }));
}

let autoVoiceCache: VoiceOption[] | null = null;

async function resolveAutoFemaleVoice(): Promise<VoiceOption | null> {
  if (!autoVoiceCache || autoVoiceCache.length === 0) {
    const voices = await listVoices();
    if (voices.length > 0) autoVoiceCache = voices;
  }

  return pickPreferredVoice(autoVoiceCache ?? []);
}

export interface SpeechLifecycle {
  type: 'start' | 'finish' | 'cancel' | 'error';
  error?: string;
}

/** Subscribes to native TTS lifecycle events. Returns a cleanup function. */
export async function subscribeSpeechLifecycle(
  handler: (event: SpeechLifecycle) => void
): Promise<() => void> {
  if (!isTauriRuntime()) return () => undefined;

  const subscriptions = await Promise.all(
    ([
      ['speech:start', 'start'],
      ['speech:finish', 'finish'],
      ['speech:cancel', 'cancel'],
      ['speech:error', 'error'],
    ] as const).map(async ([eventName, type]) =>
      onSpeechEvent(eventName, (event) => handler({ type, error: event.error }))
    )
  );

  return () => {
    for (const unsubscribe of subscriptions) unsubscribe();
  };
}

export interface SpeakResult {
  ok: boolean;
  error?: string;
  provider?: 'elevenlabs' | 'native' | 'browser' | 'edge';
}

/**
 * Speaks text using the configured TTS provider:
 * 1. Edge neural voices (free, no key, high quality)
 * 2. ElevenLabs (premium, requires key)
 * 3. Native Windows TTS (offline)
 * 4. Browser Web Speech API (preview only)
 */
export async function speakText(
  text: string,
  settings: FridaySettings,
  onBrowserEnd?: () => void
): Promise<SpeakResult> {
  const spoken = toSpeechText(text);
  if (!spoken) return { ok: false, error: 'There is nothing to speak.' };
  if (!settings.voiceEnabled) return { ok: false, error: 'Voice output is disabled.' };

  // 1. Edge neural TTS (new default — free, human-like, no key)
  if (settings.ttsProvider === 'edge' && isTauriRuntime()) {
    const edge = await speakWithEdge(spoken, settings, onBrowserEnd);
    if (edge.ok) return edge;
  }

  // 2. ElevenLabs (explicitly selected)
  if (settings.ttsProvider === 'elevenlabs' || settings.voiceProvider === 'elevenlabs') {
    const studio = await speakWithElevenLabs(spoken, settings, onBrowserEnd);
    if (studio.ok) return studio;
  }

  // 3. Native Windows TTS
  if (settings.ttsProvider === 'native' || isTauriRuntime()) {
    try {
      const autoVoice = settings.voiceId ? null : await resolveAutoFemaleVoice();
      const voiceId = settings.voiceId ?? autoVoice?.id ?? null;

      await speakNative({
        text: spoken.slice(0, 10_000),
        rate: clampRate(settings.voiceRate),
        pitch: clampPitch(settings.voicePitch),
        volume: 1,
        voiceId,
        language: voiceId ? null : 'en-GB',
      });
      return { ok: true, provider: 'native' };
    } catch {
      // Fall through to browser on error.
    }
  }

  // 4. Browser Web Speech API (preview only)
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      const synth = window.speechSynthesis;
      synth.cancel();

      const browserVoices = synth.getVoices();
      const voiceOptions = browserVoices.map((voice) => ({
        id: voice.voiceURI,
        name: voice.name,
        language: voice.lang,
      }));
      const preferredVoiceId = settings.voiceId ?? pickPreferredVoice(voiceOptions)?.id;
      const selected = preferredVoiceId
        ? browserVoices.find((voice) => voice.voiceURI === preferredVoiceId)
        : undefined;

      const utterance = new SpeechSynthesisUtterance(spoken);
      utterance.lang = selected?.lang ?? 'en-GB';
      utterance.rate = Math.min(2, Math.max(0.5, settings.voiceRate));
      utterance.pitch = Math.min(2, Math.max(0.5, settings.voicePitch));
      utterance.volume = 1;

      if (selected) {
        utterance.voice = selected;
      }

      utterance.onend = () => onBrowserEnd?.();
      utterance.onerror = () => onBrowserEnd?.();
      synth.speak(utterance);
      return { ok: true, provider: 'browser' };
    } catch (error) {
      return { ok: false, error: getErrorMessage(error) };
    }
  }

  return { ok: false, error: 'No speech engine available.' };
}

export async function stopSpeech(): Promise<void> {
  stopActiveAudio();

  if (isTauriRuntime()) {
    try {
      await stopNative();
    } catch {
      // Stopping is best effort.
    }
    return;
  }

  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

export async function previewVoiceById(voiceId: string | null): Promise<SpeakResult> {
  if (!voiceId) return { ok: false, error: 'Select a voice first.' };

  if (isTauriRuntime()) {
    try {
      await previewNativeVoice({ voiceId });
      return { ok: true };
    } catch (error) {
      return { ok: false, error: getErrorMessage(error) };
    }
  }

  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return { ok: false, error: 'Speech preview is not available here.' };
  }

  const synth = window.speechSynthesis;
  const voice = synth.getVoices().find((item) => item.voiceURI === voiceId);
  if (!voice) return { ok: false, error: 'That voice is not installed.' };

  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(
    'Good evening. All systems are online and standing by.'
  );
  utterance.voice = voice;
  utterance.rate = 0.94;
  utterance.pitch = 1;
  synth.speak(utterance);
  return { ok: true };
}

export async function startNativeDictation(): Promise<void> {
  await invokeCommand('start_dictation');
}

export async function stopNativeDictation(): Promise<void> {
  try {
    await invokeCommand('stop_dictation');
  } catch {
    // The session may already be closed.
  }
}

export async function cancelNativeDictation(): Promise<void> {
  try {
    await invokeCommand('cancel_dictation');
  } catch {
    // The session may already be closed.
  }
}
