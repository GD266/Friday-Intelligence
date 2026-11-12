import '@testing-library/jest-dom/vitest';

// Node 26 exposes a disabled localStorage global that can shadow jsdom's
// implementation. Provide a deterministic in-memory storage for tests.
class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

if (typeof window !== 'undefined' && !window.localStorage) {
  const storage = new MemoryStorage();

  try {
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
  } catch {
    // The test environment may expose a non-configurable global.
  }

  try {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  } catch {
    // The test environment may expose a non-configurable global.
  }

  // Mock matchMedia for reduced-motion queries in CoreScene tests
  try {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: (query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: () => {}, // deprecated
        removeListener: () => {}, // deprecated
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  } catch {
    // Already defined or non-configurable
  }
}
