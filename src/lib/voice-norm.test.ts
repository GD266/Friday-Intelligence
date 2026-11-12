import { describe, expect, it } from 'vitest';
import {
  calculateSimilarity,
  isLikelyCommand,
  normalizeTranscript,
} from './voice-norm';

describe('speech normalization', () => {
  describe('normalizeTranscript', () => {
    it('normalizes "Open Notepad"', () => {
      const result = normalizeTranscript('Open Notepad');
      expect(result.original).toBe('Open Notepad');
      expect(result.normalized).toBe('Open Notepad');
      expect(result.corrected).toBe(false);
    });

    it('normalizes "Open net ped" to "Open Notepad"', () => {
      const result = normalizeTranscript('Open net ped');
      expect(result.original).toBe('Open net ped');
      expect(result.normalized).toBe('Open Notepad');
      expect(result.corrected).toBe(true);
    });

    it('normalizes "Open note pad" to "Open Notepad"', () => {
      const result = normalizeTranscript('Open note pad');
      expect(result.original).toBe('Open note pad');
      expect(result.normalized).toBe('Open Notepad');
      expect(result.corrected).toBe(true);
    });

    it('normalizes "Open Calculator"', () => {
      const result = normalizeTranscript('Open Calculator');
      expect(result.original).toBe('Open Calculator');
      expect(result.normalized).toBe('Open Calculator');
      expect(result.corrected).toBe(false);
    });

    it('normalizes "open calculator" (lowercase)', () => {
      const result = normalizeTranscript('open calculator');
      expect(result.normalized).toBe('Open Calculator');
    });

    it('normalizes "Open File Explorer"', () => {
      const result = normalizeTranscript('Open File Explorer');
      expect(result.original).toBe('Open File Explorer');
      expect(result.normalized).toBe('Open File Explorer');
      expect(result.corrected).toBe(false);
    });

    it('preserves unrelated sentences unchanged', () => {
      const result = normalizeTranscript('Search for Python tutorials');
      expect(result.original).toBe('Search for Python tutorials');
      expect(result.normalized).toBe('Search for Python tutorials');
      expect(result.corrected).toBe(false);
    });

    it('preserves conversation-like utterances unchanged', () => {
      const result = normalizeTranscript('Tell me a story about robots');
      expect(result.normalized).toBe('Tell me a story about robots');
      expect(result.corrected).toBe(false);
    });

    it('handles empty and whitespace-only input', () => {
      const result = normalizeTranscript('   ');
      expect(result.normalized).toBe('');
      expect(result.corrected).toBe(false);
    });

    it('trims leading/trailing whitespace', () => {
      const result = normalizeTranscript('  Open Notepad  ');
      expect(result.normalized).toBe('Open Notepad');
    });
  });

  describe('similarity calculation', () => {
    it('returns high similarity for identical strings', () => {
      const sim = calculateSimilarity('open notepad', 'open notepad');
      expect(sim).toBe(1);
    });

    it('returns high similarity for similar strings', () => {
      const sim = calculateSimilarity('open notepad', 'open notepad now');
      expect(sim).toBeGreaterThan(0.5);
    });

    it('returns low similarity for different strings', () => {
      const sim = calculateSimilarity('open notepad', 'open calculator');
      expect(sim).toBeLessThan(0.5);
    });

    it('returns 0 for empty strings', () => {
      expect(calculateSimilarity('', 'open notepad')).toBe(0);
      expect(calculateSimilarity('open notepad', '')).toBe(0);
    });

    it('returns 1 for two empty strings', () => {
      expect(calculateSimilarity('', '')).toBe(1);
    });
  });

  describe('isLikelyCommand', () => {
    it('detects simple application commands', () => {
      expect(isLikelyCommand('Open Notepad')).toBe(true);
      expect(isLikelyCommand('Open Calculator')).toBe(true);
      expect(isLikelyCommand('Open File Explorer')).toBe(true);
    });

    it('detects volume commands', () => {
      expect(isLikelyCommand('Volume up')).toBe(true);
      expect(isLikelyCommand('Mute')).toBe(true);
    });

    it('detects browser commands', () => {
      expect(isLikelyCommand('Open Chrome')).toBe(true);
      expect(isLikelyCommand('Open Browser')).toBe(true);
    });

    it('does not match non-commands', () => {
      expect(isLikelyCommand('Tell me a joke')).toBe(false);
      expect(isLikelyCommand('What is the weather?')).toBe(false);
      expect(isLikelyCommand('Search for Python tutorials')).toBe(true); // contains 'search'
    });

    it('detects document folder commands', () => {
      expect(isLikelyCommand('Open Documents')).toBe(true);
      expect(isLikelyCommand('Open Downloads')).toBe(true);
    });
  });
});