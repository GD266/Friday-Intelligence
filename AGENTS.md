# AGENTS.md

FRIDAY Intelligence is a Phase 2 desktop AI assistant foundation: React 18 + Vite 5 + TypeScript, Zustand state persisted to `localStorage`, Tailwind 3, and a Tauri 2 / Rust desktop shell. It now includes a full-screen JARVIS-style core console, native Windows speech with an automatic female English voice profile, push-to-talk dictation, live telemetry, and a confirmed desktop automation layer.

There is still **no AI provider**. Replies come from the deterministic local demo core in `src/lib/friday.ts`; the persona must never claim to be a language model. Provider-backed reasoning, agents, memory, and project workflows remain deferred. The intended provider seam is documented in `docs/ai-engine-integration.md`.

## Commands

- `npm run dev` — Vite dev server at http://localhost:1420. `strictPort` is enabled, so free port 1420 first.
- `npm run build` — `tsc && vite build`. TypeScript is strict with `noUnusedLocals` and `noUnusedParameters`.
- `npm run typecheck` — checks `src` and the Vite/Vitest configs. Use this before builds.
- `npm run lint` — ESLint 9 flat config in `eslint.config.js`; zero warnings are allowed.
- `npm test` — Vitest with jsdom and Testing Library (`src/**/*.test.tsx?`).
- `npm run tauri dev` — starts Vite and launches the Tauri window.
- `npm run tauri build -- --debug --no-bundle` — verifies the desktop build without creating installers.
- `cd src-tauri && cargo check`, `cargo test`, `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` — Rust verification.

## Architecture

- Entry flow: `src/main.tsx` → `src/app/App.tsx` → `src/components/core/CoreStage.tsx`. The conventional sidebar/topbar/activity shell has been removed; navigation happens through overlays and the command deck. UI primitives live in `src/components/ui`; the core console and HUD in `core`; settings and automation panels in their own folders.
- `src/types/index.ts` is the canonical domain model (providers, conversations, agents, tasks, tools, memory, projects, settings, speech, automation). Reuse or extend those types instead of defining duplicate shapes.
- `src/stores/index.ts` owns all Zustand stores (`useUIStore`, `useConversationsStore`, `useProjectsStore`, `useAgentsStore`, `useTasksStore`, `useSystemStore`, `useAssistantStore`). Persisted keys are prefixed `friday_`; a JSON date reviver preserves `Date` fields. The assistant store persists settings and the audit log, but not transient mood/listening/speaking state.
- `useUIStore.overlay` controls the active `settings`, `automation`, or `log` overlay; `isCommandPaletteOpen` and the toast queue live alongside it. `App` owns overlay routing and pauses dictation whenever an overlay opens.
- `useAssistantStore` is the single source of truth for mood, listening/speaking/audio/transcript, persona settings, pending automation, and the action audit log.
- `@/*` maps to `src/*` in Vite, Vitest, and TypeScript. Follow the local file's existing import style.
- Styling uses custom Tailwind tokens (`graphite-*`, `surface-*`, `border-*`, `accent-blue`, `accent-violet`) plus the cyan/violet HUD language. Base component classes live in `src/styles/globals.css`; the orbital core, HUD, dock, overlay, and animation system lives in `src/styles/core.css`, imported after the base stylesheet. The app is dark-only. All new motion must respect `prefers-reduced-motion`.

## Voice and the demo core

- `src/lib/friday.ts` is the deterministic JARVIS persona and intent router. It handles greetings, status reports, capability questions, demo disclosures, and automation commands. Extend its patterns cautiously and keep tests in `src/lib/friday.test.ts` green.
- `src/hooks/useFridayVoice.ts` owns native/browser TTS and dictation, mirroring all observable state into `useAssistantStore`. Push-to-talk is click-or-hold on the mic button; there is no always-on wake word.
- `src/lib/voice.ts` wraps `tauri-plugin-tts`, SAPI dictation commands, and the Web Speech API fallback. `src/lib/voice-profile.ts` ranks installed voices and auto-selects a professional female English voice (en-GB preferred: Sonia, Hazel, Libby). Keep the ranking pure and covered by `voice-profile.test.ts`.
- Default voice settings are pitch `1` and rate `0.94`. The assistant store's v2 migration upgrades only untouched legacy defaults (`0.85` / `0.95`); do not overwrite a deliberately tuned profile.
- TTS lifecycle events are `speech:start`, `speech:finish`, `speech:cancel`, and `speech:error`. Dictation events use `friday://speech` with `kind` and `isFinal`.
- Dictation intentionally follows the installed Windows speech language (`locale: None`); do not hard-code `en-GB` in the native path.

## Automation safety model

- The action catalog is fixed in both `src/lib/automation.ts` and `src-tauri/src/automation.rs`. Every action has an id, category, risk level, description, and optional argument. Additions require changes in both places plus tests.
- `src/lib/automation-runner.ts` routes requests through the confirmation policy: high-risk actions always require approval; medium-risk actions follow `settings.requireConfirmation`; low-risk actions execute directly. Every execution is written to the local audit log.
- High-risk actions include `lock_workstation`, `window_close`, `type_text`, `open_url`, and `empty_recycle_bin`. Never bypass confirmation for these.
- The Rust backend only executes allowlisted ids. Do not add a generic shell/exec command or let model output choose arbitrary programs.
- The Automation console (`src/components/automation/AutomationView.tsx`) opens as an overlay and exposes the full catalog and audit log; `CommandPalette` and conversation intents use the same runner.

## Tauri

- `src-tauri/tauri.conf.json` defines the Vite dev URL, frontend dist, window, and bundle settings.
- `src-tauri/build.rs` runs `tauri_build::build()`; `tauri` is a normal dependency, `tauri-build` is the build dependency.
- `src-tauri/src/main.rs` registers commands from `automation.rs` (`run_automation`), `speech.rs` (`start_dictation`, `stop_dictation`, `cancel_dictation`, speech state), and `telemetry.rs` (`get_system_snapshot`).
- `src-tauri/capabilities/default.json` grants `core:default`, `opener:default`, and `tts:default` to the `main` window. The opener plugin and TTS plugin are registered in `main.rs`.
- Native speech uses `robius-speech` (SAPI), media keys use `enigo`, and telemetry uses `sysinfo`.
- Windows builds require `src-tauri/icons/icon.ico`. Regenerate the icon set with `npx tauri icon public/favicon.svg` if the mark changes.

## Tooling notes

- `src/test/setup.ts` installs an in-memory `localStorage` for tests because Node 26 exposes a disabled global that conflicts with jsdom. Keep the setup file referenced by `vitest.config.ts`.
- `npm audit --omit=dev` is clean. The remaining advisories are dev-only and require breaking major upgrades (Vitest 5 / Vite 8); do not run `npm audit fix --force` during Phase 2.
- `RUST_LOG` can surface extra Tauri diagnostics, but avoid logging dictated text or typed automation arguments.
- Generated paths are ignored: `dist/`, `src-tauri/target/`, `src-tauri/gen/schemas/`, and `*.tsbuildinfo`.
- `create_dirs.js` is a stale one-off referencing a different `FridayAI` path; do not use it.
