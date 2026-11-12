import { useAssistantStore } from '@/stores';
import type {
  DeveloperFile,
  DeveloperProject,
  DeveloperTask,
  EngineSource,
  FridaySettings,
  SystemSnapshot,
} from '@/types';
import { generateDeveloperDraft } from '@/lib/ai';
import { getErrorMessage, invokeCommand, isTauriRuntime } from '@/lib/runtime';
import { parseGeneratedProject } from './parse';
import { createLocalDraft } from './recipes';

export interface ForgeOutcome {
  project: DeveloperProject;
  files: DeveloperFile[];
  task: DeveloperTask;
  source: EngineSource;
  model?: string;
  warning?: string;
}

interface NativeProjectResult {
  name: string;
  path: string;
  files: Array<{ path: string; bytes: number }>;
}

/**
 * Keeps generated source in memory for the current session. The persisted
 * project record only stores metadata; the workspace on disk is the source of
 * truth once the desktop app has written it.
 */
const draftCache = new Map<string, DeveloperFile[]>();

export function rememberDraft(projectId: string, files: DeveloperFile[]): void {
  draftCache.set(projectId, files);
  while (draftCache.size > 12) {
    const oldest = draftCache.keys().next().value;
    if (!oldest) break;
    draftCache.delete(oldest);
  }
}

export function getDraftFiles(projectId: string): DeveloperFile[] | undefined {
  return draftCache.get(projectId);
}

export interface ForgeOptions {
  prompt: string;
  settings: FridaySettings;
  snapshot?: SystemSnapshot | null;
  onUpdate?: (task: DeveloperTask) => void;
}

const STEP_LABELS = [
  'Interpret the brief',
  'Compose the project',
  'Write the workspace',
  'Verify the entry point',
];

function buildTask(prompt: string): DeveloperTask {
  const startedAt = new Date();
  return {
    id: `forge-${startedAt.getTime()}`,
    prompt,
    status: 'planning',
    steps: STEP_LABELS.map((label, index) => ({
      id: `step-${index + 1}`,
      label,
      status: index === 0 ? 'running' : 'pending',
      startedAt: index === 0 ? startedAt : undefined,
    })),
    startedAt,
  };
}

function updateStep(
  task: DeveloperTask,
  index: number,
  stepStatus: 'running' | 'complete' | 'failed',
  detail?: string
): DeveloperTask {
  const now = new Date();
  const steps = task.steps.map((step, stepIndex) => {
    if (stepIndex !== index) return step;
    return {
      ...step,
      status: stepStatus,
      detail,
      startedAt: step.startedAt ?? now,
      completedAt: stepStatus === 'running' ? undefined : now,
    };
  });

  const taskStatus =
    stepStatus === 'failed'
      ? 'error'
      : index === 0
        ? 'generating'
        : index === 1
          ? 'writing'
          : index === 2
            ? 'ready'
            : 'ready';

  return { ...task, steps, status: taskStatus };
}

function projectFiles(files: DeveloperFile[]): Array<{ path: string; bytes: number }> {
  return files.map((file) => ({ path: file.path, bytes: file.content.length }));
}

function sanitizeTitle(prompt: string): string {
  const cleaned = prompt
    .replace(/^(please\s+)?(build|create|make|code|generate|scaffold|develop|design)\s+(me\s+)?/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return 'FRIDAY Forge project';
  return cleaned.length > 72 ? `${cleaned.slice(0, 72)}…` : cleaned;
}

/** Detects a project-build directive without hijacking ordinary questions. */
export function isDeveloperRequest(input: string): boolean {
  const text = input.trim().toLowerCase();
  if (!text || text.length < 6) return false;
  if (/^(what|how|why|who|when|where|can you explain|tell me about)\b/.test(text)) return false;
  if (/\b(open|close|launch)\b.*\b(app|application|window|folder)\b/.test(text)) return false;

  const buildVerb =
    /\b(build|create|make|code|generate|scaffold|develop|design|prototype|implement)\b/.test(text);
  const artifact =
    /\b(game|app|application|website|web site|site|page|landing|dashboard|portfolio|clone|tool|widget|prototype|project|clone|flappy|snake|tetris|pong|breakout|calculator|timer)\b/.test(
      text
    );

  return (buildVerb && artifact) || /\b(flappy bird|snake game|landing page|portfolio site)\b/.test(text);
}

export function forgeProjectLink(project: DeveloperProject): string {
  const index = project.files.find((file) => file.path === 'index.html');
  if (!index) return project.path;
  return `${project.path}\\index.html`;
}

/** Opens the generated entry point (or the project folder) in the host. */
export async function openDeveloperProject(project: DeveloperProject): Promise<void> {
  if (!isTauriRuntime()) return;

  const { openPath } = await import('@tauri-apps/plugin-opener');
  const index = project.files.find((file) => file.path === 'index.html');
  await openPath(index ? forgeProjectLink(project) : project.path);
}

export async function revealDeveloperProject(project: DeveloperProject): Promise<void> {
  if (!isTauriRuntime()) return;
  const { revealItemInDir } = await import('@tauri-apps/plugin-opener');
  const index = project.files.find((file) => file.path === 'index.html');
  await revealItemInDir(index ? forgeProjectLink(project) : project.path);
}

/**
 * Opens a generated project. In the desktop app this launches the real file on
 * disk. In the browser preview it opens the in-memory single-file entry point.
 */
export function previewDeveloperProject(project: DeveloperProject): boolean {
  if (isTauriRuntime()) {
    void openDeveloperProject(project);
    return true;
  }

  const files = getDraftFiles(project.id);
  const entry = files?.find((file) => file.path === 'index.html');
  if (!entry) return false;

  const url = URL.createObjectURL(new Blob([entry.content], { type: 'text/html' }));
  window.open(url, '_blank', 'noopener,noreferrer');
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return true;
}

export async function runDeveloperForge(options: ForgeOptions): Promise<ForgeOutcome> {
  const { prompt, settings, snapshot, onUpdate } = options;
  let task = buildTask(prompt);
  let warning: string | undefined;

  const publish = () => {
    useAssistantStore.getState().setDeveloperTask(task);
    onUpdate?.(task);
  };

  publish();

  const setStep = (index: number, status: 'running' | 'complete' | 'failed', detail?: string) => {
    task = updateStep(task, index, status, detail);
    publish();
  };

  try {
    setStep(0, 'complete', 'Brief accepted. Selecting the strongest available engine.');

    const title = sanitizeTitle(prompt);
    let files: DeveloperFile[] | null = null;
    let source: EngineSource = 'local';
    let model: string | undefined;
    let name = 'friday-project';
    let description = '';

    setStep(1, 'running', 'Composing a complete browser project.');

    if (!settings.demoMode) {
      try {
        const result = await generateDeveloperDraft(prompt, settings, snapshot);
        const parsed = parseGeneratedProject(result.text, prompt);
        files = parsed.files;
        source = result.provider;
        model = result.model;
        name = parsed.name;
        description = parsed.description;
        setStep(
          1,
          'complete',
          `${parsed.files.length} files composed by ${result.model} in ${Math.round(result.latencyMs / 100) / 10}s.`
        );
      } catch (error) {
        warning = getErrorMessage(error);
        useAssistantStore.getState().setEngineStatus({
          state: 'fallback',
          source: 'local',
          model: 'Local forge recipe',
          detail: warning,
        });
      }
    }

    if (!files) {
      const local = createLocalDraft(prompt);
      files = local.files;
      source = 'local';
      name = local.name;
      description = local.description;
      setStep(
        1,
        'complete',
        warning
          ? 'Engine unavailable. Using the verified offline recipe.'
          : 'Local demo mode. Using the verified offline recipe.'
      );
    }

    setStep(2, 'running', isTauriRuntime() ? 'Writing to Documents\\FRIDAY Forge.' : 'Staging a browser preview.');

    let path: string;
    let writtenFiles: Array<{ path: string; bytes: number }>;

    if (isTauriRuntime()) {
      const native = await invokeCommand<NativeProjectResult>('developer_create_project', {
        request: {
          name,
          title,
          description,
          prompt,
          engine: source,
          model: model ?? null,
          files,
        },
      });
      path = native.path;
      writtenFiles = native.files;
      setStep(2, 'complete', `${completedCount(native.files)} files written to the sandboxed workspace.`);
    } else {
      path = 'Browser preview — run the desktop app to write to Documents\\FRIDAY Forge';
      writtenFiles = projectFiles(files);
      setStep(2, 'complete', 'Preview staged in memory. The desktop app writes files to disk.');
    }

    setStep(3, 'running', 'Checking for a runnable entry point.');
    const entry = files.find((file) => file.path.replace(/\\/g, '/') === 'index.html');
    if (!entry) {
      throw new Error('The generated project has no index.html entry point.');
    }
    if (entry.content.length < 200) {
      throw new Error('The generated index.html is too small to be a working project.');
    }
    setStep(3, 'complete', 'index.html is present and self-contained.');

    const completedAt = new Date();
    task = { ...task, status: 'ready', engine: source, completedAt };
    publish();

    const project: DeveloperProject = {
      id: `project-${completedAt.getTime()}`,
      name,
      title,
      description,
      path,
      prompt,
      engine: source,
      model,
      files: writtenFiles,
      createdAt: completedAt,
    };

    rememberDraft(project.id, files);

    const state = useAssistantStore.getState();
    state.addDeveloperProject(project);
    state.setEngineStatus({
      state: source === 'local' ? 'fallback' : 'online',
      source,
      model: model ?? 'Local forge recipe',
      detail:
        source === 'local'
          ? 'The forge used its offline recipe.'
          : 'Project composed by the selected intelligence engine.',
    });

    return { project, files, task, source, model, warning };
  } catch (error) {
    const message = getErrorMessage(error);
    task = { ...task, status: 'error', error: message, completedAt: new Date() };
    task.steps = task.steps.map((step) =>
      step.status === 'running' ? { ...step, status: 'failed', detail: message } : step
    );
    publish();
    useAssistantStore.getState().setEngineStatus({
      state: 'error',
      source: 'local',
      model: 'Forge halted',
      detail: message,
    });
    throw error;
  }
}

function completedCount(files: Array<{ path: string }>): string {
  return `${files.length} file${files.length === 1 ? '' : 's'}`;
}

export function forgeCompletionMessage(outcome: ForgeOutcome, settings: FridaySettings): string {
  const address =
    settings.addressAs === 'name' && settings.userName.trim() ? settings.userName.trim() : 'sir';
  const engineLabel =
    outcome.source === 'local'
      ? 'the verified offline forge recipe'
      : `${outcome.model ?? 'the selected engine'}`;
  const sourceFile = outcome.project.files.find((file) => file.path === 'index.html');
  const location = sourceFile
    ? `Open the generated file at Documents\\FRIDAY Forge\\${outcome.project.name}\\index.html`
    : `The workspace is at ${outcome.project.path}.`;

  return [
    `Project forged, ${address}.`,
    `${outcome.project.title} is ready with ${outcome.files.length} file${outcome.files.length === 1 ? '' : 's'}.`,
    `Built by ${engineLabel}.`,
    location + ``,
    'Open the Project Forge console to launch or inspect it.',
  ].join(' ');
}
