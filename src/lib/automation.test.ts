import { describe, expect, it } from 'vitest';
import type { FridaySettings } from '@/types';
import {
  AUTOMATION_ACTIONS,
  detectAutomationIntent,
  findAutomationAction,
  requiresAutomationConfirmation,
} from './automation';

const settings: FridaySettings = {
  addressAs: 'sir',
  userName: '',
  voiceEnabled: true,
  autoSpeak: true,
  voiceRate: 0.94,
  voicePitch: 1,
  voiceId: null,
  soundEffects: true,
  requireConfirmation: true,
  demoMode: true,
  voiceLocale: 'en-IN',

  sttProvider: 'local',
  sttModel: 'small.en',
  groqApiKey: '',

  ttsProvider: 'edge',
  ttsVoice: 'en-IN-NeerjaExpressiveNeural',

  engineProvider: 'auto',
  engineModel: 'nemotron-3.5-lightning-free',
  openCodeApiKey: '',
  nvidiaApiKey: '',
  openRouterApiKey: '',
  engineTemperature: 0.7,
  engineMaxTokens: 4096,

  voiceProvider: 'native',
  elevenLabsApiKey: '',
  elevenLabsVoiceId: 'Rachel',
  elevenLabsModelId: 'eleven-labs-v1',
  elevenLabsStability: 0.7,
  elevenLabsSimilarity: 0.85,

  developerAutoOpen: false,
};

describe('automation catalog', () => {
  it('has unique ids and a keyword for every action', () => {
    const ids = AUTOMATION_ACTIONS.map((action) => action.id);

    expect(new Set(ids).size).toBe(ids.length);
    expect(AUTOMATION_ACTIONS.every((action) => action.keywords.length > 0)).toBe(true);
    expect(findAutomationAction('open_notepad')?.label).toBe('Open Notepad');
  });

  it('always confirms high-risk actions', () => {
    const target = findAutomationAction('empty_recycle_bin');
    expect(target).toBeDefined();
    if (!target) return;

    expect(
      requiresAutomationConfirmation(target, { ...settings, requireConfirmation: false })
    ).toBe(true);
  });

  it('applies the policy to medium-risk actions', () => {
    const target = findAutomationAction('screenshot');
    expect(target).toBeDefined();
    if (!target) return;

    expect(requiresAutomationConfirmation(target, settings)).toBe(true);
    expect(
      requiresAutomationConfirmation(target, { ...settings, requireConfirmation: false })
    ).toBe(false);
  });

  it('runs low-risk actions directly', () => {
    const target = findAutomationAction('volume_up');
    expect(target).toBeDefined();
    if (!target) return;

    expect(requiresAutomationConfirmation(target, settings)).toBe(false);
  });
});

describe('automation intent detection', () => {
  it.each([
    ['Open Notepad', 'open_notepad', undefined],
    ['Could you turn the volume up?', 'volume_up', undefined],
    ['Mute the sound', 'volume_mute', undefined],
    ['Search the web for quantum computing', 'search_web', 'quantum computing'],
    ['Type hello world', 'type_text', 'hello world'],
    ['Open https://example.com', 'open_url', 'https://example.com'],
    ['Empty the recycle bin', 'empty_recycle_bin', undefined],
    ['Take a screenshot', 'screenshot', undefined],
    ['Open Downloads', 'open_downloads', undefined],
  ])('routes "%s" to %s', (input, expectedId, expectedArgument) => {
    const intent = detectAutomationIntent(input);

    expect(intent?.action.id).toBe(expectedId);
    expect(intent?.argument).toBe(expectedArgument);
  });

  it('leaves ordinary conversation alone', () => {
    expect(detectAutomationIntent('Tell me a joke')).toBeNull();
    expect(detectAutomationIntent('Delete all my files')).toBeNull();
  });
});
