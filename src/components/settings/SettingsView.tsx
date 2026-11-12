import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Clock,
  Cpu,
  HardDrive,
  Info,
  Mic,
  Monitor,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  Volume2,
  Workflow,
} from 'lucide-react';
import { cn, formatBytes, formatPercent, formatUptime } from '@/lib/utils';
import { useAssistantStore, useSystemStore, useUIStore } from '@/stores';
import { isTauriRuntime } from '@/lib/runtime';
import { listVoices, previewVoiceById, speakText } from '@/lib/voice';
import { isLikelyFemaleVoice, pickPreferredVoice, formatVoiceName } from '@/lib/voice-profile';
import { AUTOMATION_ACTIONS } from '@/lib/automation';
import { Button } from '@/components/ui/Button';
import type { VoiceOption } from '@/types';

interface SettingsSectionProps {
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
  action?: ReactNode;
}

const SettingsSection = ({
  icon,
  title,
  description,
  children,
  action,
}: SettingsSectionProps) => (
  <section className="overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.015] backdrop-blur-sm">
    <header className="flex items-start justify-between gap-4 border-b border-white/[0.05] px-5 py-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-200/80">
          {icon}
        </span>
        <div>
          <h2 className="text-sm font-semibold tracking-wide text-graphite-100">{title}</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-graphite-500">{description}</p>
        </div>
      </div>
      {action}
    </header>
    <div className="divide-y divide-white/[0.05] px-5">{children}</div>
  </section>
);

interface ToggleRowProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

const ToggleRow = ({ label, description, checked, onChange, disabled = false }: ToggleRowProps) => (
  <div className="flex items-center justify-between gap-6 py-4">
    <div className="min-w-0">
      <p className="text-sm font-medium text-graphite-200">{label}</p>
      <p className="mt-0.5 text-xs leading-relaxed text-graphite-500">{description}</p>
    </div>
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full border transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-blue/60',
        checked
          ? 'border-cyan-300/50 bg-cyan-300/80'
          : 'border-white/[0.08] bg-graphite-800',
        disabled && 'cursor-not-allowed opacity-40'
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform duration-150',
          checked ? 'translate-x-[18px]' : 'translate-x-[3px]'
        )}
      />
    </button>
  </div>
);

const FieldLabel = ({ title, hint }: { title: string; hint?: string }) => (
  <div>
    <p className="text-sm font-medium text-graphite-200">{title}</p>
    {hint && <p className="mt-0.5 text-xs text-graphite-500">{hint}</p>}
  </div>
);

export const SettingsView = () => {
  const settings = useAssistantStore((state) => state.settings);
  const updateSettings = useAssistantStore((state) => state.updateSettings);
  const resetSettings = useAssistantStore((state) => state.resetSettings);
  const automationLog = useAssistantStore((state) => state.automationLog);
  const clearAutomationLog = useAssistantStore((state) => state.clearAutomationLog);
  const openOverlay = useUIStore((state) => state.openOverlay);
  const addToast = useUIStore((state) => state.addToast);
  const systemStatus = useSystemStore((state) => state.status);

  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [isPreviewing, setIsPreviewing] = useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      const available = await listVoices();
      if (active && available.length > 0) setVoices(available);
    };

    void load();

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      const handleVoicesChanged = () => void load();
      window.speechSynthesis.addEventListener('voiceschanged', handleVoicesChanged);
      return () => {
        active = false;
        window.speechSynthesis.removeEventListener('voiceschanged', handleVoicesChanged);
      };
    }

    return () => {
      active = false;
    };
  }, []);

  const highRiskCount = useMemo(
    () => AUTOMATION_ACTIONS.filter((action) => action.risk === 'high').length,
    []
  );

  const recommendedVoice = useMemo(() => pickPreferredVoice(voices), [voices]);

  const handlePreview = async () => {
    setIsPreviewing(true);
    const result = settings.voiceId
      ? await previewVoiceById(settings.voiceId)
      : await speakText('Good evening. All systems are online and standing by.', settings);
    setIsPreviewing(false);

    if (!result.ok) {
      addToast({
        type: 'error',
        title: 'Voice preview failed',
        message: result.error ?? 'The selected voice could not speak.',
      });
    }
  };

  const handleReset = () => {
    resetSettings();
    addToast({
      type: 'info',
      title: 'Settings reset',
      message: 'Persona, voice, and safety preferences are back to their defaults.',
    });
  };

  const memoryPercent =
    systemStatus.memoryTotal > 0
      ? (systemStatus.memoryUsage / systemStatus.memoryTotal) * 100
      : 0;

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-5xl px-4 pb-10 pt-5 sm:px-6">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.05] pb-3">
          <p className="font-mono text-[0.55rem] uppercase tracking-[0.22em] text-graphite-600">
            profile / persona / voice / safety / runtime
          </p>
          <Button variant="ghost" onClick={handleReset}>
            <RotateCcw className="h-3.5 w-3.5" />
            Reset defaults
          </Button>
        </header>

        <div className="space-y-6">
          <SettingsSection
            icon={<User className="h-4 w-4" />}
            title="Persona"
            description="How FRIDAY addresses you and presents itself."
          >
            <div className="grid gap-5 py-4 sm:grid-cols-2">
              <label className="block">
                <FieldLabel title="Form of address" hint="JARVIS-style briefings default to “sir”." />
                <select
                  className="input mt-2"
                  value={settings.addressAs}
                  onChange={(event) =>
                    updateSettings({
                      addressAs: event.target.value === 'name' ? 'name' : 'sir',
                    })
                  }
                >
                  <option value="sir">Address me as “sir”</option>
                  <option value="name">Use my name</option>
                </select>
              </label>

              <label className="block">
                <FieldLabel title="Preferred name" hint="Used only when the name option is active." />
                <input
                  className="input mt-2 disabled:opacity-40"
                  type="text"
                  value={settings.userName}
                  placeholder="e.g. Prana"
                  disabled={settings.addressAs !== 'name'}
                  onChange={(event) => updateSettings({ userName: event.target.value })}
                />
              </label>
            </div>

            <div className="flex items-start gap-3 py-4">
              <Sparkles className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent-violet" />
              <div>
                <p className="text-sm font-medium text-graphite-200">Local demo core</p>
                <p className="mt-0.5 text-xs leading-relaxed text-graphite-500">
                  Replies come from a deterministic local intent engine. No cloud provider is
                  configured, no prompts leave this machine, and FRIDAY will say so when asked.
                </p>
              </div>
              <span className="ml-auto rounded-full border border-accent-violet/30 bg-accent-violet/10 px-2 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wider text-accent-violet">
                Demo
              </span>
            </div>
          </SettingsSection>

          <SettingsSection
            icon={<Volume2 className="h-4 w-4" />}
            title="Voice output"
            description="FRIDAY defaults to a professional English female voice with a calm delivery."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handlePreview()}
                isLoading={isPreviewing}
              >
                <Play className="h-3 w-3" />
                Preview
              </Button>
            }
          >
            <ToggleRow
              label="Enable spoken replies"
              description="FRIDAY can speak answers through the native Windows voice engine."
              checked={settings.voiceEnabled}
              onChange={(voiceEnabled) => updateSettings({ voiceEnabled })}
            />
            <ToggleRow
              label="Speak automatically"
              description="When enabled, every text and voice reply is read aloud."
              checked={settings.autoSpeak}
              onChange={(autoSpeak) => updateSettings({ autoSpeak })}
              disabled={!settings.voiceEnabled}
            />

            <div className="py-4">
              <FieldLabel
                title="Voice"
                hint={
                  recommendedVoice
                    ? `Auto-selects the best installed female voice. Recommended: ${formatVoiceName(recommendedVoice)}.`
                    : 'Auto-selects a professional female English voice when one is installed.'
                }
              />
              <select
                className="input mt-2"
                value={settings.voiceId ?? ''}
                onChange={(event) =>
                  updateSettings({ voiceId: event.target.value || null })
                }
              >
                <option value="">
                  Auto — professional female
                  {recommendedVoice ? ` (${formatVoiceName(recommendedVoice)})` : ''}
                </option>
                {voices.map((voice) => (
                  <option key={voice.id} value={voice.id}>
                    {formatVoiceName(voice)} · {voice.language}
                    {isLikelyFemaleVoice(voice) ? ' · female' : ''}
                  </option>
                ))}
              </select>
              {voices.length === 0 && (
                <p className="mt-2 text-xs text-graphite-500">
                  No voice list is available yet; FRIDAY will use the system default.
                </p>
              )}
              <p className="mt-2 text-xs leading-relaxed text-graphite-600">
                Female-profile voices are preferred automatically. Choose a specific voice only
                if you want to override FRIDAY&apos;s default character.
              </p>
            </div>

            <div className="grid gap-5 py-4 sm:grid-cols-2">
              <label className="block">
                <div className="flex items-center justify-between">
                  <FieldLabel title="Rate" hint="Lower is more deliberate." />
                  <span className="font-mono text-xs text-cyan-300">
                    {settings.voiceRate.toFixed(2)}×
                  </span>
                </div>
                <input
                  type="range"
                  min={0.6}
                  max={1.4}
                  step={0.05}
                  value={settings.voiceRate}
                  onChange={(event) =>
                    updateSettings({ voiceRate: Number(event.target.value) })
                  }
                  className="mt-3 w-full"
                  style={{ accentColor: '#22d3ee' }}
                />
              </label>

              <label className="block">
                <div className="flex items-center justify-between">
                  <FieldLabel title="Pitch" hint="1.00 keeps the natural female register." />
                  <span className="font-mono text-xs text-violet-300">
                    {settings.voicePitch.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min={0.6}
                  max={1.3}
                  step={0.05}
                  value={settings.voicePitch}
                  onChange={(event) =>
                    updateSettings({ voicePitch: Number(event.target.value) })
                  }
                  className="mt-3 w-full"
                  style={{ accentColor: '#a78bfa' }}
                />
              </label>
            </div>

            <div className="flex items-start gap-2 py-4 text-xs text-graphite-500">
              <Mic className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-accent-blue" />
              <p>
                Push-to-talk uses native Windows dictation. The microphone opens only while the
                mic button is active.
              </p>
            </div>
          </SettingsSection>

          <SettingsSection
            icon={<ShieldCheck className="h-4 w-4" />}
            title="Automation and safety"
            description="Every desktop action is allowlisted, logged, and risk-rated."
            action={
              <span className="rounded-full border border-border-primary bg-graphite-900 px-2.5 py-1 text-[0.65rem] text-graphite-400">
                {AUTOMATION_ACTIONS.length} actions
              </span>
            }
          >
            <ToggleRow
              label="Confirm sensitive actions"
              description="Screenshots, web searches, and window controls ask first. High-risk actions always require approval."
              checked={settings.requireConfirmation}
              onChange={(requireConfirmation) => updateSettings({ requireConfirmation })}
            />

            <div className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div>
                <p className="text-sm font-medium text-graphite-200">Automation console</p>
                <p className="mt-0.5 text-xs text-graphite-500">
                  Browse the catalog, run actions, and review the audit log.
                </p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => openOverlay('automation')}>
                <Workflow className="h-3.5 w-3.5" />
                Open console
              </Button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div>
                <p className="text-sm font-medium text-graphite-200">Audit log</p>
                <p className="mt-0.5 text-xs text-graphite-500">
                  {automationLog.length} recorded action{automationLog.length === 1 ? '' : 's'}.
                  High-risk actions: {highRiskCount}.
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled={automationLog.length === 0}
                onClick={() => {
                  clearAutomationLog();
                  addToast({ type: 'info', title: 'Audit log cleared' });
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear log
              </Button>
            </div>
          </SettingsSection>

          <SettingsSection
            icon={<Cpu className="h-4 w-4" />}
            title="System telemetry"
            description={
              isTauriRuntime()
                ? 'Live readings from the native Rust telemetry service.'
                : 'Native readings appear when FRIDAY runs inside the desktop app.'
            }
            action={
              <span
                className={cn(
                  'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.65rem]',
                  isTauriRuntime()
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : 'border-border-primary bg-graphite-900 text-graphite-400'
                )}
              >
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    isTauriRuntime() ? 'bg-emerald-400' : 'bg-graphite-500'
                  )}
                />
                {isTauriRuntime() ? 'Live' : 'Preview'}
              </span>
            }
          >
            <div className="grid gap-4 py-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                {
                  icon: <Cpu className="h-3.5 w-3.5" />,
                  label: 'CPU',
                  value: formatPercent(systemStatus.cpuUsage),
                },
                {
                  icon: <HardDrive className="h-3.5 w-3.5" />,
                  label: 'Memory',
                  value: `${formatPercent(memoryPercent)} · ${formatBytes(systemStatus.memoryUsage, 1)}`,
                },
                {
                  icon: <Clock className="h-3.5 w-3.5" />,
                  label: 'Uptime',
                  value: formatUptime(systemStatus.uptime),
                },
                {
                  icon: <Monitor className="h-3.5 w-3.5" />,
                  label: 'Host',
                  value: systemStatus.hostname ?? 'Unknown',
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-lg border border-white/[0.05] bg-white/[0.015] p-3"
                >
                  <div className="flex items-center gap-2 text-graphite-500">
                    {item.icon}
                    <span className="text-[0.65rem] uppercase tracking-wider">{item.label}</span>
                  </div>
                  <p className="mt-1.5 truncate font-mono text-sm text-graphite-200">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="space-y-1 py-4 text-xs text-graphite-500">
              <p>
                <span className="text-graphite-400">Operating system:</span>{' '}
                {systemStatus.os ?? 'Desktop app required'}
              </p>
              <p className="truncate">
                <span className="text-graphite-400">Processor:</span>{' '}
                {systemStatus.cpuName ?? 'Desktop app required'}
              </p>
            </div>
          </SettingsSection>

          <SettingsSection
            icon={<Info className="h-4 w-4" />}
            title="About FRIDAY"
            description="Phase 2 desktop intelligence foundation."
          >
            <div className="grid gap-4 py-4 sm:grid-cols-3">
              <div>
                <p className="text-[0.65rem] uppercase tracking-wider text-graphite-500">Version</p>
                <p className="mt-1 font-mono text-sm text-graphite-200">0.2.0</p>
              </div>
              <div>
                <p className="text-[0.65rem] uppercase tracking-wider text-graphite-500">Runtime</p>
                <p className="mt-1 text-sm text-graphite-200">Tauri 2 · React 18</p>
              </div>
              <div>
                <p className="text-[0.65rem] uppercase tracking-wider text-graphite-500">AI engine</p>
                <p className="mt-1 text-sm text-graphite-200">Local demo core</p>
              </div>
            </div>
            <p className="py-4 text-xs leading-relaxed text-graphite-500">
              FRIDAY Intelligence is a local-first desktop assistant. Phase 2 adds native speech,
              push-to-talk dictation, live telemetry, and a confirmed desktop automation layer.
              Provider-backed reasoning is intentionally deferred to a later phase.
            </p>
          </SettingsSection>
        </div>
      </div>
    </div>
  );
};

SettingsView.displayName = 'SettingsView';

export default SettingsView;
