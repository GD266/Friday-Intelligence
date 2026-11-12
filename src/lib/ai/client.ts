import type {
  AiChatResult,
  EngineCredentialStatus,
  EngineProvider,
  FridaySettings,
  SystemSnapshot,
} from '@/types';
import { getErrorMessage, invokeCommand, isTauriRuntime } from '@/lib/runtime';
import {
  ENGINE_PROVIDERS,
  findEngineModel,
  getApiKeyForProvider,
  getFallbackModel,
  resolveEnginePlan,
  type EnginePlan,
} from './catalog';
import {
  FridayEngineError,
  summarizeAttempts,
  type ChatMessage,
  type EngineAttemptError,
} from './types';
import { buildDeveloperSystemPrompt, buildFridaySystemPrompt } from './system-prompt';

interface RawChatResponse {
  text: string;
  provider: EngineProvider;
  model: string;
  latencyMs: number;
  usage?: {
    input?: number;
    output?: number;
    total?: number;
  };
}

export interface ChatWithFridayOptions {
  settings: FridaySettings;
  messages: ChatMessage[];
  snapshot?: SystemSnapshot | null;
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
  timeoutMs?: number;
  onAttempt?: (provider: EngineProvider) => void;
}

export interface EngineTestResult {
  ok: boolean;
  provider: EngineProvider;
  model: string;
  message: string;
  latencyMs?: number;
}

function trimMessages(messages: ChatMessage[]): ChatMessage[] {
  const usable = messages
    .filter((message) => message.content.trim().length > 0)
    .slice(-20)
    .map((message) => ({
      ...message,
      content:
        message.content.length > 12_000
          ? `${message.content.slice(0, 12_000)}\n\n[truncated]`
          : message.content,
    }));

  let budget = 36_000;
  const kept: ChatMessage[] = [];
  for (let index = usable.length - 1; index >= 0; index -= 1) {
    const message = usable[index];
    if (message.content.length > budget) break;
    budget -= message.content.length;
    kept.unshift(message);
  }

  return kept;
}

function withSystemPrompt(
  messages: ChatMessage[],
  settings: FridaySettings,
  snapshot: SystemSnapshot | null | undefined,
  systemPrompt?: string
): ChatMessage[] {
  return [
    { role: 'system', content: systemPrompt ?? buildFridaySystemPrompt(settings, snapshot) },
    ...trimMessages(messages),
  ];
}

function classifyError(message: string, status?: number): EngineAttemptError['code'] {
  const normalized = message.toLowerCase();
  if (status === 401 || status === 403) return 'auth';
  if (status === 429) return 'rate-limit';
  if (status === 408 || normalized.includes('timed out') || normalized.includes('timeout')) {
    return 'timeout';
  }
  if (
    normalized.includes('no credential') ||
    normalized.includes('missing key') ||
    normalized.includes('api key') ||
    normalized.includes('unauthorized') ||
    normalized.includes('authentication')
  ) {
    return 'auth';
  }
  if (
    normalized.includes('failed to fetch') ||
    normalized.includes('network') ||
    normalized.includes('dns') ||
    normalized.includes('connection')
  ) {
    return 'network';
  }
  return 'provider';
}

function statusFromMessage(message: string): number | undefined {
  const match = message.match(/\b(?:HTTP\s*)?(400|401|403|404|408|409|422|429|500|502|503|504)\b/);
  return match ? Number(match[1]) : undefined;
}

function readContent(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const choices = (payload as { choices?: unknown }).choices;
  if (!Array.isArray(choices) || choices.length === 0) return '';

  const message = (choices[0] as { message?: { content?: unknown } }).message;
  const content = message?.content;
  if (typeof content === 'string') return content.trim();

  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part && typeof part === 'object' && 'text' in part) {
          const text = (part as { text?: unknown }).text;
          return typeof text === 'string' ? text : '';
        }
        return '';
      })
      .join('')
      .trim();
  }

  return '';
}

function readUsage(payload: unknown): RawChatResponse['usage'] {
  if (!payload || typeof payload !== 'object') return undefined;
  const usage = (payload as { usage?: Record<string, unknown> }).usage;
  if (!usage) return undefined;
  const input = typeof usage.prompt_tokens === 'number' ? usage.prompt_tokens : undefined;
  const output = typeof usage.completion_tokens === 'number' ? usage.completion_tokens : undefined;
  const total = typeof usage.total_tokens === 'number' ? usage.total_tokens : undefined;
  if (input === undefined && output === undefined && total === undefined) return undefined;
  return { input, output, total };
}

async function requestInBrowser(
  plan: EnginePlan,
  messages: ChatMessage[],
  temperature: number,
  maxTokens: number,
  timeoutMs: number
): Promise<RawChatResponse> {
  if (!plan.apiKey) {
    throw new Error(
      `No ${ENGINE_PROVIDERS[plan.provider].credentialLabel} is configured. Add one in Settings, or run FRIDAY as the desktop app to reuse OpenCode's stored credential.`
    );
  }

  const provider = ENGINE_PROVIDERS[plan.provider];
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();

  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${plan.apiKey}`,
    };
    if (plan.provider === 'openrouter') {
      headers['HTTP-Referer'] = 'https://friday.local';
      headers['X-Title'] = 'FRIDAY Intelligence';
    }

    const response = await fetch(`${provider.baseUrl}${provider.chatPath}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: plan.model.apiModel,
        messages,
        temperature,
        max_tokens: maxTokens,
        stream: false,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = (await response.text()).slice(0, 500);
      throw new Error(`HTTP ${response.status} from ${provider.shortLabel}: ${detail}`);
    }

    const payload: unknown = await response.json();
    const text = readContent(payload);
    if (!text) {
      throw new Error(`${provider.shortLabel} returned an empty response.`);
    }

    return {
      text,
      provider: plan.provider,
      model: plan.model.name,
      latencyMs: Date.now() - startedAt,
      usage: readUsage(payload),
    };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`${ENGINE_PROVIDERS[plan.provider].shortLabel} timed out after ${Math.round(timeoutMs / 1000)}s.`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timer);
  }
}

async function attemptPlan(
  plan: EnginePlan,
  messages: ChatMessage[],
  temperature: number,
  maxTokens: number,
  timeoutMs: number
): Promise<AiChatResult> {
  if (isTauriRuntime()) {
    const result = await invokeCommand<RawChatResponse>('ai_chat', {
      request: {
        provider: plan.provider,
        model: plan.model.apiModel,
        messages,
        apiKey: plan.apiKey || null,
        baseUrl: ENGINE_PROVIDERS[plan.provider].baseUrl,
        temperature,
        maxTokens,
        timeoutMs,
      },
    });

    if (!result.text?.trim()) {
      throw new Error(`${ENGINE_PROVIDERS[plan.provider].shortLabel} returned an empty response.`);
    }

    return {
      text: result.text.trim(),
      provider: result.provider,
      model: plan.model.name,
      latencyMs: result.latencyMs,
      usage: result.usage,
    };
  }

  const result = await requestInBrowser(plan, messages, temperature, maxTokens, timeoutMs);
  return {
    text: result.text,
    provider: result.provider,
    model: plan.model.name,
    latencyMs: result.latencyMs,
    usage: result.usage,
  };
}

export async function chatWithFriday(options: ChatWithFridayOptions): Promise<AiChatResult> {
  const {
    settings,
    messages,
    snapshot,
    systemPrompt,
    temperature = settings.engineTemperature,
    maxTokens = settings.engineMaxTokens,
    timeoutMs = 120_000,
    onAttempt,
  } = options;

  if (settings.demoMode) {
    throw new FridayEngineError('FRIDAY is set to local demo mode.', 'no-engine', []);
  }

  const plans = resolveEnginePlan(settings);
  if (plans.length === 0) {
    throw new FridayEngineError('No intelligence engine is configured.', 'no-engine', []);
  }

  const fullMessages = withSystemPrompt(messages, settings, snapshot, systemPrompt);
  const attempts: EngineAttemptError[] = [];

  for (const plan of plans) {
    onAttempt?.(plan.provider);
    try {
      return await attemptPlan(plan, fullMessages, temperature, maxTokens, timeoutMs);
    } catch (error) {
      const message = getErrorMessage(error);
      const status = statusFromMessage(message);
      attempts.push({
        provider: plan.provider,
        model: plan.model.name,
        message,
        status,
        code: classifyError(message, status),
      });
    }
  }

  throw new FridayEngineError(
    `Every configured engine attempt failed. ${summarizeAttempts(attempts)}`,
    'all-failed',
    attempts
  );
}

/** Tests exactly one provider, without silently falling through to another. */
export async function testEngineProvider(
  provider: EngineProvider,
  settings: FridaySettings
): Promise<EngineTestResult> {
  const model = getFallbackModel(settings.engineModel, provider);
  const apiKey = getApiKeyForProvider(provider, settings);
  const startedAt = Date.now();

  try {
    await attemptPlan(
      { provider, model, apiKey },
      [
        {
          role: 'system',
          content:
            'You are a concise connection test. Reply with exactly the word OK and nothing else.',
        },
        { role: 'user', content: 'Connection test.' },
      ],
      0,
      8,
      45_000
    );

    return {
      ok: true,
      provider,
      model: model.name,
      message: `Connected to ${model.name} in ${Date.now() - startedAt}ms.`,
      latencyMs: Date.now() - startedAt,
    };
  } catch (error) {
    return {
      ok: false,
      provider,
      model: model.name,
      message: getErrorMessage(error),
      latencyMs: Date.now() - startedAt,
    };
  }
}

export async function getCredentialStatus(
  settings: FridaySettings
): Promise<EngineCredentialStatus> {
  if (!isTauriRuntime()) {
    return {
      opencode: Boolean(settings.openCodeApiKey.trim()),
      nvidia: Boolean(settings.nvidiaApiKey.trim()),
      openrouter: Boolean(settings.openRouterApiKey.trim()),
      elevenlabs: Boolean(settings.elevenLabsApiKey.trim()),
      source: 'settings',
    };
  }

  try {
    const detected = await invokeCommand<EngineCredentialStatus>('ai_credential_status', {
      settings: {
        openCodeApiKey: settings.openCodeApiKey,
        nvidiaApiKey: settings.nvidiaApiKey,
        openRouterApiKey: settings.openRouterApiKey,
        elevenLabsApiKey: settings.elevenLabsApiKey,
      },
    });

    const merged: EngineCredentialStatus = {
      ...detected,
      opencode: detected.opencode || Boolean(settings.openCodeApiKey.trim()),
      nvidia: detected.nvidia || Boolean(settings.nvidiaApiKey.trim()),
      openrouter: detected.openrouter || Boolean(settings.openRouterApiKey.trim()),
      elevenlabs: detected.elevenlabs || Boolean(settings.elevenLabsApiKey.trim()),
    };

    if (settings.openCodeApiKey.trim() || settings.nvidiaApiKey.trim() || settings.openRouterApiKey.trim() || settings.elevenLabsApiKey.trim()) {
      merged.source = 'settings';
    }

    return merged;
  } catch {
    return {
      opencode: Boolean(settings.openCodeApiKey.trim()),
      nvidia: Boolean(settings.nvidiaApiKey.trim()),
      openrouter: Boolean(settings.openRouterApiKey.trim()),
      elevenlabs: Boolean(settings.elevenLabsApiKey.trim()),
      source: 'settings',
    };
  }
}

export function describeSelectedModel(settings: FridaySettings): string {
  const model = findEngineModel(settings.engineModel);
  if (!model) return 'Local demo core';
  return `${model.name} · ${ENGINE_PROVIDERS[model.provider].shortLabel}`;
}

export async function generateDeveloperDraft(
  prompt: string,
  settings: FridaySettings,
  snapshot?: SystemSnapshot | null
): Promise<AiChatResult> {
  return chatWithFriday({
    settings,
    messages: [{ role: 'user', content: prompt }],
    snapshot,
    systemPrompt: buildDeveloperSystemPrompt(settings),
    temperature: 0.35,
    maxTokens: 8192,
    timeoutMs: 240_000,
  });
}