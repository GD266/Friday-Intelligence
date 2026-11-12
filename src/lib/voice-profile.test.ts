import { describe, expect, it } from 'vitest';
import type { VoiceOption } from '@/types';
import {
  formatVoiceName,
  isLikelyFemaleVoice,
  pickPreferredVoice,
  scoreVoiceFit,
} from './voice-profile';

const voice = (id: string, name: string, language: string): VoiceOption => ({
  id,
  name,
  language,
});

const windowsVoices: VoiceOption[] = [
  voice('david', 'Microsoft David Desktop', 'en-US'),
  voice('mark', 'Microsoft Mark Desktop', 'en-US'),
  voice('zira', 'Microsoft Zira Desktop', 'en-US'),
  voice('hazel', 'Microsoft Hazel Desktop', 'en-GB'),
];

describe('FRIDAY voice profile', () => {
  it('identifies likely female voices from Windows voice names', () => {
    expect(isLikelyFemaleVoice(voice('hazel', 'Microsoft Hazel Desktop', 'en-GB'))).toBe(true);
    expect(isLikelyFemaleVoice(voice('sonia', 'Microsoft Sonia Online (Natural)', 'en-GB'))).toBe(true);
    expect(isLikelyFemaleVoice(voice('female', 'Female Voice', 'en-US'))).toBe(true);
    expect(isLikelyFemaleVoice(voice('david', 'Microsoft David Desktop', 'en-US'))).toBe(false);
    expect(isLikelyFemaleVoice(voice('mark', 'Microsoft Mark Desktop', 'en-US'))).toBe(false);
  });

  it('prefers the en-GB female voice over en-US female and local male voices', () => {
    expect(pickPreferredVoice(windowsVoices)?.id).toBe('hazel');
  });

  it('ranks a natural en-GB female voice above a legacy one', () => {
    const voices = [
      voice('hazel', 'Microsoft Hazel Desktop', 'en-GB'),
      voice('sonia', 'Microsoft Sonia Online (Natural)', 'en-GB'),
      voice('libby', 'Microsoft Libby Online (Natural)', 'en-GB'),
    ];

    expect(pickPreferredVoice(voices)?.id).toBe('sonia');
  });

  it('rejects an all-male pool in favour of any available female voice', () => {
    const voices = [
      voice('david', 'Microsoft David Desktop', 'en-GB'),
      voice('mark', 'Microsoft Mark Desktop', 'en-US'),
      voice('zira', 'Microsoft Zira Desktop', 'en-US'),
    ];

    expect(pickPreferredVoice(voices)?.id).toBe('zira');
  });

  it('falls back to the best available voice when no female voice exists', () => {
    const voices = [
      voice('david', 'Microsoft David Desktop', 'en-GB'),
      voice('mark', 'Microsoft Mark Desktop', 'en-US'),
    ];

    expect(pickPreferredVoice(voices)?.id).toBe('david');
  });

  it('falls back to non-English voices rather than returning nothing', () => {
    const voices = [voice('anna', 'Microsoft Anna', 'de-DE')];

    expect(pickPreferredVoice(voices)?.id).toBe('anna');
  });

  it('returns null when no voices are installed', () => {
    expect(pickPreferredVoice([])).toBeNull();
  });

  it('penalises male names in the fit score', () => {
    const david = voice('david', 'Microsoft David Desktop', 'en-GB');
    const hazel = voice('hazel', 'Microsoft Hazel Desktop', 'en-GB');

    expect(scoreVoiceFit(hazel)).toBeGreaterThan(scoreVoiceFit(david));
  });

  it('shortens verbose Windows voice names for the settings list', () => {
    expect(formatVoiceName(voice('sonia', 'Microsoft Sonia Online (Natural) - English (United Kingdom)', 'en-GB'))).toBe('Sonia');
    expect(formatVoiceName(voice('hazel', 'Microsoft Hazel Desktop', 'en-GB'))).toBe('Hazel');
    expect(formatVoiceName(voice('zira', 'Microsoft Zira Desktop', 'en-US'))).toBe('Zira');
  });
});
