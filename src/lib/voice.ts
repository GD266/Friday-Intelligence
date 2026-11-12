import {
  getVoices as getNativeVoices,
  onSpeechEvent,
  previewVoice as previewNativeVoice,
  speak as speakNative,
  stop as stopNative,
} from 'tauri-plugin-tts-api';
import type { FridaySettings, VoiceOption } from '@/types';
import { getErrorMessage, invokeCommand, isTauriRuntime } from './runtime';
import { pickPreferredVoice } from './voice-profile';

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
}

/**
 * Speaks text using native Windows TTS inside Tauri, with the Web Speech API
 * as a browser-preview fallback. Resolves when the engine accepts the utterance.
 */
export async function speakText(
  text: string,
  settings: FridaySettings,
  onBrowserEnd?: () => void
): Promise<SpeakResult> {
  const spoken = toSpeechText(text);
  if (!spoken) return { ok: false, error: 'There is nothing to speak.' };
  if (!settings.voiceEnabled) return { ok: false, error: 'Voice output is disabled.' };

  if (isTauriRuntime()) {
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
      return { ok: true };
    } catch (error) {
      return { ok: false, error: getErrorMessage(error) };
    }
  }

  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return { ok: false, error: 'Speech output is not available in this environment.' };
  }

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
    return { ok: true };
  } catch (error) {
    return { ok: false, error: getErrorMessage(error) };
  }
}

export async function stopSpeech(): Promise<void> {
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
