/**
 * Speech normalization for dictation commands.
 * Corrects common misrecognition errors while preserving user intent.
 */

/** Application aliases for common recognition errors. */
const APP_ALIASES: Record<string, string> = {
  // Notepad variants
  'open note pad': 'Open Notepad',
  'open net pad': 'Open Notepad',
  'open net ped': 'Open Notepad',
  'open notepad': 'Open Notepad',

  // Calculator variants
  'open calc': 'Open Calculator',
  'open calculator': 'Open Calculator',

  // File Explorer variants
  'open file explorer': 'Open File Explorer',
  'open explorer': 'Open File Explorer',
  'open my computer': 'Open File Explorer',
  'open this pc': 'Open File Explorer',

  // Browser variants
  'open chrome': 'Open Chrome',
  'open edge': 'Open Edge',
  'open firefox': 'Open Firefox',
  'open safari': 'Open Safari',
  'open browser': 'Open Browser',
  'open internet': 'Open Browser',
  'open web browser': 'Open Browser',

  // Media control variations
  'volume up': 'Volume up',
  'volume down': 'Volume down',
  'mute': 'Mute',
  'un mute': 'Unmute',
  'unmute': 'Unmute',

  // Common command patterns
  'type ': 'Type ',
  'search for ': 'Search for ',
  'searching for': 'Search for ',

  // Document shortcuts
  'open documents': 'Open Documents',
  'open downloads': 'Open Downloads',
  'open desktop': 'Open Desktop',
  'open pictures': 'Open Pictures',
  'open music': 'Open Music',
  'open videos': 'Open Videos',

  // System commands
  'shutdown': 'Shutdown',
  'restart': 'Restart',
  'sleep': 'Sleep',
  'lock': 'Lock Workstation',
  'log out': 'Log out',
  'logout': 'Log out',
};

interface NormalizationResult {
  original: string;
  normalized: string;
  corrected: boolean;
}

/**
 * Normalizes a speech transcript to correct common recognition errors.
 * Only applies corrections for known patterns; otherwise returns original.
 */
export function normalizeTranscript(transcript: string): NormalizationResult {
  const trimmed = transcript.trim();
  const lowerTrimmed = trimmed.toLowerCase();

  // Check for exact matches in aliases
  for (const [alias, normalized] of Object.entries(APP_ALIASES)) {
    if (lowerTrimmed === alias || lowerTrimmed === normalized.toLowerCase()) {
      // If already in the correct format, no correction needed
      const alreadyCorrect = trimmed === normalized;
      return {
        original: trimmed,
        normalized,
        corrected: !alreadyCorrect,
      };
    }
  }

  // Check for phrase matches (transcript starts with or contains the alias)
  for (const [alias, normalized] of Object.entries(APP_ALIASES)) {
    if (lowerTrimmed.startsWith(alias + ' ')) {
      // Extract the rest of the transcript after the alias
      const rest = trimmed.slice(alias.length + 1);
      const result = normalized + (rest ? ' ' + rest : '');
      return {
        original: trimmed,
        normalized: result,
        corrected: true,
      };
    }
  }

  // No correction needed
  return {
    original: trimmed,
    normalized: trimmed,
    corrected: false,
  };
}

/**
 * Detects if a transcript appears to be a duplicate of recent transcripts.
 * This prevents accidental double-submission during push-to-talk.
 */
export function isDuplicateTranscript(
  transcript: string,
  recentTranscripts: string[],
  threshold = 0.9
): boolean {
  const normalized = transcript.trim().toLowerCase();

  for (const recent of recentTranscripts) {
    const recentNormalized = recent.trim().toLowerCase();

    // Check for exact matches
    if (normalized === recentNormalized) {
      return true;
    }

    // Check for very similar transcripts (simple edit distance check)
    const similarity = calculateSimilarity(normalized, recentNormalized);
    if (similarity > threshold) {
      return true;
    }
  }

  return false;
}

/**
 * Simple similarity calculation using Jaccard index on word sets.
 */
export function calculateSimilarity(a: string, b: string): number {
  const wordsA = new Set(a.split(/\s+/));
  const wordsB = new Set(b.split(/\s+/));

  if (wordsA.size === 0 && wordsB.size === 0) return 1;
  if (wordsA.size === 0 || wordsB.size === 0) return 0;

  let intersection = 0;
  for (const word of wordsA) {
    if (wordsB.has(word)) intersection++;
  }

  const union = wordsA.size + wordsB.size - intersection;
  return union > 0 ? intersection / union : 0;
}

/**
 * Checks if a transcript represents a potential automation command.
 * Returns true for phrases that look like commands to be corrected.
 */
export function isLikelyCommand(transcript: string): boolean {
  const lower = transcript.toLowerCase().trim();

  const commandPatterns = [
    'open',
    'close',
    'launch',
    'run',
    'type',
    'search',
    'click',
    'press',
    'take a screenshot',
    'screenshot',
    'volume',
    'mute',
    'calculator',
    'notepad',
    'explorer',
    'browser',
    'chrome',
    'edge',
    'firefox',
    'safari',
    'documents',
    'downloads',
    'desktop',
    'shutdown',
    'restart',
    'lock',
  ];

  return commandPatterns.some((pattern) => lower.startsWith(pattern) || lower.includes(pattern));
}

/**
 * Generates a human-readable message about the normalization that occurred.
 */
export function normalizationReason(original: string, normalized: string): string | null {
  if (original.toLowerCase() === normalized.toLowerCase()) {
    return null;
  }
  return `Normalized " "${original}" → "${normalized}"`;
}