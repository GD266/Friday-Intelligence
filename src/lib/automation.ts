import type {
  AutomationAction,
  AutomationCategory,
  AutomationResult,
  FridaySettings,
} from '@/types';
import { invokeCommand } from './runtime';

export const AUTOMATION_CATEGORY_LABELS: Record<AutomationCategory, string> = {
  apps: 'Applications',
  folders: 'Folders',
  system: 'System',
  media: 'Media',
  window: 'Windows',
  input: 'Input',
  web: 'Web',
  info: 'Information',
};

const action = (
  id: string,
  label: string,
  description: string,
  category: AutomationCategory,
  risk: AutomationAction['risk'],
  keywords: string[],
  extra: Partial<AutomationAction> = {}
): AutomationAction => ({
  id,
  label,
  description,
  category,
  risk,
  keywords,
  requiresConfirmation: risk === 'high' || extra.requiresConfirmation === true,
  ...extra,
});

export const AUTOMATION_ACTIONS: AutomationAction[] = [
  action('open_notepad', 'Open Notepad', 'Launch the Windows text editor.', 'apps', 'low', [
    'notepad',
    'notes',
    'text editor',
  ]),
  action('open_calculator', 'Open Calculator', 'Launch the Windows calculator.', 'apps', 'low', [
    'calculator',
    'calc',
    'math',
  ]),
  action('open_explorer', 'Open File Explorer', 'Browse files and drives.', 'apps', 'low', [
    'file explorer',
    'explorer',
    'files',
    'my files',
  ]),
  action('open_terminal', 'Open Terminal', 'Launch Windows Terminal or Command Prompt.', 'apps', 'low', [
    'terminal',
    'command prompt',
    'cmd',
    'console',
  ]),
  action('open_settings', 'Open Windows Settings', 'Open the Windows Settings app.', 'system', 'low', [
    'windows settings',
    'system settings',
    'settings app',
  ]),
  action('open_browser', 'Open Browser', 'Open the default browser at Google.', 'apps', 'low', [
    'browser',
    'web browser',
    'chrome',
    'edge',
  ]),
  action('open_task_manager', 'Open Task Manager', 'Monitor running processes and performance.', 'system', 'low', [
    'task manager',
    'processes',
  ]),
  action('open_paint', 'Open Paint', 'Launch Microsoft Paint.', 'apps', 'low', ['paint', 'drawing', 'mspaint']),
  action('open_desktop', 'Open Desktop Folder', 'Open your Windows desktop folder.', 'folders', 'low', [
    'desktop folder',
    'my desktop',
  ]),
  action('open_downloads', 'Open Downloads', 'Open your Downloads folder.', 'folders', 'low', ['downloads', 'download folder']),
  action('open_documents', 'Open Documents', 'Open your Documents folder.', 'folders', 'low', ['documents', 'document folder']),
  action(
    'open_folder',
    'Open Folder',
    'Open a folder by its full path.',
    'folders',
    'medium',
    ['folder path', 'open folder at', 'open directory'],
    { argumentLabel: 'Folder path', requiresConfirmation: true }
  ),
  action('lock_workstation', 'Lock Workstation', 'Lock Windows and require your password to return.', 'system', 'high', [
    'lock computer',
    'lock pc',
    'lock screen',
    'lock windows',
    'lock workstation',
  ]),
  action('volume_up', 'Volume Up', 'Increase the system volume.', 'media', 'low', [
    'volume up',
    'louder',
    'turn it up',
    'increase volume',
  ]),
  action('volume_down', 'Volume Down', 'Decrease the system volume.', 'media', 'low', [
    'volume down',
    'quieter',
    'turn it down',
    'decrease volume',
  ]),
  action('volume_mute', 'Mute Volume', 'Mute or unmute the system audio.', 'media', 'low', [
    'mute',
    'unmute',
    'silence',
  ]),
  action('media_play_pause', 'Play / Pause Media', 'Toggle playback in the active media app.', 'media', 'low', [
    'play music',
    'pause music',
    'play pause',
    'resume music',
  ]),
  action('media_next', 'Next Track', 'Skip to the next media track.', 'media', 'low', ['next track', 'next song', 'skip song']),
  action('media_previous', 'Previous Track', 'Return to the previous media track.', 'media', 'low', [
    'previous track',
    'previous song',
    'last song',
  ]),
  action('media_stop', 'Stop Media', 'Stop playback in the active media app.', 'media', 'low', ['stop music', 'stop playback']),
  action('window_minimize', 'Minimize Window', 'Minimize the active window.', 'window', 'medium', [
    'minimize window',
    'minimize this',
  ], { requiresConfirmation: true }),
  action('window_maximize', 'Maximize Window', 'Maximize the active window.', 'window', 'medium', [
    'maximize window',
    'maximize this',
  ], { requiresConfirmation: true }),
  action('window_close', 'Close Active Window', 'Send Alt+F4 to the active window. Unsaved work may be lost.', 'window', 'high', [
    'close window',
    'close this window',
    'close active window',
  ]),
  action(
    'type_text',
    'Type Text',
    'Hide FRIDAY, type text into the active window, then return.',
    'input',
    'high',
    ['type text', 'write text', 'type this'],
    { argumentLabel: 'Text to type' }
  ),
  action(
    'search_web',
    'Search the Web',
    'Open a Google search in the default browser.',
    'web',
    'medium',
    ['search web', 'google', 'look up'],
    { argumentLabel: 'Search query', requiresConfirmation: true }
  ),
  action(
    'open_url',
    'Open URL',
    'Open a specific http or https address.',
    'web',
    'high',
    ['open url', 'open website', 'visit website'],
    { argumentLabel: 'URL' }
  ),
  action('screenshot', 'Take Screenshot', 'Capture the primary display to Pictures\\FRIDAY.', 'system', 'medium', [
    'screenshot',
    'screen capture',
    'capture screen',
  ], { requiresConfirmation: true }),
  action(
    'empty_recycle_bin',
    'Empty Recycle Bin',
    'Permanently delete everything in the Windows Recycle Bin.',
    'system',
    'high',
    ['empty recycle bin', 'clear recycle bin', 'empty trash']
  ),
];

const ACTIONS_BY_ID = new Map(AUTOMATION_ACTIONS.map((item) => [item.id, item]));

export function findAutomationAction(id: string): AutomationAction | undefined {
  return ACTIONS_BY_ID.get(id);
}

export function requiresAutomationConfirmation(
  target: AutomationAction,
  settings: FridaySettings
): boolean {
  if (target.risk === 'high') return true;
  return settings.requireConfirmation && target.requiresConfirmation;
}

export async function executeAutomation(
  actionId: string,
  argument?: string
): Promise<AutomationResult> {
  const target = findAutomationAction(actionId);
  if (!target) {
    return { success: false, action: actionId, message: 'Unknown automation action.' };
  }

  if (argument && !target.argumentLabel) {
    return {
      success: false,
      action: actionId,
      message: 'That action does not accept an argument.',
    };
  }

  if (target.argumentLabel && !argument?.trim() && target.id !== 'type_text') {
    return {
      success: false,
      action: actionId,
      message: `Please provide ${target.argumentLabel.toLowerCase()}.`,
    };
  }

  try {
    return await invokeCommand<AutomationResult>('run_automation', {
      action: actionId,
      argument: argument?.trim() || null,
    });
  } catch (error) {
    return {
      success: false,
      action: actionId,
      message: error instanceof Error ? error.message : 'The action could not be completed.',
    };
  }
}

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[’']/g, '')
    .replace(/[^a-z0-9\s:/._-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function stripWakePhrase(text: string): string {
  return text
    .replace(/^(hey|hi|hello|okay|ok|yo)\s+friday[,:\s]*/i, '')
    .replace(/^friday[,:\s]*/i, '')
    .replace(/^(please|kindly)\s+/i, '')
    .replace(/^(can|could|would)\s+you\s+/i, '')
    .replace(/^(will\s+you|i\s+want\s+you\s+to|i\s+need\s+you\s+to)\s+/i, '')
    .trim();
}

export interface AutomationIntent {
  action: AutomationAction;
  argument?: string;
}

/**
 * Deterministic natural-language router for the local FRIDAY core.
 * It only returns actions from the audited catalog above.
 */
export function detectAutomationIntent(input: string): AutomationIntent | null {
  const cleaned = stripWakePhrase(input);
  const text = normalize(cleaned);
  if (!text) return null;

  const byId = (id: string, argument?: string): AutomationIntent | null => {
    const target = findAutomationAction(id);
    return target ? { action: target, argument } : null;
  };

  if (/(empty|clear|clean)\s+(out\s+)?(the\s+)?(recycle|trash)\s*bin?/.test(text)) {
    return byId('empty_recycle_bin');
  }

  if (/(lock)\s+(the\s+)?(screen|computer|pc|workstation|windows|machine)/.test(text) || text === 'lock it') {
    return byId('lock_workstation');
  }

  if (/\b(screenshot|screen shot|screen capture|capture the screen)\b/.test(text)) {
    return byId('screenshot');
  }

  const typed = cleaned.match(/^(?:type|write|enter)\s+(?:out\s+)?(.+)$/i);
  if (typed && typed[1].trim()) {
    const argument = typed[1].trim().replace(/^["']|["']$/g, '');
    if (argument && !/^(text|this)\b/i.test(argument)) {
      return byId('type_text', argument);
    }
  }

  const urlMatch = cleaned.match(/(?:open|go to|visit)\s+(?:the\s+)?(https?:\/\/[^\s]+)/i);
  if (urlMatch) {
    return byId('open_url', urlMatch[1]);
  }

  const directUrl = cleaned.match(/^(https?:\/\/[^\s]+)$/i);
  if (directUrl) {
    return byId('open_url', directUrl[1]);
  }

  if (/(close)\s+(the\s+|this\s+|the current\s+|the active\s+)?(window|app|application)\b/.test(text)) {
    return byId('window_close');
  }

  if (/\b(minimi[sz]e)\b/.test(text)) {
    return byId('window_minimize');
  }

  if (/\b(maximi[sz]e)\b/.test(text)) {
    return byId('window_maximize');
  }

  const search = cleaned.match(
    /^(?:search(?:\s+(?:the\s+)?(?:web|google|online))?\s+for|google|look\s+up|search\s+up)\s+(.+)$/i
  );
  if (search && search[1].trim()) {
    return byId('search_web', search[1].trim().replace(/^["']|["']$/g, ''));
  }

  const folder = cleaned.match(/^open\s+(?:the\s+)?(?:folder|directory)\s+(?:at\s+)?["']?([A-Za-z]:\\[^"']+)["']?$/i);
  if (folder) {
    return byId('open_folder', folder[1].trim());
  }

  if (/(mute|unmute)\b/.test(text)) {
    return byId('volume_mute');
  }
  if (/(volume up|louder|turn it up|increase (the )?volume|raise (the )?volume)/.test(text)) {
    return byId('volume_up');
  }
  if (/(volume down|quieter|turn it down|decrease (the )?volume|lower (the )?volume)/.test(text)) {
    return byId('volume_down');
  }

  if (/(play|pause|resume)\s+(the\s+)?(music|song|media|track|playback)/.test(text) || text === 'play' || text === 'pause') {
    return byId('media_play_pause');
  }
  if (/(next|skip)\s+(the\s+)?(track|song|media)/.test(text)) {
    return byId('media_next');
  }
  if (/(previous|last)\s+(track|song|media)/.test(text)) {
    return byId('media_previous');
  }
  if (/stop\s+(the\s+)?(music|media|playback)/.test(text)) {
    return byId('media_stop');
  }

  if (/(open|launch|start|bring up)\b/.test(text)) {
    if (/\bnotepad\b/.test(text)) return byId('open_notepad');
    if (/\b(calculator|calc)\b/.test(text)) return byId('open_calculator');
    if (/\btask manager\b/.test(text)) return byId('open_task_manager');
    if (/\bpaint\b/.test(text)) return byId('open_paint');
    if (/\b(file explorer|explorer|files)\b/.test(text)) return byId('open_explorer');
    if (/\b(terminal|command prompt|cmd|console)\b/.test(text)) return byId('open_terminal');
    if (/\b(windows settings|system settings|settings app)\b/.test(text)) return byId('open_settings');
    if (/\b(browser|chrome|edge|google)\b/.test(text) && !/search/.test(text)) return byId('open_browser');
    if (/\b(downloads|download folder)\b/.test(text)) return byId('open_downloads');
    if (/\b(documents|document folder)\b/.test(text)) return byId('open_documents');
    if (/\b(desktop|desktop folder)\b/.test(text)) return byId('open_desktop');
  }

  if (/^notepad$/.test(text)) return byId('open_notepad');
  if (/^(calculator|calc)$/.test(text)) return byId('open_calculator');

  return null;
}

/** Returns a concise catalog summary used by the persona and help view. */
export function describeAutomationCatalog(): string {
  return AUTOMATION_ACTIONS.map((item) => `${item.label} (${item.risk} risk)`).join(', ');
}
