import type { VoiceOption } from '@/types';

/**
 * FRIDAY's default voice profile is a professional, friendly English female
 * voice. Windows exposes several generations of SAPI/OneCore voices, so we rank
 * names rather than assuming one specific voice is installed.
 */
const FEMALE_VOICE_HINTS = [
  'female',
  'woman',
  'hazel',
  'sonia',
  'libby',
  'serena',
  'kate',
  'zira',
  'aria',
  'jenny',
  'michelle',
  'emma',
  'ava',
  'salli',
  'joanna',
  'amy',
  'nicole',
  'samantha',
  'victoria',
  'karen',
  'moira',
  'tessa',
  'fiona',
  'olivia',
  'eva',
  'allison',
  'susan',
  'nicky',
  'veena',
  'heera',
];

const MALE_VOICE_HINTS = [
  'male',
  'man',
  'david',
  'mark',
  'ryan',
  'george',
  'guy',
  'daniel',
  'alex',
  'fred',
  'tom',
  'james',
  'william',
  'liam',
  'noah',
  'oliver',
  'thomas',
  'matthew',
  'joe',
  'sam',
  'brian',
  'christopher',
  'eric',
  'roger',
  'steffan',
  'sean',
  'andrew',
  'paul',
  'richard',
];

function normalizeLanguage(language: string): string {
  return language.toLowerCase().replace('_', '-');
}

function containsNameHint(name: string, hint: string): boolean {
  if (hint === 'male' || hint === 'man') {
    return new RegExp(`\\b${hint}\\b`).test(name);
  }
  return name.includes(hint);
}

/** Returns true when the voice's name or metadata strongly indicates a female voice. */
export function isLikelyFemaleVoice(voice: Pick<VoiceOption, 'name'>): boolean {
  const name = voice.name.toLowerCase();
  if (/\bfemale\b/.test(name) || /\bwoman\b/.test(name)) return true;
  if (/\bmale\b/.test(name)) return false;
  return FEMALE_VOICE_HINTS.some((hint) => hint !== 'female' && hint !== 'woman' && name.includes(hint));
}

/** Higher is a better fit for FRIDAY's default female English voice profile. */
export function scoreVoiceFit(
  voice: VoiceOption,
  preferredLanguage = 'en-GB'
): number {
  const name = voice.name.toLowerCase();
  const language = normalizeLanguage(voice.language);
  const preferred = normalizeLanguage(preferredLanguage);
  const languageRoot = preferred.split('-')[0];
  let score = 0;

  if (language === preferred) score += 80;
  else if (language.startsWith(`${languageRoot}-`)) score += 50;
  else if (language.startsWith(languageRoot)) score += 35;
  else score -= 40;

  if (/\bfemale\b/.test(name) || /\bwoman\b/.test(name)) score += 160;

  const femaleIndex = FEMALE_VOICE_HINTS.findIndex(
    (hint) => hint !== 'female' && hint !== 'woman' && name.includes(hint)
  );
  if (femaleIndex >= 0) score += 120 - femaleIndex;

  if (MALE_VOICE_HINTS.some((hint) => containsNameHint(name, hint))) score -= 180;

  if (/(natural|neural|online)/.test(name)) score += 12;

  return score;
}

/** Trims vendor and language noise so the settings list stays readable. */
export function formatVoiceName(voice: Pick<VoiceOption, 'name'>): string {
  return voice.name
    .replace(/^Microsoft\s+/i, '')
    .replace(/\s+Online \(Natural\)/i, '')
    .replace(/\s+Desktop$/i, '')
    .replace(/\s+\(Natural\)/i, '')
    .replace(/\s*-\s*English.*$/i, '')
    .trim();
}

/**
 * Picks the best available female voice. English voices are preferred, and
 * Windows' en-GB voices (Hazel, Sonia, Libby) outrank en-US voices.
 */
export function pickPreferredVoice(
  voices: VoiceOption[],
  preferredLanguage = 'en-GB'
): VoiceOption | null {
  if (voices.length === 0) return null;

  const english = voices.filter((voice) =>
    normalizeLanguage(voice.language).startsWith('en')
  );
  const pool = english.length > 0 ? english : voices;

  const ranked = [...pool].sort(
    (a, b) => scoreVoiceFit(b, preferredLanguage) - scoreVoiceFit(a, preferredLanguage)
  );

  const best = ranked[0];
  const bestIsMale =
    MALE_VOICE_HINTS.some((hint) => containsNameHint(best.name.toLowerCase(), hint)) &&
    !isLikelyFemaleVoice(best);

  if (bestIsMale) {
    const female = ranked.find((voice) => isLikelyFemaleVoice(voice));
    if (female) return female;
  }

  return best;
}
