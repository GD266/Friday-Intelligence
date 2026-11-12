import { useCallback, useEffect, useRef, useState } from 'react';
import { useAssistantStore } from '@/stores';
import {
  getErrorMessage,
  isTauriRuntime,
} from '@/lib/runtime';
import {
  canUseSpeech,
  speakText,
  stopSpeech,
  subscribeSpeechLifecycle,
  transcribeLocal,
  transcribeGroq,
  sttLocalStatus,
  type EdgeVoice,
} from '@/lib/voice';
import { normalizeTranscript } from '@/lib/voice-norm';
import { MicrophoneRecorder, RecordingResult } from '@/lib/audio/recorder';

// Track recent transcripts for duplicate detection (5-second window, max 5 entries)
const RECENT_TRANSCRIPT_WINDOW_MS = 5000;
const MAX_RECENT_TRANSCRIPTS = 5;

interface RecentTranscript {
  text: string;
  timestamp: number;
}

let recentTranscripts: RecentTranscript[] = [];

function isDuplicateTranscript(text: string): boolean {
  const now = Date.now();
  recentTranscripts = recentTranscripts.filter(
    (t) => now - t.timestamp < RECENT_TRANSCRIPT_WINDOW_MS
  );
  return recentTranscripts.some((t) => t.text.toLowerCase() === text.toLowerCase());
}

function addRecentTranscript(text: string): void {
  recentTranscripts.push({ text, timestamp: Date.now() });
  if (recentTranscripts.length > MAX_RECENT_TRANSCRIPTS) {
    recentTranscripts = recentTranscripts.slice(-MAX_RECENT_TRANSCRIPTS);
  }
}

export interface UseFridayVoiceOptions {
  onTranscript?: (text: string) => void;
}

/**
 * Owns push-to-talk dictation and speech output. All observable state is mirrored
 * into the assistant store so the core orb and HUD animate from a single source.
 */
export function useFridayVoice(options: UseFridayVoiceOptions = {}) {
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [availableVoices, setAvailableVoices] = useState<EdgeVoice[]>([]);
  const [sttStatus, setSttStatus] = useState<{
    engineReady: boolean;
    modelReady: boolean;
    ready: boolean;
    message: string;
  } | null>(null);

  const onTranscriptRef = useRef(options.onTranscript);
  const recorderRef = useRef<MicrophoneRecorder | null>(null);

  onTranscriptRef.current = options.onTranscript;

  // Native TTS lifecycle (speech:start / speech:finish / speech:error).
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;

    void subscribeSpeechLifecycle((event) => {
      if (disposed) return;
      const store = useAssistantStore.getState();

      if (event.type === 'start') {
        store.setSpeaking(true);
        store.setStatusText('Speaking');
        return;
      }

      store.setSpeaking(false);
      store.setStatusText('Online');
      if (useAssistantStore.getState().mood === 'speaking') {
        store.setMood('idle');
      }

      if (event.type === 'error') {
        setVoiceError(event.error ?? 'Speech playback failed.');
      }
    }).then((unsubscribe) => {
      if (disposed) {
        unsubscribe?.();
      } else {
        cleanup = unsubscribe;
      }
    });

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, []);

  // Load Edge voices and STT status on mount (Tauri only).
  useEffect(() => {
    let disposed = false;

    async function load(): Promise<void> {
      if (!isTauriRuntime()) return;

      try {
        const { listEdgeVoices } = await import('@/lib/voice');
        const voices = await listEdgeVoices();
        if (!disposed) setAvailableVoices(voices);
      } catch {
        // Non-fatal.
      }

      try {
        const status = await sttLocalStatus();
        if (!disposed) setSttStatus(status);
      } catch {
        // Non-fatal.
      }
    }

    void load();

    return () => {
      disposed = true;
    };
  }, []);

  // Cleanup on unmount.
  useEffect(
    () => () => {
      recorderRef.current?.cancel();
      recorderRef.current = null;
      if (isTauriRuntime()) {
        void stopSpeech();
      }
    },
    []
  );

  const stopSpeaking = useCallback(async () => {
    await stopSpeech();
    const store = useAssistantStore.getState();
    store.setSpeaking(false);
    store.setStatusText('Online');
    if (useAssistantStore.getState().mood === 'speaking') {
      store.setMood('idle');
    }
  }, []);

  const speak = useCallback(async (text: string) => {
    const store = useAssistantStore.getState();
    if (!store.settings.voiceEnabled || !text.trim()) return false;

    store.setMood('speaking');
    store.setSpeaking(true);
    store.setStatusText('Speaking');

    const result = await speakText(text, store.settings, () => {
      const current = useAssistantStore.getState();
      current.setSpeaking(false);
      current.setStatusText('Online');
      if (current.mood === 'speaking') current.setMood('idle');
    });

    if (!result.ok) {
      const current = useAssistantStore.getState();
      current.setSpeaking(false);
      current.setStatusText('Online');
      if (current.mood === 'speaking') current.setMood('idle');
      if (result.error && result.error !== 'Voice output is disabled.') {
        setVoiceError(result.error);
      }
      return false;
    }

    return true;
  }, []);

  const stopListening = useCallback(async () => {
    const store = useAssistantStore.getState();
    if (!store.isListening) return;

    // Stop recording and get audio.
    let recording: RecordingResult | null = null;
    if (recorderRef.current) {
      try {
        recording = await recorderRef.current.stop();
      } catch (error) {
        store.setListening(false);
        store.setAudioLevel(0);
        store.setStatusText('Online');
        if (store.mood === 'listening') store.setMood('idle');
        setVoiceError(error instanceof Error ? error.message : 'Recording failed.');
        return;
      }
      recorderRef.current = null;
    } else {
      store.setListening(false);
      store.setAudioLevel(0);
      store.setStatusText('Online');
      if (store.mood === 'listening') store.setMood('idle');
      return;
    }

    store.setAudioLevel(0);
    store.setStatusText('Processing...');

    if (!recording || recording.silent) {
      store.setListening(false);
      store.setStatusText('Online');
      if (store.mood === 'listening') store.setMood('idle');
      setVoiceError('No speech detected. Hold the button and speak clearly.');
      return;
    }

    setIsTranscribing(true);

    try {
      const settings = store.settings;
      let result: { text: string; empty: boolean; provider: string; model: string; elapsedMs: number };

      if (settings.sttProvider === 'groq') {
        result = await transcribeGroq(recording.audioBase64, settings);
      } else {
        // Default to local Whisper.
        result = await transcribeLocal(recording.audioBase64, settings);
      }

      if (result.empty || !result.text.trim()) {
        store.setListening(false);
        store.setStatusText('Online');
        if (store.mood === 'listening') store.setMood('idle');
        setVoiceError('Could not understand. Try again in a quieter room.');
        return;
      }

      const rawText = result.text.trim();

      // Check for duplicate submissions
      if (isDuplicateTranscript(rawText)) {
        store.setTranscript('');
        store.setListening(false);
        store.setStatusText('Duplicate transcript ignored');
        setTimeout(() => store.setStatusText('Online'), 2000);
        return;
      }

      // Apply speech normalization
      const { original, normalized, corrected } = normalizeTranscript(rawText);
      addRecentTranscript(rawText);

      store.setTranscript(normalized);
      store.setListening(false);
      store.setStatusText('Online');
      if (store.mood === 'listening') store.setMood('idle');

      // Log normalization in development
      if (corrected && import.meta.env.DEV) {
        console.debug('[VoiceNorm]', {
          original,
          normalized,
          reason: 'Common recognition error correction',
          locale: settings.voiceLocale,
          provider: result.provider,
        });
      }

      // Send the normalized text (not raw) to the handler
      onTranscriptRef.current?.(normalized);
    } catch (error) {
      store.setListening(false);
      store.setStatusText('Online');
      if (store.mood === 'listening') store.setMood('idle');
      setVoiceError(getErrorMessage(error));
    } finally {
      setIsTranscribing(false);
    }
  }, []);

  const startListening = useCallback(async () => {
    const store = useAssistantStore.getState();
    if (store.isListening) return;

    setVoiceError(null);
    store.setTranscript('');
    setAudioLevel(0);

    if (store.isSpeaking) {
      await stopSpeaking();
    }

    // Create recorder if needed.
    if (!recorderRef.current) {
      recorderRef.current = new MicrophoneRecorder({
        onLevel: (level) => {
          const current = useAssistantStore.getState();
          current.setAudioLevel(level);
          setAudioLevel(level);
        },
        onAutoStop: () => {
          void stopListening();
        },
      });
    }

    try {
      await recorderRef.current.start();
      store.setListening(true);
      store.setMood('listening');
      store.setStatusText('Listening');
    } catch (error) {
      store.setListening(false);
      store.setMood('idle');
      store.setStatusText('Online');
      setVoiceError(error instanceof Error ? error.message : 'Could not start recording.');
      recorderRef.current = null;
    }
  }, [stopSpeaking, stopListening]);

  const cancelListening = useCallback(async () => {
    const store = useAssistantStore.getState();

    if (recorderRef.current) {
      recorderRef.current.cancel();
      recorderRef.current = null;
    }

    store.setListening(false);
    store.setAudioLevel(0);
    store.setTranscript('');
    store.setStatusText('Online');
    if (store.mood === 'listening') store.setMood('idle');
    setAudioLevel(0);
    setVoiceError(null);
  }, []);

  const toggleListening = useCallback(async () => {
    if (useAssistantStore.getState().isListening) {
      await stopListening();
    } else {
      await startListening();
    }
  }, [startListening, stopListening]);

  // Refresh STT status (called after install).
  const refreshSttStatus = useCallback(async () => {
    try {
      const status = await sttLocalStatus();
      setSttStatus(status);
    } catch {
      // Non-fatal.
    }
  }, []);

  return {
    speak,
    stopSpeaking,
    startListening,
    stopListening,
    cancelListening,
    toggleListening,
    voiceError,
    clearVoiceError: () => setVoiceError(null),
    isListening: useAssistantStore((state) => state.isListening),
    isSpeaking: useAssistantStore((state) => state.isSpeaking),
    audioLevel,
    transcript: useAssistantStore((state) => state.transcript),
    speechSupported: canUseSpeech(),
    dictationSupported: true, // Always available in Tauri with our recorder.
    isTranscribing,
    availableVoices,
    sttStatus,
    refreshSttStatus,
  };
}