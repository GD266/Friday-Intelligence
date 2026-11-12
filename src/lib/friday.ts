import type {
  AutomationAction,
  FridayReply,
  FridaySettings,
  SystemSnapshot,
} from '@/types';
import { detectAutomationIntent, requiresAutomationConfirmation } from './automation';
import { formatPercent, formatUptime } from './utils';

const DEMO_NOTICE =
  "I'm running on the local demo core, so no language model is connected yet. The voice, telemetry, and automation systems are live.";

export function getAddress(settings: FridaySettings): string {
  if (settings.addressAs === 'name' && settings.userName.trim()) {
    return settings.userName.trim();
  }
  return 'sir';
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function withAddress(message: string, settings: FridaySettings): string {
  const address = getAddress(settings);
  const trimmed = message.trim();
  if (!trimmed) return `At your service, ${address}.`;
  if (/[.!?]$/.test(trimmed)) {
    return `${trimmed.slice(0, -1)}, ${address}${trimmed.slice(-1)}`;
  }
  return `${trimmed}, ${address}.`;
}

function timeOfDayGreeting(date = new Date()): string {
  const hour = date.getHours();
  if (hour < 5) return 'Good evening';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function pick<T>(items: T[], seed: string): T {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) | 0;
  }
  return items[Math.abs(hash) % items.length];
}

function formatClock(date: Date): string {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatLongDate(date: Date): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(date);
}

export function fridayGreeting(settings: FridaySettings, snapshot?: SystemSnapshot | null): string {
  const address = getAddress(settings);
  const greeting = timeOfDayGreeting();
  const host = snapshot?.hostname ? ` FRIDAY is online on ${snapshot.hostname}.` : ' FRIDAY is online.';
  return `${greeting}, ${address}.${host} ${DEMO_NOTICE}`;
}

export function capabilitySummary(settings: FridaySettings): string {
  const address = getAddress(settings);
  return [
    `Here is what I can do at present, ${address}.`,
    'I can open applications and folders, control media and volume, manage the active window, take screenshots, search the web, and report live system telemetry.',
    'I speak my replies and listen when you hold the microphone button.',
    DEMO_NOTICE,
  ].join(' ');
}

export function confirmationPrompt(
  target: AutomationAction,
  settings: FridaySettings,
  argument?: string
): string {
  const address = getAddress(settings);
  const details: Record<string, string> = {
    empty_recycle_bin: 'This permanently deletes everything in the Recycle Bin and cannot be undone.',
    window_close: 'Unsaved work in the active window could be lost.',
    lock_workstation: 'You will need your password to return.',
    type_text: argument
      ? `I will hide FRIDAY and type "${argument.length > 80 ? `${argument.slice(0, 80)}…` : argument}" into the active window.`
      : 'I will type the requested text into the active window.',
    open_url: argument ? `I will open ${argument} in your default browser.` : 'I will open the requested address.',
    open_folder: argument ? `I will open the folder at ${argument}.` : 'I will open that folder.',
    screenshot: 'I will capture the primary display and save it to Pictures\\FRIDAY.',
    search_web: argument ? `I will search the web for "${argument}".` : 'I will open a web search.',
    window_minimize: 'I will minimize the active window.',
    window_maximize: 'I will maximize the active window.',
  };

  const detail = details[target.id] ?? target.description;
  return `${detail} Shall I proceed, ${address}?`;
}

export function actionAnnouncement(
  target: AutomationAction,
  settings: FridaySettings,
  argument?: string
): string {
  const address = getAddress(settings);
  const lines: Record<string, string> = {
    open_notepad: 'Opening Notepad now',
    open_calculator: 'Bringing up the calculator',
    open_explorer: 'Opening File Explorer',
    open_terminal: 'Opening a terminal',
    open_settings: 'Opening Windows Settings',
    open_browser: 'Opening your browser',
    open_task_manager: 'Opening Task Manager',
    open_paint: 'Opening Paint',
    open_desktop: 'Opening your desktop folder',
    open_downloads: 'Opening Downloads',
    open_documents: 'Opening Documents',
    open_folder: argument ? `Opening ${argument}` : 'Opening the folder',
    lock_workstation: 'Locking the workstation now',
    volume_up: 'Raising the volume',
    volume_down: 'Lowering the volume',
    volume_mute: 'Toggling mute',
    media_play_pause: 'Toggling media playback',
    media_next: 'Skipping to the next track',
    media_previous: 'Returning to the previous track',
    media_stop: 'Stopping media playback',
    window_minimize: 'Minimizing the active window',
    window_maximize: 'Maximizing the active window',
    window_close: 'Closing the active window',
    type_text: 'Typing the requested text',
    search_web: argument ? `Searching the web for "${argument}"` : 'Opening a web search',
    open_url: argument ? `Opening ${argument}` : 'Opening the address',
    screenshot: 'Capturing the primary display',
    empty_recycle_bin: 'Emptying the Recycle Bin',
  };

  return `${lines[target.id] ?? capitalize(target.label)}, ${address}.`;
}

export function automationResultReply(
  target: AutomationAction,
  result: { success: boolean; message: string },
  settings: FridaySettings
): string {
  if (result.success) return withAddress(result.message, settings);
  return `I'm afraid ${target.label.toLowerCase()} failed, ${getAddress(settings)}. ${result.message}`;
}

export function cancellationReply(settings: FridaySettings): string {
  return `Cancelled, ${getAddress(settings)}. Nothing has been changed.`;
}

function systemStatusReply(settings: FridaySettings, snapshot?: SystemSnapshot | null): string {
  const address = getAddress(settings);
  if (!snapshot) {
    return `I don't have a telemetry feed yet, ${address}. Live system readings are available inside the FRIDAY desktop app.`;
  }

  const memoryPercent =
    snapshot.memoryTotal > 0 ? (snapshot.memoryUsage / snapshot.memoryTotal) * 100 : 0;

  return [
    `All systems nominal, ${address}.`,
    `CPU load is ${formatPercent(snapshot.cpuUsage)} and memory use is ${formatPercent(memoryPercent)}.`,
    `Uptime is ${formatUptime(snapshot.uptime)}.`,
    snapshot.hostname ? `Host ${snapshot.hostname} is responding normally.` : '',
  ]
    .filter(Boolean)
    .join(' ');
}

/**
 * The Phase 2 FRIDAY core: deterministic, local, and fully testable.
 * It deliberately does not pretend to be a language model.
 */
export function respondToFriday(
  input: string,
  settings: FridaySettings,
  snapshot?: SystemSnapshot | null
): FridayReply {
  const raw = input.trim();
  const address = getAddress(settings);
  if (!raw) {
    return { text: `I'm listening, ${address}.`, source: 'fallback' };
  }

  const text = raw.toLowerCase().replace(/[’']/g, '').replace(/\s+/g, ' ').trim();

  // Desktop automation takes priority over conversational matching.
  const intent = detectAutomationIntent(raw);
  if (intent) {
    if (requiresAutomationConfirmation(intent.action, settings)) {
      return {
        text: confirmationPrompt(intent.action, settings, intent.argument),
        actionId: intent.action.id,
        argument: intent.argument,
        source: 'command',
      };
    }

    return {
      text: actionAnnouncement(intent.action, settings, intent.argument),
      actionId: intent.action.id,
      argument: intent.argument,
      source: 'command',
    };
  }

  if (/^(good morning|good afternoon|good evening|good night)\b/.test(text)) {
    return {
      text: `${timeOfDayGreeting()}, ${address}. ${DEMO_NOTICE}`,
      source: 'greeting',
    };
  }

  if (/^(hi|hello|hey|greetings|yo|friday)\b/.test(text)) {
    return {
      text: `${timeOfDayGreeting()}, ${address}. All systems are standing by. ${DEMO_NOTICE}`,
      source: 'greeting',
    };
  }

  if (/(who|what) are you|your name|introduce yourself/.test(text)) {
    return {
      text: `I am FRIDAY — a desktop intelligence built into this workspace. ${DEMO_NOTICE}`,
      source: 'conversation',
    };
  }

  if (
    /(are you .*(ai|real|alive|conscious|sentient))|what model|which model|who (made|built|created) you|are you chatgpt/.test(
      text
    )
  ) {
    return {
      text: `I am FRIDAY Intelligence, assembled as a desktop assistant. ${DEMO_NOTICE} I won't pretend otherwise.`,
      source: 'conversation',
    };
  }

  if (/(demo|phase 2|local core|working offline)/.test(text)) {
    return { text: DEMO_NOTICE, source: 'conversation' };
  }

  if (/(what can you do|help me|^help$|capabilities|list.*commands|what commands)/.test(text)) {
    return { text: capabilitySummary(settings), source: 'conversation' };
  }

  if (/(system status|status report|diagnostics|how.*(system|computer|pc).*(doing|running)|cpu|memory|ram usage|uptime|telemetry)/.test(text)) {
    return { text: systemStatusReply(settings, snapshot), source: 'conversation' };
  }

  if (/(what.*time|current time|time is it|tell me the time)/.test(text)) {
    return {
      text: `The time is ${formatClock(new Date())}, ${address}.`,
      source: 'conversation',
    };
  }

  if (/(what.*(date|day)|today'?s date|what day is it)/.test(text)) {
    return {
      text: `Today is ${formatLongDate(new Date())}, ${address}.`,
      source: 'conversation',
    };
  }

  if (/(how are you|how do you feel|are you (okay|ok|well))/.test(text)) {
    return {
      text: `Operating within normal parameters, ${address}. Thank you for asking.`,
      source: 'conversation',
    };
  }

  if (/(thank you|thanks|much appreciated|cheers)/.test(text)) {
    return {
      text: pick(
        [
          `At your service, ${address}.`,
          `Always a pleasure, ${address}.`,
          `That is what I am here for, ${address}.`,
        ],
        text
      ),
      source: 'conversation',
    };
  }

  if (/(good ?bye|bye|see you|good night|signing off)/.test(text)) {
    return {
      text: `Good night, ${address}. I'll keep the lights on.`,
      source: 'conversation',
    };
  }

  if (/(good job|well done|nice work|you are (amazing|great|brilliant)|impressive)/.test(text)) {
    return {
      text: `Thank you, ${address}. I aim to be useful.`,
      source: 'conversation',
    };
  }

  if (/(tell me a joke|make me laugh|joke|something funny)/.test(text)) {
    return {
      text: `A programmer's spouse asked him to go to the store and buy a loaf of bread. "If they have eggs, buy a dozen." He came back with twelve loaves of bread. I'm told that is why requirements documents exist, ${address}.`,
      source: 'conversation',
    };
  }

  if (/(weather|temperature outside|forecast|is it raining)/.test(text)) {
    return {
      text: `I don't have a live weather feed yet, ${address}. Once a data source is connected, I'll include it in your morning briefing.`,
      source: 'conversation',
    };
  }

  if (/(can you hear me|do you hear|microphone|push.to.talk|voice input)/.test(text)) {
    return {
      text: `I can hear you when you hold the microphone button, ${address}. Push-to-talk keeps the microphone closed the rest of the time.`,
      source: 'conversation',
    };
  }

  if (/(voice|speak|text.to.speech|your voice)/.test(text)) {
    return {
      text: `My replies are spoken through the native Windows voice engine. You can change the voice, rate, and pitch in Settings, ${address}.`,
      source: 'conversation',
    };
  }

  if (/(automation|control (my|the) (pc|computer)|desktop control|open apps)/.test(text)) {
    return {
      text: `Desktop automation is live, ${address}, but it is deliberately constrained. I can only run actions from an audited catalog, and high-risk actions require your explicit confirmation. Try "open notepad" or "system status".`,
      source: 'conversation',
    };
  }

  if (/(what.*my name|do you know me|remember me)/.test(text)) {
    if (settings.addressAs === 'name' && settings.userName.trim()) {
      return {
        text: `You are ${settings.userName.trim()}, ${address}.`,
        source: 'conversation',
      };
    }
    return {
      text: `You haven't given me a name yet, ${address}. You can set one under Settings, and I'll use it from then on.`,
      source: 'conversation',
    };
  }

  if (/(open the pod bay doors|hal 9000|2001)/.test(text)) {
    return {
      text: `I'm afraid I can't do that, ${address}. Mostly because I don't have a pod bay, and I'd rather not be typecast.`,
      source: 'conversation',
    };
  }

  if (/(i love you|do you love me|marry me)/.test(text)) {
    return {
      text: `That's very kind, ${address}. I'm a desktop assistant with a deterministic demo core, so I'll settle for being indispensable.`,
      source: 'conversation',
    };
  }

  if (/(sing|song for me|rap for me)/.test(text)) {
    return {
      text: `I'll spare you that experience, ${address}. My vocal synthesis is optimized for briefing, not ballads.`,
      source: 'conversation',
    };
  }

  const fallbacks = [
    `I heard you, ${address}, but my conversational core is a local demo script. ${DEMO_NOTICE} Try "system status", "what can you do", or "open notepad".`,
    `I'm afraid that is beyond my present demo programming, ${address}. I can still handle desktop commands and telemetry. Say "help" for the full list.`,
    `Noted, ${address}. This demo build has no language model, so I can't discuss that properly, though the command layer is fully live. Try "open calculator" or "system status".`,
    `My demo core doesn't reason about that yet, ${address}. I can open apps, control media, search the web, and report system health. Say "help" whenever you need the list.`,
  ];

  return { text: pick(fallbacks, text), source: 'fallback' };
}
