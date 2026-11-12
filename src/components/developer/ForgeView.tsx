import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Code2,
  Copy,
  Cpu,
  ExternalLink,
  FileCode2,
  FolderCode,
  FolderOpen,
  Hammer,
  Layers,
  Loader2,
  RefreshCw,
  Sparkles,
  Terminal,
  Wand2,
} from 'lucide-react';
import { cn, formatBytes, formatRelativeTime } from '@/lib/utils';
import { useAssistantStore, useSystemStore, useUIStore } from '@/stores';
import {
  openDeveloperProject,
  previewDeveloperProject,
  revealDeveloperProject,
  runDeveloperForge,
} from '@/lib/developer';
import { isTauriRuntime } from '@/lib/runtime';
import type { DeveloperProject, DeveloperTaskStatus } from '@/types';

const EXAMPLES = [
  {
    icon: Code2,
    label: 'Flappy Bird',
    prompt:
      'Build a 2D Flappy Bird game with neon visuals, scoring, sound, and a restart flow.',
  },
  {
    icon: Layers,
    label: 'Snake',
    prompt:
      'Create a polished snake game with keyboard and swipe controls and a persistent high score.',
  },
  {
    icon: Sparkles,
    label: 'Landing page',
    prompt:
      'Design a premium landing page for a developer productivity tool with a code-forward hero.',
  },
  {
    icon: FolderCode,
    label: 'Portfolio',
    prompt:
      'Build a personal portfolio website for a product designer with selected work and contact details.',
  },
];

const activeStatuses: DeveloperTaskStatus[] = ['planning', 'generating', 'writing'];

const statusLabel: Record<DeveloperTaskStatus, string> = {
  idle: 'Standby',
  planning: 'Planning',
  generating: 'Composing',
  writing: 'Writing',
  ready: 'Ready',
  error: 'Halted',
};

function sourceLabel(project: DeveloperProject): string {
  if (project.model) return project.model;
  if (project.engine === 'local') return 'Offline forge recipe';
  return project.engine;
}

function snapshotFromStatus() {
  const status = useSystemStore.getState().status;
  if (!status.hostname && !status.cpuName) return null;
  return {
    cpuUsage: status.cpuUsage,
    memoryUsage: status.memoryUsage,
    memoryTotal: status.memoryTotal,
    uptime: status.uptime,
    hostname: status.hostname ?? 'this workstation',
    os: status.os ?? 'Windows',
    cpuName: status.cpuName ?? '',
  };
}

export const ForgeView = () => {
  const settings = useAssistantStore((state) => state.settings);
  const task = useAssistantStore((state) => state.developerTask);
  const projects = useAssistantStore((state) => state.developerProjects);
  const engineStatus = useAssistantStore((state) => state.engineStatus);
  const addToast = useUIStore((state) => state.addToast);

  const [prompt, setPrompt] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const busy = isRunning || (task ? activeStatuses.includes(task.status) : false);
  const selectedProject = useMemo(() => {
    if (selectedId) {
      const found = projects.find((project) => project.id === selectedId);
      if (found) return found;
    }
    return projects[0] ?? null;
  }, [projects, selectedId]);

  const handleForge = async () => {
    const brief = prompt.trim();
    if (!brief || busy) return;

    setIsRunning(true);
    try {
      const snapshot = snapshotFromStatus();
      const outcome = await runDeveloperForge({ prompt: brief, settings, snapshot });
      setSelectedId(outcome.project.id);
      setPrompt('');
      addToast({
        type: 'success',
        title: 'Project forged',
        message: `${outcome.project.title} is ready with ${outcome.files.length} file${
          outcome.files.length === 1 ? '' : 's'
        }.`,
      });
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Forge halted',
        message: error instanceof Error ? error.message : 'The project could not be generated.',
      });
    } finally {
      setIsRunning(false);
    }
  };

  const handlePreview = async (project: DeveloperProject) => {
    if (!previewDeveloperProject(project)) {
      addToast({
        type: 'info',
        title: 'Preview unavailable here',
        message:
          'Run FRIDAY as the desktop app to launch the file from disk, or forge a new project for an in-browser preview.',
      });
    }
  };

  const handleReveal = async (project: DeveloperProject) => {
    try {
      await revealDeveloperProject(project);
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Could not open the folder',
        message: error instanceof Error ? error.message : project.path,
      });
    }
  };

  const handleOpen = async (project: DeveloperProject) => {
    if (!isTauriRuntime()) {
      await handlePreview(project);
      return;
    }
    try {
      await openDeveloperProject(project);
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Could not launch the project',
        message: error instanceof Error ? error.message : project.path,
      });
    }
  };

  const handleCopyPath = async (project: DeveloperProject) => {
    try {
      await navigator.clipboard.writeText(project.path);
      addToast({ type: 'info', title: 'Path copied', message: project.path });
    } catch {
      addToast({ type: 'error', title: 'Clipboard unavailable', message: project.path });
    }
  };

  const taskProgress = task ? task.steps.filter((step) => step.status === 'complete').length : 0;

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5 sm:px-6">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.05] pb-3">
          <p className="font-mono text-[0.55rem] uppercase tracking-[0.22em] text-graphite-600">
            sandboxed workspace / {projects.length} project{projects.length === 1 ? '' : 's'} forged
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] px-2.5 py-1 font-mono text-[0.55rem] uppercase tracking-[0.12em] text-graphite-400">
              <Cpu className="h-3 w-3 text-cyan-300/70" />
              {engineStatus.model}
            </span>
            <span
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[0.55rem] uppercase tracking-[0.12em]',
                engineStatus.state === 'online'
                  ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                  : engineStatus.state === 'error'
                    ? 'border-red-500/25 bg-red-500/10 text-red-300'
                    : 'border-amber-500/25 bg-amber-500/10 text-amber-200'
              )}
            >
              <span className="h-1 w-1 rounded-full bg-current" />
              {engineStatus.state}
            </span>
          </div>
        </header>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <div className="space-y-4">
            <section className="forge-hero relative overflow-hidden rounded-xl border border-cyan-300/[0.12] p-5 sm:p-6">
              <span className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-cyan-400/[0.08] blur-3xl" />
              <span className="pointer-events-none absolute -bottom-24 -left-20 h-56 w-56 rounded-full bg-violet-500/[0.08] blur-3xl" />
              <div className="relative">
                <span className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/[0.05] px-2.5 py-1 font-mono text-[0.52rem] uppercase tracking-[0.18em] text-cyan-200/80">
                  <Hammer className="h-3 w-3" />
                  forge online
                </span>
                <h1 className="mt-3 max-w-md text-2xl font-light tracking-tight text-graphite-50 sm:text-[1.9rem]">
                  Describe it. <span className="text-cyan-300/90">FRIDAY builds it.</span>
                </h1>
                <p className="mt-2 max-w-md text-sm leading-relaxed text-graphite-400">
                  A working, self-contained browser project is composed by the selected engine and
                  written to a sandboxed folder under Documents. No shell commands, no arbitrary
                  executables.
                </p>

                <label htmlFor="forge-brief" className="mt-5 block">
                  <span className="font-mono text-[0.55rem] uppercase tracking-[0.18em] text-graphite-500">
                    Project brief
                  </span>
                  <textarea
                    id="forge-brief"
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                        event.preventDefault();
                        handleForge();
                      }
                    }}
                    rows={4}
                    placeholder="Build a 2D Flappy Bird game..."
                    className="input mt-2 min-h-[7.5rem] resize-y text-sm leading-relaxed"
                    disabled={busy}
                  />
                </label>

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[0.52rem] uppercase tracking-[0.14em] text-graphite-600">
                    ctrl + enter to forge
                  </span>
                  <button
                    type="button"
                    onClick={handleForge}
                    disabled={!prompt.trim() || busy}
                    className="inline-flex items-center gap-2 rounded-lg border border-cyan-300/30 bg-cyan-300/[0.12] px-4 py-2 text-sm font-semibold text-cyan-100 transition-all duration-200 hover:border-cyan-300/50 hover:bg-cyan-300/[0.18] disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Wand2 className="h-4 w-4" />
                    )}
                    {busy ? 'Forging…' : 'Forge project'}
                  </button>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="font-mono text-[0.55rem] uppercase tracking-[0.18em] text-graphite-500">
                  Start from a blueprint
                </p>
                <span className="font-mono text-[0.5rem] uppercase tracking-[0.14em] text-graphite-600">
                  click to load
                </span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((example) => {
                  const Icon = example.icon;
                  return (
                    <button
                      key={example.label}
                      type="button"
                      onClick={() => setPrompt(example.prompt)}
                      disabled={busy}
                      className="group flex items-start gap-2.5 rounded-lg border border-white/[0.05] bg-white/[0.01] px-2.5 py-1.5 text-left transition-colors hover:border-cyan-300/20 hover:bg-cyan-300/[0.03] disabled:opacity-40"
                    >
                      <span className="mt-0.5 flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded-md border border-cyan-300/15 bg-cyan-300/[0.05] text-cyan-200/70">
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <span>
                        <span className="block text-xs font-medium text-graphite-200">
                          {example.label}
                        </span>
                        <span className="mt-0.5 line-clamp-2 block text-[0.68rem] leading-relaxed text-graphite-500">
                          {example.prompt}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>

            {task && (
              <section className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-[0.55rem] uppercase tracking-[0.18em] text-graphite-500">
                    Build sequence
                  </p>
                  <span
                    className={cn(
                      'rounded-full border px-2 py-0.5 font-mono text-[0.5rem] uppercase tracking-[0.14em]',
                      task.status === 'error'
                        ? 'border-red-500/25 bg-red-500/10 text-red-300'
                        : task.status === 'ready'
                          ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                          : 'border-cyan-300/25 bg-cyan-300/10 text-cyan-200'
                    )}
                  >
                    {statusLabel[task.status]} · {taskProgress}/{task.steps.length}
                  </span>
                </div>

                <ol className="mt-3 space-y-2.5">
                  {task.steps.map((step) => (
                    <li key={step.id} className="flex items-start gap-2.5">
                      <span className="mt-0.5 flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center">
                        {step.status === 'complete' ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                        ) : step.status === 'running' ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-300" />
                        ) : step.status === 'failed' ? (
                          <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                        ) : (
                          <Circle className="h-3 w-3 text-graphite-700" />
                        )}
                      </span>
                      <div>
                        <p
                          className={cn(
                            'text-xs font-medium',
                            step.status === 'pending' ? 'text-graphite-600' : 'text-graphite-200'
                          )}
                        >
                          {step.label}
                        </p>
                        {step.detail && (
                          <p className="mt-0.5 text-[0.68rem] leading-relaxed text-graphite-500">
                            {step.detail}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>

                {task.error && (
                  <p className="mt-3 rounded border border-red-500/20 bg-red-500/[0.05] px-3 py-2 text-xs leading-relaxed text-red-200/80">
                    {task.error}
                  </p>
                )}
                {task.status === 'error' && (
                  <button
                    type="button"
                    onClick={async () => {
                      if (prompt.trim()) {
                        handleForge();
                      }
                    }}
                    disabled={!prompt.trim() || busy}
                    className="mt-3 inline-flex items-center gap-1.5 text-[0.65rem] font-medium text-cyan-300/80 transition-colors hover:text-cyan-200 disabled:opacity-40"
                  >
                    <RefreshCw className="h-3 w-3" />
                    Retry this brief
                  </button>
                )}
              </section>
            )}
          </div>

          <div className="space-y-4">
            {selectedProject ? (
              <section className="overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.015]">
                <div className="forge-project-preview relative border-b border-white/[0.06] p-5">
                  <span className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-violet-500/[0.1] blur-3xl" />
                  <div className="relative flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                    <div>
                      <span className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/[0.05] px-2.5 py-1 font-mono text-[0.52rem] uppercase tracking-[0.18em] text-cyan-200/80">
                        <Terminal className="h-3 w-3" />
                        {sourceLabel(selectedProject)}
                      </span>
                      <h2 className="mt-1.5 truncate text-lg font-medium text-graphite-50">
                        {selectedProject.title}
                      </h2>
                      <p className="mt-1 truncate text-xs leading-relaxed text-graphite-400">
                        {selectedProject.description}
                      </p>
                    </div>
                    <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border border-cyan-300/15 bg-cyan-300/[0.05] text-cyan-200/70">
                      <FolderCode className="h-4 w-4" />
                    </span>
                  </div>

                  <div className="relative mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleOpen(selectedProject)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-cyan-300/25 bg-cyan-300/[0.08] px-2.5 py-1.5 text-[0.68rem] font-medium text-cyan-100 transition-colors hover:bg-cyan-300/[0.14]"
                    >
                      <ExternalLink className="h-3 w-3" />
                      Open project
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleReveal(selectedProject)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.02] px-2.5 py-1.5 text-[0.68rem] text-graphite-300 transition-colors hover:border-cyan-300/20 hover:text-cyan-200"
                    >
                      <FolderOpen className="h-3 w-3" />
                      Show folder
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleCopyPath(selectedProject)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.02] px-2.5 py-1.5 text-[0.68rem] text-graphite-300 transition-colors hover:border-cyan-300/20 hover:text-cyan-200"
                    >
                      <Copy className="h-3 w-3" />
                      Copy path
                    </button>
                  </div>
                </div>

                <div className="p-4">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[0.52rem] uppercase tracking-[0.16em] text-graphite-500">
                      workspace
                    </p>
                    <span className="font-mono text-[0.5rem] text-graphite-600">
                      {formatRelativeTime(selectedProject.createdAt)}
                    </span>
                  </div>
                  <p className="mt-1.5 break-all rounded border border-white/[0.05] bg-[#03060b] px-2.5 py-2 font-mono text-[0.62rem] leading-relaxed text-graphite-400">
                    {selectedProject.path}
                  </p>

                  <p className="mt-4 font-mono text-[0.52rem] uppercase tracking-[0.16em] text-graphite-500">
                    files · {selectedProject.files.length}
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {selectedProject.files.slice(0, 8).map((file) => (
                      <li
                        key={file.path}
                        className="flex items-center justify-between gap-3 rounded border border-white/[0.04] bg-white/[0.01] px-2.5 py-1.5"
                      >
                        <span className="flex min-w-0 items-center gap-1.5">
                          <FileCode2 className="h-3 w-3 flex-shrink-0 text-cyan-300/50" />
                          <span className="truncate font-mono text-[0.64rem] text-graphite-300">
                            {file.path}
                          </span>
                        </span>
                        <span className="flex-shrink-0 font-mono text-[0.55rem] text-graphite-600">
                          {formatBytes(file.bytes, 1)}
                        </span>
                      </li>
                    ))}
                    {selectedProject.files.length > 8 && (
                      <li className="px-2.5 font-mono text-[0.58rem] text-graphite-600">
                        +{selectedProject.files.length - 8} more files
                      </li>
                    )}
                  </ul>
                </div>
              </section>
            ) : (
              <section className="flex h-full min-h-[22rem] flex-col items-center justify-center rounded-xl border border-dashed border-white/[0.08] bg-white/[0.01] px-6 py-12 text-center">
                <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md border border-cyan-300/15 bg-cyan-300/[0.05] text-cyan-200/70">
                  <Hammer className="h-5 w-5" />
                </span>
                <h2 className="mt-4 text-base font-medium text-graphite-200">No project yet</h2>
                <p className="mt-2 max-w-sm text-xs leading-relaxed text-graphite-500">
                  Describe a game, site, dashboard, or tool. FRIDAY composes a complete project
                  with files, styles, and a working entry point.
                </p>
                {projects.length > 0 && (
                  <p className="mt-2 text-xs text-graphite-600">
                    {projects[0]?.title} is your most recent forge result.
                  </p>
                )}
              </section>
            )}

            {projects.length > 0 && selectedProject && selectedProject.id !== selectedId && (
              <section className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
                <p className="font-mono text-[0.55rem] uppercase tracking-[0.18em] text-graphite-500">
                  Other projects • {projects.length - 1}
                </p>
                <div className="mt-3 space-y-1.5">
                  {projects
                    .filter((project) => project.id !== selectedProject.id)
                    .map((project) => (
                      <button
                        key={project.id}
                        type="button"
                        onClick={() => setSelectedId(project.id)}
                        className={cn(
                          'flex w-full items-start gap-3 rounded-md border px-2.5 py-2 text-left transition-colors',
                          project.id === selectedId
                            ? 'border-cyan-300/20 bg-cyan-300/[0.05]'
                            : 'border-transparent hover:border-white/[0.06] hover:bg-white/[0.02]'
                        )}
                      >
                        <span className="flex-shrink-0">
                          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-cyan-300/15 bg-cyan-300/[0.05] text-cyan-200/70">
                            <FolderCode className="h-3.5 w-3.5" />
                          </span>
                        </span>
                        <span className="min-w-0">
                          <span className="block text-xs text-graphite-200">{project.title}</span>
                          <span className="mt-0.5 block font-mono text-[0.55rem] uppercase tracking-[0.12em] text-graphite-600">
                            {sourceLabel(project)} • {formatRelativeTime(project.createdAt)}
                          </span>
                        </span>
                      </button>
                    ))}
                </div>
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

ForgeView.displayName = 'ForgeView';

export default ForgeView;