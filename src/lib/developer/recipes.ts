import type { DeveloperFile } from '@/types';
import flappyTemplate from './templates/flappy.html?raw';
import landingTemplate from './templates/landing.html?raw';
import portfolioTemplate from './templates/portfolio.html?raw';
import snakeTemplate from './templates/snake.html?raw';

export type RecipeKind = 'flappy' | 'snake' | 'landing' | 'portfolio';

export interface LocalRecipeDraft {
  kind: RecipeKind;
  name: string;
  title: string;
  description: string;
  files: DeveloperFile[];
  run: string;
}

export function detectRecipeKind(prompt: string): RecipeKind {
  const text = prompt.toLowerCase();
  if (/\b(flappy|flap|bird)\b/.test(text)) return 'flappy';
  if (/\b(snake|serpent)\b/.test(text)) return 'snake';
  if (/\b(portfolio|personal site|personal website|resume|cv site|designer site|photographer)\b/.test(text)) {
    return 'portfolio';
  }
  if (/\b(game|arcade|pong|breakout|tetris|platformer|endless runner)\b/.test(text)) return 'flappy';
  return 'landing';
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function cleanBrief(prompt: string): string {
  return prompt
    .replace(/^(please\s+)?(build|create|make|code|generate|scaffold|develop|design|prototype)\s+(me\s+)?/i, '')
    .replace(/^(a|an|the|my|our)\s+/i, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function projectTitle(prompt: string, fallback: string): string {
  const brief = cleanBrief(prompt)
    .replace(/\s+(website|web site|landing page|web app|site|page)$/i, '')
    .trim();
  if (!brief) return fallback;
  const limited = brief.length > 64 ? `${brief.slice(0, 64).trim()}…` : brief;
  return titleCase(limited);
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
  return slug || 'friday-project';
}

function brandFrom(value: string): string {
  const words = value
    .replace(/[^a-zA-Z0-9 ]/g, ' ')
    .split(/\s+/)
    .filter(Boolean);
  const first =
    words.find((word) => !['a', 'an', 'the', 'my', 'our'].includes(word.toLowerCase())) ??
    words[0];
  if (!first) return 'NOVA';
  return first.length > 14 ? first.slice(0, 14) : first;
}

function applyTemplate(template: string, tokens: Record<string, string>): string {
  return template.replace(/\{\{([A-Z]+)\}\}/g, (match, token: string) => {
    const value = tokens[token];
    return value === undefined ? match : value;
  });
}

export function createLocalDraft(prompt: string): LocalRecipeDraft {
  const kind = detectRecipeKind(prompt);
  const year = String(new Date().getFullYear());

  if (kind === 'flappy') {
    return {
      kind,
      name: 'flappy-neon-drift',
      title: 'Flappy // Neon Drift',
      description:
        'A complete neon arcade flyer with responsive canvas rendering, scoring, persistent best score, particles, sound, and restart flow.',
      files: [{ path: 'index.html', content: flappyTemplate }],
      run: 'Open index.html in a browser, then tap, click, or press Space to fly.',
    };
  }

  if (kind === 'snake') {
    return {
      kind,
      name: 'snake-vector-run',
      title: 'Snake // Vector Run',
      description:
        'A neon grid snake game with keyboard, swipe and pause controls, accelerating difficulty, particles, sound, and a persistent best score.',
      files: [{ path: 'index.html', content: snakeTemplate }],
      run: 'Open index.html in a browser and use the arrow keys or WASD to steer.',
    };
  }

  const title = projectTitle(
    prompt,
    kind === 'portfolio' ? 'Independent Designer' : 'Nova Workspace'
  );
  const brand = brandFrom(title);
  const slug = slugify(brand);
  const mark = brand.slice(0, 2).toUpperCase();
  const description =
    kind === 'portfolio'
      ? 'A complete personal portfolio with selected work, an about section, experience timeline, and a direct contact path. Built to feel considered on every screen.'
      : 'A complete, responsive product website with a clear story, credible proof, a code-forward hero, and a direct path from interest to action.';

  if (kind === 'portfolio') {
    return {
      kind,
      name: `portfolio-${slug}`,
      title: `${title} — Portfolio`,
      description,
      files: [
        {
          path: 'index.html',
          content: applyTemplate(portfolioTemplate, {
            TITLE: escapeHtml(`${title} — Portfolio`),
            BRAND: escapeHtml(title),
            MARK: escapeHtml(mark),
            EYEBROW: escapeHtml('Independent designer · Available for select projects'),
            DESCRIPTION: escapeHtml(description),
            LOCATION: 'Working worldwide',
            SLUG: escapeHtml(slug),
            YEAR: year,
          }),
        },
      ],
      run: 'Open index.html in a browser. Edit the name, work, and contact email in the markup.',
    };
  }

  return {
    kind,
    name: `${slug}-landing`,
    title: `${title}`,
    description,
    files: [
      {
        path: 'index.html',
        content: applyTemplate(landingTemplate, {
          TITLE: escapeHtml(title),
          BRAND: escapeHtml(brand),
          MARK: escapeHtml(mark),
          SLUG: escapeHtml(slug),
          EYEBROW: escapeHtml('Built for teams shipping ambitious software'),
          DESCRIPTION: escapeHtml(description),
          TAGLINE: escapeHtml(`Designed for ${cleanBrief(prompt) || 'your next launch'}`),
          YEAR: year,
        }),
      },
    ],
    run: 'Open index.html in a browser. No build step or dependencies are required.',
  };
}
