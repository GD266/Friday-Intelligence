import { useCallback, useEffect, useRef, useState } from 'react';
import { useAssistantStore } from '@/stores';
import {
  getErrorMessage,
  isTauriRuntime,
  listenEvent,
} from '@/lib/runtime';
import {
  canUseDictation,
  canUseSpeech,
  cancelNativeDictation,
  speakText,
  startNativeDictation,
  stopNativeDictation,
  stopSpeech,
  subscribeSpeechLifecycle,
} from '@/lib/voice';
import type { SpeechEventPayload } from '@/types';

interface BrowserRecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}

interface BrowserRecognitionEvent {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: BrowserRecognitionResult;
  };
}

interface BrowserRecognitionErrorEvent {
  error: string;
}

interface BrowserRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onresult: ((event: BrowserRecognitionEvent) => void) | null;
  onerror: ((event: BrowserRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type BrowserRecognitionConstructor = new () => BrowserRecognition;

function getBrowserRecognition(): BrowserRecognitionConstructor | null {
  if (typeof window === 'undefined') return null;
  const scope = window as unknown as {
    SpeechRecognition?: BrowserRecognitionConstructor;
    webkitSpeechRecognition?: BrowserRecognitionConstructor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
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
  const browserRecognitionRef = useRef<BrowserRecognition | null>(null);
  const onTranscriptRef = useRef(options.onTranscript);

  onTranscriptRef.current = options.onTranscript;

  const isListening = useAssistantStore((state) => state.isListening);
  const isSpeaking = useAssistantStore((state) => state.isSpeaking);
  const audioLevel = useAssistantStore((state) => state.audioLevel);
  const transcript = useAssistantStore((state) => state.transcript);

  // Native dictation event stream (Windows SAPI through Rust).
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;

    void listenEvent<SpeechEventPayload>('friday://speech', (payload) => {
      if (disposed) return;
      const store = useAssistantStore.getState();

      switch (payload.kind) {
        case 'started': {
          store.setListening(true);
          store.setMood('listening');
          store.setStatusText('Listening');
          break;
        }
        case 'audioLevel': {
          store.setAudioLevel(Math.min(1, Math.max(0, payload.level ?? 0)));
          break;
        }
        case 'transcript': {
          store.setTranscript(payload.text ?? '');
          if (payload.isFinal && payload.text?.trim()) {
            const finalText = payload.text.trim();
            store.setListening(false);
            store.setAudioLevel(0);
            store.setMood('idle');
            store.setStatusText('Online');
            onTranscriptRef.current?.(finalText);
            void stopNativeDictation();
          }
          break;
        }
        case 'stopped': {
          store.setListening(false);
          store.setAudioLevel(0);
          store.setStatusText('Online');
          if (useAssistantStore.getState().mood === 'listening') {
            store.setMood('idle');
          }
          break;
        }
        case 'error': {
          store.setListening(false);
          store.setAudioLevel(0);
          store.setMood('idle');
          store.setStatusText('Online');
          setVoiceError(payload.message ?? 'Speech recognition stopped unexpectedly.');
          break;
        }
        default:
          break;
      }
    }).then((unlisten) => {
      if (disposed) {
        unlisten?.();
      } else {
        cleanup = unlisten ?? undefined;
      }
    });

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, []);

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
        unsubscribe();
      } else {
        cleanup = unsubscribe;
      }
    });

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, []);

  // Release the microphone if the view unmounts mid-dictation.
  useEffect(
    () => () => {
      browserRecognitionRef.current?.abort();
      browserRecognitionRef.current = null;
      if (isTauriRuntime()) void cancelNativeDictation();
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

  const startListening = useCallback(async () => {
    const store = useAssistantStore.getState();
    if (store.isListening) return;

    setVoiceError(null);
    store.setTranscript('');
    store.setAudioLevel(0);

    if (store.isSpeaking) {
      await stopSpeaking();
    }

    if (isTauriRuntime()) {
      try {
        await startNativeDictation();
        store.setListening(true);
        store.setMood('listening');
        store.setStatusText('Listening');
      } catch (error) {
        store.setListening(false);
        store.setMood('idle');
        store.setStatusText('Online');
        setVoiceError(getErrorMessage(error));
      }
      return;
    }

    const Recognition = getBrowserRecognition();
    if (!Recognition) {
      setVoiceError('Push-to-talk is available in the FRIDAY desktop app.');
      return;
    }

    try {
      const recognition = new Recognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-GB';

      recognition.onstart = () => {
        const current = useAssistantStore.getState();
        current.setListening(true);
        current.setMood('listening');
        current.setStatusText('Listening');
      };

      recognition.onresult = (event) => {
        let interim = '';
        let finalText = '';

        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          if (result.isFinal) {
            finalText += result[0].transcript;
          } else {
            interim += result[0].transcript;
          }
        }

        const current = useAssistantStore.getState();
        if (interim) current.setTranscript(interim);

        if (finalText.trim()) {
          current.setTranscript(finalText);
          current.setListening(false);
          current.setAudioLevel(0);
          current.setStatusText('Online');
          if (current.mood === 'listening') current.setMood('idle');
          onTranscriptRef.current?.(finalText.trim());
        }
      };

      recognition.onerror = (event) => {
        const current = useAssistantStore.getState();
        current.setListening(false);
        current.setAudioLevel(0);
        current.setStatusText('Online');
        if (current.mood === 'listening') current.setMood('idle');
        setVoiceError(
          event.error === 'not-allowed'
            ? 'Microphone access was denied. Allow microphone access and try again.'
            : `Speech recognition error: ${event.error}.`
        );
      };

      recognition.onend = () => {
        const current = useAssistantStore.getState();
        current.setListening(false);
        current.setAudioLevel(0);
        current.setStatusText('Online');
        if (current.mood === 'listening') current.setMood('idle');
        browserRecognitionRef.current = null;
      };

      browserRecognitionRef.current = recognition;
      recognition.start();
    } catch (error) {
      setVoiceError(getErrorMessage(error));
    }
  }, [stopSpeaking]);

  const stopListening = useCallback(async () => {
    if (isTauriRuntime()) {
      await stopNativeDictation();
    } else {
      browserRecognitionRef.current?.stop();
    }

    const store = useAssistantStore.getState();
    store.setListening(false);
    store.setAudioLevel(0);
    store.setStatusText('Online');
    if (store.mood === 'listening') store.setMood('idle');
  }, []);

  const cancelListening = useCallback(async () => {
    if (isTauriRuntime()) {
      await cancelNativeDictation();
    } else {
      browserRecognitionRef.current?.abort();
      browserRecognitionRef.current = null;
    }

    const store = useAssistantStore.getState();
    store.setListening(false);
    store.setAudioLevel(0);
    store.setTranscript('');
    store.setStatusText('Online');
    if (store.mood === 'listening') store.setMood('idle');
  }, []);

  const toggleListening = useCallback(async () => {
    if (useAssistantStore.getState().isListening) {
      await stopListening();
    } else {
      await startListening();
    }
  }, [startListening, stopListening]);

  return {
    speak,
    stopSpeaking,
    startListening,
    stopListening,
    cancelListening,
    toggleListening,
    voiceError,
    clearVoiceError: () => setVoiceError(null),
    isListening,
    isSpeaking,
    audioLevel,
    transcript,
    speechSupported: canUseSpeech(),
    dictationSupported: canUseDictation(),
  };
}
