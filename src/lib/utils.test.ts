import { describe, expect, it } from 'vitest';
import { cn, formatBytes, formatDuration, generateId, sortBy, truncate } from './utils';

describe('utils', () => {
  it('merges conflicting Tailwind classes', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4');
  });

  it('formats bytes and durations', () => {
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatDuration(500)).toBe('500ms');
    expect(formatDuration(1500)).toBe('1.5s');
  });

  it('sorts numbers and strings', () => {
    expect(sortBy([3, 1, 2], (value) => value)).toEqual([1, 2, 3]);
    expect(sortBy(['beta', 'alpha'], (value) => value)).toEqual(['alpha', 'beta']);
  });

  it('generates prefixed ids and truncates text', () => {
    expect(generateId('conversation')).toMatch(/^conversation_/);
    expect(truncate('hello world', 8)).toBe('hello w…');
  });
});
