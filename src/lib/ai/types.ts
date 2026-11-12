import type { EngineProvider } from '@/types';

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface EngineAttemptError {
  provider: EngineProvider;
  model: string;
  message: string;
  status?: number;
  code: 'auth' | 'rate-limit' | 'network' | 'timeout' | 'provider' | 'missing-key' | 'empty';
}

export type EngineErrorCode = 'no-engine' | 'all-failed';

export class FridayEngineError extends Error {
  readonly code: EngineErrorCode;
  readonly attempts: EngineAttemptError[];

  constructor(message: string, code: EngineErrorCode, attempts: EngineAttemptError[]) {
    super(message);
    this.name = 'FridayEngineError';
    this.code = code;
    this.attempts = attempts;
  }
}

export function isRetryableEngineError(error: EngineAttemptError): boolean {
  return (
    error.code === 'auth' ||
    error.code === 'rate-limit' ||
    error.code === 'network' ||
    error.code === 'timeout' ||
    error.code === 'missing-key'
  );
}

export function summarizeAttempts(attempts: EngineAttemptError[]): string {
  if (attempts.length === 0) return 'No intelligence engine is configured.';
  const seen = new Set<string>();
  return attempts
    .filter((attempt) => {
      const key = `${attempt.provider}:${attempt.code}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((attempt) => `${attempt.provider}: ${attempt.message}`)
    .join(' · ');
}
