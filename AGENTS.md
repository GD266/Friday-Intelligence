# AGENTS.md

FRIDAY Intelligence is a Phase 1 desktop AI workspace foundation: React 18 + Vite 5 + TypeScript, Zustand state persisted to `localStorage`, Tailwind 3, and a Tauri 2 / Rust desktop shell. AI providers, agents, memory, voice, and automation are intentionally not implemented; conversations are local-only.

## Commands

- `npm run dev` — Vite dev server at http://localhost:1420. `strictPort` is enabled, so free port 1420 first.
- `npm run build` — `tsc && vite build`. TypeScript is strict with `noUnusedLocals` and `noUnusedParameters`.
- `npm run typecheck` — checks `src` and the Vite/Vitest configs. Use this before builds.
- `npm run lint` — ESLint 9 flat config in `eslint.config.js`; zero warnings are allowed.
- `npm test` — Vitest with jsdom and Testing Library (`src/**/*.test.tsx?`).
- `npm run tauri dev` — starts Vite and launches the Tauri window.
- `npm run tauri build -- --debug --no-bundle` — verifies the desktop build without creating installers.
- `cd src-tauri && cargo check`, `cargo test`, `cargo fmt --check` — Rust verification.

## Architecture

- Entry flow: `src/main.tsx` → `src/app/App.tsx` → `src/layouts/Layout.tsx`. UI primitives live in `src/components/ui`; layout chrome in `sidebar`, `topbar`, and `activity`; workspace UI in `workspace`.
- `src/types/index.ts` is the canonical domain model (providers, conversations, agents, tasks, tools, memory, projects, settings). Reuse or extend those types instead of defining duplicate shapes.
- `src/stores/index.ts` owns all Zustand stores (`useUIStore`, `useConversationsStore`, `useProjectsStore`, `useAgentsStore`, `useTasksStore`, `useSystemStore`). Persisted keys are prefixed `friday_`; a JSON date reviver preserves `Date` fields.
- `useUIStore.sidebar.activeSection` controls which section `App` renders. Sidebar navigation, the activity panel, new conversations, and the settings shortcut are wired through this store.
- `@/*` maps to `src/*` in Vite, Vitest, and TypeScript. Follow the local file's existing import style.
- Styling uses custom Tailwind tokens (`graphite-*`, `surface-*`, `border-*`, `accent-blue`, `accent-violet`) and component classes in `src/styles/globals.css`. The `accent-blue`/`accent-violet` colors rely on their `DEFAULT` entries in `tailwind.config.js`; keep those when editing the palette. The app is dark-only.

## Tauri

- `src-tauri/tauri.conf.json` defines the Vite dev URL, frontend dist, window, and bundle settings.
- `src-tauri/build.rs` runs `tauri_build::build()`; `tauri` is a normal dependency, `tauri-build` is the build dependency.
- `src-tauri/capabilities/default.json` grants `core:default` and `opener:default` to the `main` window. The opener plugin is registered in `src-tauri/src/main.rs`.
- Windows builds require `src-tauri/icons/icon.ico`. Regenerate the icon set with `npx tauri icon public/favicon.svg` if the mark changes.

## Tooling notes

- `src/test/setup.ts` installs an in-memory `localStorage` for tests because Node 26 exposes a disabled global that conflicts with jsdom. Keep the setup file referenced by `vitest.config.ts`.
- `npm audit --omit=dev` is clean. The remaining advisories are dev-only and require breaking major upgrades (Vitest 5 / Vite 8); do not run `npm audit fix --force` during Phase 1.
- Generated paths are ignored: `dist/`, `src-tauri/target/`, `src-tauri/gen/schemas/`, and `*.tsbuildinfo`.
- `create_dirs.js` is a stale one-off referencing a different `FridayAI` path; do not use it.
