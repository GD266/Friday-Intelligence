import { describe, expect, it } from 'vitest';
import type { FridaySettings } from '@/types';
import { automationResultReply, respondToFriday } from './friday';
import { findAutomationAction } from './automation';

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

describe('FRIDAY persona', () => {
  it('greets in character and discloses the demo core', () => {
    const reply = respondToFriday('Hello', settings);

    expect(reply.source).toBe('greeting');
    expect(reply.text).toMatch(/Good (morning|afternoon|evening), sir/);
    expect(reply.text).toContain('demo core');
  });

  it('uses the configured name when requested', () => {
    const reply = respondToFriday('Good morning', {
      ...settings,
      addressAs: 'name',
      userName: 'Prana',
    });

    expect(reply.text).toContain('Prana');
  });

  it('routes low-risk desktop commands', () => {
    const reply = respondToFriday('Open Notepad', settings);

    expect(reply.actionId).toBe('open_notepad');
    expect(reply.source).toBe('command');
    expect(reply.text).toBe('Opening Notepad now, sir.');
  });

  it('always confirms high-risk commands, even when confirmation is relaxed', () => {
    const reply = respondToFriday('Empty the recycle bin', {
      ...settings,
      requireConfirmation: false,
    });

    expect(reply.actionId).toBe('empty_recycle_bin');
    expect(reply.text).toContain('Shall I proceed, sir?');
    expect(reply.text).toContain('cannot be undone');
  });

  it('follows the confirmation setting for medium-risk commands', () => {
    const confirming = respondToFriday('Take a screenshot', settings);
    const direct = respondToFriday('Take a screenshot', {
      ...settings,
      requireConfirmation: false,
    });

    expect(confirming.text).toContain('Shall I proceed');
    expect(direct.text).toContain('Capturing the primary display');
  });

  it('summarises live telemetry when available', () => {
    const reply = respondToFriday('System status', settings, {
      cpuUsage: 12.4,
      memoryUsage: 8 * 1024 ** 3,
      memoryTotal: 16 * 1024 ** 3,
      uptime: 3661,
      hostname: 'WORKSTATION',
      os: 'Windows 11',
      cpuName: 'Ryzen',
    });

    expect(reply.text).toContain('CPU load is 12%');
    expect(reply.text).toContain('memory use is 50%');
    expect(reply.text).toContain('1h 1m');
    expect(reply.text).toContain('WORKSTATION');
  });

  it('refuses to pretend it is a language model', () => {
    const reply = respondToFriday('Are you a real AI?', settings);

    expect(reply.text).toContain('demo core');
    expect(reply.text).toContain('language model');
  });

  it('falls back honestly instead of inventing an answer', () => {
    const reply = respondToFriday('Explain quantum chromodynamics', settings);

    expect(reply.source).toBe('fallback');
    expect(reply.text.toLowerCase()).toContain('demo');
  });

  it('formats automation results with the configured address', () => {
    const target = findAutomationAction('open_notepad');
    expect(target).toBeDefined();

    if (!target) return;

    expect(
      automationResultReply(target, { success: true, message: 'Notepad is opening.' }, settings)
    ).toBe('Notepad is opening, sir.');
  });
});
