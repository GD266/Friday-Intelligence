import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Activity,
  ArrowUpRight,
  AudioWaveform,
  Camera,
  Command,
  Cpu,
  HelpCircle,
  History,
  MemoryStick,
  Plus,
  ScrollText,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { cn, formatPercent, formatRelativeTime, formatUptime } from '@/lib/utils';
import { useAssistantStore, useConversationsStore, useSystemStore, useUIStore } from '@/stores';
import { getAddress } from '@/lib/friday';
import { AUTOMATION_ACTIONS } from '@/lib/automation';
import type { FridayMood, Message } from '@/types';
import { CoreOrb } from './CoreOrb';
import { HudBackground } from './HudBackground';
import { DirectiveDock } from './DirectiveDock';

export interface CoreStageProps {
  messages: Message[];
  onSend: (content: string) => void;
  isBusy: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  audioLevel: number;
  transcript: string;
  voiceError: string | null;
  onToggleListening: () => void;
  onDismissVoiceError: () => void;
  dictationSupported: boolean;
}

const moodCopy: Record<FridayMood, { tag: string; label: string }> = {
  idle: { tag: 'NOMINAL', label: 'Standing by' },
  listening: { tag: 'VOICE LINK', label: 'Listening' },
  thinking: { tag: 'PROCESSING', label: 'Working' },
  speaking: { tag: 'TRANSMITTING', label: 'Responding' },
  alert: { tag: 'ATTENTION', label: 'Alert' },
};

const messageText = (message: Message | undefined): string =>
  message?.content.text?.trim() ?? '';

const timeOfDay = () => {
  const hour = new Date().getHours();
  if (hour < 5) return 'Good evening';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
};

const HudButton = ({
  icon: Icon,
  label,
  onClick,
  accent = false,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  accent?: boolean;
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    title={label}
    className={cn(
      'group flex h-9 items-center gap-2 rounded border px-2.5 transition-all duration-200',
      accent
        ? 'border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-200 hover:bg-cyan-300/10'
        : 'border-white/[0.06] bg-white/[0.015] text-graphite-400 hover:border-cyan-300/20 hover:text-cyan-200'
    )}
  >
    <Icon className="h-3.5 w-3.5" />
    <span className="hidden font-mono text-[0.56rem] uppercase tracking-[0.16em] xl:inline">
      {label}
    </span>
  </button>
);

const RailLabel = ({ children }: { children: ReactNode }) => (
  <div className="flex items-center gap-2">
    <span className="font-mono text-[0.55rem] font-semibold uppercase tracking-[0.24em] text-graphite-500">
      {children}
    </span>
    <span className="h-px flex-1 bg-gradient-to-r from-white/[0.08] to-transparent" />
  </div>
);

const RailRow = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-center justify-between gap-3">
    <span className="font-mono text-[0.58rem] uppercase tracking-[0.14em] text-graphite-600">
      {label}
    </span>
    <span className="truncate font-mono text-[0.65rem] text-graphite-300">{value}</span>
  </div>
);

const Meter = ({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: 'cyan' | 'violet';
}) => {
  const clamped = Math.min(100, Math.max(0, value));
  const bars = Array.from({ length: 24 }, (_, index) => {
    const wave = (Math.sin((index / 24) * Math.PI * 3.4) + 1) / 2;
    const active = index / 24 <= clamped / 100;
    return active ? 28 + wave * 66 : 8 + wave * 10;
  });

  return (
    <div>
      <div className="flex items-end justify-between">
        <span className="flex items-center gap-1.5 font-mono text-[0.56rem] uppercase tracking-[0.18em] text-graphite-500">
          <Icon className="h-3 w-3" />
          {label}
        </span>
        <span className="font-mono text-sm text-graphite-200">
          {Math.round(clamped)}
          <span className="ml-0.5 text-[0.6rem] text-graphite-600">%</span>
        </span>
      </div>
      <div className="mt-2 flex h-9 items-end gap-[3px]" aria-hidden="true">
        {bars.map((height, index) => (
          <span
            key={index}
            className={cn(
              'flex-1 rounded-[1px] transition-all duration-500',
              index / 24 <= clamped / 100
                ? tone === 'cyan'
                  ? 'bg-cyan-300/55'
                  : 'bg-violet-400/45'
                : 'bg-white/[0.04]'
            )}
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
    </div>
  );
};

const SystemRail = () => {
  const status = useSystemStore((state) => state.status);
  const memoryPercent =
    status.memoryTotal > 0 ? (status.memoryUsage / status.memoryTotal) * 100 : 0;

  return (
    <aside className="hidden min-h-0 flex-col justify-center gap-5 self-center lg:flex">
      <div>
        <RailLabel>system telemetry</RailLabel>
        <div className="mt-4 space-y-4">
          <Meter label="cpu load" value={status.cpuUsage} icon={Cpu} tone="cyan" />
          <Meter label="memory" value={memoryPercent} icon={MemoryStick} tone="violet" />
        </div>
      </div>

      <div className="h-px bg-gradient-to-r from-white/[0.07] via-white/[0.03] to-transparent" />

      <div className="space-y-2">
        <RailRow label="uptime" value={formatUptime(status.uptime)} />
        <RailRow label="host" value={status.hostname ?? 'browser preview'} />
        <RailRow label="platform" value={status.os ?? 'web runtime'} />
        <RailRow label="memory" value={formatPercent(memoryPercent)} />
      </div>

      <div className="rounded border border-violet-400/10 bg-violet-400/[0.03] px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3 w-3 text-violet-300/70" />
          <span className="font-mono text-[0.55rem] uppercase tracking-[0.18em] text-violet-200/80">
            local demo core
          </span>
        </div>
        <p className="mt-1.5 text-[0.62rem] leading-relaxed text-graphite-500">
          Deterministic persona. No cloud model connected. Voice, telemetry, and automation are
          live.
        </p>
      </div>
    </aside>
  );
};

const SignalRail = () => {
  const isListening = useAssistantStore((state) => state.isListening);
  const isSpeaking = useAssistantStore((state) => state.isSpeaking);
  const audioLevel = useAssistantStore((state) => state.audioLevel);
  const settings = useAssistantStore((state) => state.settings);
  const automationLog = useAssistantStore((state) => state.automationLog);
  const conversations = useConversationsStore((state) => state.conversations);
  const activeConversationId = useConversationsStore((state) => state.activeConversationId);
  const createConversation = useConversationsStore((state) => state.createConversation);
  const openOverlay = useUIStore((state) => state.openOverlay);

  const activeConversation =
    conversations.find((conversation) => conversation.id === activeConversationId) ?? null;
  const lastAction = automationLog[0];
  const level = Math.min(1, Math.max(0, audioLevel));
  const voiceActive = isListening || isSpeaking;

  return (
    <aside className="hidden min-h-0 flex-col justify-center gap-4 self-center lg:flex">
      <div>
        <RailLabel>voice link</RailLabel>
        <div className="mt-3 rounded border border-white/[0.05] bg-white/[0.015] px-3 py-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-mono text-[0.56rem] uppercase tracking-[0.16em] text-graphite-400">
              <AudioWaveform className="h-3 w-3 text-cyan-300/70" />
              {isListening ? 'capturing' : isSpeaking ? 'transmitting' : 'ready'}
            </span>
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                voiceActive ? 'animate-pulse bg-cyan-300' : 'bg-emerald-400'
              )}
            />
          </div>
          <div className="mt-3 flex h-7 items-center justify-center gap-[3px]" aria-hidden="true">
            {Array.from({ length: 18 }, (_, index) => (
              <span
                key={index}
                className={cn(
                  'w-[2px] rounded-full transition-all duration-300',
                  voiceActive ? 'voice-bar bg-cyan-300/70' : 'bg-white/[0.07]'
                )}
                style={{
                  height: voiceActive
                    ? `${18 + ((index * 37) % 70) * (0.35 + level * 0.65)}%`
                    : `${16 + ((index * 23) % 26)}%`,
                  animationDelay: `${index * 55}ms`,
                }}
              />
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between font-mono text-[0.5rem] uppercase tracking-[0.14em] text-graphite-600">
            <span>{settings.voiceId ? 'manual voice' : 'auto / female'}</span>
            <span>en-gb</span>
          </div>
        </div>
      </div>

      <div>
        <RailLabel>automation</RailLabel>
        <div className="mt-3 rounded border border-white/[0.05] bg-white/[0.015] px-3 py-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-mono text-[0.56rem] uppercase tracking-[0.16em] text-graphite-400">
              <ShieldCheck className="h-3 w-3 text-emerald-300/70" />
              armed
            </span>
            <span className="font-mono text-[0.55rem] text-graphite-600">
              {AUTOMATION_ACTIONS.length} actions
            </span>
          </div>
          <div className="mt-2 space-y-1.5">
            <RailRow label="policy" value={settings.requireConfirmation ? 'confirm' : 'relaxed'} />
            <RailRow label="audit" value={`${automationLog.length} entries`} />
          </div>
          {lastAction ? (
            <div className="mt-2 border-t border-white/[0.05] pt-2">
              <p className="truncate font-mono text-[0.55rem] uppercase tracking-[0.1em] text-graphite-500">
                {lastAction.label}
              </p>
              <div className="mt-1 flex items-center justify-between font-mono text-[0.5rem] uppercase tracking-wider text-graphite-600">
                <span
                  className={
                    lastAction.status === 'success'
                      ? 'text-emerald-300/80'
                      : lastAction.status === 'failed'
                        ? 'text-red-300/80'
                        : 'text-cyan-300/80'
                  }
                >
                  {lastAction.status}
                </span>
                <span>{formatRelativeTime(new Date(lastAction.timestamp))}</span>
              </div>
            </div>
          ) : (
            <p className="mt-2 border-t border-white/[0.05] pt-2 text-[0.6rem] leading-relaxed text-graphite-600">
              No actions executed. The audit log is clear.
            </p>
          )}
          <button
            type="button"
            onClick={() => openOverlay('automation')}
            className="mt-2 flex items-center gap-1 font-mono text-[0.52rem] uppercase tracking-[0.16em] text-cyan-300/70 transition-colors hover:text-cyan-200"
          >
            open console
            <ArrowUpRight className="h-2.5 w-2.5" />
          </button>
        </div>
      </div>

      <div>
        <RailLabel>session</RailLabel>
        <div className="mt-3 rounded border border-white/[0.05] bg-white/[0.015] px-3 py-3">
          <p className="truncate text-xs text-graphite-300">
            {activeConversation?.title ?? 'Unfiled session'}
          </p>
          <p className="mt-1 font-mono text-[0.52rem] uppercase tracking-[0.14em] text-graphite-600">
            {activeConversation?.messages.length ?? 0} transmissions
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={() => openOverlay('log')}
              className="flex items-center gap-1 font-mono text-[0.52rem] uppercase tracking-[0.14em] text-cyan-300/70 transition-colors hover:text-cyan-200"
            >
              <History className="h-2.5 w-2.5" />
              open log
            </button>
            <span className="h-2.5 w-px bg-white/[0.08]" />
            <button
              type="button"
              onClick={() => createConversation()}
              className="flex items-center gap-1 font-mono text-[0.52rem] uppercase tracking-[0.14em] text-graphite-500 transition-colors hover:text-graphite-200"
            >
              <Plus className="h-2.5 w-2.5" />
              new
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};

const CoreArray = ({
  mood,
  audioLevel,
}: {
  mood: FridayMood;
  audioLevel: number;
}) => (
  <div className="core-array relative flex h-[17.5rem] w-[17.5rem] flex-shrink-0 items-center justify-center sm:h-[21rem] sm:w-[21rem] xl:h-[22rem] xl:w-[22rem]">
    <div className="core-array__aura" aria-hidden="true" />
    <div className="core-array__ring core-array__ring--a" aria-hidden="true" />
    <div className="core-array__ring core-array__ring--b" aria-hidden="true" />
    <div className="core-array__ring core-array__ring--c" aria-hidden="true" />
    <div className="core-array__sweep" aria-hidden="true" />
    <div className="core-array__axis core-array__axis--x" aria-hidden="true" />
    <div className="core-array__axis core-array__axis--y" aria-hidden="true" />
    <div className="core-array__node core-array__node--north" aria-hidden="true" />
    <div className="core-array__node core-array__node--east" aria-hidden="true" />
    <div className="core-array__node core-array__node--south" aria-hidden="true" />
    <div className="core-array__node core-array__node--west" aria-hidden="true" />

    <span className="core-array__readout core-array__readout--tl">CORE.01</span>
    <span className="core-array__readout core-array__readout--tr">SYNC 99.8</span>
    <span className="core-array__readout core-array__readout--bl">
      {mood === 'listening' ? 'AUDIO.IN' : 'AUDIO.EN-GB'}
    </span>
    <span className="core-array__readout core-array__readout--br">LOCAL.CORE</span>

    <CoreOrb mood={mood} size="hero" audioLevel={audioLevel} />
  </div>
);

const QuickDirective = ({
  icon: Icon,
  label,
  onClick,
  disabled,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className="group flex items-center gap-2 rounded border border-white/[0.06] bg-white/[0.015] px-2.5 py-1.5 font-mono text-[0.55rem] uppercase tracking-[0.14em] text-graphite-500 transition-all duration-200 hover:border-cyan-300/25 hover:bg-cyan-300/[0.04] hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-35"
  >
    <Icon className="h-3 w-3 text-graphite-600 transition-colors group-hover:text-cyan-300/80" />
    {label}
    <ArrowUpRight className="h-2.5 w-2.5 opacity-0 transition-all group-hover:opacity-100" />
  </button>
);

export const CoreStage = ({
  messages,
  onSend,
  isBusy,
  isListening,
  isSpeaking,
  audioLevel,
  transcript,
  voiceError,
  onToggleListening,
  onDismissVoiceError,
  dictationSupported,
}: CoreStageProps) => {
  const settings = useAssistantStore((state) => state.settings);
  const mood = useAssistantStore((state) => state.mood);
  const openOverlay = useUIStore((state) => state.openOverlay);
  const toggleCommandPalette = useUIStore((state) => state.toggleCommandPalette);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const address = getAddress(settings);
  const lastAssistant = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant'),
    [messages]
  );
  const lastUser = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'user'),
    [messages]
  );
  const latestReply = messageText(lastAssistant);
  const latestDirective = messageText(lastUser);
  const status = moodCopy[mood];

  const headline =
    mood === 'listening'
      ? 'Listening.'
      : mood === 'thinking'
        ? 'Processing directive.'
        : mood === 'speaking'
          ? 'Transmitting response.'
          : messages.length === 0
            ? `${timeOfDay()}, ${address}.`
            : 'At your service.';

  const displayText =
    mood === 'listening'
      ? transcript || 'The voice channel is open. Speak your directive.'
      : mood === 'thinking'
        ? 'Parsing your request through the local command core.'
        : latestReply ||
          'All systems are nominal. The core is standing by for your first directive.';

  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(now);

  const date = new Intl.DateTimeFormat('en-GB', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
    .format(now)
    .toUpperCase();

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-[#04060b] text-graphite-100">
      <HudBackground />

      <header className="absolute inset-x-0 top-0 z-40 flex items-start justify-between gap-3 px-4 py-4 sm:px-6 sm:py-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="relative flex h-9 w-9 flex-shrink-0 items-center justify-center">
            <span className="absolute inset-0 rotate-45 border border-cyan-300/20" />
            <span className="absolute inset-[5px] rotate-45 border border-cyan-300/10" />
            <span className="relative font-mono text-[0.62rem] font-semibold tracking-[0.04em] text-cyan-200">
              FR
            </span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-[0.28em] text-graphite-100">
                FRIDAY
              </span>
              <span className="rounded border border-cyan-300/15 bg-cyan-300/[0.04] px-1.5 py-0.5 font-mono text-[0.48rem] uppercase tracking-[0.16em] text-cyan-200/70">
                core.02
              </span>
            </div>
            <p className="mt-0.5 hidden font-mono text-[0.48rem] uppercase tracking-[0.26em] text-graphite-600 sm:block">
              intelligence / local desktop
            </p>
          </div>
        </div>

        <div className="hidden items-center gap-2 self-center rounded-full border border-white/[0.05] bg-white/[0.015] px-3 py-1.5 md:flex">
          <span className="h-1 w-1 rounded-full bg-emerald-400" />
          <span className="font-mono text-[0.5rem] uppercase tracking-[0.18em] text-graphite-500">
            core online
          </span>
          <span className="h-2.5 w-px bg-white/[0.08]" />
          <span className="font-mono text-[0.5rem] uppercase tracking-[0.16em] text-graphite-600">
            local demo
          </span>
        </div>

        <div className="flex flex-shrink-0 items-start gap-2">
          <div className="mr-1 hidden text-right sm:block">
            <p className="font-mono text-sm tracking-[0.14em] text-graphite-200">{time}</p>
            <p className="font-mono text-[0.5rem] uppercase tracking-[0.18em] text-graphite-600">
              {date}
            </p>
          </div>

          <HudButton icon={ScrollText} label="Log" onClick={() => openOverlay('log')} />
          <HudButton
            icon={Workflow}
            label="Automation"
            onClick={() => openOverlay('automation')}
          />
          <HudButton
            icon={Settings2}
            label="Settings"
            onClick={() => openOverlay('settings')}
          />

          <button
            type="button"
            onClick={toggleCommandPalette}
            aria-label="Open command deck"
            className="group flex h-9 items-center gap-2 rounded border border-cyan-300/25 bg-cyan-300/[0.06] px-2.5 text-cyan-200 transition-all duration-200 hover:bg-cyan-300/10"
          >
            <Command className="h-3.5 w-3.5" />
            <span className="hidden font-mono text-[0.56rem] uppercase tracking-[0.16em] xl:inline">
              command
            </span>
            <kbd className="hidden rounded border border-cyan-300/15 bg-[#03060b] px-1 py-0.5 font-mono text-[0.5rem] text-cyan-200/60 sm:block">
              K
            </kbd>
          </button>
        </div>
      </header>

      <main className="relative z-10 flex min-h-0 flex-1 flex-col pt-20 sm:pt-24">
        <div className="grid min-h-0 flex-1 grid-cols-1 items-center gap-4 px-4 sm:px-6 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_minmax(0,14rem)] xl:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_minmax(0,16rem)]">
          <SystemRail />

          <section className="flex min-h-0 flex-col items-center justify-center overflow-y-auto scrollbar-none py-1">
            <div className="flex items-center gap-2 self-center">
              <span
                className={cn(
                  'h-1 w-1 rounded-full',
                  isListening
                    ? 'animate-pulse bg-cyan-300'
                    : isBusy
                      ? 'animate-pulse bg-amber-300'
                      : isSpeaking
                        ? 'animate-pulse bg-accent-blue'
                        : 'bg-emerald-400'
                )}
              />
              <p className="font-mono text-[0.52rem] uppercase tracking-[0.26em] text-graphite-500">
                friday core / {status.tag}
              </p>
              <span className="h-px w-8 bg-gradient-to-r from-white/[0.12] to-transparent" />
            </div>

            <CoreArray mood={mood} audioLevel={audioLevel} />

            <div className="mt-5 flex flex-col items-center px-2 text-center sm:mt-7">
              <h1 className="max-w-2xl text-[1.55rem] font-light tracking-tight text-graphite-50 sm:text-[2rem] xl:text-[2.35rem]">
                {headline}
                <span className="ml-1 inline-block text-cyan-300/80 animate-cursor">_</span>
              </h1>

              <div className="mt-2 flex min-h-[3.2rem] max-w-2xl items-start justify-center">
                {isBusy && !isSpeaking ? (
                  <span className="mt-2 flex items-center gap-1.5" aria-label="FRIDAY is processing">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </span>
                ) : (
                  <p className="line-clamp-4 text-sm leading-relaxed text-graphite-400 sm:text-[0.95rem]">
                    {displayText}
                  </p>
                )}
              </div>

              {latestDirective && mood !== 'listening' && (
                <p className="mt-1 max-w-xl truncate font-mono text-[0.55rem] uppercase tracking-[0.14em] text-graphite-600">
                  last directive / {latestDirective}
                </p>
              )}

              <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5">
                <QuickDirective
                  icon={Activity}
                  label="system status"
                  onClick={() => onSend('System status')}
                  disabled={isBusy}
                />
                <QuickDirective
                  icon={Terminal}
                  label="open notepad"
                  onClick={() => onSend('Open Notepad')}
                  disabled={isBusy}
                />
                <QuickDirective
                  icon={Camera}
                  label="screenshot"
                  onClick={() => onSend('Take a screenshot')}
                  disabled={isBusy}
                />
                <QuickDirective
                  icon={HelpCircle}
                  label="capabilities"
                  onClick={() => onSend('What can you do?')}
                  disabled={isBusy}
                />
              </div>
            </div>
          </section>

          <SignalRail />
        </div>

        <div className="flex-shrink-0 px-4 pb-4 pt-3 sm:px-6 sm:pb-5">
          <DirectiveDock
            onSend={onSend}
            isBusy={isBusy}
            isListening={isListening}
            isSpeaking={isSpeaking}
            audioLevel={audioLevel}
            transcript={transcript}
            voiceError={voiceError}
            onToggleListening={onToggleListening}
            onDismissVoiceError={onDismissVoiceError}
            dictationSupported={dictationSupported}
          />
        </div>
      </main>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex items-end justify-between px-4 pb-1 font-mono text-[0.46rem] uppercase tracking-[0.2em] text-graphite-700 sm:px-6">
        <span>friday intelligence // orbital interface</span>
        <span className="hidden items-center gap-2 sm:flex">
          <span>build 0.2.0</span>
          <span className="h-1 w-1 rounded-full bg-emerald-400/60" />
          <span>aes local</span>
        </span>
      </div>
    </div>
  );
};

CoreStage.displayName = 'CoreStage';

export default CoreStage;
