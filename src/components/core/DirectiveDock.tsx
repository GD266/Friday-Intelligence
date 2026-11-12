import { useRef, useState, type FormEvent, type PointerEvent } from 'react';
import { ArrowUpRight, AudioWaveform, Mic, MicOff, Radio, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAssistantStore } from '@/stores';

export interface DirectiveDockProps {
  onSend?: (content: string) => void;
  isBusy?: boolean;
  isListening?: boolean;
  isSpeaking?: boolean;
  audioLevel?: number;
  transcript?: string;
  voiceError?: string | null;
  onToggleListening?: () => void;
  onDismissVoiceError?: () => void;
  dictationSupported?: boolean;
}

const waveBars = [0.3, 0.55, 0.85, 0.45, 0.7, 0.38, 0.62, 0.28, 0.52, 0.78, 0.4, 0.66, 0.34, 0.58];

export const DirectiveDock = ({
  onSend,
  isBusy = false,
  isListening = false,
  isSpeaking = false,
  audioLevel = 0,
  transcript = '',
  voiceError = null,
  onToggleListening,
  onDismissVoiceError,
  dictationSupported = true,
}: DirectiveDockProps) => {
  const [value, setValue] = useState('');
  const pressStartRef = useRef<number | null>(null);
  const startedPressRef = useRef(false);
  const ignoreClickUntilRef = useRef(0);
  const level = Math.min(1, Math.max(0, audioLevel));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const directive = value.trim();
    if (!onSend || !directive || isBusy) return;
    onSend(directive);
    setValue('');
  };

  const handleMicPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const listening = useAssistantStore.getState().isListening;
    pressStartRef.current = Date.now();
    startedPressRef.current = !listening;
    if (!listening) onToggleListening?.();
  };

  const handleMicPointerUp = (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const startedAt = pressStartRef.current;
    pressStartRef.current = null;
    ignoreClickUntilRef.current = Date.now() + 500;
    if (startedAt === null) return;

    const elapsed = Date.now() - startedAt;
    const listening = useAssistantStore.getState().isListening;

    if (!startedPressRef.current) {
      if (listening) onToggleListening?.();
    } else if (elapsed >= 280 && listening) {
      onToggleListening?.();
    }

    startedPressRef.current = false;
  };

  const handleMicPointerLeave = () => {
    if (pressStartRef.current === null) return;
    pressStartRef.current = null;
    ignoreClickUntilRef.current = Date.now() + 500;
    if (useAssistantStore.getState().isListening) onToggleListening?.();
    startedPressRef.current = false;
  };

  const handleMicClick = () => {
    if (Date.now() < ignoreClickUntilRef.current) return;
    onToggleListening?.();
  };

  return (
    <div className="relative mx-auto w-full max-w-[58rem]">
      {(isListening || isSpeaking) && (
        <div className="pointer-events-none absolute -top-px left-1/2 h-px w-2/3 -translate-x-1/2 bg-gradient-to-r from-transparent via-cyan-300/80 to-transparent" />
      )}

      {isListening && (
        <div className="mb-3 overflow-hidden rounded-xl border border-cyan-300/20 bg-cyan-400/[0.04] px-4 py-3 backdrop-blur-xl animate-in">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 font-mono text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-cyan-300">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300" />
              voice channel live
            </span>
            <div className="flex h-6 flex-1 items-center justify-center gap-[3px]" aria-hidden="true">
              {waveBars.map((bar, index) => (
                <span
                  key={index}
                  className="voice-bar w-[2px] rounded-full bg-cyan-300/80"
                  style={{
                    height: `${16 + bar * (20 + level * 64)}%`,
                    animationDelay: `${index * 62}ms`,
                  }}
                />
              ))}
            </div>
            <button
              type="button"
              className="flex items-center gap-1 rounded border border-border-primary px-2 py-1 font-mono text-[0.6rem] uppercase tracking-wider text-graphite-400 transition-colors hover:border-cyan-300/30 hover:text-cyan-200"
              onClick={onToggleListening}
            >
              <X className="h-3 w-3" />
              stop
            </button>
          </div>
          <p className="mt-2 min-h-[1.15rem] truncate font-mono text-xs text-graphite-200">
            {transcript || 'Speak now — the channel is open.'}
          </p>
        </div>
      )}

      {voiceError && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-400/20 bg-red-400/[0.06] px-3 py-2 font-mono text-[0.68rem] text-red-200">
          <span className="min-w-0 flex-1">{voiceError}</span>
          <button
            type="button"
            className="text-red-300/60 transition-colors hover:text-red-200"
            onClick={onDismissVoiceError}
            aria-label="Dismiss voice error"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <div
        className={cn(
          'directive-dock group relative overflow-hidden rounded-xl border bg-[#060a12]/85 backdrop-blur-2xl transition-all duration-300',
          isListening
            ? 'border-cyan-300/35 shadow-[0_0_40px_rgba(34,211,238,0.1)]'
            : isBusy
              ? 'border-amber-300/30 shadow-[0_0_40px_rgba(251,191,36,0.08)]'
              : 'border-white/[0.08] shadow-[0_20px_80px_rgba(0,0,0,0.55)] hover:border-cyan-300/20'
        )}
      >
        <span className="pointer-events-none absolute left-0 top-0 h-px w-full bg-gradient-to-r from-transparent via-cyan-300/30 to-transparent" />
        <span className="pointer-events-none absolute -right-16 -top-16 h-32 w-32 rounded-full bg-cyan-400/5 blur-2xl" />

        <form className="relative flex items-center gap-2 p-2 sm:gap-3 sm:p-2.5" onSubmit={submit}>
          <button
            type="button"
            aria-label={isListening ? 'Stop listening' : 'Start voice input'}
            aria-pressed={isListening}
            title={
              dictationSupported
                ? 'Click or hold to talk'
                : 'Push-to-talk is available in the desktop app'
            }
            className={cn(
              'relative flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg border transition-all duration-200 sm:h-12 sm:w-12',
              isListening
                ? 'border-cyan-300/50 bg-cyan-400/10 text-cyan-200 shadow-[0_0_24px_rgba(34,211,238,0.18)]'
                : 'border-white/[0.08] bg-white/[0.02] text-graphite-400 hover:border-cyan-300/30 hover:text-cyan-200',
              !dictationSupported && 'opacity-50'
            )}
            onPointerDown={handleMicPointerDown}
            onPointerUp={handleMicPointerUp}
            onPointerLeave={handleMicPointerLeave}
            onPointerCancel={handleMicPointerLeave}
            onClick={handleMicClick}
            disabled={isBusy}
          >
            {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            {isListening && (
              <>
                <span className="absolute inset-0 rounded-lg border border-cyan-300/30 animate-ping-slow" />
                <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border border-[#060a12] bg-cyan-300" />
              </>
            )}
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 px-1">
              <Radio className="h-2.5 w-2.5 text-cyan-300/60" />
              <span className="font-mono text-[0.55rem] uppercase tracking-[0.24em] text-graphite-600">
                directive input
              </span>
              <span className="ml-auto hidden font-mono text-[0.55rem] uppercase tracking-[0.16em] text-graphite-600 sm:block">
                local core
              </span>
            </div>
            <input
              value={value}
              onChange={(event) => setValue(event.target.value)}
              disabled={isBusy}
              placeholder={
                isBusy ? 'Core is processing the current directive…' : 'Enter a directive for FRIDAY…'
              }
              aria-label="Directive input"
              autoComplete="off"
              spellCheck={false}
              className="mt-0.5 w-full bg-transparent px-1 font-mono text-sm text-graphite-100 placeholder-graphite-600 focus:outline-none disabled:cursor-wait"
            />
          </div>

          <button
            type="submit"
            disabled={!value.trim() || isBusy}
            aria-label="Send directive"
            className={cn(
              'group/send relative flex h-11 flex-shrink-0 items-center gap-2 overflow-hidden rounded-lg border px-3 font-mono text-[0.65rem] font-semibold uppercase tracking-[0.16em] transition-all duration-200 sm:h-12 sm:px-4',
              value.trim() && !isBusy
                ? 'border-cyan-300/30 bg-cyan-300/10 text-cyan-200 hover:bg-cyan-300/15'
                : 'border-white/[0.06] bg-white/[0.02] text-graphite-600'
            )}
          >
            <span className="hidden sm:inline">execute</span>
            <ArrowUpRight className="h-4 w-4 transition-transform duration-200 group-hover/send:-translate-y-0.5 group-hover/send:translate-x-0.5" />
          </button>
        </form>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between px-3 pb-1.5 font-mono text-[0.5rem] uppercase tracking-[0.18em] text-graphite-700">
          <span className="flex items-center gap-1.5">
            <AudioWaveform className="h-2.5 w-2.5" />
            {isListening ? 'capturing' : isSpeaking ? 'transmitting' : 'standby'}
          </span>
          <span className="hidden sm:block">enter to transmit</span>
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 px-1 font-mono text-[0.56rem] uppercase tracking-[0.16em] text-graphite-600">
        <span className="flex items-center gap-2">
          <span
            className={cn(
              'h-1 w-1 rounded-full',
              isListening ? 'bg-cyan-300' : isSpeaking ? 'bg-accent-blue' : 'bg-emerald-400'
            )}
          />
          {isListening ? 'voice link active' : isSpeaking ? 'voice link transmitting' : 'voice link ready'}
        </span>
        <span className="hidden items-center gap-2 sm:flex">
          <span>ctrl k · command deck</span>
          <span className="text-graphite-700">/</span>
          <span>hold mic to speak</span>
        </span>
      </div>
    </div>
  );
};

DirectiveDock.displayName = 'DirectiveDock';

export default DirectiveDock;
