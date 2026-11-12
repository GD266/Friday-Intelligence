import type { EngineModel, EngineProvider, FridaySettings } from '@/types';

export interface EngineProviderConfig {
  id: EngineProvider;
  label: string;
  shortLabel: string;
  description: string;
  baseUrl: string;
  chatPath: string;
  credentialLabel: string;
  credentialEnv: string;
  docsUrl: string;
}

export const ENGINE_PROVIDERS: Record<EngineProvider, EngineProviderConfig> = {
  opencode: {
    id: 'opencode',
    label: 'OpenCode Console',
    shortLabel: 'OpenCode',
    description:
      'Free Nemotron and frontier open models through the OpenCode gateway. Uses the credential already stored by OpenCode when available.',
    baseUrl: 'https://opencode.ai/inference/openai/v1',
    chatPath: '/chat/completions',
    credentialLabel: 'OpenCode Console key',
    credentialEnv: 'OPENCODE_API_KEY',
    docsUrl: 'https://opencode.ai/docs/zen/',
  },
  nvidia: {
    id: 'nvidia',
    label: 'NVIDIA Nemotron',
    shortLabel: 'NVIDIA',
    description:
      'Direct NVIDIA NIM access to Nemotron. FRIDAY can reuse the NVIDIA credential stored in OpenCode.',
    baseUrl: 'https://integrate.api.nvidia.com/v1',
    chatPath: '/chat/completions',
    credentialLabel: 'NVIDIA API key',
    credentialEnv: 'NVIDIA_API_KEY',
    docsUrl: 'https://build.nvidia.com/',
  },
  openrouter: {
    id: 'openrouter',
    label: 'OpenRouter Free',
    shortLabel: 'OpenRouter',
    description:
      'Zero-cost community endpoints for Nemotron, Gemma, and other open models. Availability and rate limits vary.',
    baseUrl: 'https://openrouter.ai/api/v1',
    chatPath: '/chat/completions',
    credentialLabel: 'OpenRouter key',
    credentialEnv: 'OPENROUTER_API_KEY',
    docsUrl: 'https://openrouter.ai/models?max_price=0',
  },
  groq: {
    id: 'groq',
    label: 'Groq Cloud',
    shortLabel: 'Groq',
    description:
      'Ultra-fast inference for open models including Whisper. Free tier available for speech-to-text.',
    baseUrl: 'https://api.groq.com/openai/v1',
    chatPath: '/chat/completions',
    credentialLabel: 'Groq API key',
    credentialEnv: 'GROQ_API_KEY',
    docsUrl: 'https://console.groq.com/docs/models',
  },
};

const OPENCODE_MODELS: EngineModel[] = [
  {
    id: 'opencode/nemotron-3.5-lightning-free',
    apiModel: 'nemotron-3.5-lightning-free',
    provider: 'opencode',
    name: 'Nemotron 3.5 Lightning',
    family: 'nemotron-lightning',
    description: 'FRIDAY’s default. Fast, capable reasoning with a zero-cost OpenCode endpoint.',
    contextWindow: 131_072,
    speed: 'fast',
    free: true,
    recommended: true,
  },
  {
    id: 'opencode/nemotron-3-ultra-free',
    apiModel: 'nemotron-3-ultra-free',
    provider: 'opencode',
    name: 'Nemotron 3 Ultra',
    family: 'nemotron-ultra',
    description: 'The deepest Nemotron tier for architecture, debugging, and long-form code.',
    contextWindow: 131_072,
    speed: 'deep',
    free: true,
  },
  {
    id: 'opencode/nemotron-3.5-super-vl-free',
    apiModel: 'nemotron-3.5-super-vl-free',
    provider: 'opencode',
    name: 'Nemotron 3.5 Super VL',
    family: 'nemotron-vision',
    description: 'Vision-language Nemotron for screenshots, diagrams, and interface review.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
    vision: true,
  },
  {
    id: 'opencode/deepseek-v4.1-flash-free',
    apiModel: 'deepseek-v4.1-flash-free',
    provider: 'opencode',
    name: 'DeepSeek V4.1 Flash',
    family: 'deepseek',
    description: 'Strong coding and tool use with low latency.',
    contextWindow: 163_840,
    speed: 'fast',
    free: true,
  },
  {
    id: 'opencode/glm-5.3-flash-free',
    apiModel: 'glm-5.3-flash-free',
    provider: 'opencode',
    name: 'GLM 5.3 Flash',
    family: 'glm',
    description: 'Fast general-purpose model with solid code generation.',
    contextWindow: 131_072,
    speed: 'fast',
    free: true,
  },
  {
    id: 'opencode/minimax-m3.1-flash-free',
    apiModel: 'minimax-m3.1-flash-free',
    provider: 'opencode',
    name: 'MiniMax M3.1 Flash',
    family: 'minimax',
    description: 'Quick creative and conversational model.',
    contextWindow: 131_072,
    speed: 'fast',
    free: true,
  },
  {
    id: 'opencode/mimo-v2.6-flash-free',
    apiModel: 'mimo-v2.6-flash-free',
    provider: 'opencode',
    name: 'MiMo V2.6 Flash',
    family: 'mimo',
    description: 'Lightweight reasoning model for short directives.',
    contextWindow: 65_536,
    speed: 'fast',
    free: true,
  },
  {
    id: 'opencode/flint-40b-free',
    apiModel: 'flint-40b-free',
    provider: 'opencode',
    name: 'Flint 40B',
    family: 'flint',
    description: 'Open 40B model with a balanced speed/quality profile.',
    contextWindow: 65_536,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'opencode/beam-free',
    apiModel: 'beam-free',
    provider: 'opencode',
    name: 'Beam',
    family: 'beam',
    description: 'General-purpose no-cost model with 30-day safety retention.',
    contextWindow: 65_536,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'opencode/iceman-free',
    apiModel: 'iceman-free',
    provider: 'opencode',
    name: 'Iceman',
    family: 'iceman',
    description: 'Stealth OpenCode model. Fast conversational fallback.',
    contextWindow: 65_536,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'opencode/big-pickle',
    apiModel: 'big-pickle',
    provider: 'opencode',
    name: 'Big Pickle',
    family: 'big-pickle',
    description: 'Stealth coding model. Good for larger code edits.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'opencode/longcat-2.5-free',
    apiModel: 'longcat-2.5-free',
    provider: 'opencode',
    name: 'LongCat 2.5',
    family: 'longcat',
    description: 'Long-context model, limited to 100 requests per day.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'opencode/inkling-2-small-free',
    apiModel: 'inkling-2-small-free',
    provider: 'opencode',
    name: 'Inkling 2 Small',
    family: 'inkling',
    description: 'Small research model. Availability varies by region.',
    contextWindow: 32_768,
    speed: 'fast',
    free: true,
  },
];

const NVIDIA_MODELS: EngineModel[] = [
  {
    id: 'nvidia/nemotron-3.5-lightning-30b-a3b',
    apiModel: 'nvidia/nemotron-3.5-lightning-30b-a3b',
    provider: 'nvidia',
    name: 'Nemotron 3.5 Lightning',
    family: 'nemotron-lightning',
    description: 'Direct NVIDIA endpoint for FRIDAY’s default model.',
    contextWindow: 131_072,
    speed: 'fast',
    free: true,
    recommended: true,
  },
  {
    id: 'nvidia/nemotron-3-ultra-550b-a55b',
    apiModel: 'nvidia/nemotron-3-ultra-550b-a55b',
    provider: 'nvidia',
    name: 'Nemotron 3 Ultra',
    family: 'nemotron-ultra',
    description: 'Deep NVIDIA reasoning for demanding builds.',
    contextWindow: 131_072,
    speed: 'deep',
    free: true,
  },
  {
    id: 'nvidia/nemotron-3.5-super-vl-120b-a12b',
    apiModel: 'nvidia/nemotron-3.5-super-vl-120b-a12b',
    provider: 'nvidia',
    name: 'Nemotron 3.5 Super VL',
    family: 'nemotron-vision',
    description: 'NVIDIA vision-language model.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
    vision: true,
  },
  {
    id: 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
    apiModel: 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
    provider: 'nvidia',
    name: 'Nemotron 3 Nano Omni',
    family: 'nemotron-nano',
    description: 'Compact reasoning model for quick directives.',
    contextWindow: 65_536,
    speed: 'fast',
    free: true,
  },
  {
    id: 'nvidia/nemotron-3.5-bolt-e4b',
    apiModel: 'nvidia/nemotron-3.5-bolt-e4b',
    provider: 'nvidia',
    name: 'Nemotron 3.5 Bolt',
    family: 'nemotron-bolt',
    description: 'Very small, very fast Nemotron.',
    contextWindow: 32_768,
    speed: 'fast',
    free: true,
  },
];

const OPENROUTER_MODELS: EngineModel[] = [
  {
    id: 'openrouter/nvidia/nemotron-3.5-lightning:free',
    apiModel: 'nvidia/nemotron-3.5-lightning:free',
    provider: 'openrouter',
    name: 'Nemotron 3.5 Lightning',
    family: 'nemotron-lightning',
    description: 'Zero-cost Nemotron through OpenRouter.',
    contextWindow: 131_072,
    speed: 'fast',
    free: true,
    recommended: true,
  },
  {
    id: 'openrouter/nvidia/nemotron-3.5-super-vl:free',
    apiModel: 'nvidia/nemotron-3.5-super-vl:free',
    provider: 'openrouter',
    name: 'Nemotron 3.5 Super VL',
    family: 'nemotron-vision',
    description: 'Vision-language Nemotron free tier.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
    vision: true,
  },
  {
    id: 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free',
    apiModel: 'nvidia/nemotron-3-ultra-550b-a55b:free',
    provider: 'openrouter',
    name: 'Nemotron 3 Ultra',
    family: 'nemotron-ultra',
    description: 'Deep Nemotron reasoning through OpenRouter.',
    contextWindow: 131_072,
    speed: 'deep',
    free: true,
  },
  {
    id: 'openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free',
    apiModel: 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free',
    provider: 'openrouter',
    name: 'Nemotron 3 Nano Omni',
    family: 'nemotron-nano',
    description: 'Compact free reasoning model.',
    contextWindow: 65_536,
    speed: 'fast',
    free: true,
  },
  {
    id: 'openrouter/google/gemma-4-31b-it:free',
    apiModel: 'google/gemma-4-31b-it:free',
    provider: 'openrouter',
    name: 'Gemma 4 31B',
    family: 'gemma',
    description: 'Google open model, strong general reasoning.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'openrouter/google/gemma-4-26b-a4b-it:free',
    apiModel: 'google/gemma-4-26b-a4b-it:free',
    provider: 'openrouter',
    name: 'Gemma 4 26B A4B',
    family: 'gemma',
    description: 'Faster Gemma variant for everyday chat.',
    contextWindow: 131_072,
    speed: 'fast',
    free: true,
  },
  {
    id: 'openrouter/thinkingmachines/inkling-2-small:free',
    apiModel: 'thinkingmachines/inkling-2-small:free',
    provider: 'openrouter',
    name: 'Inkling 2 Small',
    family: 'inkling',
    description: 'Small research model on the free tier.',
    contextWindow: 32_768,
    speed: 'fast',
    free: true,
  },
  {
    id: 'openrouter/cohere/north-mini-code:free',
    apiModel: 'cohere/north-mini-code:free',
    provider: 'openrouter',
    name: 'North Mini Code',
    family: 'north-code',
    description: 'Code-focused free model from Cohere.',
    contextWindow: 131_072,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'openrouter/baidu/ernie-5.5-flash-preview:free',
    apiModel: 'baidu/ernie-5.5-flash-preview:free',
    provider: 'openrouter',
    name: 'ERNIE 5.5 Flash',
    family: 'ernie',
    description: 'Fast multilingual free model.',
    contextWindow: 65_536,
    speed: 'fast',
    free: true,
  },
  {
    id: 'openrouter/dots-studio/dots-3-note-preview:free',
    apiModel: 'dots-studio/dots-3-note-preview:free',
    provider: 'openrouter',
    name: 'Dots 3 Note',
    family: 'dots',
    description: 'Free preview model for concise analysis.',
    contextWindow: 65_536,
    speed: 'balanced',
    free: true,
  },
  {
    id: 'openrouter/liquid/lfm-3-1.7b:free',
    apiModel: 'liquid/lfm-3-1.7b:free',
    provider: 'openrouter',
    name: 'Liquid LFM 3',
    family: 'liquid',
    description: 'Tiny, quick model for simple commands.',
    contextWindow: 32_768,
    speed: 'fast',
    free: true,
  },
  {
    id: 'openrouter/recursive/flint-v1.0:free',
    apiModel: 'recursive/flint-v1.0:free',
    provider: 'openrouter',
    name: 'Flint v1',
    family: 'flint',
    description: 'Free open model with a balanced profile.',
    contextWindow: 65_536,
    speed: 'balanced',
    free: true,
  },
];

export const ENGINE_MODELS: EngineModel[] = [
  ...OPENCODE_MODELS,
  ...NVIDIA_MODELS,
  ...OPENROUTER_MODELS,
];

export const DEFAULT_ENGINE_MODEL = 'opencode/nemotron-3.5-lightning-free';

export function providerFromModelId(modelId: string): EngineProvider | null {
  const provider = modelId.split('/')[0];
  return provider === 'opencode' || provider === 'nvidia' || provider === 'openrouter'
    ? provider
    : null;
}

export function getModelsForProvider(provider: EngineProvider): EngineModel[] {
  return ENGINE_MODELS.filter((model) => model.provider === provider);
}

export function findEngineModel(modelId: string): EngineModel | null {
  return ENGINE_MODELS.find((model) => model.id === modelId) ?? null;
}

export function getRecommendedModel(provider: EngineProvider): EngineModel {
  return (
    getModelsForProvider(provider).find((model) => model.recommended) ??
    getModelsForProvider(provider)[0]
  );
}

/**
 * Picks the equivalent model on another provider. If the user selected a
 * specialised model, keep its family; otherwise fall back to that provider's
 * recommended free model.
 */
export function getFallbackModel(selectedModelId: string, provider: EngineProvider): EngineModel {
  const selected = findEngineModel(selectedModelId);
  if (selected?.provider === provider) return selected;

  if (selected) {
    const sameFamily = getModelsForProvider(provider).find(
      (model) => model.family === selected.family
    );
    if (sameFamily) return sameFamily;
  }

  return getRecommendedModel(provider);
}

export function getApiKeyForProvider(
  provider: EngineProvider,
  settings: FridaySettings
): string {
  switch (provider) {
    case 'opencode':
      return settings.openCodeApiKey.trim();
    case 'nvidia':
      return settings.nvidiaApiKey.trim();
    case 'openrouter':
      return settings.openRouterApiKey.trim();
    default:
      return '';
  }
}

export interface EnginePlan {
  provider: EngineProvider;
  model: EngineModel;
  apiKey: string;
}

export function resolveEnginePlan(settings: FridaySettings): EnginePlan[] {
  const selectedProvider = providerFromModelId(settings.engineModel);
  const providers: EngineProvider[] =
    settings.engineProvider === 'auto'
      ? [
          selectedProvider ?? 'opencode',
          ...(['opencode', 'nvidia', 'openrouter'] as EngineProvider[]).filter(
            (provider) => provider !== (selectedProvider ?? 'opencode')
          ),
        ]
      : [settings.engineProvider];

  return providers.map((provider) => ({
    provider,
    model: getFallbackModel(settings.engineModel, provider),
    apiKey: getApiKeyForProvider(provider, settings),
  }));
}
