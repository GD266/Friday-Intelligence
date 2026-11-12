import type { DeveloperFile } from '@/types';

export interface GeneratedProject {
  name: string;
  title: string;
  description: string;
  files: DeveloperFile[];
  run?: string;
}

const ALLOWED_EXTENSIONS = new Set([
  'html',
  'htm',
  'css',
  'js',
  'mjs',
  'jsx',
  'ts',
  'tsx',
  'json',
  'md',
  'txt',
  'svg',
  'webmanifest',
  'csv',
  'yml',
  'yaml',
]);

function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
  return slug || 'friday-project';
}

function fallbackTitle(prompt: string): string {
  const cleaned = prompt
    .replace(/^(please\s+)?(build|create|make|code|generate|scaffold|develop|design)\s+(me\s+)?/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return 'FRIDAY Forge project';
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function normalizePath(raw: unknown): string {
  if (typeof raw !== 'string') throw new Error('A generated file is missing its path.');
  const path = raw.trim().replace(/\\/g, '/');
  if (!path || path.length > 180) throw new Error('A generated file path was empty or too long.');
  if (path.startsWith('/') || /^[a-z]:/i.test(path)) {
    throw new Error(`Generated file path must be relative: ${raw}`);
  }

  const segments = path.split('/');
  for (const segment of segments) {
    if (!segment || segment === '.' || segment === '..') {
      throw new Error(`Generated file path is not safe: ${raw}`);
    }
    if (segment.startsWith('.') || segment.includes(':')) {
      throw new Error(`Generated file path is not safe: ${raw}`);
    }
  }

  const extension = path.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    throw new Error(`Generated file type .${extension} is outside the forge allowlist.`);
  }

  return segments.join('/');
}

function candidateJson(text: string): string[] {
  const candidates: string[] = [];
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]) candidates.push(fenced[1].trim());

  const first = text.indexOf('{');
  const last = text.lastIndexOf('}');
  if (first >= 0 && last > first) candidates.push(text.slice(first, last + 1).trim());

  return [...new Set(candidates)];
}

/**
 * Accepts the strict JSON contract from the developer prompt, tolerating a
 * model that wraps it in a markdown fence or adds a short preamble.
 */
export function parseGeneratedProject(
  raw: string,
  prompt: string
): GeneratedProject {
  if (!raw.trim()) throw new Error('The engine returned an empty project.');

  let payload: unknown;
  let lastError: unknown;

  for (const candidate of candidateJson(raw)) {
    try {
      payload = JSON.parse(candidate);
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!payload || typeof payload !== 'object') {
    throw new Error(
      `The engine did not return valid project JSON. ${
        lastError instanceof Error ? lastError.message : ''
      }`.trim()
    );
  }

  const record = payload as Record<string, unknown>;
  if (!Array.isArray(record.files) || record.files.length === 0) {
    throw new Error('The generated project did not contain any files.');
  }
  if (record.files.length > 12) {
    throw new Error('The generated project exceeds the 12-file forge limit.');
  }

  const seen = new Set<string>();
  const files: DeveloperFile[] = [];
  let totalBytes = 0;

  for (const entry of record.files) {
    if (!entry || typeof entry !== 'object') continue;
    const file = entry as Record<string, unknown>;
    if (typeof file.content !== 'string' || file.content.trim().length === 0) {
      throw new Error('A generated file had no content.');
    }

    const path = normalizePath(file.path);
    const key = path.toLowerCase();
    if (seen.has(key)) {
      throw new Error(`The generated project contains a duplicate file: ${path}`);
    }
    seen.add(key);

    totalBytes += file.content.length;
    if (file.content.length > 400_000 || totalBytes > 3_000_000) {
      throw new Error('The generated project exceeds the forge size limit.');
    }

    files.push({ path, content: file.content });
  }

  if (files.length === 0) throw new Error('The generated project had no usable files.');

  let entry = files.find((file) => file.path === 'index.html');
  if (!entry) {
    const singleHtml = files.filter((file) => /\.html?$/i.test(file.path));
    if (singleHtml.length === 1) {
      singleHtml[0].path = 'index.html';
      entry = singleHtml[0];
    }
  }
  if (!entry) {
    throw new Error('The generated project is missing an index.html entry point.');
  }

  const title =
    typeof record.title === 'string' && record.title.trim()
      ? record.title.trim().slice(0, 100)
      : fallbackTitle(prompt);
  const description =
    typeof record.description === 'string' && record.description.trim()
      ? record.description.trim().slice(0, 400)
      : `A generated browser project for: ${prompt.trim()}`;

  return {
    name: slugify(typeof record.name === 'string' ? record.name : title),
    title,
    description,
    files,
    run: typeof record.run === 'string' ? record.run.trim() : undefined,
  };
}
