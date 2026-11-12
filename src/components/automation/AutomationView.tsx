import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  AppWindow,
  Cpu,
  FolderOpen,
  Globe,
  Info,
  Keyboard,
  Monitor,
  Play,
  Search,
  ShieldCheck,
  Trash2,
  Volume2,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { cn, formatRelativeTime } from '@/lib/utils';
import { useAssistantStore, useUIStore } from '@/stores';
import {
  AUTOMATION_ACTIONS,
  AUTOMATION_CATEGORY_LABELS,
  requiresAutomationConfirmation,
} from '@/lib/automation';
import { requestAutomation } from '@/lib/automation-runner';
import { isTauriRuntime } from '@/lib/runtime';
import { Button } from '@/components/ui/Button';
import type { AutomationAction, AutomationCategory, AutomationRisk } from '@/types';

const riskClasses: Record<AutomationRisk, string> = {
  low: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
  medium: 'border-amber-500/25 bg-amber-500/10 text-amber-300',
  high: 'border-red-500/25 bg-red-500/10 text-red-300',
};

const categoryIcons: Record<AutomationCategory, LucideIcon> = {
  apps: AppWindow,
  folders: FolderOpen,
  system: Cpu,
  media: Volume2,
  window: Monitor,
  input: Keyboard,
  web: Globe,
  info: Info,
};

const statusClasses = {
  pending: 'text-graphite-400',
  running: 'text-accent-blue',
  success: 'text-emerald-300',
  failed: 'text-red-300',
  cancelled: 'text-amber-300',
} as const;

interface AutomationCardProps {
  action: AutomationAction;
  requireConfirmation: boolean;
}

const AutomationCard = ({ action, requireConfirmation }: AutomationCardProps) => {
  const [argument, setArgument] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const CategoryIcon = categoryIcons[action.category];
  const needsApproval = requiresAutomationConfirmation(action, {
    ...useAssistantStore.getState().settings,
    requireConfirmation,
  });
  const requiresArgument = Boolean(action.argumentLabel);

  const handleRun = async () => {
    if (requiresArgument && !argument.trim()) return;
    setIsRunning(true);
    await requestAutomation(action, requiresArgument ? argument.trim() : undefined, 'automation-page');
    setIsRunning(false);
    if (requiresArgument) setArgument('');
  };

  return (
    <article className="flex h-full flex-col rounded-xl border border-white/[0.06] bg-white/[0.015] p-4 transition-colors hover:border-cyan-300/20 hover:bg-cyan-300/[0.02]">
      <div className="flex items-start gap-3">
        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-cyan-300/15 bg-cyan-300/[0.05] text-cyan-200/70">
          <CategoryIcon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-medium text-graphite-100">{action.label}</h3>
            <span
              className={cn(
                'flex-shrink-0 rounded-full border px-2 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wider',
                riskClasses[action.risk]
              )}
            >
              {action.risk}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-graphite-500">{action.description}</p>
        </div>
      </div>

      <div className="mt-auto pt-4">
        {requiresArgument && (
          <input
            className="input mb-2 text-xs"
            value={argument}
            onChange={(event) => setArgument(event.target.value)}
            placeholder={action.argumentLabel}
            aria-label={`${action.label} argument`}
          />
        )}

        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1 text-[0.65rem] text-graphite-500">
            {needsApproval ? (
              <>
                <ShieldCheck className="h-3 w-3 text-amber-400" />
                Confirmation required
              </>
            ) : (
              <>
                <Play className="h-3 w-3 text-emerald-400" />
                Ready
              </>
            )}
          </span>
          <Button
            variant={action.risk === 'high' ? 'danger' : 'secondary'}
            size="sm"
            onClick={() => void handleRun()}
            disabled={requiresArgument && !argument.trim()}
            isLoading={isRunning}
          >
            <Play className="h-3 w-3" />
            Run
          </Button>
        </div>
      </div>
    </article>
  );
};

export const AutomationView = () => {
  const automationLog = useAssistantStore((state) => state.automationLog);
  const clearAutomationLog = useAssistantStore((state) => state.clearAutomationLog);
  const settings = useAssistantStore((state) => state.settings);
  const addToast = useUIStore((state) => state.addToast);

  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return AUTOMATION_ACTIONS;
    return AUTOMATION_ACTIONS.filter((action) =>
      [action.label, action.description, action.category, ...action.keywords]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    );
  }, [query]);

  const grouped = useMemo(
    () =>
      (Object.keys(AUTOMATION_CATEGORY_LABELS) as AutomationCategory[])
        .map((category) => ({
          category,
          actions: filtered.filter((action) => action.category === category),
        }))
        .filter((group) => group.actions.length > 0),
    [filtered]
  );

  const highRiskCount = AUTOMATION_ACTIONS.filter((action) => action.risk === 'high').length;
  const successCount = automationLog.filter((entry) => entry.status === 'success').length;

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5 sm:px-6">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.05] pb-3">
          <p className="font-mono text-[0.55rem] uppercase tracking-[0.22em] text-graphite-600">
            catalog / allowlisted / audited
          </p>
          <div className="flex flex-wrap items-center gap-1.5 text-[0.6rem]">
            <span className="rounded-full border border-white/[0.06] bg-white/[0.02] px-2.5 py-1 font-mono uppercase tracking-wider text-graphite-400">
              {AUTOMATION_ACTIONS.length} actions
            </span>
            <span className="rounded-full border border-red-500/20 bg-red-500/[0.08] px-2.5 py-1 font-mono uppercase tracking-wider text-red-300">
              {highRiskCount} high risk
            </span>
            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/[0.08] px-2.5 py-1 font-mono uppercase tracking-wider text-emerald-300">
              {successCount} successful
            </span>
          </div>
        </header>

        {!isTauriRuntime() && (
          <div className="mb-5 flex items-start gap-3 rounded-lg border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <p>
              Desktop actions require the FRIDAY desktop app. The browser preview shows the full
              catalog and confirmation flow, but native execution is disabled.
            </p>
          </div>
        )}

        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-graphite-500" />
            <input
              className="input pl-9 text-xs"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter actions…"
              aria-label="Filter automation actions"
            />
          </div>
          <p className="text-xs text-graphite-500">
            Confirmation policy:{' '}
            <span className="text-graphite-300">
              {settings.requireConfirmation ? 'sensitive actions ask first' : 'low-risk actions run directly'}
            </span>
          </p>
        </div>

        <div className="space-y-7">
          {grouped.map((group) => (
            <section key={group.category}>
              <div className="mb-2 flex items-center gap-2">
                <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-graphite-500">
                  {AUTOMATION_CATEGORY_LABELS[group.category]}
                </h2>
                <span className="text-[0.65rem] text-graphite-600">
                  {group.actions.length}
                </span>
                <div className="h-px flex-1 bg-white/[0.05]" />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {group.actions.map((action) => (
                  <AutomationCard
                    key={action.id}
                    action={action}
                    requireConfirmation={settings.requireConfirmation}
                  />
                ))}
              </div>
            </section>
          ))}

          {grouped.length === 0 && (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-10 text-center text-sm text-graphite-500">
              No actions match “{query}”.
            </div>
          )}
        </div>

        <section className="mt-8">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-graphite-200">Audit log</h2>
              <p className="mt-0.5 text-xs text-graphite-500">
                Every action FRIDAY executes is recorded locally.
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
              Clear
            </Button>
          </div>

          <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.015]">
            {automationLog.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-6 py-10 text-center text-graphite-500">
                <Workflow className="h-5 w-5" />
                <p className="mt-2 text-xs">No actions have been executed yet.</p>
              </div>
            ) : (
              <ul className="divide-y divide-white/[0.05]">
                {automationLog.slice(0, 25).map((entry) => (
                  <li key={entry.id} className="flex items-start gap-3 px-4 py-3">
                    <span
                      className={cn(
                        'mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full',
                        entry.status === 'success'
                          ? 'bg-emerald-400'
                          : entry.status === 'failed'
                            ? 'bg-red-400'
                            : 'bg-accent-blue'
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-medium text-graphite-200">{entry.label}</span>
                        <span
                          className={cn(
                            'rounded border px-1.5 py-0.5 text-[0.55rem] font-semibold uppercase tracking-wider',
                            riskClasses[entry.risk]
                          )}
                        >
                          {entry.risk}
                        </span>
                        <span className={cn('text-[0.65rem] font-medium', statusClasses[entry.status])}>
                          {entry.status}
                        </span>
                      </div>
                      <p className="mt-0.5 truncate text-xs text-graphite-500">{entry.message}</p>
                    </div>
                    <div className="flex flex-shrink-0 flex-col items-end text-[0.6rem] text-graphite-500">
                      <span>{formatRelativeTime(new Date(entry.timestamp))}</span>
                      {entry.durationMs != null && <span>{entry.durationMs}ms</span>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

AutomationView.displayName = 'AutomationView';

export default AutomationView;
