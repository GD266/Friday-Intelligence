import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

/**
 * Returns true when the UI is running inside the Tauri desktop shell.
 * The Vite browser preview keeps working, but native commands are not available there.
 */
export function isTauriRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  const candidate = window as unknown as {
    __TAURI_INTERNALS__?: unknown;
    __TAURI__?: unknown;
  };
  return Boolean(candidate.__TAURI_INTERNALS__ ?? candidate.__TAURI__);
}

export function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error;
  if (error instanceof Error) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return 'An unexpected error occurred.';
}

/**
 * Invokes a Tauri command. Throws a readable error when the command fails or when
 * the app is running in a plain browser.
 */
export async function invokeCommand<T>(
  command: string,
  args?: Record<string, unknown>
): Promise<T> {
  if (!isTauriRuntime()) {
    throw new Error('This capability is only available in the FRIDAY desktop app.');
  }

  try {
    return await invoke<T>(command, args);
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}

/** Subscribes to a Tauri event. Returns null outside the Tauri runtime. */
export async function listenEvent<T>(
  event: string,
  handler: (payload: T) => void
): Promise<UnlistenFn | null> {
  if (!isTauriRuntime()) return null;

  try {
    return await listen<T>(event, (payload) => handler(payload.payload));
  } catch {
    return null;
  }
}
